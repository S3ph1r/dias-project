#!/usr/bin/env python3
"""
Stage B2 (Macro) - The Macro-Spotter
Analizza i Macro-chunk di uno script per selezionare il Pad Musicale (PAD).
Se i suoni mancano nel catalogo ARIA, genera una shopping_list_macro.
"""

import os
import json
import logging
import sys
import yaml
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime

# Aggiungi il path root al Python path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.common.config import get_config
from src.common.redis_factory import get_redis_client
from src.common.persistence import DiasPersistence
from src.common.gateway_client import GatewayClient
from src.common.logging_setup import get_logger
from src.common.models import MacroCue, ShoppingItem

class StageB2Macro:
    def __init__(self, project_id: str):
        self.project_id = DiasPersistence.normalize_id(project_id)
        self.config = get_config()
        self.redis = get_redis_client()
        self.persistence = DiasPersistence(project_id=self.project_id)
        self.logger = get_logger("b2_macro")
        self.gemini_client = GatewayClient(redis_client=self.redis, client_id="dias")
        self.model_name = self.config.google.model_flash_lite
        
        # Setup Traceability Logger
        self.trace_log_path = self.persistence.project_root / "stages" / "stage_b2" / "output" / "b2_traceability.log"
        self.trace_log_path.parent.mkdir(parents=True, exist_ok=True)

    def _log_trace(self, message: str):
        """Scrive un log temporizzato nel file di tracciabilità del progetto."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(self.trace_log_path, "a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] [MACRO] {message}\n")

    def _load_preproduction_dossier(self) -> Dict[str, Any]:
        """Carica il dossier di preproduzione (palette choice) dello Stage 0."""
        path = self.persistence.get_preproduction_path()
        if not path.exists():
            return {}
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def _load_palette_proposals(self) -> List[Dict]:
        """Carica le proposte della palette (fingerprint) dello Stage 0."""
        path = self.persistence.get_fingerprint_path()
        if not path.exists():
            return []
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return data.get("sound_design", {}).get("palette_proposals", [])

    def _fetch_aria_registry_mus(self) -> Dict[str, Any]:
        """Recupera gli asset musicali (pads) dal registro ARIA."""
        try:
            raw_data = self.redis.get("aria:registry:master")
            if not raw_data:
                return {}
            data = json.loads(raw_data)
            return data.get("assets", {}).get("pad", {})
        except Exception as e:
            self.logger.error(f"❌ Errore nel recupero del registro ARIA: {e}")
            return {}

    def _prepare_prompt(self, chunk_data: Dict, registry_mus: Dict, dossier: Dict, proposals: List[Dict]) -> str:
        # V3 prompt
        prompt_path = Path(__file__).parent.parent.parent / "config/prompts/stage_b2/b2_macro_v3.0.yaml"

        with open(prompt_path, 'r', encoding='utf-8') as f:
            template = yaml.safe_load(f).get("prompt_template", "")

        available_mus = "\n".join([f"- {pid}: {p.get('tags', [])} - {p.get('description', '')}" for pid, p in registry_mus.items()])
        if not available_mus: available_mus = "(Nessun Tema Musicale disponibile)"

        return template.format(
            project_id=self.project_id,
            chunk_label=chunk_data.get("chunk_label", "unknown"),
            chosen_palette=dossier.get("chosen_palette", dossier.get("palette_choice", "Generica")),
            palette_proposals=json.dumps(proposals, indent=2, ensure_ascii=False),
            fingerprint_values=json.dumps(dossier.get("fingerprint_values", []), ensure_ascii=False),
            primary_emotion=chunk_data.get("block_analysis", {}).get("primary_emotion", "neutral"),
            setting=chunk_data.get("block_analysis", {}).get("setting", "unknown"),
            summary=chunk_data.get("block_analysis", {}).get("summary", ""),
            available_mus=available_mus
        )

    def process_chunk(self, chunk_id: str) -> bool:
        """
        Elabora un singolo macro-chunk.
        """
        chunk_label = f"chunk-{chunk_id}"
        self.logger.info(f"🎬 B2 Macro-Spotter (PAD): Processing {chunk_label}...")
        self._log_trace(f"Inizio elaborazione {chunk_label}")

        # 1. Idempotency Check (Disk)
        output_label = f"{chunk_label}-macro-cue"
        existing = self.persistence.load_stage_output("b2", self.project_id, output_label)
        if existing:
            self.logger.info(f"⏭️ Skipping B2 Macro: Analisi già presente su disco per {self.project_id}-{output_label}")
            return True

        # 2. Get Chunk Data (Analysis from Stage B)
        analysis_file = self.persistence.project_root / "stages" / "stage_b" / "output" / f"{self.project_id}-{chunk_label}.json"
        if not analysis_file.exists():
            self.logger.error(f"❌ Analisi Stage B mancante per {chunk_label}.")
            return False
            
        with open(analysis_file, 'r', encoding='utf-8') as f:
            chunk_data = json.load(f)

        # 3. Load Dossier & Fingerprint (Stage 0)
        dossier = self._load_preproduction_dossier()
        proposals = self._load_palette_proposals()
        
        self._log_trace(f"Palette Scelta: {dossier.get('chosen_palette', dossier.get('palette_choice'))}")

        # 4. Fetch Registry & Call Gemini
        registry_mus = self._fetch_aria_registry_mus()
        prompt = self._prepare_prompt(chunk_data, registry_mus, dossier, proposals)
        
        job_id = f"b2-macro-{self.project_id}-{chunk_label}"
        
        max_retries = 3
        response = None
        for attempt in range(max_retries):
            self._log_trace(f"Tentativo {attempt+1}/{max_retries} per Gemini ({self.model_name})...")
            response = self.gemini_client.generate_content(
                contents=[{"role": "user", "parts": [{"text": prompt}]}],
                model_id=self.model_name,
                job_id=job_id
            )
            if response["status"] != "error":
                break
                
            error_msg = response.get("error", "Unknown error")
            if "503" in str(error_msg) or "429" in str(error_msg):
                wait_time = 70
                self.logger.warning(f"⚠️ Gemini temporaneamente non disponibile (503/429). Attesa di {wait_time}s... (Tentativo {attempt+1})")
                import time
                time.sleep(wait_time)
                # IMPORTANTE: cancelliamo la callback key per permettere un nuovo invio pulito
                self.gemini_client.delete_callback_key(job_id)
            else:
                self.logger.error(f"❌ Errore irreversibile Gateway: {error_msg}")
                return False

        if not response or response["status"] == "error":
            self.logger.error(f"❌ Falliti tutti i {max_retries} tentativi per {chunk_label}.")
            return False

        # 5. Parse Result
        response_text = response["output"].get("text", "")
        try:
            start_idx = response_text.find('{')
            end_idx = response_text.rfind('}') + 1
            result_json = json.loads(response_text[start_idx:end_idx])
            
            # 6. Validate & Save Macro-Cue
            macro_cue_data = {
                "project_id": self.project_id,
                "chunk_label": chunk_label,
                "selected_pad_id": result_json.get("selected_pad_id") or result_json.get("selected_mus_id"),
                "music_justification": result_json.get("music_justification", "")
            }
            macro_cue = MacroCue(**macro_cue_data)
            self.persistence.save_stage_output("b2", macro_cue.model_dump(), self.project_id, f"{chunk_label}-macro-cue", include_timestamp=False)
            
            self._log_trace(f"Decisione Finale: PAD={macro_cue.selected_pad_id}")
            self._log_trace(f"Giustificazione Artistica: {macro_cue.music_justification}")
            
            # 7. Acknowledge Job (Clear Redis Mailbox)
            self.gemini_client.delete_callback_key(job_id)

            # 8. Save Shopping List Macro (V3: canonical_id + production_prompt)
            shopping_list_raw = result_json.get("shopping_list_macro", [])
            if shopping_list_raw:
                validated_items = []
                for item_raw in shopping_list_raw:
                    # Normalize category to singular (ARIA v1.1)
                    if item_raw.get('type') == 'mus': item_raw['type'] = 'pad'
                    
                    if 'canonical_id' not in item_raw:
                        item_raw['canonical_id'] = f"{item_raw.get('type', 'pad')}_unknown"
                    
                    if 'production_prompt' not in item_raw:
                        item_raw['production_prompt'] = item_raw.get('universal_prompt', 'Missing prompt')
                        
                    validated_items.append(ShoppingItem(**item_raw).model_dump())
                
                self.persistence.save_stage_output("b2", {"missing_assets": validated_items}, self.project_id, f"{chunk_label}-shopping-list-macro", include_timestamp=False)
                
                for item in validated_items:
                    self._log_trace(f"⚠️ ASSET MANCANTE: [{item['type']}] canonical_id={item['canonical_id']} | {item['production_prompt'][:80]}...")
            else:
                self.logger.info(f"✅ Macro completato senza mancanze per {chunk_label}.")
            
        except Exception as e:
            self.logger.error(f"❌ Errore validazione MacroCue: {e}")
            return False

        return True

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python stage_b2_macro.py <project_id> [chunk_id]")
        sys.exit(1)
    
    stage = StageB2Macro(sys.argv[1])
    if len(sys.argv) > 2:
        stage.process_chunk(sys.argv[2])
    else:
        # Default test
        stage.process_chunk("000")
