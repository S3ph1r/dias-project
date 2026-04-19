#!/usr/bin/env python3
"""
Stage 0.5 — Theme Factory
==========================
Genera il profilo musicale (leitmotif) per ogni personaggio principale del progetto.

Cosa fa:
  - Legge characters_dossier e palette_choice da preproduction.json
  - Per ogni personaggio primary (e secondary se richiesto):
      chiama Gemini con profilo narrativo + palette artistica
      ottiene: musical_profile, generation_prompt, tags, seed, duration
  - Scrive project_sound_palette in preproduction.json

Cosa NON fa:
  - NON chiama ARIA, NON produce WAV
  - La produzione dei WAV base è responsabilità di Stage D2

La produzione ARIA dei leitmotif avviene in Stage D2, che legge project_sound_palette
e inserisce i leitmotif_creation nella shopping list prima dei PAD.
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


PROMPT_PATH = Path(__file__).parent.parent.parent / "config/prompts/stage_0_5/leitmotif_prompt_v1.0.yaml"

# Quali categorie di personaggio ricevono un leitmotif
LEITMOTIF_ROLES = {"primary", "secondary"}


class Stage05ThemeFactory:

    def __init__(self, project_id: str, include_secondary: bool = True):
        self.project_id = DiasPersistence.normalize_id(project_id)
        self.config     = get_config()
        self.redis      = get_redis_client()
        self.persistence = DiasPersistence(project_id=self.project_id)
        self.logger     = get_logger("stage_0_5")
        self.gemini     = GatewayClient(redis_client=self.redis, client_id="dias")
        self.model_name = self.config.google.model_flash_lite

        self.include_secondary = include_secondary
        self.preproduction_path = self.persistence.get_preproduction_path()

        prompt_data = yaml.safe_load(PROMPT_PATH.read_text(encoding="utf-8"))
        self.prompt_template = prompt_data["prompt_template"]

    # ─────────────────────────────────────────────────────────────
    # Loaders
    # ─────────────────────────────────────────────────────────────

    def _load_preproduction(self) -> Dict:
        if not self.preproduction_path or not self.preproduction_path.exists():
            self.logger.error(f"❌ preproduction.json non trovato: {self.preproduction_path}")
            return {}
        with open(self.preproduction_path, encoding="utf-8") as f:
            return json.load(f)

    def _save_preproduction(self, data: Dict) -> None:
        with open(self.preproduction_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def _select_characters(self, characters: List[Dict]) -> List[Dict]:
        roles = {"primary"} | ({"secondary"} if self.include_secondary else set())
        return [c for c in characters if c.get("role_category") in roles]

    # ─────────────────────────────────────────────────────────────
    # Prompt builder
    # ─────────────────────────────────────────────────────────────

    def _build_prompt(self, character: Dict, palette_choice: str, theatrical_standard: Any) -> str:
        ts_str = ""
        if isinstance(theatrical_standard, dict):
            ts_str = theatrical_standard.get("instruct", str(theatrical_standard))
        elif isinstance(theatrical_standard, str):
            ts_str = theatrical_standard

        return (
            self.prompt_template
            .replace("{palette_choice}", palette_choice)
            .replace("{theatrical_standard}", ts_str[:500])
            .replace("{character_name}", character.get("name", "Unknown"))
            .replace("{character_role}", character.get("role_description", ""))
            .replace("{character_traits}", character.get("traits", ""))
            .replace("{character_vocal_profile}", character.get("vocal_profile", ""))
        )

    # ─────────────────────────────────────────────────────────────
    # Gemini call
    # ─────────────────────────────────────────────────────────────

    def _call_gemini(self, prompt: str, job_id: str) -> Optional[Dict]:
        for attempt in range(3):
            self.logger.info(f"   Tentativo {attempt+1}/3 → Gemini ({self.model_name})")
            response = self.gemini.generate_content(
                contents=[{"role": "user", "parts": [{"text": prompt}]}],
                model_id=self.model_name,
                job_id=job_id,
            )
            if response["status"] != "error":
                break
            error_msg = response.get("error", "")
            if "503" in str(error_msg) or "429" in str(error_msg):
                self.logger.warning(f"   ⚠  Gemini 503/429, attesa 70s...")
                time.sleep(70)
                self.gemini.delete_callback_key(job_id)
            else:
                self.logger.error(f"   ❌ Errore Gemini: {error_msg}")
                return None

        if not response or response["status"] == "error":
            return None

        text = response["output"].get("text", "")
        self.gemini.delete_callback_key(job_id)
        try:
            start = text.find("{")
            end   = text.rfind("}") + 1
            return json.loads(text[start:end])
        except (json.JSONDecodeError, ValueError) as e:
            self.logger.error(f"   ❌ Parse JSON fallito: {e}\n   Raw: {text[:300]}")
            return None

    # ─────────────────────────────────────────────────────────────
    # Per-character processing
    # ─────────────────────────────────────────────────────────────

    def _process_character(
        self,
        character: Dict,
        palette_choice: str,
        theatrical_standard: Any,
    ) -> Optional[Dict]:
        name     = character.get("name", "unknown")
        role_cat = character.get("role_category", "primary")
        safe_name = name.lower().replace(" ", "_").replace("'", "").replace(".", "")
        canonical_id = f"leitmotif_{safe_name}_base"

        self.logger.info(f"   [{role_cat}] {name} → {canonical_id}")

        prompt = self._build_prompt(character, palette_choice, theatrical_standard)
        job_id = f"theme-factory-{self.project_id}-{safe_name}"

        result = self._call_gemini(prompt, job_id)
        if not result:
            self.logger.warning(f"   ⚠  {name}: nessun risultato Gemini, skip")
            return None

        entry = {
            "canonical_id":     canonical_id,
            "character_id":     safe_name,
            "character_name":   name,
            "role_category":    role_cat,
            "musical_profile":  result.get("musical_profile", ""),
            "generation_prompt": result.get("generation_prompt", ""),
            "generation_tags":  result.get("generation_tags", ""),
            "negative_prompt":  result.get("negative_prompt", ""),
            "duration_s":       int(result.get("duration_s", 24)),
            "seed":             int(result.get("seed", 42)),
            "guidance_scale":   float(result.get("guidance_scale", 7.0)),
            "inference_steps":  int(result.get("inference_steps", 60)),
            "local_wav":        None,   # popolato da D2 dopo produzione ARIA
            "aria_url":         None,   # popolato da D2 dopo produzione ARIA
            "generated_at":     None,
            "created_at":       datetime.now().isoformat(),
        }

        self.logger.info(f"   ✅ {name}: '{result.get('musical_profile','')[:80]}...'")
        return entry

    # ─────────────────────────────────────────────────────────────
    # Main
    # ─────────────────────────────────────────────────────────────

    def run(self, force: bool = False) -> bool:
        self.logger.info(f"🎼 Stage 0.5 Theme Factory — {self.project_id}")

        preproduction = self._load_preproduction()
        if not preproduction:
            return False

        # Idempotency
        if not force and preproduction.get("project_sound_palette"):
            existing = preproduction["project_sound_palette"]
            self.logger.info(
                f"⏭️  project_sound_palette già presente ({len(existing)} temi). "
                "Usa --force per rigenerare."
            )
            return True

        palette_choice      = preproduction.get("palette_choice", "")
        theatrical_standard = preproduction.get("theatrical_standard", {})
        characters          = preproduction.get("characters_dossier", [])

        if not palette_choice:
            self.logger.error("❌ palette_choice mancante in preproduction.json")
            return False
        if not characters:
            self.logger.error("❌ characters_dossier vuoto in preproduction.json")
            return False

        selected = self._select_characters(characters)
        self.logger.info(
            f"   Personaggi selezionati: {len(selected)} "
            f"({'primary+secondary' if self.include_secondary else 'primary only'})"
        )
        self.logger.info(f"   Palette: {palette_choice}")

        palette: Dict[str, Dict] = {}
        for character in selected:
            entry = self._process_character(character, palette_choice, theatrical_standard)
            if entry:
                palette[entry["canonical_id"]] = entry
            # Breve pausa tra chiamate Gemini
            time.sleep(3)

        if not palette:
            self.logger.error("❌ Nessun leitmotif generato.")
            return False

        # Salva in preproduction.json
        preproduction["project_sound_palette"] = palette
        self._save_preproduction(preproduction)

        self.logger.info(
            f"\n✅ project_sound_palette salvato: {len(palette)} leitmotif\n"
            + "\n".join(
                f"   {cid}: {e['musical_profile'][:70]}..."
                for cid, e in palette.items()
            )
        )
        return True


# ─────────────────────────────────────────────────────────────────────────────
# CLI diretto
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("project_id")
    p.add_argument("--no-secondary", action="store_true",
                   help="Genera leitmotif solo per personaggi primary")
    p.add_argument("--force", action="store_true",
                   help="Rigenera anche se project_sound_palette esiste già")
    a = p.parse_args()
    stage = Stage05ThemeFactory(a.project_id, include_secondary=not a.no_secondary)
    sys.exit(0 if stage.run(force=a.force) else 1)
