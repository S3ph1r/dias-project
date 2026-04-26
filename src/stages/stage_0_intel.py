#!/usr/bin/env python3
"""
DIAS Stage 0 - Book Intelligence
Analyzes the full text of a book to extract metadata, characters, and sound design suggestions.
Uses Gemini 1.5 Flash via ARIA Gateway.
"""

import sys
import os
import json
import logging
import yaml
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional

# Add root to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.common.base_stage import BaseStage
from src.common.config import get_config
from src.common.gateway_client import GatewayClient
from src.common.persistence import DiasPersistence

class Stage0Intelligence(BaseStage):
    """
    Stage 0: Book Intelligence
    Performs one-time analysis of the entire book source.
    """
    
    def __init__(self, redis_client=None, config=None):
        cfg = config or get_config()
        super().__init__(
            stage_name="stage_0_intel",
            stage_number=0,
            input_queue="dias:q:0:intel",
            output_queue=None, 
            config=cfg,
            redis_client=redis_client
        )
        self.gateway = GatewayClient(redis_client=self.redis, client_id="dias")
        self.model_name = self.config.google.model_flash_lite
        self.logger.info(f"Stage 0 Intelligence initialized with model {self.model_name}")

    def _load_prompt(self, prompt_path_rel: str) -> Dict[str, Any]:
        """Loads a YAML prompt from a relative path."""
        prompt_full_path = Path(__file__).parent.parent.parent / prompt_path_rel
        with open(prompt_full_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)

    def _run_discovery(self, project_id: str, text_content: str) -> Optional[Dict[str, Any]]:
        """Step 0.1: Discover book structure and structural punctuation mechanics."""
        self.logger.info(f"Step 0.1: Starting Structural Discovery for {project_id}...")
        discovery_prompt_path = "config/prompts/stage_0/0.1_discovery_v1.3.yaml"
        discovery_prompt_data = self._load_prompt(discovery_prompt_path)
        template = discovery_prompt_data.get('prompt_template', '')
        
        # [RESTORE] Invio libro completo come richiesto dall'utente.
        # [FIX] Usiamo .replace() invece di .format() per evitare KeyError se il libro contiene graffe.
        prompt = template.replace("{text_content}", text_content)
        contents = [{"role": "user", "parts": [{"text": prompt}]}]
        
        # [DETERNIMISTIC ID - Stage B Style]
        job_id_meta = {"project_id": project_id, "step": "0.1_discovery"}
        
        result = self.gateway.generate_content(
            contents=contents,
            model_id=self.model_name,
            job_id_meta=job_id_meta,
            timeout=1200
        )
        
        if result.get("status") != "success":
            self.logger.error(f"Structural Discovery Gateway error: {result.get('error')}")
            return None
            
        raw_text = result.get("output", {}).get("text", "")
        # Clean response
        if "```json" in raw_text:
            raw_text = raw_text.split("```json")[1].split("```")[0].strip()
        elif "```" in raw_text:
            raw_text = raw_text.split("```")[1].split("```")[0].strip()
            
        try:
            discovery_data = json.loads(raw_text)
            self.logger.info(f"✅ Structural Discovery completed for {project_id}")
            return discovery_data
        except Exception as e:
            self.logger.error(f"Failed to parse discovery JSON: {e}")
            return None

    def process(self, message: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Process a Stage 0 task: 0.1 Discovery -> 0.2 Intelligence.
        Compatible with Dashboard (project_id) and Manual triggers.
        """
        self.logger.info(f"DEBUG RAW MSG: {json.dumps(message)}")
        
        # [SANITY CHECK] Normalize project_id IMMEDIATELY.
        # This is the single source of truth for the rest of the pipeline.
        raw_project_id = message.get("project_id") or "unknown"
        project_id = DiasPersistence.normalize_id(raw_project_id)
        
        persistence = DiasPersistence(project_id=project_id)
        
        # 2. Deterministic Source File Detection
        config_path = persistence.project_root / "config.json"
        source_path = None
        
        if config_path.exists():
            with open(config_path, 'r', encoding='utf-8') as f:
                cfg = json.load(f)
            processed_rel_path = cfg.get("processed_text")
            if processed_rel_path:
                source_path = persistence.project_root / processed_rel_path
        
        # Fallback legacy (solo se non c'è processed_text)
        if not source_path or not source_path.exists():
            source_file = message.get("source_file")
            if source_file:
                source_path = Path(persistence.project_root) / "source" / source_file
            
            if not source_path or not source_path.exists():
                source_path = persistence.get_source_text_path()
            
        if not source_path or not source_path.exists():
            self.logger.error(f"❌ Source text file not found for project {project_id}")
            return None

        self.logger.info(f"🚀 Starting Automated Stage 0 for project: {project_id}")
        self.logger.info(f"📍 Final Source Path: {source_path.absolute()}")
        
        try:
            # --- STEP 0.1: DISCOVERY (Full Scan v1.2) ---
            with open(source_path, 'r', encoding='utf-8') as f:
                source_text = f.read()
            
            discovery_data = self._run_discovery(project_id, source_text)
            if not discovery_data:
                self.logger.error("❌ Step 0.1 (Discovery) failed. Stopping.")
                return None
            
            # Save fingerprint
            fingerprint_path = persistence.get_fingerprint_path()
            with open(fingerprint_path, 'w', encoding='utf-8') as f:
                json.dump(discovery_data, f, indent=4, ensure_ascii=False)
            
            # --- STEP 0.1.5: NORMALIZATION (Discovery-Driven) ---
            self.logger.info(f"🔄 Starting Source Normalization for {project_id}...")
            from src.tools.normalize_source import SourceNormalizer
            normalizer = SourceNormalizer(project_id)
            if not normalizer.normalize():
                self.logger.warning("⚠️ Normalization was inconclusive, proceeding with original.")
            
            # --- PACING: Waiting 60s to avoid 429 quota exhaustion ---
            self.logger.info("⏳ [PACING] Waiting 60 seconds before Step 0.2 (Google Quota Protection)...")
            time.sleep(60)

            # --- STEP 0.2: INTELLIGENCE & CASTING ---
            # Load normalized text if available
            normalized_path = persistence.get_normalized_text_path()
            if normalized_path and normalized_path.exists():
                self.logger.info(f"📖 Loading Normalized Text: {normalized_path.name}")
                with open(normalized_path, 'r', encoding='utf-8') as f:
                    text_content = f.read()
            else:
                self.logger.warning("⚠️ Normalized text not found, falling back to source.")
                text_content = source_text

            self.logger.info(f"🧠 Step 0.2: Starting Intelligence Analysis (Casting) for {project_id}...")
            intel_prompt_data = self._load_prompt("config/prompts/stage_0/0.2_intelligence_v1.0.yaml")
            template = intel_prompt_data.get('prompt_template', '')
            
            # Extract chapters from Step 1 for the prompt context
            chapters_data = discovery_data.get("chapters_list", [])
            chapters_summary = "\n".join([f"- {c.get('name', c.get('id', 'Unknown'))}" for c in chapters_data])

            prompt = template.format(
                text_content=text_content,
                expected_chapters_list=chapters_summary
            )
            contents = [{"role": "user", "parts": [{"text": prompt}]}]
            
            result = self.gateway.generate_content(
                contents=contents,
                model_id=self.model_name,
                job_id_meta={"project_id": project_id, "stage": "0", "task": "intelligence_analysis"},
                timeout=600 
            )
            
            if result.get("status") != "success":
                self.logger.error(f"Intelligence Gateway error: {result.get('error')}")
                return None
                
            raw_text = result.get("output", {}).get("text", "")
            if "```json" in raw_text:
                raw_text = raw_text.split("```json")[1].split("```")[0].strip()
            elif "```" in raw_text:
                raw_text = raw_text.split("```")[1].split("```")[0].strip()
            
            intel_data = json.loads(raw_text)
            self.logger.info(f"✅ Intelligence Analysis completed for {project_id}")

            # [FIX] AGGIORNAMENTO FINGERPRINT CON INTELLIGENCE (DOSSIER)
            # Uniamo i dati strutturali (Step 1) con quelli creativi (Step 2)
            fingerprint_path = persistence.get_fingerprint_path()
            with open(fingerprint_path, 'r', encoding='utf-8') as f:
                fp_data = json.load(f)
            
            # Merge metadati estesi
            if "metadata" in intel_data:
                fp_data["metadata"].update(intel_data["metadata"])

            # Merge chapters from Stage 0.2 (has 'title' + 'summary', preferred by pipeline)
            # Stage 0.1 produces 'chapters_list' with 'name'; Stage 0.2 produces 'chapters'
            # with 'title'. Keep both keys for backward compat; pipeline prefers 'chapters'.
            if "chapters" in intel_data and intel_data["chapters"]:
                fp_data["chapters"] = intel_data["chapters"]

            # Merge casting dossier (quello che la Dashboard aspetta)
            fp_data["casting"] = intel_data.get("casting", {})
            fp_data["sound_design"] = intel_data.get("sound_design", {})
            
            # Salvataggio Fingerprint COMPLETO
            with open(fingerprint_path, 'w', encoding='utf-8') as f:
                json.dump(fp_data, f, indent=4)
            self.logger.info(f"📁 Fingerprint aggiornato con Dossier Artistico per {project_id}")

            # Creazione/Aggiornamento dossier preproduction.json (solo assegnazioni)
            self._ensure_preproduction_dossier(project_id, persistence, intel_data)
            
            # 4. Final Status Summary
            self.logger.info(f"=== REPILOGO FINALE ANALISI PER {project_id} ===")
            self.logger.info(f"Step 0.1 (Discovery): SUCCESS")
            self.logger.info(f"Step 0.2 (Intelligence): SUCCESS")
            self.logger.info(f"Dossier Artistico: {persistence.get_preproduction_path()}")
            self.logger.info(f"Status in config.json: analisi_completed")
            self.logger.info(f"================================================")
            
            # [FIX] Aggiorna status e processed_text del progetto in config.json
            config_path = persistence.project_root / "config.json"
            if config_path.exists():
                try:
                    with open(config_path, 'r', encoding='utf-8') as f:
                        cfg = json.load(f)
                    
                    cfg["status"] = "analisi_completed"
                    cfg["last_analysis"] = datetime.now().isoformat()
                    
                    # AGGIORNAMENTO PUNTATORE TESTO: Ora punta al file normalizzato
                    normalized_path = persistence.get_normalized_text_path()
                    if normalized_path:
                        # Salviamo il path relativo alla root del progetto
                        rel_p = os.path.relpath(normalized_path, persistence.project_root)
                        cfg["processed_text"] = rel_p
                        self.logger.info(f"📍 Puntatore 'processed_text' aggiornato a: {rel_p}")
                    
                    with open(config_path, 'w', encoding='utf-8') as f:
                        json.dump(cfg, f, indent=4)
                    self.logger.info(f"✅ Status aggiornato a 'analisi_completed' per {project_id}")
                except Exception as e:
                    self.logger.error(f"⚠️ Errore aggiornamento config.json: {e}")
            
            self.logger.info(f"✨ Stage 0 COMPLETED for {project_id}.")
            return {
                "project_id": project_id,
                "status": "stage_0_complete",
                "preproduction": str(persistence.get_preproduction_path()),
                "fingerprint": str(fingerprint_path)
            }

        except Exception as e:
            self.logger.error(f"Error during Stage 0 Intelligence: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            return None

    def _ensure_preproduction_dossier(self, project_id: str, persistence: DiasPersistence, intel_data: Dict[str, Any] = None):
        """
        Garantisce la creazione del preproduction dossier basato sui risultati dell'intelligence.
        Logica Smart Merge: Aggiorna i dati IA (dossier) ma preserva le scelte utente (casting).
        """
        preprod_path = persistence.get_preproduction_path()
        
        # Carica esistente o crea nuovo
        preprod_data = {}
        if preprod_path.exists():
            try:
                with open(preprod_path, 'r', encoding='utf-8') as f:
                    preprod_data = json.load(f)
            except Exception as e:
                self.logger.error(f"Errore lettura preproduction.json esistente: {e}")
        
        # 1. Impostazioni Voice Standard (se mancano)
        if "theatrical_standard" not in preprod_data:
            preprod_data["theatrical_standard"] = {
                "subtalker_temperature": 0.75,
                "temperature": 0.7,
                "instruct": "Natural Narrative",
                "voice_ref_text_active": True
            }
            self.logger.info(f"Iniettato 'Theatrical Standard' nel dossier di {project_id}")

        # 2. Popolamento DOSSIER (Sempre aggiornato dall'IA)
        casting_root = intel_data.get("casting", {}) if intel_data else {}
        chars = casting_root.get("characters", [])
        
        if chars:
            # Aggiorniamo sempre il dossier artistico con i nuovi dati Gemini
            preprod_data["characters_dossier"] = chars
            self.logger.info(f"💾 Dossier artistico aggiornato con {len(chars)} profili personaggi.")
        
        # 3. SMART MERGE CASTING (Preserva scelte utente)
        if "casting" not in preprod_data:
            preprod_data["casting"] = {}
            
        if chars:
            added_count = 0
            for char_obj in chars:
                char_name = char_obj.get("name")
                # Aggiungiamo solo se il personaggio è nuovo
                if char_name and char_name not in preprod_data["casting"]:
                    preprod_data["casting"][char_name] = ""
                    added_count += 1
            if added_count > 0:
                self.logger.info(f"Aggiunti {added_count} nuovi personaggi al casting di {project_id}.")

        # 4. Temi Musicali / Palette (Default se manca)
        if "palette_choice" not in preprod_data:
            palette_list = intel_data.get("sound_design", {}).get("palette_proposals", []) if intel_data else []
            if palette_list:
                preprod_data["palette_choice"] = palette_list[0].get("name", "Standard")
                self.logger.info(f"Impostata palette default: {preprod_data['palette_choice']}")
            else:
                preprod_data["palette_choice"] = "Standard Narrative"

        # 5. Global Voice (Narratore default se manca)
        if "global_voice" not in preprod_data:
            backend_cfg = self.config.models.qwen3_tts
            preprod_data["global_voice"] = getattr(backend_cfg, "default_voice", "luca")
            self.logger.info(f"Impostata global_voice default: {preprod_data['global_voice']}")

        # Salva il dossier aggiornato
        try:
            with open(preprod_path, 'w', encoding='utf-8') as f:
                json.dump(preprod_data, f, indent=4, ensure_ascii=False)
            self.logger.info(f"Dossier preproduction.json aggiornato e popolato per {project_id}")
        except Exception as e:
            self.logger.error(f"Errore salvataggio preproduction.json: {e}")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="DIAS Stage 0 - Book Intelligence")
    parser.add_argument("--once", action="store_true", help="Process one task from queue and exit")
    parser.add_argument("--project-id", type=str, help="Process a specific project immediately and exit")
    parser.add_argument("--source-file", type=str, help="Specific source file name (optional)")
    args = parser.parse_args()
    
    stage = Stage0Intelligence()
    
    if args.project_id:
        # Normalizziamo l'ID per sicurezza prima di passarlo al processore
        norm_id = args.project_id.strip("/")
        if "/" in norm_id: norm_id = norm_id.split("/")[-1]
        
        print(f"🚀 [ON-DEMAND] Avvio analisi specifica per: {norm_id}")
        mock_msg = {
            "project_id": norm_id,
            "source_file": args.source_file # Passiamo esplicitamente se arriva da CLI
        }
        result = stage.process(mock_msg)
        
        if result:
            print(f"✨ Analisi completata per {args.project_id}")
            sys.exit(0)
        else:
            print(f"❌ Errore durante l'analisi di {args.project_id}")
            sys.exit(1)
    else:
        # Modalità classica (ascolto coda o single run se --once)
        stage.run(once=args.once)
