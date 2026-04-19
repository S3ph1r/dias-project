"""
DIAS Serial Orchestrator
Gestisce l'esecuzione sequenziale degli stadi (B -> C -> D) 
per garantire qualità e prevenire collisioni API.
"""

import os
import time
import subprocess
import signal
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional
import json
import re
import datetime # ensure datetime is available for timestamps if needed

from src.common.config import get_config
from src.common.redis_factory import get_redis_client
from src.common.persistence import DiasPersistence
from src.common.logging_setup import get_logger

logger = get_logger("orchestrator")

class SerialOrchestrator:
    def __init__(self, project_id: str):
        # [SANITY CHECK] Force the official sanitized ID as the only truth from the start
        self.project_id = DiasPersistence.normalize_id(project_id)
        
        self.config = get_config()
        self.redis = get_redis_client()
        self.persistence = DiasPersistence(project_id=self.project_id)
        
        # Mapping stadi e script
        self.stages = [
            {"id": "stage_a", "name": "Text Ingester", "script": "src/stages/stage_a_text_ingester.py", "queue": "dias:q:0:upload"},
            {"id": "stage_b", "name": "Semantic Analyzer", "script": "src/stages/stage_b_semantic_analyzer.py", "queue": self.config.queues.ingestion},
            {"id": "stage_c", "name": "Scene Director", "script": "src/stages/stage_c_scene_director.py", "queue": self.config.queues.semantic},
            {"id": "stage_d", "name": "Voice Generator", "script": "src/stages/stage_d_voice_gen.py", "queue": self.config.queues.voice},
            {"id": "stage_b2", "name": "Sound Spotter", "script": "src/stages/stage_b2_spotter.py", "queue": self.config.queues.spotter},
        ]
        
        self.base_dir = Path(__file__).resolve().parent.parent.parent

    def get_total_chunks(self, stage_id: str) -> int:
        """Conta i task totali previsti in base allo stadio."""
        if stage_id == "stage_a":
            # Stage A elabora l'intero libro
            return 1 # Just a flag
        
        source_path = self.persistence.project_root / "stages" / "stage_a" / "output"
        
        # Usiamo glob standard: il project_id e' gia' normalizzato
        files = list(source_path.glob("*-chunk-*.json"))
        # Filter matches for this project and exclude micro
        files = [f for f in files if self.project_id in f.name and "-micro-" not in f.name]
        return len(files)

    def get_completed_chunks(self, stage_id: str) -> int:
        """Conta i chunk/scene completati per uno specifico stadio"""
        target_path = self.persistence.project_root / "stages" / stage_id / "output"
        if not target_path.exists():
            return 0
        
        # Per Stage A contiamo se ci sono chunk prodotti
        if stage_id == "stage_a":
            files = list(target_path.glob("*-chunk-*.json"))
            files = [f for f in files if self.project_id in f.name]
            config_path = self.persistence.project_root / "config.json"
            if config_path.exists():
                with open(config_path) as f:
                    cfg = json.load(f)
                    if cfg.get("status") in ["ingested", "ready_for_semantic"] and len(files) > 0:
                        return 1
            return 1 if len(files) > 0 else 0

        # Per Stage C contiamo i file master
        if stage_id == "stage_c":
            files = list(target_path.glob("*-chunk-*-scenes*.json"))
            files = [f for f in files if self.project_id in f.name]
            return len(files)
        
        # Per Stage D misuriamo in base ai WAV
        if stage_id == "stage_d":
            files = list(target_path.glob("*.wav"))
            valid_files = [f for f in files if f.stat().st_size > 1000 and self.project_id in f.name]
            return len(valid_files)
        
        # Per Stage B2 (Spotter) contiamo i cue-sheet
        if stage_id == "stage_b2":
            files = list(target_path.glob("*-cue-sheet.json"))
            files = [f for f in files if self.project_id in f.name]
            return len(files)
        
        # Per Stage B
        files = list(target_path.glob("*-chunk-*.json"))
        # Filtra via i micro-chunk/scene-semantic e assicura file validi
        valid_files = [f for f in files if f.stat().st_size > 500 and "-micro-" not in f.name and "-scene-" not in f.name and self.project_id in f.name]
        return len(valid_files)

    def is_queue_empty(self, queue_name: str) -> bool:
        """Verifica se la coda Redis è vuota"""
        return self.redis.llen(queue_name) == 0

    def repopulate_queue(self, stage_info: Dict[str, Any]):
        """Trova i file mancanti e li rimette in coda con logica specifica per stadio"""
        stage_id = stage_info["id"]
        queue_name = stage_info["queue"]
        
        # Svuota la coda prima di ripopolarla per evitare duplicati
        self.redis.delete(queue_name)
        
        # --- LOGICA STAGE A (Triggers Ingestion) ---
        if stage_id == "stage_a":
            config_path = self.persistence.project_root / "config.json"
            if not config_path.exists():
                logger.error(f"Config for {self.project_id} not found!")
                return
                
            with open(config_path) as f:
                cfg = json.load(f)
            
            # Leggiamo il puntatore deterministico dal config
            source_file = cfg.get("processed_text")
            
            if not source_file:
                logger.warning(f"⚠️ 'processed_text' non trovato in config per {self.project_id}. Fallback legacy.")
                orig_filename = cfg.get("original_filename")
                if not orig_filename:
                    logger.error("original_filename missing in config")
                    return
                # Caso legacy: assumiamo .txt basato sull'originale
                source_file = f"{orig_filename}.txt"
            
            message = {
                "project_id": self.project_id,
                "book_id": self.project_id,
                "file_path": source_file,
                "title": self.project_id.replace("-", " ").capitalize(),
                "author": "Unknown" # Verra' sovrascritto se presente
            }
            self.redis.push_to_queue(queue_name, message)
            logger.info(f"🚀 Innescato Stage A per {self.project_id}")
            return

        # Identifica sorgente (indirizzo precedente)
        source_map = {"stage_b": "stage_a", "stage_c": "stage_b", "stage_d": "stage_c", "stage_b2": "stage_c"}
        source_stage = source_map.get(stage_id)
        if not source_stage: return
        
        source_path = self.persistence.project_root / "stages" / source_stage / "output"
        target_path = self.persistence.project_root / "stages" / stage_id / "output"
        
        count = 0

        # --- LOGICA STAGE C (Semantic -> Scene Director) ---
        if stage_id == "stage_c":
            # 1. Cerchiamo se ci sono micro-chunk arricchiti dallo Stage B
            micro_files = list(source_path.glob(f"{self.project_id}-chunk-*-micro-*-semantic.json"))
            
            if micro_files:
                logger.info(f"Orchestrator: Trovati {len(micro_files)} micro-chunk semantici per {self.project_id}. Uso granularità micro.")
                for sf in sorted(micro_files):
                    # Estrai il label (es: chunk-000-micro-001)
                    match = re.search(r"(chunk-\d{3}-micro-\d{3})", sf.name)
                    if not match: continue
                    chunk_label = match.group(1)
                    
                    # Verifica se esiste già il Master Scene file per questo micro-chunk
                    masters = list(target_path.glob(f"{self.project_id}-{chunk_label}-scenes-*.json")) + \
                              list(target_path.glob(f"{self.project_id}-{chunk_label}-scenes.json"))
                    if not masters:
                        with open(sf, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                        
                        # Inject label per Stage C
                        data["chunk_label"] = chunk_label
                        self.redis.push_to_queue(queue_name, data)
                        count += 1
            else:
                # 2. Fallback: Logica originale per Macro-Chunk (se non ci sono micro distribuiti)
                logger.info(f"Orchestrator: Nessun micro-chunk trovato. Fallback su Macro-chunk per Stage C.")
                source_files = list(source_path.glob(f"{self.project_id}-chunk-*.json"))
                source_files = [f for f in source_files if "-micro-" not in f.name]
                for sf in sorted(source_files):
                    match = re.search(r"chunk-(\d{3})", sf.name)
                    if not match: continue
                    chunk_id = match.group(1)
                    
                    masters = list(target_path.glob(f"{self.project_id}-chunk-{chunk_id}-scenes-*.json")) + \
                              list(target_path.glob(f"{self.project_id}-chunk-{chunk_id}-scenes.json"))
                    if not masters:
                        with open(sf, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                        
                        data["chunk_label"] = f"chunk-{chunk_id}"
                        self.redis.push_to_queue(queue_name, data)
                        count += 1

        # --- LOGICA STAGE D (Scene Director -> Voice) ---
        elif stage_id == "stage_d":
                # 1. Verifica override da Redis (Dashboard integration)
                voice_override = self.redis.client.hget(f"dias:project:{self.project_id}:config", "voice_id")
                if voice_override:
                    voice_override = voice_override.decode('utf-8') if isinstance(voice_override, bytes) else voice_override
                    logger.info(f"Orchestrator: Applicazione override voce '{voice_override}' per {self.project_id}")

                # 2. Trova le Master Scenes (base per caricare le micro-scene)
                # print(f"DEBUG: Repopulating Stage D. Source: {source_path}")
                master_files = list(source_path.glob(f"*-chunk-*-micro-*-scenes*.json"))
                
                for mf in sorted(master_files):
                    # Verifica che il file appartenga al progetto
                    if self.project_id not in mf.name:
                        continue

                    # Estrai il label completo (es: chunk-000-micro-001)
                    label_match = re.search(r"(chunk-\d{3}-micro-\d{3})", mf.name)
                    if not label_match: continue
                    full_label = label_match.group(1)
                    
                    # 3. Carica solo le scene che appartengono a QUESTO micro-master
                    # Usiamo pattern più flessibile per l'ID
                    micro_scenes = list(source_path.glob(f"*{full_label}-scene-*.json"))
                
                    for ms in sorted(micro_scenes):
                        if self.project_id not in ms.name:
                            continue

                        s_match = re.search(r"scene-(\d{3})", ms.name)
                        if not s_match: continue
                        scene_id = s_match.group(1)
                        
                        # 4. Verifica se l'audio/json esiste già in target
                        search_pattern = f"{self.project_id}-*-{full_label}-scene-{scene_id}*.json"
                        if not list(target_path.glob(search_pattern)):
                            with open(ms, 'r', encoding='utf-8') as f:
                                data = json.load(f)
                            
                            if voice_override:
                                data["voice_id"] = voice_override
                                
                            self.redis.push_to_queue(queue_name, data)
                            count += 1

        # --- LOGICA STAGE B2 (Spotter) ---
        elif stage_id == "stage_b2":
            # B2 opera sui Master JSON dello Stage C
            master_files = list(source_path.glob(f"*-chunk-*-micro-*-scenes*.json"))
            
            for mf in sorted(master_files):
                if self.project_id not in mf.name:
                    continue
                
                label_match = re.search(r"(chunk-\d{3}-micro-\d{3})", mf.name)
                if not label_match: continue
                full_label = label_match.group(1)
                
                # Verifica se esiste già il cue-sheet in target
                cue_sheets = list(target_path.glob(f"{self.project_id}-{full_label}-cue-sheet.json"))
                
                if not cue_sheets:
                    # Carica i dati minimi per il messaggio B2
                    message = {
                        "project_id": self.project_id,
                        "chunk_label": full_label,
                        "job_id": f"b2-job-{self.project_id}-{full_label}",
                        "timestamp": datetime.datetime.now().isoformat()
                    }
                    self.redis.push_to_queue(queue_name, message)
                    count += 1

        # --- LOGICA STANDARD (Stage B o Generica) ---
        else:
            source_files = list(source_path.glob("*-chunk-*.json"))
            # Filtra via i micro-chunk (es: chunk-000-micro-001.json) e file di altri progetti
            source_files = [f for f in source_files if "-micro-" not in f.name and self.project_id in f.name]
            
            for sf in sorted(source_files):
                match = re.search(r"chunk-(\d{3})", sf.name)
                if not match: continue
                chunk_id = match.group(1)
                
                # Check target output
                targets = list(target_path.glob(f"*{self.project_id}*-chunk-{chunk_id}*.json"))
                
                exists = any(t.stat().st_size > 1000 for t in targets)
                
                if not exists:
                    with open(sf, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    
                    # Inject metadata
                    data["chunk_label"] = f"chunk-{chunk_id}"
                    data["block_index"] = int(chunk_id)

                    # Fix per Stage B: mappa block_text -> text
                    if stage_id == "stage_b" and "block_text" in data and "text" not in data:
                        data["text"] = data.pop("block_text")
                        
                    self.redis.push_to_queue(queue_name, data)
                    count += 1
        
        if count > 0:
            logger.info(f"🔄 Ripopolata coda {queue_name} con {count} messaggi mancanti.")

    def run_stage(self, stage_info: Dict[str, Any]):
        """Avvia un worker e aspetta che finisca i chunk"""
        stage_id = stage_info["id"]
        total = self.get_total_chunks(stage_id)
        
        logger.info(f"--- 🚀 AVVIO {stage_info['name']} ({stage_id}) ---")
        
        # Report status to Redis for Dashboard
        self.redis.set(f"dias:project:{self.project_id}:active_stage", stage_id)
        
        # Primo popolamento (Resume)
        self.repopulate_queue(stage_info)
        
        # Loop di monitoraggio
        while True:
            completed = self.get_completed_chunks(stage_id)
            queue_len = self.redis.llen(stage_info["queue"])
            
            logger.info(f"[{stage_id}] Progress: {completed}/{total} | Queue: {queue_len}")
            
            if completed >= total and queue_len == 0:
                logger.info(f"✅ {stage_info['name']} COMPLETATO con successo.")
                # Aggiornamento automatico dello stato del progetto nel config.json
                self.persistence.update_project_config({"last_stage": stage_id, "status": "processing"})
                break
                
            # Verifica se la pipeline è in PAUSA GLOBALE
            paused_reason = self.redis.get("dias:status:paused")
            if paused_reason:
                logger.warning(f"⚠️ PIPELINE PAUSATA: {paused_reason}")
                logger.warning("L'orchestratore rimarrà in attesa. Rimuovi 'dias:status:paused' in Redis per riprendere.")
            else:
                # Verifica se il processo è attivo, altrimenti avvialo (solo se NON in pausa)
                if not self._is_worker_running(stage_info):
                    logger.info(f"Worker {stage_id} non attivo. Lo avvio...")
                    self._start_worker(stage_info["script"])
            
            # Special Stage A Wait: if Stage A just started, wait a bit for total to become > 1 for next stages
            if stage_id == "stage_a" and completed == 0:
                time.sleep(10)
            
            time.sleep(30) # Monitoraggio ogni 30s

    def _is_worker_running(self, stage_info: Dict[str, Any]) -> bool:
        """Controlla se esiste un processo del worker specifico basandosi sul percorso dello script"""
        script_path = stage_info["script"]
        try:
            # Match specifically the script name to avoid false positives with other grep
            # including the orchestrator's own command line
            cmd = f"ps aux | grep '{script_path}' | grep -v grep"
            output = subprocess.check_output(cmd, shell=True).decode()
            return len(output.strip()) > 0
        except subprocess.CalledProcessError:
            return False

    def _start_worker(self, script_path: str):
        """Avvia lo script dello stadio in background"""
        python_bin = self.base_dir / ".venv" / "bin" / "python3"
        log_name = Path(script_path).stem + ".log"
        # Usiamo percorsi assoluti per evitare ogni ambiguità
        abs_script_path = (self.base_dir / script_path).resolve()
        log_path = (self.base_dir / "logs" / log_name).resolve()
        
        logger.info(f"Avvio worker: {abs_script_path} (log: {log_path})")
        
        cmd = f"nohup {python_bin} {abs_script_path} >> {log_path} 2>&1 &"
        subprocess.Popen(cmd, shell=True, cwd=self.base_dir)

    def stop_all_workers(self):
        """Ferma tutti i worker per iniziare puliti"""
        logger.info("Fermo tutti i worker esistenti...")
        # Usiamo un pattern specifico per colpire solo i worker e non l'orchestratore stesso
        subprocess.run("pkill -9 -f 'src/stages/stage_'", shell=True)

    def run(self, limit_stage: Optional[str] = None):
        """Esegue la pipeline in modo sequenziale, opzionalmente fermandosi a uno stadio."""
        logger.info(f"=== 🎭 DIAS SERIAL ORCHESTRATOR: {self.project_id} ===")
        
        # Pulizia iniziale
        self.stop_all_workers()
        
        for stage in self.stages:
            # SKIP Stage A if outputs exist (Ingestion already completed)
            if stage["id"] == "stage_a":
                stage_a_output = self.persistence.project_root / "stages" / "stage_a" / "output"
                if list(stage_a_output.glob("*.json")):
                    logger.info("⏭️ Ingestion Stage A già presente. Salto lo stadio.")
                    continue
                    
            self.run_stage(stage)
            # Ferma il worker prima di passare al prossimo per evitare collisioni API
            self.stop_all_workers()
            time.sleep(5)
            
            if limit_stage and stage["id"] == limit_stage:
                logger.info(f"🛑 Raggiunto stadio limite richiesto: {limit_stage}. Mi fermo.")
                break
        
        # === CERIMONIA DI CHIUSURA (FINISH) ===
        if not limit_stage or limit_stage == self.stages[-1]["id"]:
            logger.info(f"✨ Progetto {self.project_id} completato con successo!")
            self.redis.delete(f"dias:project:{self.project_id}:active_stage")
            
            # Aggiorna lo stato nel config del progetto
            config_path = self.persistence.project_root / "config.json"
            if config_path.exists():
                with open(config_path) as f:
                    cfg = json.load(f)
                cfg["status"] = "completed"
                cfg["last_stage"] = self.stages[-1]["id"]
                with open(config_path, "w") as f:
                    json.dump(cfg, f, indent=4)
                    
            self.stop_all_workers()
            logger.info("👋 Orchestratore terminato. Dashboard pulita.")

if __name__ == "__main__":
    import sys
    import argparse
    
    parser = argparse.ArgumentParser(description="DIAS Serial Orchestrator")
    parser.add_argument("project_id", help="ID del progetto (es: Cronache-del-Silicio)")
    parser.add_argument("--limit-stage", help="Fermati dopo questo stadio (es: stage_c)")
    
    args = parser.parse_args()
        
    orch = SerialOrchestrator(args.project_id)
    orch.run(limit_stage=args.limit_stage)
