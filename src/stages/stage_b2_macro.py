#!/usr/bin/env python3
"""
Stage B2 (Macro) — The Musical Director v4.0
Architettura Sound-on-Demand: zero dipendenze dal catalogo ARIA/Redis.
Per ogni macro-chunk, produce:
  1. Un MacroCue con PadRequest completo (canonical_id + production_prompt + pad_arc)
  2. La partitura emotiva (pad_arc) che Stage E userà per gestire i layer Demucs nel tempo.

Il PAD verrà prodotto ex-novo da Stage D2 tramite ARIA SoundFactory (ACE-Step).
Stage D2 applicherà HTDemucs per isolare Bass, Melody, Drums.
Stage E caricherà i 3 stem e li gestirà dinamicamente via pad_arc.
"""

import json
import sys
import time
import yaml
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.common.config import get_config
from src.common.redis_factory import get_redis_client
from src.common.persistence import DiasPersistence
from src.common.gateway_client import GatewayClient
from src.common.logging_setup import get_logger
from src.common.models import MacroCue, PadRequest, PadArcSegment


class StageB2Macro:
    PROMPT_PATH = Path(__file__).parent.parent.parent / "config/prompts/stage_b2/b2_macro_v4.0.yaml"

    def __init__(self, project_id: str):
        self.project_id = DiasPersistence.normalize_id(project_id)
        self.config = get_config()
        self.redis = get_redis_client()
        self.persistence = DiasPersistence(project_id=self.project_id)
        self.logger = get_logger("b2_macro")
        self.gemini_client = GatewayClient(redis_client=self.redis, client_id="dias")
        self.model_name = self.config.google.model_flash_lite

        # Traceability log
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
            f.write(f"[{ts}] [MACRO] {message}\n")

    # ─────────────────────────────────────────────────────────────
    # Data Loaders (Stage 0 + Stage B + Timing Grid)
    # ─────────────────────────────────────────────────────────────

    def _load_preproduction_dossier(self) -> Dict[str, Any]:
        path = self.persistence.get_preproduction_path()
        if not path or not path.exists():
            return {}
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _load_palette_proposals(self) -> List[Dict]:
        path = self.persistence.get_fingerprint_path()
        if not path or not path.exists():
            return []
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("sound_design", {}).get("palette_proposals", [])

    def _load_chunk_analysis(self, chunk_label: str) -> Optional[Dict]:
        """Carica l'analisi emotiva del macro-chunk prodotta da Stage B."""
        analysis_file = (
            self.persistence.project_root
            / "stages" / "stage_b" / "output"
            / f"{self.project_id}-{chunk_label}.json"
        )
        if not analysis_file.exists():
            self.logger.error(f"❌ Analisi Stage B mancante: {analysis_file}")
            return None
        with open(analysis_file, "r", encoding="utf-8") as f:
            return json.load(f)

    def _load_chunk_text(self, chunk_label: str) -> str:
        """Carica il testo grezzo del macro-chunk da Stage A."""
        chunk_file = (
            self.persistence.project_root
            / "stages" / "stage_a" / "output"
            / f"{self.project_id}-{chunk_label}.json"
        )
        if not chunk_file.exists():
            return "(Testo non disponibile)"
        with open(chunk_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("block_text", data.get("text", "(Testo non disponibile)"))

    def _get_chunk_total_duration(self, chunk_label: str) -> float:
        """Ottiene la durata totale del chunk dalla Master Timing Grid."""
        grid_file = (
            self.persistence.project_root
            / "stages" / "stage_d" / "master_timing_grid.json"
        )
        if not grid_file.exists():
            return 900.0  # Fallback: 15 minuti stimati
        try:
            with open(grid_file, "r", encoding="utf-8") as f:
                grid = json.load(f)
            macro_key = chunk_label  # es: "chunk-000"
            macro_data = grid.get("macro_chunks", {}).get(macro_key, {})
            return float(macro_data.get("duration", 900.0))
        except Exception:
            return 900.0

    # ─────────────────────────────────────────────────────────────
    # Prompt Preparation
    # ─────────────────────────────────────────────────────────────

    def _prepare_prompt(
        self,
        chunk_label: str,
        chunk_analysis: Dict,
        chunk_text: str,
        total_duration_s: float,
        dossier: Dict,
        proposals: List[Dict],
    ) -> str:
        with open(self.PROMPT_PATH, "r", encoding="utf-8") as f:
            template = yaml.safe_load(f).get("prompt_template", "")

        block_analysis = chunk_analysis.get("block_analysis", {})

        # project_sound_palette: leitmotif dei personaggi definiti in Stage 0.5
        sound_palette = dossier.get("project_sound_palette", {})
        if sound_palette:
            palette_str = "\n".join(
                f"  - {cid} ({entry.get('character_name', '?')} [{entry.get('role_category', '?')}]):"
                f" {entry.get('musical_profile', '')[:120]}"
                for cid, entry in sound_palette.items()
            )
        else:
            palette_str = "(Nessun leitmotif definito per questo progetto)"

        return template.format(
            project_id=self.project_id,
            chunk_label=chunk_label,
            chosen_palette=dossier.get("chosen_palette", dossier.get("palette_choice", "Generica")),
            palette_proposals=json.dumps(proposals, indent=2, ensure_ascii=False),
            fingerprint_values=json.dumps(dossier.get("fingerprint_values", []), ensure_ascii=False),
            project_sound_palette=palette_str,
            primary_emotion=block_analysis.get("primary_emotion", "neutral"),
            secondary_emotion=block_analysis.get("secondary_emotion", ""),
            setting=block_analysis.get("setting", "unknown"),
            emotional_arc=block_analysis.get("emotional_arc", ""),
            summary=block_analysis.get("summary", ""),
            audio_cues=json.dumps(block_analysis.get("audio_cues", []), ensure_ascii=False),
            total_duration_s=int(total_duration_s),
            chunk_text=chunk_text[:6000],  # Limita a ~6000 chars per non saturare il contesto
        )

    # ─────────────────────────────────────────────────────────────
    # Core Processing
    # ─────────────────────────────────────────────────────────────

    def process_chunk(self, chunk_id: str) -> bool:
        chunk_label = f"chunk-{chunk_id}"
        self.logger.info(f"🎬 B2 Macro-Spotter v4 (Sound-on-Demand): Processing {chunk_label}...")
        self._log_trace(f"{'='*60}")
        self._log_trace(f"Inizio elaborazione {chunk_label}")

        # 1. Idempotency check
        output_label = f"{chunk_label}-macro-cue"
        if self.persistence.load_stage_output("b2", self.project_id, output_label):
            self.logger.info(f"⏭️  Skipping: MacroCue già su disco per {chunk_label}")
            return True

        # 2. Load inputs
        chunk_analysis = self._load_chunk_analysis(chunk_label)
        if not chunk_analysis:
            return False

        chunk_text = self._load_chunk_text(chunk_label)
        total_duration_s = self._get_chunk_total_duration(chunk_label)
        dossier = self._load_preproduction_dossier()
        proposals = self._load_palette_proposals()

        palette = dossier.get("chosen_palette", dossier.get("palette_choice", "?"))
        self._log_trace(f"Palette: {palette} | Durata capitolo: {int(total_duration_s)}s")

        # 3. Prepare prompt and call Gemini
        prompt = self._prepare_prompt(
            chunk_label, chunk_analysis, chunk_text, total_duration_s, dossier, proposals
        )
        job_id = f"b2-macro-{self.project_id}-{chunk_label}"

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
            self.logger.error(f"❌ Tutti i tentativi falliti per {chunk_label}.")
            return False

        # 4. Parse response
        response_text = response["output"].get("text", "")
        try:
            start = response_text.find("{")
            end = response_text.rfind("}") + 1
            result_json = json.loads(response_text[start:end])

            pad_raw = result_json.get("pad", {})

            # Build and validate PadArcSegment list
            arc_segments = []
            for seg in pad_raw.get("pad_arc", []):
                arc_segments.append(PadArcSegment(
                    start_s=float(seg.get("start_s", 0)),
                    end_s=float(seg.get("end_s", total_duration_s)),
                    intensity=seg.get("intensity", "mid"),
                    note=seg.get("note"),
                    roadmap_item=seg.get("roadmap_item"),
                ))

            # Validate with Pydantic (v4.1 — ACE-Step Ready)
            pad_request = PadRequest(
                canonical_id=pad_raw.get("canonical_id", "pad_unknown_01"),
                production_prompt=pad_raw.get("production_prompt", "Orchestral cinematic pad."),
                production_tags=pad_raw.get("production_tags", ""),
                negative_prompt=pad_raw.get("negative_prompt", "epic, cinematic, generic ai"),
                guidance_scale=float(pad_raw.get("guidance_scale", 4.5)),
                inference_steps=int(pad_raw.get("inference_steps", 60)),
                is_leitmotif=bool(pad_raw.get("is_leitmotif", False)),
                estimated_duration_s=total_duration_s,
                pad_arc=arc_segments,
            )
            macro_cue = MacroCue(
                project_id=self.project_id,
                chunk_label=chunk_label,
                pad=pad_request,
                music_justification=result_json.get("music_justification", ""),
            )

            # 5. Persist
            self.persistence.save_stage_output(
                "b2", macro_cue.model_dump(), self.project_id, output_label, include_timestamp=False
            )
            self.gemini_client.delete_callback_key(job_id)

            # 6. Trace
            leitmotif_flag = " [LEITMOTIF]" if pad_request.is_leitmotif else " [NUOVO]"
            self._log_trace(f"PAD assegnato{leitmotif_flag}: {pad_request.canonical_id}")
            self._log_trace(f"Arc: {[(s.intensity, f'{s.start_s}s-{s.end_s}s') for s in arc_segments]}")
            self._log_trace(f"Giustificazione: {macro_cue.music_justification[:200]}")

            self.logger.info(f"✅ MacroCue salvato: PAD={pad_request.canonical_id}")

        except Exception as e:
            self.logger.error(f"❌ Errore parsing/validazione MacroCue: {e}", exc_info=True)
            return False

        return True


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python stage_b2_macro.py <project_id> [chunk_id]")
        sys.exit(1)
    stage = StageB2Macro(sys.argv[1])
    stage.process_chunk(sys.argv[2] if len(sys.argv) > 2 else "000")
