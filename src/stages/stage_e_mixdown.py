#!/usr/bin/env python3
"""
Stage E — Mixdown Engine v1.0
==============================
Assembla la traccia audio finale di un capitolo mixando:
  - Voce (WAV per scena, da Stage D)
  - PAD musicale con stems Demucs (bass/drums/other, da Stage D2 via ARIA)
  - Leitmotif: firma musicale dei personaggi (da Stage D2, project_sound_palette)
  - AMB: ambience transitional (da Stage D2)
  - SFX: effetti puntuali (da Stage D2)
  - STING: accenti orchestrali (da Stage D2)

Principio fondamentale:
  La voce detta il tempo. Il timing assoluto di ogni elemento viene calcolato
  dalla MasterTimingGrid di Stage D (misure WAV reali, non stime testuali).

Output:
  stages/stage_e/output/{project_id}-chunk-{N}-master.wav
  stages/stage_e/output/{project_id}-chunk-{N}-mix-report.json
"""

import json
import sys
import wave
import array
import struct
import shutil
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime

import numpy as np
import soundfile as sf

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.common.persistence import DiasPersistence
from src.common.logging_setup import get_logger


# ─────────────────────────────────────────────────────────────────────────────
# Mix level constants (dB relative to voice at 0 dB)
# Target loudness: EBU R128 -23 LUFS (standard audiolibri/podcast)
# ─────────────────────────────────────────────────────────────────────────────

LEVEL_PAD_BASS  = -20.0   # Bass stem — sempre presente, fondamenta armoniche
LEVEL_PAD_DRUMS = -23.0   # Drums stem — baseline, duckato aggressivo durante voce
LEVEL_PAD_OTHER = -20.0   # Melody/harmony stem — baseline

LEVEL_AMB       = -28.0   # Ambience — quasi impercettibile, tessuto di sfondo
LEVEL_SFX       = -12.0   # SFX — puntuale e nitido
LEVEL_STING     = -6.0    # STING — impatto drammatico
LEVEL_LEITMOTIF = -10.0   # Leitmotif — sopra il PAD, sotto STING/SFX

# Duck amounts (dB aggiuntivi durante la voce, per stem)
DUCK_NONE   = 0.0
DUCK_LIGHT  = -8.0
DUCK_MEDIUM = -14.0
DUCK_HEAVY  = -20.0

DUCK_DEPTH_MAP = {
    "none":    DUCK_NONE,
    "light":   DUCK_LIGHT,
    "shallow": DUCK_LIGHT,   # alias LLM
    "medium":  DUCK_MEDIUM,
    "deep":    DUCK_HEAVY,   # alias LLM
    "heavy":   DUCK_HEAVY,
}

# Fade durations per pad_fade_speed (ms)
FADE_MS_MAP = {
    "instant": 30,
    "snap":    30,    # alias LLM
    "sharp":   60,
    "smooth":  180,
    "slow":    400,
}

# Stems Demucs (prodotti da ARIA HTDemucs)
DEMUCS_STEMS = ["bass", "drums", "other"]


# ─────────────────────────────────────────────────────────────────────────────
# Audio I/O utilities
# ─────────────────────────────────────────────────────────────────────────────

def _load_wav(path: Path) -> Tuple[np.ndarray, int]:
    """
    Carica WAV → (samples float32 [-1,1], sample_rate).
    Converte sempre in stereo. Ritorna array vuoto se il file non esiste.
    """
    if not path or not path.exists():
        return np.array([], dtype=np.float32), 0

    data, sr = sf.read(str(path), dtype="float32", always_2d=True)
    # Converti in stereo se mono
    if data.shape[1] == 1:
        data = np.repeat(data, 2, axis=1)
    return data, sr


def _save_wav(samples: np.ndarray, sr: int, path: Path) -> None:
    """Salva array float32 stereo come WAV 16-bit PCM."""
    path.parent.mkdir(parents=True, exist_ok=True)
    # Clamp per evitare clipping
    samples = np.clip(samples, -1.0, 1.0)
    sf.write(str(path), samples, sr, subtype="PCM_16")


def _db_to_linear(db: float) -> float:
    return 10.0 ** (db / 20.0)


def _ms_to_samples(ms: float, sr: int) -> int:
    return int(ms * sr / 1000.0)


def _seconds_to_samples(s: float, sr: int) -> int:
    return int(s * sr)


