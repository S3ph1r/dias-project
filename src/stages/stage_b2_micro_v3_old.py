#!/usr/bin/env python3
"""
Stage B2 (Micro) - The Micro-Spotter
Analizza le scene di un Micro-chunk per inserire SFX, STNG e domare i volumi MUS.
Dipende dalle scelte fatte dal Macro-Spotter per il Macro-chunk genitore.
"""

import os
import json
import logging
import sys
import yaml
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime
import re

# Aggiungi il path root al Python path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.common.config import get_config
from src.common.redis_factory import get_redis_client
from src.common.persistence import DiasPersistence
from src.common.gateway_client import GatewayClient
from src.common.logging_setup import get_logger
from src.common.models import IntegratedCueSheet, MicroCueAutomation, ShoppingItem

class StageB2Micro:
    def __init__(self, project_id: str):
        self.project_id = DiasPersistence.normalize_id(project_id)
        self.config = get_config()
        self.redis = get_redis_client()
        self.persistence = DiasPersistence(project_id=self.project_id)
        self.logger = get_logger("b2_micro")
        self.gemini_client = GatewayClient(redis_client=self.redis, client_id="dias")
        self.model_name = self.config.google.model_flash_lite
        
        # Setup Traceability Logger (Same file as Macro)
        self.trace_log_path = self.persistence.project_root / "stages" / "stage_b2" / "output" / "b2_traceability.log"
        self.trace_log_path.parent.mkdir(parents=True, exist_ok=True)

    def _log_trace(self, message: str):
        """Scrive un log temporizzato nel file di tracciabilità del progetto."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(self.trace_log_path, "a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] [MICRO] {message}\n")

    def _fetch_aria_registry_all(self) -> Dict[str, Any]:
        """Recupera tutti gli asset (stings, sfx, pads) dal registro ARIA."""
        try:
            raw_data = self.redis.get("aria:registry:master")
            if not raw_data:
                return {"stings": {}, "sfx": {}, "pads": {}}
            data = json.loads(raw_data)
            assets = data.get("assets", {})
            return {
                "sting": assets.get("sting", {}),
                "sfx": assets.get("sfx", {}),
                "pad": assets.get("pad", {}),
                "amb": assets.get("amb", {})
            }
        except Exception as e:
            self.logger.error(f"❌ Errore registro: {e}")
            return {"stings": {}, "sfx": {}, "pads": {}}

    def _format_registry_for_prompt(self, assets: Dict) -> str:
        """Formatta gli asset con canonical_id esplicito per aiutare il matching diretto."""
        if not assets:
            return "(Nessun asset disponibile nel catalogo)"
        lines = []
        for asset_id, asset_data in assets.items():
            tags = asset_data.get('tags', [])
            desc = asset_data.get('description', '')
            lines.append(f"  - canonical_id: {asset_id} | tags: {tags} | {desc}")
        return "\n".join(lines)

    def _prepare_prompt(self, block_id: str, scenes_with_timing: List[Dict], current_mus: str, registry: Dict) -> str:
        # V3 prompt
        prompt_path = Path(__file__).parent.parent.parent / "config/prompts/stage_b2/b2_micro_v3.0.yaml"

        with open(prompt_path, 'r', encoding='utf-8') as f:
            template = yaml.safe_load(f).get("prompt_template", "")

        available_pads    = self._format_registry_for_prompt(registry.get('pad', {}))
        available_amb     = self._format_registry_for_prompt(registry.get('amb', {}))
        available_stings  = self._format_registry_for_prompt(registry.get('sting', {}))
        available_sfx     = self._format_registry_for_prompt(registry.get('sfx', {}))

        return template.format(
            current_mus_id=current_mus,
            available_pads=available_pads,
            available_amb=available_amb,
            available_stings=available_stings,
            available_sfx=available_sfx,
            scenes_with_timing=json.dumps(scenes_with_timing, indent=2, ensure_ascii=False),
            project_id=self.project_id,
            block_id=block_id
        )

    def process_micro(self, chunk_id: str, micro_id: str) -> bool:
        """
        Elabora un singolo micro-chunk integrando dati macro e fisici.
        """
        chunk_label = f"chunk-{chunk_id}"
        block_id = f"chunk-{chunk_id}-micro-{micro_id}"
        self.logger.info(f"🎬 B2 Micro-Spotter (Integrated): Processing {block_id}...")
        self._log_trace(f"Inizio elaborazione {block_id}")

        # 1. Idempotency Check (Disk)
        output_label = f"{block_id}-micro-cue"
        existing = self.persistence.load_stage_output("b2", self.project_id, output_label)
        if existing:
            self.logger.info(f"⏭️ Skipping B2 Micro: Analisi già presente su disco per {self.project_id}-{output_label}")
            return True

        # 2. Load Macro-Cue (Inherit MUS)
        macro_cue_file = self.persistence.project_root / "stages" / "stage_b2" / "output" / f"{self.project_id}-{chunk_label}-macro-cue.json"
        if not macro_cue_file.exists():
            self.logger.error(f"❌ Macro-cue mancante per {chunk_label}. Esegui b2-macro prima.")
            return False
            
        with open(macro_cue_file, 'r', encoding='utf-8') as f:
            macro_cue = json.load(f)
        current_pad = macro_cue.get("selected_pad_id") or macro_cue.get("selected_mus_id") or "null"
        self._log_trace(f"PAD Ereditato: {current_pad}")

        # 3. Load Master Timing Grid
        grid_file = self.persistence.project_root / "stages" / "stage_d" / "master_timing_grid.json"
        if not grid_file.exists():
            self.logger.error(f"❌ Master Timing Grid mancante. Esegui create_timing_grid.py prima.")
            return False
        
        with open(grid_file, 'r', encoding='utf-8') as f:
            grid_data = json.load(f)
        
        # Estrai i timing del micro-chunk corrente
        micro_timing = grid_data.get("macro_chunks", {}).get(chunk_label, {}).get("micro_chunks", {}).get(block_id, {})
        if not micro_timing:
            self.logger.error(f"❌ Timing non trovati per {block_id} nella Timing Grid.")
            return False
        
        timing_scenes = micro_timing.get("scenes", [])
        timing_map = {s["scene_id"]: s for s in timing_scenes}

        # 4. Load Scenes Output (Stage C text content)
        scenes_file = self.persistence.project_root / "stages" / "stage_c" / "output" / f"{self.project_id}-{block_id}-scenes.json"
        if not scenes_file.exists():
            self.logger.error(f"❌ Scenes JSON mancante per {block_id}.")
            return False
            
        with open(scenes_file, 'r', encoding='utf-8') as f:
            scenes_data = json.load(f)
            scenes = scenes_data.get("scenes", [])

        # 5. Merge Text + Timing for Prompt
        scenes_for_prompt = []
        for s in scenes:
            sid = s.get("scene_id")
            t = timing_map.get(sid, {})
            scenes_for_prompt.append({
                "scene_id": sid,
                "speaker": s.get("speaker"),
                "text": s.get("text_content"),
                "voice_duration_s": t.get("voice_duration", 0.0),
                "pause_after_s": t.get("pause_after", 0.0)
            })

        # 6. Fetch Registry & Call Gemini
        registry = self._fetch_aria_registry_all()
        prompt = self._prepare_prompt(block_id, scenes_for_prompt, current_pad, registry)
        job_id = f"b2-micro-{self.project_id}-{block_id}"
        
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
                self.gemini_client.delete_callback_key(job_id)
            else:
                self.logger.error(f"❌ Errore irreversibile Gateway: {error_msg}")
                return False

        if not response or response["status"] == "error":
            self.logger.error(f"❌ Falliti tutti i {max_retries} tentativi per {block_id}.")
            return False

        # 7. Parse & Validate
        response_text = response["output"].get("text", "")
        try:
            start_idx = response_text.find('{')
            end_idx = response_text.rfind('}') + 1
            result_json = json.loads(response_text[start_idx:end_idx])
            
            cue_data = result_json.get("integrated_cue_sheet", {})
            integrated_cue = IntegratedCueSheet(**cue_data)
            self.persistence.save_stage_output("b2", integrated_cue.model_dump(), self.project_id, f"{block_id}-micro-cue", include_timestamp=False)
            
            # Acknowledge Job (Clear Redis Mailbox)
            self.gemini_client.delete_callback_key(job_id)
            
            # Log Decisions (V3: include duck_depth and fade_speed)
            active_count = 0
            for auto in integrated_cue.scenes_automation:
                has_sound = any([auto.amb_id, auto.sfx_id, auto.sting_id])
                if has_sound:
                    active_count += 1
                    choice = f"AMB={auto.amb_id}, SFX={auto.sfx_id}, STG={auto.sting_id}"
                    volume = f"vol={auto.pad_volume_automation}({auto.pad_duck_depth}/{auto.pad_fade_speed})"
                    self._log_trace(f"Scena {auto.scene_id}: {choice} | {volume} | {auto.reasoning}")
                else:
                    volume = f"vol={auto.pad_volume_automation}({auto.pad_duck_depth}/{auto.pad_fade_speed})"
                    self._log_trace(f"Scena {auto.scene_id}: SILENZIO | {volume}")
            
            self._log_trace(f"Blocco completato: {active_count}/{len(integrated_cue.scenes_automation)} scene con suoni attivi")
            
            # 8. Shopping List Micro (V3: canonical_id + production_prompt)
            shopping_list_raw = result_json.get("shopping_list_micro", [])
            if shopping_list_raw:
                validated_items = []
                for item_raw in shopping_list_raw:
                    # Normalize category to singular (ARIA v1.1)
                    if item_raw.get('type') == 'mus': item_raw['type'] = 'pad'
                    
                    if 'canonical_id' not in item_raw:
                        item_raw['canonical_id'] = f"{item_raw.get('type', 'unknown')}_unknown"
                    
                    if 'production_prompt' not in item_raw:
                        item_raw['production_prompt'] = item_raw.get('universal_prompt', 'Missing prompt')
                        
                    validated_items.append(ShoppingItem(**item_raw).model_dump())
                
                self.persistence.save_stage_output("b2", {"missing_assets": validated_items}, self.project_id, f"{block_id}-shopping-list-micro", include_timestamp=False)
                
                for item in validated_items:
                    self._log_trace(f"⚠️ ASSET MANCANTE: [{item['type']}] canonical_id={item['canonical_id']} | {item['production_prompt'][:80]}...")

        except Exception as e:
            self.logger.error(f"❌ Errore durante il parsing o la validazione B2-Micro: {e}")
            return False

        return True

if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("Usage: python stage_b2_micro.py <project_id> <chunk_id> <micro_id>")
        sys.exit(1)
    
    stage = StageB2Micro(sys.argv[1])
    stage.process_micro(sys.argv[2], sys.argv[3])
