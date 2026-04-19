#!/usr/bin/env python3
"""
Stage B2 (Micro-Director) — Narrative Event Extractor v1.0
Architettura Director/Engineer: primo passaggio del sound design scena per scena.

Per ogni micro-chunk, analizza il testo e identifica gli eventi fisici che
giustificano un suono (AMB, SFX, STING) e il comportamento del PAD per ogni scena.
Output: SoundEventScore in linguaggio naturale — zero vocabolario tecnico ACE-Step.

Il SoundEventScore viene poi letto da B2-Micro-Engineer che produce le spec ACE-Step.
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
from src.common.models import (
    SoundEventScore, SceneEvent, AmbientEvent, SfxEvent, StingEvent
)


class StageB2MicroDirector:
    PROMPT_PATH = Path(__file__).parent.parent.parent / "config/prompts/stage_b2/b2_micro_director_v1.0.yaml"
    OUTPUT_SUFFIX = "-director-score"

    def __init__(self, project_id: str):
        self.project_id = DiasPersistence.normalize_id(project_id)
        self.config = get_config()
        self.redis = get_redis_client()
        self.persistence = DiasPersistence(project_id=self.project_id)
        self.logger = get_logger("b2_director")
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
            f.write(f"[{ts}] [DIRECTOR] {message}\n")

    # ─────────────────────────────────────────────────────────────
    # Data Loaders
    # ─────────────────────────────────────────────────────────────

    def _load_macro_cue(self, chunk_label: str) -> Optional[Dict]:
        cue = self.persistence.load_stage_output("b2", self.project_id, f"{chunk_label}-macro-cue")
        if not cue:
            self.logger.error(f"❌ MacroCue mancante per {chunk_label}. Eseguire B2-Macro prima.")
        return cue

    def _load_scenes_with_timing(self, block_id: str) -> List[Dict]:
        """Carica scene + timing fisico (stesso metodo di B2-Micro monolitico)."""
        scenes_file = (
            self.persistence.project_root
            / "stages" / "stage_c" / "output"
            / f"{self.project_id}-{block_id}-scenes.json"
        )
        if not scenes_file.exists():
            self.logger.error(f"❌ Scene Stage C mancanti: {scenes_file}")
            return []

        with open(scenes_file, "r", encoding="utf-8") as f:
            scenes_raw = json.load(f)
        scenes = scenes_raw if isinstance(scenes_raw, list) else scenes_raw.get("scenes", [])

        grid_file = (
            self.persistence.project_root
            / "stages" / "stage_d" / "master_timing_grid.json"
        )
        timing_map: Dict[str, Dict] = {}
        if grid_file.exists():
            with open(grid_file, "r", encoding="utf-8") as f:
                grid = json.load(f)
            for macro_data in grid.get("macro_chunks", {}).values():
                micro_data = macro_data.get("micro_chunks", {}).get(block_id, {})
                for scene in micro_data.get("scenes", []):
                    timing_map[scene["scene_id"]] = {
                        "start_offset_s": scene.get("start_offset", 0.0),
                        "voice_duration_s": scene.get("voice_duration", 0.0),
                        "pause_after_s": scene.get("pause_after", 0.0),
                    }

        scenes_with_timing = []
        for scene in scenes:
            sid = scene.get("scene_id", "")
            timing = timing_map.get(sid, {
                "start_offset_s": 0.0,
                "voice_duration_s": 5.0,
                "pause_after_s": 0.5,
            })
            scenes_with_timing.append({
                "scene_id": sid,
                "speaker": scene.get("speaker", "NARRATOR"),
                "text": scene.get("text_content", scene.get("text", "")),
                "scene_type": scene.get("scene_type", "narration"),
                "start_offset_s": timing["start_offset_s"],
                "voice_duration_s": timing["voice_duration_s"],
                "pause_after_s": timing["pause_after_s"],
            })

        return scenes_with_timing

    # ─────────────────────────────────────────────────────────────
    # Prompt Preparation
    # ─────────────────────────────────────────────────────────────

    def _format_pad_arc_summary(self, macro_cue: Dict) -> str:
        arc = macro_cue.get("pad", {}).get("pad_arc", [])
        if not arc:
            return "(Nessuna partitura emotiva disponibile)"
        lines = []
        for seg in arc:
            intensity_desc = {
                "low": "solo Bass (quasi silenzio musicale)",
                "mid": "Bass + Melody (musica presente)",
                "high": "Bass + Melody + Drums (climax, massima intensità)",
            }.get(seg.get("intensity", "mid"), seg.get("intensity", "mid"))
            note = f" — {seg['note']}" if seg.get("note") else ""
            lines.append(f"  {seg.get('start_s', 0)}s → {seg.get('end_s', '?')}s: {intensity_desc}{note}")
        return "\n".join(lines)

    def _prepare_prompt(self, block_id: str, scenes_with_timing: List[Dict], macro_cue: Dict) -> str:
        with open(self.PROMPT_PATH, "r", encoding="utf-8") as f:
            template = yaml.safe_load(f).get("prompt_template", "")

        pad_canonical_id = macro_cue.get("pad", {}).get("canonical_id", "pad_unknown_01")
        pad_arc_summary = self._format_pad_arc_summary(macro_cue)

        return template.format(
            project_id=self.project_id,
            block_id=block_id,
            pad_canonical_id=pad_canonical_id,
            pad_arc_summary=pad_arc_summary,
            scenes_with_timing=json.dumps(scenes_with_timing, indent=2, ensure_ascii=False),
        )

    # ─────────────────────────────────────────────────────────────
    # Core Processing
    # ─────────────────────────────────────────────────────────────

    def process(self, block_id: str) -> bool:
        """Analizza le scene e produce il SoundEventScore (eventi fisici in linguaggio naturale)."""
        self.logger.info(f"🎬 B2 Director v1.0: Analyzing events for {block_id}...")
        self._log_trace(f"{'─'*50}")
        self._log_trace(f"[Director] Inizio analisi {block_id}")

        output_label = f"{block_id}{self.OUTPUT_SUFFIX}"
        if self.persistence.load_stage_output("b2", self.project_id, output_label):
            self.logger.info(f"⏭️  Skipping: SoundEventScore già su disco per {block_id}")
            return True

        chunk_label = "-".join(block_id.split("-")[:2])
        macro_cue = self._load_macro_cue(chunk_label)
        if not macro_cue:
            return False

        scenes_with_timing = self._load_scenes_with_timing(block_id)
        if not scenes_with_timing:
            self.logger.error(f"❌ Nessuna scena trovata per {block_id}")
            return False

        self._log_trace(f"[Director] Scene caricate: {len(scenes_with_timing)}")

        prompt = self._prepare_prompt(block_id, scenes_with_timing, macro_cue)
        job_id = f"b2-director-{self.project_id}-{block_id}"

        response = None
        for attempt in range(3):
            self._log_trace(f"[Director] Tentativo {attempt+1}/3 → Gemini ({self.model_name})")
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

            scene_events = []
            for s in result_json.get("scenes", []):
                amb_raw = s.get("ambient_event")
                sfx_raw = s.get("sfx_event")
                sting_raw = s.get("sting_event")

                scene_events.append(SceneEvent(
                    scene_id=s["scene_id"],
                    pad_behavior=s.get("pad_behavior", "ducking"),
                    pad_duck_depth=s.get("pad_duck_depth", "medium"),
                    ambient_event=AmbientEvent(**amb_raw) if amb_raw else None,
                    sfx_event=SfxEvent(**sfx_raw) if sfx_raw else None,
                    sting_event=StingEvent(**sting_raw) if sting_raw else None,
                ))

            pad_canonical_id = macro_cue.get("pad", {}).get("canonical_id", "pad_unknown_01")
            score = SoundEventScore(
                project_id=self.project_id,
                block_id=block_id,
                pad_canonical_id=pad_canonical_id,
                scenes=scene_events,
                asset_summary=result_json.get("asset_summary", []),
            )

            self.persistence.save_stage_output(
                "b2", score.model_dump(), self.project_id, output_label, include_timestamp=False
            )
            self.gemini_client.delete_callback_key(job_id)

            amb_count = sum(1 for s in scene_events if s.ambient_event)
            sfx_count = sum(1 for s in scene_events if s.sfx_event)
            sting_count = sum(1 for s in scene_events if s.sting_event)

            self._log_trace(
                f"[Director] Score salvato: {len(scene_events)} scene | "
                f"AMB={amb_count} SFX={sfx_count} STING={sting_count}"
            )
            self.logger.info(
                f"✅ SoundEventScore: {len(scene_events)} scene, "
                f"AMB={amb_count} SFX={sfx_count} STING={sting_count}"
            )

        except Exception as e:
            self.logger.error(f"❌ Errore parsing SoundEventScore: {e}", exc_info=True)
            return False

        return True


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python stage_b2_micro_director.py <project_id> <block_id>")
        sys.exit(1)
    stage = StageB2MicroDirector(sys.argv[1])
    stage.process(sys.argv[2])