def _ensure_stereo_length(data: np.ndarray, n_samples: int) -> np.ndarray:
    """Assicura che data sia (n_samples, 2). Taglia o estende con silenzio."""
    if data.shape[0] == 0:
        return np.zeros((n_samples, 2), dtype=np.float32)
    if data.shape[0] < n_samples:
        pad = np.zeros((n_samples - data.shape[0], 2), dtype=np.float32)
        data = np.vstack([data, pad])
    return data[:n_samples]


def _apply_gain(data: np.ndarray, gain_db: float) -> np.ndarray:
    return data * _db_to_linear(gain_db)


def _apply_fade_in(data: np.ndarray, fade_samples: int) -> np.ndarray:
    """Fade-in lineare sui primi fade_samples campioni."""
    if fade_samples <= 0 or data.shape[0] == 0:
        return data
    n = min(fade_samples, data.shape[0])
    envelope = np.linspace(0.0, 1.0, n, dtype=np.float32)[:, np.newaxis]
    result = data.copy()
    result[:n] *= envelope
    return result


def _apply_fade_out(data: np.ndarray, fade_samples: int) -> np.ndarray:
    """Fade-out lineare sugli ultimi fade_samples campioni."""
    if fade_samples <= 0 or data.shape[0] == 0:
        return data
    n = min(fade_samples, data.shape[0])
    envelope = np.linspace(1.0, 0.0, n, dtype=np.float32)[:, np.newaxis]
    result = data.copy()
    result[-n:] *= envelope
    return result


def _overlay(canvas: np.ndarray, segment: np.ndarray, offset_samples: int) -> np.ndarray:
    """
    Sovrappone segment su canvas a partire da offset_samples.
    Non modifica canvas in-place — ritorna una copia.
    """
    if segment.shape[0] == 0:
        return canvas
    end = offset_samples + segment.shape[0]
    if end > canvas.shape[0]:
        extra = np.zeros((end - canvas.shape[0], 2), dtype=np.float32)
        canvas = np.vstack([canvas, extra])
    canvas = canvas.copy()
    canvas[offset_samples:end] += segment
    return canvas


# ─────────────────────────────────────────────────────────────────────────────
# Timeline builder
# ─────────────────────────────────────────────────────────────────────────────

def build_scene_timeline(
    macro_chunk_id: str,
    timing_grid: Dict,
    stage_d_dir: Path,
    project_id: str,
) -> List[Dict]:
    """
    Costruisce la timeline assoluta di ogni scena per un macro-chunk.

    Ogni elemento: {
        scene_id, t_start_s, t_end_s, voice_wav (Path|None),
        micro_chunk_id, t_start_ms (int), t_end_ms (int)
    }
    """
    macro_data = timing_grid.get("macro_chunks", {}).get(macro_chunk_id, {})
    micro_chunks = macro_data.get("micro_chunks", {})

    timeline = []
    for micro_id, micro_data in sorted(micro_chunks.items()):
        for scene in micro_data.get("scenes", []):
            scene_id  = scene["scene_id"]
            t_start_s = float(scene["start_offset"])
            t_end_s   = t_start_s + float(scene["total_scene_time"])

            # Cerca il WAV voce in Stage D output
            wav_name = f"{project_id}-{scene_id}.wav"
            voice_wav = stage_d_dir / wav_name
            if not voice_wav.exists():
                voice_wav = None

            timeline.append({
                "scene_id":      scene_id,
                "micro_chunk_id": micro_id,
                "t_start_s":     t_start_s,
                "t_end_s":       t_end_s,
                "voice_wav":     voice_wav,
                "voice_duration": float(scene.get("voice_duration", 0)),
                "pause_after":   float(scene.get("pause_after", 0)),
            })

    return sorted(timeline, key=lambda x: x["t_start_s"])


# ─────────────────────────────────────────────────────────────────────────────
# PAD track builder with ducking automation
# ─────────────────────────────────────────────────────────────────────────────

