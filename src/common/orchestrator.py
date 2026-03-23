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

from src.common.config import get_config
from src.common.redis_factory import get_redis_client
from src.common.persistence import DiasPersistence
from src.common.logging_setup import get_logger

logger = get_logger("orchestrator")

class SerialOrchestrator:
    def __init__(self, project_id: str):
        self.project_id = project_id
        self.config = get_config()
        self.redis = get_redis_client()
        self.persistence = DiasPersistence()
        
        # Mapping stadi e script
        self.stages = [
            {"id": "stage_b", "name": "Semantic Analyzer", "script": "src/stages/stage_b_semantic_analyzer.py", "queue": self.config.queues.ingestion},
            {"id": "stage_c", "name": "Scene Director", "script": "src/stages/stage_c_scene_director.py", "queue": self.config.queues.semantic},
            {"id": "stage_d", "name": "Voice Generator", "script": "src/stages/stage_d_voice_gen.py", "queue": self.config.queues.voice},
        ]
        
        self.base_dir = Path(__file__).resolve().parent.parent.parent

    def get_total_chunks(self, stage_id: str = "stage_a") -> int:
        """Conta i task totali previsti in base allo stadio."""
        if stage_id == "stage_d":
            # Il totale degli item per lo Stage D corrisponde ai micro-json prodotti dallo Stage C
            path = self.base_dir / "data" / "stage_c" / "output"
            files = list(path.glob(f"{self.project_id}-chunk-*-scene-*.json"))
            return len(files)
        else:
            # Per B e C, il totale corrisponde ai chunk madre dello Stage A
            path = self.base_dir / "data" / "stage_a" / "output"
            files = list(path.glob(f"{self.project_id}-chunk-*.json"))
            return len(files)

    def get_completed_chunks(self, stage_id: str) -> int:
        """Conta i chunk/scene completati per uno specifico stadio"""
        path = self.base_dir / "data" / stage_id / "output"
        if not path.exists():
            return 0
            
        # Per Stage C contiamo i file master
        if stage_id == "stage_c":
            files = list(path.glob(f"{self.project_id}-chunk-*-scenes-*.json"))
            return len(files)
        
        # Per Stage D misuriamo in base ai WAV, garantendo che ci sia l'audio!
        if stage_id == "stage_d":
            files = list(path.rglob("*.wav"))
            valid_files = [f for f in files if f.stat().st_size > 1000]
            return len(valid_files)
        
        # Per Stage B
        files = list(path.glob(f"{self.project_id}-chunk-*.json"))
        valid_files = [f for f in files if f.stat().st_size > 1000]
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
        
        # Identifica sorgente (indirizzo precedente)
        source_map = {"stage_b": "stage_a", "stage_c": "stage_b", "stage_d": "stage_c"}
        source_stage = source_map.get(stage_id)
        if not source_stage: return
        
        source_path = self.base_dir / "data" / source_stage / "output"
        target_path = self.base_dir / "data" / stage_id / "output"
        
        count = 0
        import re
        import json

        # --- LOGICA STAGE C (Semantic -> Scene Director) ---
        if stage_id == "stage_c":
            source_files = list(source_path.glob(f"{self.project_id}-chunk-*.json"))
            for sf in sorted(source_files):
                match = re.search(r"chunk-(\d{3})", sf.name)
                if not match: continue
                chunk_id = match.group(1)
                
            # Valida esistenza tramite MASTER SCENE file
                masters = list(target_path.glob(f"{self.project_id}-chunk-{chunk_id}-scenes-*.json"))
                exists = any(m.stat().st_size > 1000 for m in masters)
                
                logger.debug(f"[repopulate_queue STAGE_C] Chunk {chunk_id}: masters={len(masters)}, exists={exists}")

                if not exists:
                    with open(sf, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    
                    # Inject metadata for Stage C
                    data["chunk_label"] = f"chunk-{chunk_id}"
                    data["block_index"] = int(chunk_id)
                    
                    self.redis.push_to_queue(queue_name, data)
                    count += 1

        # --- LOGICA STAGE D (Scene Director -> Voice) ---
        elif stage_id == "stage_d":
            # 1. Trova le Master Scenes (base per caricare le micro-scene)
            master_files = list(source_path.glob(f"{self.project_id}-chunk-*-scenes-*.json"))
            
            for mf in sorted(master_files):
                match = re.search(r"chunk-(\d{3})", mf.name)
                if not match: continue
                chunk_id = match.group(1)
                
                # 2. Carica tutte le micro-scene per questo chunk
                micro_scenes = list(source_path.glob(f"{self.project_id}-chunk-{chunk_id}-scene-*.json"))
                
                for ms in sorted(micro_scenes):
                    s_match = re.search(r"scene-(\d{3})", ms.name)
                    if not s_match: continue
                    scene_id = s_match.group(1)
                    
                    # 3. Verifica se l'audio/json esiste già in target
                    targets = list(target_path.glob(f"{self.project_id}-chunk-{chunk_id}-scene-{scene_id}*.json"))
                    exists = any(t.stat().st_size > 1000 for t in targets)
                    
                    if not exists:
                        with open(ms, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                        self.redis.push_to_queue(queue_name, data)
                        count += 1

        # --- LOGICA STANDARD (Stage B o Generica) ---
        else:
            source_files = list(source_path.glob(f"{self.project_id}-chunk-*.json"))
            for sf in sorted(source_files):
                match = re.search(r"chunk-(\d{3})", sf.name)
                if not match: continue
                chunk_id = match.group(1)
                
                targets = list(target_path.glob(f"{self.project_id}-chunk-{chunk_id}*.json"))
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
        
        # Primo popolamento (Resume)
        self.repopulate_queue(stage_info)
        
        # Loop di monitoraggio
        while True:
            completed = self.get_completed_chunks(stage_id)
            queue_len = self.redis.llen(stage_info["queue"])
            
            logger.info(f"[{stage_id}] Progress: {completed}/{total} | Queue: {queue_len}")
            
            if completed >= total and queue_len == 0:
                logger.info(f"✅ {stage_info['name']} COMPLETATO con successo.")
                break
                
            # Verifica se la pipeline è in PAUSA GLOBALE
            paused_reason = self.redis.get("dias:status:paused")
            if paused_reason:
                logger.warning(f"⚠️ PIPELINE PAUSATA: {paused_reason}")
                logger.warning("L'orchestratore rimarrà in attesa. Rimuovi 'dias:status:paused' in Redis per riprendere.")
            else:
                # Verifica se il processo è attivo, altrimenti avvialo (solo se NON in pausa)
                if not self._is_worker_running(stage_id):
                    logger.info(f"Worker {stage_id} non attivo. Lo avvio...")
                    self._start_worker(stage_info["script"])
            
            time.sleep(30) # Monitoraggio ogni 30s

    def _is_worker_running(self, stage_id: str) -> bool:
        """Controlla se esiste un processo del worker specifico"""
        try:
            cmd = f"ps aux | grep {stage_id} | grep -v grep"
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
        subprocess.run("pkill -9 -f stage_", shell=True)

    def run(self):
        """Esegue l'intera pipeline in modo sequenziale"""
        logger.info(f"=== 🎭 DIAS SERIAL ORCHESTRATOR: {self.project_id} ===")
        total = self.get_total_chunks()
        if total == 0:
            logger.error("Nessun chunk trovato in Stage A. Esco.")
            return

        logger.info(f"Project: {self.project_id} | Total Chunks: {total}")
        
        # Pulizia iniziale
        self.stop_all_workers()
        
        for stage in self.stages:
            self.run_stage(stage)
            # Ferma il worker prima di passare al prossimo per evitare collisioni API
            self.stop_all_workers()
            time.sleep(5)

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python3 src/common/orchestrator.py <project_id>")
        sys.exit(1)
        
    orch = SerialOrchestrator(sys.argv[1])
    orch.run()
