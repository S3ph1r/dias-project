#!/usr/bin/env python3
"""
Stage B2 (Micro-Engineer) — ACE-Step Spec Generator v1.0
Architettura Director/Engineer: secondo passaggio del sound design scena per scena.

Legge il SoundEventScore prodotto da B2-Micro-Director e converte ogni evento fisico
in specifiche tecniche ACE-Step (production_tags in vocabolario Qwen3, canonical_id,
guidance_scale, duration_s).

Output: IntegratedCueSheet (scenes_automation + sound_shopping_list), identico
al formato del B2-Micro monolitico — compatibile con Stage D2 e Stage E.

Vantaggio chiave: la shopping list viene costruita PRIMA delle scene_automation,
rendendo strutturalmente impossibile il canonical_id mismatch.
"""

import json
import sys
import time
import yaml
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.common.config import get_config
from src.common.redis_factory import get_redis_client
from src.common.persistence import DiasPersistence
from src.common.gateway_client import GatewayClient
from src.common.logging_setup import get_logger
from src.common.models import IntegratedCueSheet, MicroCueAutomation, SoundShoppingItem


class StageB2MicroEngineer:
    PROMPT_PATH = Path(__file__).parent.parent.parent / "config/prompts/stage_b2/b2_micro_engineer_v1.0.yaml"
    DIRECTOR_SUFFIX = "-director-score"
    OUTPUT_SUFFIX = "-micro-cue"

    def __init__(self, project_id: str):
        self.project_id = DiasPersistence.normalize_id(project_id)
        self.config = get_config()
        self.redis = get_redis_client()
        self.persistence = DiasPersistence(project_id=self.project_id)
        self.logger = get_logger("b2_engineer")
        self.gemini_client = GatewayClient(redis_client=self.redis, client_id="dias")
        self.model_name = self.config.google.model_flash_lite

        self.trace_log_path = (
            self.persistence.project_root / "stages" / "stage_b2" / "output" / "b2_traceability.log"
        )
        self.trace_log_path.parent.mkdir(parents=True, exist_ok=True)

    # ─────────────────────────────────────────────────────────────
    # Logging
    # ─────────────────────────────────────────────────────────────

    def _log_trace(self, message: str):
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(self.trace_log_path, "a", encoding="utf-8") as f:
            f.write(f"[{ts}] [ENGINEER] {message}\n")

    # ─────────────────────────────────────────────────────────────
    # Data Loaders
    # ─────────────────────────────────────────────────────────────

    def _load_sound_event_score(self, block_id: str) -> Optional[Dict]:
        score = self.persistence.load_stage_output(
            "b2", self.project_id, f"{block_id}{self.DIRECTOR_SUFFIX}"
        )
        if not score:
            self.logger.error(f"❌ SoundEventScore mancante per {block_id}. Eseguire B2-Director prima.")
        return score

    def _load_macro_cue(self, chunk_label: str) -> Optional[Dict]:
        cue = self.persistence.load_stage_output("b2", self.project_id, f"{chunk_label}-macro-cue")
        if not cue:
            self.logger.error(f"❌ MacroCue mancante per {chunk_label}.")
        return cue

    # ─────────────────────────────────────────────────────────────
    # Prompt Preparation
    # ─────────────────────────────────────────────────────────────

    def _prepare_prompt(self, block_id: str, sound_event_score: Dict) -> str:
        with open(self.PROMPT_PATH, "r", encoding="utf-8") as f:
            template = yaml.safe_load(f).get("prompt_template", "")

        return template.format(
            project_id=self.project_id,
            block_id=block_id,
            sound_event_score=json.dumps(sound_event_score, indent=2, ensure_ascii=False),
        )

    # ─────────────────────────────────────────────────────────────
    # Core Processing
    # ─────────────────────────────────────────────────────────────

    def process(self, block_id: str) -> bool:
        """Converte il SoundEventScore in IntegratedCueSheet con spec ACE-Step."""
        self.logger.info(f"🔧 B2 Engineer v1.0: Generating ACE-Step specs for {block_id}...")
        self._log_trace(f"{'─'*50}")
        self._log_trace(f"[Engineer] Inizio elaborazione {block_id}")

        output_label = f"{block_id}{self.OUTPUT_SUFFIX}"
        if self.persistence.load_stage_output("b2", self.project_id, output_label):
            self.logger.info(f"⏭️  Skipping: MicroCue già su disco per {block_id}")
            return True

        sound_event_score = self._load_sound_event_score(block_id)
        if not sound_event_score:
            return False

        chunk_label = "-".join(block_id.split("-")[:2])
        macro_cue = self._load_macro_cue(chunk_label)
        if not macro_cue:
            return False

        pad_canonical_id = macro_cue.get("pad", {}).get("canonical_id", "pad_unknown_01")
        self._log_trace(f"[Engineer] PAD: {pad_canonical_id} | Asset summary: {sound_event_score.get('asset_summary', [])}")

        prompt = self._prepare_prompt(block_id, sound_event_score)
        job_id = f"b2-engineer-{self.project_id}-{block_id}"

        response = None
        for attempt in range(3):
            self._log_trace(f"[Engineer] Tentativo {attempt+1}/3 → Gemini ({self.model_name})")
            response = self.gemini_client.generate_content(
                contents=[{"role": "user", "parts": [{"text": prompt}]}],
                model_id=self.model_name,
                job_id=job_id,
            )
            if response["status"] != "error":
                break

            error_msg = response.get("error", "")
            if "503" in str(error_msg) or "429" in str(error_msg):
                self.logger.warning(f"⚠️  Gemini 503/429. Attesa 70s... (tentativo {attempt+1})")
                time.sleep(70)
                self.gemini_client.delete_callback_key(job_id)
            else:
                self.logger.error(f"❌ Errore Gateway irreversibile: {error_msg}")
                return False

        if not response or response["status"] == "error":
            self.logger.error(f"❌ Tutti i tentativi falliti per {block_id}.")
            return False

        response_text = response["output"].get("text", "")
        try:
            start = response_text.find("{")
            end = response_text.rfind("}") + 1
            result_json = json.loads(response_text[start:end])

            # Build shopping list FIRST (canonical_ids are established here)
            shopping_items = []
            for item_raw in result_json.get("sound_shopping_list", []):
                item = SoundShoppingItem(
                    type=item_raw.get("type", "sfx"),
                    canonical_id=item_raw.get("canonical_id", "sfx_unknown_01"),
                    production_prompt=item_raw.get("production_prompt", "Missing prompt."),
                    production_tags=item_raw.get("production_tags", ""),
                    negative_prompt=item_raw.get("negative_prompt", ""),
                    guidance_scale=float(item_raw.get("guidance_scale", 7.0)),
                    duration_s=float(item_raw.get("duration_s", 4.0)),
                    scene_id=item_raw.get("scene_id"),
                )
                shopping_items.append(item)

            # Ensure all canonical_ids end with numeric suffix
            import re as _re
            _suffix_re = _re.compile(r'_\d+$')
            for item in shopping_items:
                if not _suffix_re.search(item.canonical_id):
                    item.canonical_id = item.canonical_id + "_01"

            # Build id map: base → full (e.g. "amb_urban_street" → "amb_urban_street_01")
            shop_id_map: Dict[str, str] = {}
            for item in shopping_items:
                cid = item.canonical_id
                base = _suffix_re.sub('', cid)
                shop_id_map[base] = cid
                shop_id_map[cid] = cid

            # Build automations (sting uniqueness enforced)
            automations = []
            active_asset_ids = []
            sting_used = False

            for scene_raw in result_json.get("scenes_automation", []):
                if scene_raw.get("sting_id") and sting_used:
                    scene_raw["sting_id"] = None
                    scene_raw["sting_timing"] = None
                if scene_raw.get("sting_id"):
                    sting_used = True

                auto = MicroCueAutomation(
                    scene_id=scene_raw.get("scene_id", "unknown"),
                    pad_volume_automation=scene_raw.get("pad_volume_automation", "ducking"),
                    pad_duck_depth=scene_raw.get("pad_duck_depth", "medium"),
                    pad_fade_speed=scene_raw.get("pad_fade_speed", "smooth"),
                    amb_id=shop_id_map.get(scene_raw.get("amb_id"), scene_raw.get("amb_id")) if scene_raw.get("amb_id") else None,
                    amb_offset_s=float(scene_raw.get("amb_offset_s", 0.0)),
                    amb_duration_s=scene_raw.get("amb_duration_s"),
                    sfx_id=shop_id_map.get(scene_raw.get("sfx_id"), scene_raw.get("sfx_id")) if scene_raw.get("sfx_id") else None,
                    sfx_timing=scene_raw.get("sfx_timing"),
                    sfx_offset_s=float(scene_raw.get("sfx_offset_s", 0.0)),
                    sting_id=shop_id_map.get(scene_raw.get("sting_id"), scene_raw.get("sting_id")) if scene_raw.get("sting_id") else None,
                    sting_timing=scene_raw.get("sting_timing"),
                    reasoning=scene_raw.get("reasoning", ""),
                )
                automations.append(auto)

                if auto.amb_id:
                    active_asset_ids.append(f"AMB={auto.amb_id}")
                if auto.sfx_id:
                    active_asset_ids.append(f"SFX={auto.sfx_id}")
                if auto.sting_id:
                    active_asset_ids.append(f"STG={auto.sting_id}")

            cue_sheet = IntegratedCueSheet(
                project_id=self.project_id,
                block_id=block_id,
                pad_canonical_id=pad_canonical_id,
                scenes_automation=automations,
                sound_shopping_list=shopping_items,
            )

            self.persistence.save_stage_output(
                "b2", cue_sheet.model_dump(), self.project_id, output_label, include_timestamp=False
            )
            self.gemini_client.delete_callback_key(job_id)

            unique_active = list(set(active_asset_ids))
            self._log_trace(
                f"[Engineer] Completato: {len(automations)} scene | "
                f"Asset attivi: {unique_active or 'Nessuno'} | "
                f"Shopping: {len(shopping_items)} item"
            )
            self.logger.info(
                f"✅ MicroCue (Engineer): {len(automations)} scene, "
                f"{len(shopping_items)} asset in shopping list"
            )

        except Exception as e:
            self.logger.error(f"❌ Errore parsing/validazione MicroCue (Engineer): {e}", exc_info=True)
            return False

        return True


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python stage_b2_micro_engineer.py <project_id> <block_id>")
        sys.exit(1)
    stage = StageB2MicroEngineer(sys.argv[1])
    stage.process(sys.argv[2])