def build_pad_track(
    pad_stems: Dict[str, np.ndarray],
    timeline: List[Dict],
    scenes_automation_index: Dict[str, Dict],
    total_samples: int,
    sr: int,
) -> np.ndarray:
    """
    Costruisce la traccia PAD completa (bass + drums + other) con ducking per scena.
    Usa i 3 stem Demucs se disponibili, altrimenti il master PAD.

    Ducking: durante la voce di ogni scena, abbassa drums e other in base a
    pad_duck_depth dalla scenes_automation. Il bass è mai duckato — mantiene
    le fondamenta armoniche sempre udibili.
    """
    has_stems = all(k in pad_stems for k in DEMUCS_STEMS) and pad_stems["bass"].shape[0] > 0

    if has_stems:
        bass_src  = _ensure_stereo_length(pad_stems["bass"],  total_samples)
        drums_src = _ensure_stereo_length(pad_stems["drums"], total_samples)
        other_src = _ensure_stereo_length(pad_stems["other"], total_samples)
    else:
        # Fallback: usa il master PAD per tutti e tre i canali con guadagni diversi
        master = pad_stems.get("master", np.zeros((total_samples, 2), dtype=np.float32))
        bass_src  = _ensure_stereo_length(master, total_samples)
        drums_src = _ensure_stereo_length(master, total_samples)
        other_src = _ensure_stereo_length(master, total_samples)

    # Canvas per ogni stem
    bass_track  = _apply_gain(bass_src,  LEVEL_PAD_BASS)
    drums_track = _apply_gain(drums_src, LEVEL_PAD_DRUMS)
    other_track = _apply_gain(other_src, LEVEL_PAD_OTHER)

    # Applica ducking per ogni scena
    for scene in timeline:
        scene_id = scene["scene_id"]
        automation = scenes_automation_index.get(scene_id, {})
        duck_depth_str = automation.get("pad_duck_depth") or "medium"
        fade_speed_str = automation.get("pad_fade_speed") or "smooth"
        automation_type = automation.get("pad_volume_automation", "ducking")

        duck_db = DUCK_DEPTH_MAP.get(duck_depth_str, DUCK_MEDIUM)
        fade_ms = FADE_MS_MAP.get(fade_speed_str, 180)
        fade_n  = _ms_to_samples(fade_ms, sr)

        if automation_type == "none" or duck_db == 0.0:
            continue

        # Solo durante la voce (non il pause_after)
        t_start = scene["t_start_s"]
        t_end   = scene["t_start_s"] + scene["voice_duration"]
        s_start = _seconds_to_samples(t_start, sr)
        s_end   = _seconds_to_samples(t_end, sr)

        if s_start >= total_samples or s_end <= s_start:
            continue
        s_end = min(s_end, total_samples)
        n = s_end - s_start

        # Crea maschera di gain: fade-in → duck → fade-out
        gain_curve = np.ones(n, dtype=np.float32) * _db_to_linear(duck_db)
        if fade_n > 0 and n > fade_n * 2:
            ramp_in  = np.linspace(1.0, _db_to_linear(duck_db), min(fade_n, n // 3))
            ramp_out = np.linspace(_db_to_linear(duck_db), 1.0, min(fade_n, n // 3))
            gain_curve[:len(ramp_in)]  = ramp_in
            gain_curve[-len(ramp_out):] = ramp_out
        elif fade_n > 0:
            gain_curve = np.linspace(1.0, _db_to_linear(duck_db), n)

        gain_stereo = gain_curve[:, np.newaxis]

        # Applica a drums e other (non a bass)
        drums_track[s_start:s_end] *= gain_stereo
        other_track[s_start:s_end] *= gain_stereo

    return bass_track + drums_track + other_track


# ─────────────────────────────────────────────────────────────────────────────
# Main Stage E class
# ─────────────────────────────────────────────────────────────────────────────

class StageEMixdown:

    TARGET_SR = 48000  # Sample rate standard per output

    def __init__(self, project_id: str):
        self.project_id = DiasPersistence.normalize_id(project_id)
        self.persistence = DiasPersistence(project_id=self.project_id)
        self.logger = get_logger("stage_e")

        self.stage_d_dir  = self.persistence.project_root / "stages" / "stage_d"  / "output"
        self.stage_b2_dir = self.persistence.project_root / "stages" / "stage_b2" / "output"
        self.stage_d2_dir = self.persistence.project_root / "stages" / "stage_d2"
        self.output_dir   = self.persistence.project_root / "stages" / "stage_e"  / "output"
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.timing_grid = self._load_timing_grid()
        self.d2_manifest = self._load_d2_manifest()

    # ─────────────────────────────────────────────────────────────────────────
    # Loaders
    # ─────────────────────────────────────────────────────────────────────────

    def _load_timing_grid(self) -> Dict:
        path = self.persistence.project_root / "stages" / "stage_d" / "master_timing_grid.json"
        if not path.exists():
            self.logger.error(f"❌ MasterTimingGrid non trovata: {path}")
            return {}
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    def _load_d2_manifest(self) -> Dict:
        """Carica il manifest D2. Supporta sia manifest.json che d2_dry_run_payloads.json."""
        manifest_path = self.stage_d2_dir / "manifest.json"
        if manifest_path.exists():
            with open(manifest_path, encoding="utf-8") as f:
                return json.load(f)
        # Fallback: costruisce un indice dai dry_run payloads
        dry_run = self.stage_d2_dir / "d2_dry_run_payloads.json"
        if dry_run.exists():
            with open(dry_run, encoding="utf-8") as f:
                payloads = json.load(f)
            # Index by canonical_id
            return {"assets": {p["canonical_id"]: {"type": p["type"]} for p in payloads}}
        return {"assets": {}}

    def _load_macro_cue(self, chunk_label: str) -> Dict:
        fname = f"{self.project_id}-{chunk_label}-macro-cue.json"
        path  = self.stage_b2_dir / fname
        if not path.exists():
            self.logger.error(f"❌ MacroCue non trovato: {path}")
            return {}
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    def _load_micro_cues(self, chunk_label: str) -> List[Dict]:
        """Carica tutti i micro-cue (IntegratedCueSheet) per un macro-chunk, in ordine."""
        pattern = f"{self.project_id}-{chunk_label}-micro-*-micro-cue.json"
        files   = sorted(self.stage_b2_dir.glob(pattern))
        cues    = []
        for f in files:
            with open(f, encoding="utf-8") as fp:
                cues.append(json.load(fp))
        return cues

    def _load_pad_stems(self, canonical_id: str) -> Dict[str, np.ndarray]:
        """
        Carica il master PAD e gli stem Demucs (se disponibili).
        Ritorna dict {master, bass, drums, other} → np.ndarray float32 stereo.
        """
        assets_dir = self.stage_d2_dir / "assets"
        stems: Dict[str, np.ndarray] = {}

        # Master WAV
        master_path = assets_dir / "pad" / f"{canonical_id}.wav"
        if master_path.exists():
            data, sr = _load_wav(master_path)
            stems["master"] = data
            stems["_sr"] = sr
        else:
            self.logger.warning(f"⚠  PAD master non trovato: {master_path}")
            stems["master"] = np.array([], dtype=np.float32)
            stems["_sr"] = self.TARGET_SR

        # Stem WAV (prodotti da ARIA HTDemucs)
        for stem_name in DEMUCS_STEMS:
            stem_path = assets_dir / "pad" / "stems" / canonical_id / f"{stem_name}.wav"
            if not stem_path.exists():
                # Prova path alternativo flat
                stem_path = assets_dir / "pad" / f"{canonical_id}_{stem_name}.wav"
            if stem_path.exists():
                data, _ = _load_wav(stem_path)
                stems[stem_name] = data
            else:
                stems[stem_name] = np.array([], dtype=np.float32)

        return stems

    def _get_asset_path(self, canonical_id: str, asset_type: str) -> Optional[Path]:
        """Trova il file WAV locale di un asset D2 (AMB/SFX/STING/PAD)."""
        assets_dir = self.stage_d2_dir / "assets"
        candidates = [
            assets_dir / asset_type / f"{canonical_id}.wav",
            assets_dir / asset_type / f"{canonical_id}" / f"{canonical_id}.wav",
        ]
        for p in candidates:
            if p.exists():
                return p
        return None

    # ─────────────────────────────────────────────────────────────────────────
    # Layer builders — ognuno ritorna (canvas np.ndarray, stats dict)
    # ─────────────────────────────────────────────────────────────────────────

    def _layer_voice(
        self, timeline: List[Dict], total_samples: int, sr: int
    ) -> Tuple[np.ndarray, Dict]:
        canvas = np.zeros((total_samples, 2), dtype=np.float32)
        ok, miss = 0, 0
        for scene in timeline:
            if not scene["voice_wav"]:
                miss += 1
                continue
            data, _ = _load_wav(scene["voice_wav"])
            if data.shape[0] == 0:
                miss += 1
                continue
            canvas = _overlay(canvas, data, _seconds_to_samples(scene["t_start_s"], sr))
            ok += 1
        self.logger.info(f"   [voice]  {ok} scene overlay ({miss} mancanti)")
        return canvas, {"voice_overlay": ok, "voice_missing": miss}

    def _layer_music(
        self,
        pad_stems: Dict,
        timeline: List[Dict],
        scenes_auto_index: Dict,
        total_samples: int,
        sr: int,
        with_ducking: bool,
    ) -> Tuple[np.ndarray, Dict]:
        auto = scenes_auto_index if with_ducking else {}
        canvas = build_pad_track(pad_stems, timeline, auto, total_samples, sr)
        has_stems = any(pad_stems.get(s, np.array([])).shape[0] > 0 for s in DEMUCS_STEMS)
        self.logger.info(f"   [music]  stems={'✓' if has_stems else '✗ (master)'} ducking={'on' if with_ducking else 'off'}")
        return canvas, {"stems_used": has_stems}

    def _layer_fx(
        self,
        timeline: List[Dict],
        scenes_auto_index: Dict,
        total_samples: int,
        sr: int,
    ) -> Tuple[np.ndarray, Dict]:
        canvas = np.zeros((total_samples, 2), dtype=np.float32)
        count = {"amb": 0, "sfx": 0, "sting": 0}

        for scene in timeline:
            scene_id   = scene["scene_id"]
            automation = scenes_auto_index.get(scene_id, {})
            t_scene    = scene["t_start_s"]
            voice_dur  = scene["voice_duration"]

            amb_id = automation.get("amb_id")
            if amb_id:
                p = self._get_asset_path(amb_id, "amb")
                if p:
                    data, _ = _load_wav(p)
                    t = t_scene + float(automation.get("amb_offset_s", 0))
                    canvas = _overlay(canvas, _apply_gain(data, LEVEL_AMB),
                                      _seconds_to_samples(t, sr))
                    count["amb"] += 1
                else:
                    self.logger.warning(f"   ⚠  AMB '{amb_id}' non trovato")

            sfx_id = automation.get("sfx_id")
            if sfx_id:
                p = self._get_asset_path(sfx_id, "sfx")
                if p:
                    data, _ = _load_wav(p)
                    timing = automation.get("sfx_timing", "middle")
                    if timing == "middle":
                        t_base = t_scene + voice_dur / 2.0
                    elif timing == "end":
                        t_base = t_scene + voice_dur - data.shape[0] / sr
                    else:
                        t_base = t_scene
                    t = max(0.0, t_base + float(automation.get("sfx_offset_s", 0)))
                    canvas = _overlay(canvas, _apply_gain(data, LEVEL_SFX),
                                      _seconds_to_samples(t, sr))
                    count["sfx"] += 1
                else:
                    self.logger.warning(f"   ⚠  SFX '{sfx_id}' non trovato")

            sting_id = automation.get("sting_id")
            if sting_id:
                p = self._get_asset_path(sting_id, "sting")
                if p:
                    data, _ = _load_wav(p)
                    timing = automation.get("sting_timing", "end")
                    if timing == "end":
                        t_base = t_scene + voice_dur
                    elif timing == "middle":
                        t_base = t_scene + voice_dur / 2.0
                    else:
                        t_base = t_scene
                    canvas = _overlay(canvas, _apply_gain(data, LEVEL_STING),
                                      _seconds_to_samples(max(0.0, t_base), sr))
                    count["sting"] += 1
                else:
                    self.logger.warning(f"   ⚠  STING '{sting_id}' non trovato")

        self.logger.info(
            f"   [fx]     AMB={count['amb']} SFX={count['sfx']} STING={count['sting']}"
        )
        return canvas, {"events": count}

    def _layer_leitmotif(
        self,
        micro_cues: List[Dict],
        timeline: List[Dict],
        total_samples: int,
        sr: int,
    ) -> Tuple[np.ndarray, Dict]:
        """
        Mixa i leitmotif dei personaggi (non-diegetici, sopra il PAD).
        Ogni evento in leitmotif_events specifica scena + timing + canonical_id.
        Il WAV viene cercato in assets/leitmotif/{canonical_id}.wav (prodotto da D2).
        Livello: LEVEL_LEITMOTIF (-10 dB) — udibile senza sovrastare la voce.
        """
        canvas = np.zeros((total_samples, 2), dtype=np.float32)

        # Indice scene: scene_id → t_start_s, voice_duration
        scene_timing: Dict[str, Dict] = {
            s["scene_id"]: s for s in timeline
        }

        # Raccoglie tutti gli eventi leitmotif dai micro-cue del chunk
        events: List[Dict] = []
        for mc in micro_cues:
            for evt in mc.get("leitmotif_events", []):
                events.append(evt)

        count = 0
        for evt in events:
            leitmotif_id = evt.get("leitmotif_id", "")
            scene_id     = evt.get("scene_id", "")
            timing       = evt.get("timing", "start")

            if not leitmotif_id or not scene_id:
                continue

            p = self._get_asset_path(leitmotif_id, "leitmotif")
            if not p:
                self.logger.warning(f"   ⚠  Leitmotif '{leitmotif_id}' non trovato in assets/leitmotif/")
                continue

            scene = scene_timing.get(scene_id)
            if not scene:
                self.logger.warning(f"   ⚠  Scena '{scene_id}' non in timeline, skip leitmotif")
                continue

            data, _ = _load_wav(p)
            if data.shape[0] == 0:
                continue

            t_scene    = scene["t_start_s"]
            voice_dur  = scene["voice_duration"]
            leitmotif_dur = data.shape[0] / sr

            if timing == "end":
                # Centra il leitmotif verso la fine della scena vocale
                t = max(0.0, t_scene + voice_dur - leitmotif_dur * 0.5)
            elif timing == "middle":
                t = t_scene + voice_dur * 0.5
            else:  # "start"
                t = t_scene

            canvas = _overlay(
                canvas,
                _apply_gain(data, LEVEL_LEITMOTIF),
                _seconds_to_samples(t, sr),
            )
            count += 1
            self.logger.debug(
                f"   [leitmotif] {leitmotif_id} → scena {scene_id} @{t:.1f}s ({timing})"
            )

        self.logger.info(f"   [leitmotif] {count} eventi mixati")
        return canvas, {"leitmotif_events": count}

    # ─────────────────────────────────────────────────────────────────────────
    # Render — entry point unico
    # ─────────────────────────────────────────────────────────────────────────

    # Mappa mode → suffisso file output
    _MODE_SUFFIX = {
        "voice":    "-voice.wav",
        "music":    "-music.wav",
        "music+fx": "-music-fx.wav",
        "full":     "-master.wav",
    }
    # Quali layer include ogni mode (voice, music, fx)
    # Per music e music+fx il ducking è OFF — la voce non c'è, si sente il PAD pieno
    _MODE_LAYERS = {
        "voice":    (True,  False, False),
        "music":    (False, True,  False),
        "music+fx": (False, True,  True),
        "full":     (True,  True,  True),
    }

    def render(self, chunk_id: str, mode: str = "full") -> bool:
        """
        Esegue il render per un chunk nel mode specificato.
        mode: "voice" | "music" | "music+fx" | "full" | "all"
        "all" esegue tutti e 4 i mode in sequenza.
        """
        if mode == "all":
            return all(self.render(chunk_id, m) for m in self._MODE_SUFFIX)

        if mode not in self._MODE_SUFFIX:
            self.logger.error(f"❌ Mode non valido: '{mode}'. Validi: {list(self._MODE_SUFFIX)}")
            return False

        chunk_label = f"chunk-{chunk_id}"
        suffix      = self._MODE_SUFFIX[mode]
        output_wav  = self.output_dir / f"{self.project_id}-{chunk_label}{suffix}"
        want_voice, want_music, want_fx = self._MODE_LAYERS[mode]

        self.logger.info(f"🎚  Stage E [{mode}] — {chunk_label}")

        if output_wav.exists():
            self.logger.info(f"⏭️  Skipping: {output_wav.name} già presente")
            return True

        # Validazioni comuni
        if not self.timing_grid:
            self.logger.error("❌ MasterTimingGrid vuota")
            return False
        macro_data = self.timing_grid.get("macro_chunks", {}).get(chunk_label)
        if not macro_data:
            self.logger.error(f"❌ Chunk '{chunk_label}' non in timing grid")
            return False
        total_duration_s = float(macro_data.get("duration", 0))
        if total_duration_s <= 0:
            self.logger.error(f"❌ Durata nulla per {chunk_label}")
            return False

        timeline = build_scene_timeline(
            chunk_label, self.timing_grid, self.stage_d_dir, self.project_id
        )
        self.logger.info(f"   Timeline: {len(timeline)} scene, {total_duration_s:.1f}s")

        # PAD — necessario solo se want_music
        pad_stems = {}
        pad_canonical = ""
        if want_music:
            macro_cue = self._load_macro_cue(chunk_label)
            pad_canonical = (
                macro_cue.get("pad", {}).get("canonical_id")
                or macro_cue.get("pad_canonical_id")
                or ""
            )
            if not pad_canonical:
                self.logger.error(f"❌ Nessun PAD canonical_id in MacroCue per {chunk_label}")
                return False
            pad_stems = self._load_pad_stems(pad_canonical)
            has_master = pad_stems.get("master", np.array([])).shape[0] > 0
            has_stems  = any(pad_stems.get(s, np.array([])).shape[0] > 0 for s in DEMUCS_STEMS)
            if not has_master and not has_stems:
                self.logger.error(f"❌ Nessun audio PAD per {pad_canonical}")
                return False

        # Automation index — necessario se want_fx o (want_music e want_voice per ducking)
        micro_cues: List[Dict] = []
        scenes_auto_index: Dict[str, Dict] = {}
        if want_fx or (want_music and want_voice):
            micro_cues = self._load_micro_cues(chunk_label)
            for mc in micro_cues:
                for sa in mc.get("scenes_automation", []):
                    scenes_auto_index[sa["scene_id"]] = sa
            if not micro_cues:
                self.logger.warning("⚠  Nessun micro-cue — FX e ducking disabilitati")

        # SR — preferenza: PAD > primo voice WAV > default
        sr = pad_stems.get("_sr", 0) or self.TARGET_SR
        if sr == self.TARGET_SR and want_voice:
            for scene in timeline:
                if scene["voice_wav"]:
                    _, detected = _load_wav(scene["voice_wav"])
                    if detected > 0:
                        sr = detected
                        break

        total_samples = _seconds_to_samples(total_duration_s, sr)
        canvas = np.zeros((total_samples, 2), dtype=np.float32)
        stats: Dict[str, Any] = {}

        if want_music:
            # Ducking attivo solo quando c'è anche la voce nel mix
            mus, s = self._layer_music(pad_stems, timeline, scenes_auto_index,
                                       total_samples, sr, with_ducking=want_voice)
            canvas += mus
            stats.update(s)

        if want_voice:
            voc, s = self._layer_voice(timeline, total_samples, sr)
            canvas += voc
            stats.update(s)

        if want_fx:
            fx, s = self._layer_fx(timeline, scenes_auto_index, total_samples, sr)
            canvas += fx
            stats.update(s)

            # Leitmotif: non-diegetico, mixato insieme ai FX in tutti i mode con FX
            if micro_cues:
                lm, s = self._layer_leitmotif(micro_cues, timeline, total_samples, sr)
                canvas += lm
                stats.update(s)

        # Normalizzazione peak
        peak = np.max(np.abs(canvas))
        target_db = -1.0 if mode == "voice" else -3.0
        if peak > 0:
            canvas = canvas * (_db_to_linear(target_db) / peak)
            self.logger.info(f"   Norm: {20*np.log10(peak):.1f} dBFS → {target_db} dBFS")

        _save_wav(canvas, sr, output_wav)
        actual_dur = canvas.shape[0] / sr
        self.logger.info(f"✅ Salvato: {output_wav.name} ({actual_dur:.2f}s)")

        report = {
            "project_id":      self.project_id,
            "chunk_label":     chunk_label,
            "mode":            mode,
            "output_wav":      str(output_wav),
            "duration_s":      actual_dur,
            "sample_rate":     sr,
            "pad_canonical_id": pad_canonical,
            "scene_count":     len(timeline),
            "timestamp":       datetime.now().isoformat(),
            **stats,
        }
        report_path = self.output_dir / f"{self.project_id}-{chunk_label}-{mode.replace('+', '-')}-report.json"
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)

        return True

    # Alias per retrocompatibilità con script esistenti
    def process_chunk(self, chunk_id: str) -> bool:
        return self.render(chunk_id, mode="full")

    def export_voice_track(self, chunk_id: str) -> bool:
        return self.render(chunk_id, mode="voice")


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse as _ap
    p = _ap.ArgumentParser()
    p.add_argument("project_id")
    p.add_argument("--chunk", default="000")
    p.add_argument("--mode",  default="full",
                   choices=list(StageEMixdown._MODE_SUFFIX) + ["all"])
    a = p.parse_args()
    stage = StageEMixdown(a.project_id)
    sys.exit(0 if stage.render(a.chunk, a.mode) else 1)
