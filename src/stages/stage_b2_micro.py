#!/usr/bin/env python3
"""
Stage B2 (Micro) — The Sound Designer of Detail v4.0
Architettura Sound-on-Demand: zero dipendenze dal catalogo ARIA/Redis.
Per ogni micro-chunk, produce:
  1. IntegratedCueSheet: copione artistico scena per scena (PAD breathing + AMB/SFX/STING).
  2. sound_shopping_list: TUTTI gli asset richiesti (AMB/SFX/STING) da produrre in Stage D2.

La coerenza tra copione e shopping list è garantita dal prompt (Regola Fondamentale).
Stage D2 produrrà ogni asset tramite ARIA SoundFactory e li salverà in locale.
Stage E eseguirà il copione usando gli asset fisici salvati (nessun lookup remoto).
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
from src.common.models import IntegratedCueSheet, MicroCueAutomation, SoundShoppingItem, LeitmotifEvent


class StageB2Micro:
    PROMPT_PATH = Path(__file__).parent.parent.parent / "config/prompts/stage_b2/b2_micro_v4.1.yaml"

    def __init__(self, project_id: str):
        self.project_id = DiasPersistence.normalize_id(project_id)
        self.config = get_config()
        self.redis = get_redis_client()
        self.persistence = DiasPersistence(project_id=self.project_id)
        self.logger = get_logger("b2_micro")
        self.gemini_client = GatewayClient(redis_client=self.redis, client_id="dias")
        self.model_name = self.config.google.model_flash_lite

        # Traceability log (condiviso con Macro)
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
            f.write(f"[{ts}] [MICRO] {message}\n")

    # ─────────────────────────────────────────────────────────────
    # Data Loaders
    # ─────────────────────────────────────────────────────────────

    def _load_macro_cue(self, chunk_label: str) -> Optional[Dict]:
        """Carica il MacroCue v4 prodotto da B2-Macro."""
        cue = self.persistence.load_stage_output("b2", self.project_id, f"{chunk_label}-macro-cue")
        if not cue:
            self.logger.error(f"❌ MacroCue mancante per {chunk_label}. Eseguire B2-Macro prima.")
        return cue

    def _load_scenes_with_timing(self, block_id: str) -> List[Dict]:
        """
        Carica le scene del micro-chunk con il timing fisico dalla Master Timing Grid.
        Unisce i dati di Stage C (testo, speaker) con quelli di Stage D (timing fisico).
        """
        # Scene da Stage C
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

        # Timing dalla Master Grid
        grid_file = (
            self.persistence.project_root
            / "stages" / "stage_d" / "master_timing_grid.json"
        )
        timing_map: Dict[str, Dict] = {}
        if grid_file.exists():
            with open(grid_file, "r", encoding="utf-8") as f:
                grid = json.load(f)
            # Naviga: macro_chunk → micro_chunk → scenes
            for macro_data in grid.get("macro_chunks", {}).values():
                micro_data = macro_data.get("micro_chunks", {}).get(block_id, {})
                for scene in micro_data.get("scenes", []):
                    timing_map[scene["scene_id"]] = {
                        "start_offset_s": scene.get("start_offset", 0.0),
                        "voice_duration_s": scene.get("voice_duration", 0.0),
                        "pause_after_s": scene.get("pause_after", 0.0),
                    }

        # Merge
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

    def _load_available_leitmotifs(self) -> tuple[str, dict]:
        """
        Legge project_sound_palette da preproduction.json.
        Ritorna: (stringa formattata per il prompt, dict canonical_id → entry).
        """
        preprod_path = self.persistence.get_preproduction_path()
        if not preprod_path or not preprod_path.exists():
            return "(Nessun leitmotif disponibile)", {}

        with open(preprod_path, encoding="utf-8") as f:
            preprod = json.load(f)

        palette = preprod.get("project_sound_palette", {})
        if not palette:
            return "(Nessun leitmotif disponibile)", {}

        lines = []
        for cid, entry in palette.items():
            name = entry.get("character_name", "?")
            role = entry.get("role_category", "?")
            profile = entry.get("musical_profile", "")[:120]
            lines.append(f"  - {cid} ({name} [{role}]): {profile}")

        return "\n".join(lines), palette

    # ─────────────────────────────────────────────────────────────
    # Prompt Preparation
    # ─────────────────────────────────────────────────────────────

    def _format_pad_arc_summary(self, macro_cue: Dict) -> str:
        """Formatta il pad_arc del MacroCue in una stringa leggibile per il prompt."""
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

    def _prepare_prompt(
        self, block_id: str, scenes_with_timing: List[Dict], macro_cue: Dict,
        available_leitmotifs: str = "(Nessun leitmotif disponibile)",
    ) -> str:
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
            available_leitmotifs=available_leitmotifs,
        )

    # ─────────────────────────────────────────────────────────────
    # Core Processing
    # ─────────────────────────────────────────────────────────────

    def process_micro_chunk(self, block_id: str) -> bool:
        """Processa un singolo micro-chunk e produce IntegratedCueSheet + SoundShoppingList."""
        self.logger.info(f"🎬 B2 Micro-Spotter v4 (Sound-on-Demand): Processing {block_id}...")
        self._log_trace(f"{'─'*50}")
        self._log_trace(f"Inizio elaborazione {block_id}")

        # 1. Idempotency check
        output_label = f"{block_id}-micro-cue"
        if self.persistence.load_stage_output("b2", self.project_id, output_label):
            self.logger.info(f"⏭️  Skipping: MicroCue già su disco per {block_id}")
            return True

        # 2. Load Macro-Cue (PAD ereditato)
        # block_id es: "chunk-000-micro-001" → chunk_label = "chunk-000"
        chunk_label = "-".join(block_id.split("-")[:2])
        macro_cue = self._load_macro_cue(chunk_label)
        if not macro_cue:
            return False

        pad_canonical_id = macro_cue.get("pad", {}).get("canonical_id", "pad_unknown_01")
        self._log_trace(f"PAD ereditato: {pad_canonical_id}")

        # 3. Load scenes with timing
        scenes_with_timing = self._load_scenes_with_timing(block_id)
        if not scenes_with_timing:
            self.logger.error(f"❌ Nessuna scena trovata per {block_id}")
            return False

        self._log_trace(f"Scene caricate: {len(scenes_with_timing)}")

        # 4. Prepare prompt and call Gemini
        available_leitmotifs_str, _palette = self._load_available_leitmotifs()
        prompt = self._prepare_prompt(block_id, scenes_with_timing, macro_cue, available_leitmotifs_str)
        job_id = f"b2-micro-{self.project_id}-{block_id}"

        response = None
        for attempt in range(3):
            self._log_trace(f"Tentativo {attempt+1}/3 → Gemini ({self.model_name})")
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

        # 5. Parse response
        response_text = response["output"].get("text", "")
        try:
            start = response_text.find("{")
            end = response_text.rfind("}") + 1
            result_json = json.loads(response_text[start:end])

            cue_raw = result_json.get("integrated_cue_sheet", result_json)
            shopping_raw = result_json.get("sound_shopping_list", [])

            # Build MicroCueAutomation list
            automations = []
            active_asset_ids = []
            sting_used = False

            for scene_raw in cue_raw.get("scenes_automation", []):
                # Enforce sting uniqueness
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
                    amb_id=scene_raw.get("amb_id"),
                    amb_offset_s=float(scene_raw.get("amb_offset_s", 0.0)),
                    amb_duration_s=scene_raw.get("amb_duration_s"),
                    sfx_id=scene_raw.get("sfx_id"),
                    sfx_timing=scene_raw.get("sfx_timing"),
                    sfx_offset_s=float(scene_raw.get("sfx_offset_s", 0.0)),
                    sting_id=scene_raw.get("sting_id"),
                    sting_timing=scene_raw.get("sting_timing"),
                    reasoning=scene_raw.get("reasoning", ""),
                )
                automations.append(auto)

                # Collect active asset ids for trace
                if auto.amb_id:
                    active_asset_ids.append(f"AMB={auto.amb_id}")
                if auto.sfx_id:
                    active_asset_ids.append(f"SFX={auto.sfx_id}")
                if auto.sting_id:
                    active_asset_ids.append(f"STG={auto.sting_id}")

            # Build SoundShoppingItem list (v4.1 — ACE-Step Ready)
            shopping_items = []
            for item_raw in shopping_raw:
                item = SoundShoppingItem(
                    type=item_raw.get("type", "sfx"),
                    canonical_id=item_raw.get("canonical_id", "sfx_unknown_01"),
                    production_prompt=item_raw.get("production_prompt", "Missing prompt."),
                    production_tags=item_raw.get("production_tags", ""),
                    negative_prompt=item_raw.get("negative_prompt", ""),
                    guidance_scale=float(item_raw.get("guidance_scale", 7.0)),
                    duration_s=float(item_raw.get("duration_s", 10.0)),
                    scene_id=item_raw.get("scene_id"),
                )
                shopping_items.append(item)

            # Normalize canonical_ids for consistency between scenes and shopping list.
            # Rule: every canonical_id must end with a numeric suffix (_01, _02, ...).
            # Shopping list is patched first, then scenes are aligned to it.
            import re as _re
            _suffix_re = _re.compile(r'_\d+$')
            for item in shopping_items:
                if not _suffix_re.search(item.canonical_id):
                    item.canonical_id = item.canonical_id + "_01"
            # Build base→full map from (now-normalized) shopping list
            shop_id_map: Dict[str, str] = {}
            for item in shopping_items:
                cid = item.canonical_id
                base = _suffix_re.sub('', cid)
                shop_id_map[base] = cid   # "amb_enclosed_cave" → "amb_enclosed_cave_01"
                shop_id_map[cid] = cid    # exact match passthrough
            for auto in automations:
                if auto.amb_id:
                    auto.amb_id = shop_id_map.get(auto.amb_id, auto.amb_id)
                if auto.sfx_id:
                    auto.sfx_id = shop_id_map.get(auto.sfx_id, auto.sfx_id)
                if auto.sting_id:
                    auto.sting_id = shop_id_map.get(auto.sting_id, auto.sting_id)

            # Build LeitmotifEvent list
            leitmotif_events = []
            for evt_raw in cue_raw.get("leitmotif_events", []):
                lid = evt_raw.get("leitmotif_id", "")
                if not lid:
                    continue
                leitmotif_events.append(LeitmotifEvent(
                    scene_id=evt_raw.get("scene_id", "unknown"),
                    leitmotif_id=lid,
                    timing=evt_raw.get("timing", "start"),
                    reasoning=evt_raw.get("reasoning", ""),
                ))
            if leitmotif_events:
                self._log_trace(f"Leitmotif events: {[e.leitmotif_id for e in leitmotif_events]}")

            # Build & validate IntegratedCueSheet
            cue_sheet = IntegratedCueSheet(
                project_id=self.project_id,
                block_id=block_id,
                pad_canonical_id=pad_canonical_id,
                scenes_automation=automations,
                sound_shopping_list=shopping_items,
                leitmotif_events=leitmotif_events,
            )

            # 6. Persist (copione + shopping list embedded)
            self.persistence.save_stage_output(
                "b2", cue_sheet.model_dump(), self.project_id, output_label, include_timestamp=False
            )
            self.gemini_client.delete_callback_key(job_id)

            # 7. Trace
            unique_active = list(set(active_asset_ids))
            self._log_trace(
                f"Blocco completato: {len(automations)} scene | "
                f"Asset attivi: {unique_active or 'Nessuno'}"
            )
            self._log_trace(
                f"Shopping list: {len(shopping_items)} item "
                f"({', '.join(i.type for i in shopping_items) or 'Nessuno'})"
            )

            self.logger.info(
                f"✅ MicroCue salvato: {len(automations)} scene, "
                f"{len(shopping_items)} asset in shopping list"
            )

        except Exception as e:
            self.logger.error(f"❌ Errore parsing/validazione MicroCue: {e}", exc_info=True)
            return False

        return True


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python stage_b2_micro.py <project_id> <block_id>")
        sys.exit(1)
    stage = StageB2Micro(sys.argv[1])
    stage.process_micro_chunk(sys.argv[2])
