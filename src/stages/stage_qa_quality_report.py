#!/usr/bin/env python3
"""
DIAS — Stage QA: Quality Report
================================
Analisi tecnica e semantica degli asset prodotti da Stage D2, Stage D (voce)
e Stage E (mix). Riutilizzabile per ogni produzione.

Uso:
    python -m src.stages.stage_qa_quality_report <project_id> [--chunk 000]

Output:
    stages/stage_qa/qa_report.json
    stages/stage_qa/qa_report_human.md
"""

import json
import sys
import argparse
import warnings
from pathlib import Path
from datetime import datetime

import numpy as np
import soundfile as sf
import librosa

warnings.filterwarnings("ignore")

# ── Soglie per i flag ─────────────────────────────────────────────────────────
THRESHOLDS = {
    "clipping_samples":    10,       # campioni >= 0.99 prima di flaggare
    "silence_ratio_max":   0.40,     # max 40% silenzio accettabile
    "rms_min_db":         -40.0,     # sotto = asset troppo silenzioso
    "peak_max_db":         -0.1,     # sopra = rischio clipping
    "duration_tolerance":   0.20,    # ±20% della durata richiesta
    "voice_rms_min_db":   -35.0,     # voce: RMS minimo accettabile
    "voice_silence_max":    0.35,    # voce: silenzio max 35%
}

ASSET_EXPECTED_RMS = {              # range RMS target per tipo (dBFS)
    "amb":       (-30, -18),
    "sfx":       (-25, -10),
    "sting":     (-22, -10),
    "pad":       (-28, -12),
    "leitmotif": (-28, -12),
    "voice":     (-28, -10),
    "mix":       (-10,  -2),
}

# ── Analisi audio ─────────────────────────────────────────────────────────────

def analyze_audio(path: Path, asset_type: str = "generic", requested_duration: float = None) -> dict:
    """Analisi tecnica completa di un file WAV. Ritorna un dict con metriche e flag."""
    result = {
        "path": str(path),
        "exists": path.exists(),
        "flags": [],
        "metrics": {},
    }

    if not path.exists():
        result["flags"].append("🔴 FILE_MISSING")
        return result

    try:
        data, sr = sf.read(str(path), dtype="float32", always_2d=True)
    except Exception as e:
        result["flags"].append(f"🔴 READ_ERROR: {e}")
        return result

    # data: (samples, channels)
    mono = data.mean(axis=1)
    duration = len(mono) / sr

    # RMS
    rms_linear = np.sqrt(np.mean(mono ** 2)) if len(mono) > 0 else 1e-10
    rms_db = float(20 * np.log10(max(rms_linear, 1e-10)))

    # Peak
    peak = float(np.max(np.abs(mono)))
    peak_db = float(20 * np.log10(max(peak, 1e-10)))

    # Clipping
    clipping_samples = int(np.sum(np.abs(mono) >= 0.99))

    # Silence ratio (frames sotto -60 dBFS)
    frame_len = 2048
    hop_len = 512
    rms_frames = librosa.feature.rms(y=mono, frame_length=frame_len, hop_length=hop_len)[0]
    rms_frames_db = 20 * np.log10(np.maximum(rms_frames, 1e-10))
    silence_ratio = float(np.mean(rms_frames_db < -60.0))

    # Spectral centroid (media pesata delle frequenze)
    spec_centroid = float(np.mean(librosa.feature.spectral_centroid(y=mono, sr=sr)))

    # Spectral rolloff (freq sotto cui cade l'85% dell'energia)
    spec_rolloff = float(np.mean(librosa.feature.spectral_rolloff(y=mono, sr=sr, roll_percent=0.85)))

    # Zero Crossing Rate (tonalità vs rumore)
    zcr = float(np.mean(librosa.feature.zero_crossing_rate(y=mono)))

    result["metrics"] = {
        "duration_s":        round(duration, 2),
        "sample_rate":       sr,
        "channels":          data.shape[1],
        "rms_db":            round(rms_db, 1),
        "peak_db":           round(peak_db, 1),
        "clipping_samples":  clipping_samples,
        "silence_ratio":     round(silence_ratio, 3),
        "spectral_centroid_hz": round(spec_centroid, 0),
        "spectral_rolloff_hz":  round(spec_rolloff, 0),
        "zero_crossing_rate":   round(zcr, 4),
    }

    # Metriche extra per asset musicali (leitmotif, pad, sting)
    if asset_type in ("leitmotif", "pad", "sting"):
        chroma = librosa.feature.chroma_stft(y=mono, sr=sr)
        chroma_var = float(np.mean(np.var(chroma, axis=1)))
        result["metrics"]["chroma_variance"] = round(chroma_var, 4)

    # Onset strength per SFX (deve avere un attacco netto)
    if asset_type == "sfx":
        onset_env = librosa.onset.onset_strength(y=mono, sr=sr)
        result["metrics"]["onset_strength_max"] = round(float(np.max(onset_env)), 2)
        result["metrics"]["onset_strength_mean"] = round(float(np.mean(onset_env)), 2)

    # ── Flag ─────────────────────────────────────────────────────────────────
    if clipping_samples > THRESHOLDS["clipping_samples"]:
        result["flags"].append(f"🔴 CLIPPING ({clipping_samples} campioni)")

    if silence_ratio > THRESHOLDS["silence_ratio_max"]:
        result["flags"].append(f"🟡 SILENZIO_ECCESSIVO ({silence_ratio:.0%})")

    if rms_db < THRESHOLDS["rms_min_db"]:
        result["flags"].append(f"🟡 RMS_BASSO ({rms_db:.1f} dBFS)")

    if peak_db > THRESHOLDS["peak_max_db"]:
        result["flags"].append(f"🔴 PEAK_ALTO ({peak_db:.1f} dBFS)")

    if requested_duration is not None:
        tol = requested_duration * THRESHOLDS["duration_tolerance"]
        if abs(duration - requested_duration) > max(tol, 0.5):
            result["flags"].append(
                f"🟡 DURATA ({duration:.1f}s vs {requested_duration:.1f}s richiesti)"
            )

    # RMS fuori range atteso per il tipo
    if asset_type in ASSET_EXPECTED_RMS:
        lo, hi = ASSET_EXPECTED_RMS[asset_type]
        if rms_db < lo:
            result["flags"].append(f"🟡 RMS_SOTTO_TARGET (target {lo}→{hi} dBFS)")
        elif rms_db > hi:
            result["flags"].append(f"🟡 RMS_SOPRA_TARGET (target {lo}→{hi} dBFS)")

    # SFX senza attacco
    if asset_type == "sfx" and result["metrics"].get("onset_strength_max", 0) < 5.0:
        result["flags"].append("🟡 ATTACCO_DEBOLE (SFX senza transiente chiaro)")

    # Leitmotif senza varietà melodica
    if asset_type == "leitmotif" and result["metrics"].get("chroma_variance", 1) < 0.005:
        result["flags"].append("🟡 MELODIA_PIATTA (chroma variance bassa)")

    if not result["flags"]:
        result["flags"].append("✅ OK")

    return result


# ── Caricamento dati ──────────────────────────────────────────────────────────

def load_prompts(project_root: Path) -> dict:
    """Carica i prompt usati per la generazione da d2_dry_run_payloads.json."""
    p = project_root / "stages" / "stage_d2" / "d2_dry_run_payloads.json"
    if not p.exists():
        return {}
    data = json.loads(p.read_text())
    prompts = {}
    for item in data:
        cid = item["canonical_id"]
        payload = item["redis_task"]["payload"]
        prompts[cid] = {
            "type":     item["type"],
            "prompt":   payload.get("prompt") or payload.get("tags", ""),
            "duration": payload.get("duration"),
            "model_id": item["redis_task"].get("model_id"),
        }
    return prompts


def load_d2_manifest(project_root: Path) -> dict:
    """Carica il manifest D2 con i path degli asset."""
    p = project_root / "stages" / "stage_d2" / "manifest.json"
    if not p.exists():
        return {}
    return json.loads(p.read_text()).get("assets", {})


def load_leitmotif_assets(project_root: Path) -> dict:
    """Trova i WAV dei leitmotif in stage_d2/assets/leitmotif/."""
    lm_dir = project_root / "stages" / "stage_d2" / "assets" / "leitmotif"
    result = {}
    if lm_dir.exists():
        for wav in lm_dir.glob("*.wav"):
            cid = wav.stem
            result[cid] = {"type": "leitmotif", "master_path": str(wav)}
    return result


def load_voice_scenes(project_root: Path, chunk: str) -> list:
    """Carica le scene vocali prodotte da Stage D."""
    stage_d = project_root / "stages" / "stage_d" / "output"
    scenes = []
    if not stage_d.exists():
        return scenes
    for json_file in sorted(stage_d.glob(f"*{chunk}*.json")):
        wav_file = json_file.with_suffix(".wav")
        try:
            meta = json.loads(json_file.read_text())
        except Exception:
            continue
        scenes.append({
            "scene_id":   meta.get("scene_id", json_file.stem),
            "speaker":    meta.get("speaker", "?"),
            "emotion":    meta.get("primary_emotion", "?"),
            "text":       str(meta.get("text_content", ""))[:80],
            "wav_path":   wav_file if wav_file.exists() else None,
            "estimated_duration": meta.get("timing_estimate", {}).get("estimated_duration_seconds"),
            "word_count": meta.get("word_count", 0),
            "tts_backend": meta.get("tts_backend", "?"),
        })
    return scenes


def load_mix_outputs(project_root: Path, chunk: str) -> dict:
    """Trova i WAV di Stage E."""
    stage_e = project_root / "stages" / "stage_e" / "output"
    result = {}
    if not stage_e.exists():
        return result
    for wav in stage_e.glob(f"*{chunk}*.wav"):
        name = wav.stem
        if "master" in name:
            result["master"] = wav
        elif "music-fx" in name:
            result["music_fx"] = wav
        elif "music" in name:
            result["music"] = wav
        elif "voice" in name:
            result["voice"] = wav
    return result


# ── Report ────────────────────────────────────────────────────────────────────

def run_qa(project_id: str, chunk: str) -> dict:
    base = Path(__file__).parent.parent.parent
    project_root = base / "data" / "projects" / project_id

    print(f"\n🔍 QA Report — {project_id} | chunk-{chunk}")
    print("=" * 70)

    report = {
        "project_id": project_id,
        "chunk": chunk,
        "generated_at": datetime.now().isoformat(),
        "assets": {},
        "voice_scenes": [],
        "mix": {},
        "summary": {},
    }

    prompts   = load_prompts(project_root)
    d2_assets = load_d2_manifest(project_root)
    leitmotifs = load_leitmotif_assets(project_root)

    # Merge manifest + leitmotif (manifest non include leitmotif)
    all_assets = {**d2_assets, **leitmotifs}

    # ── Asset D2 (AMB/SFX/STING/PAD/Leitmotif) ───────────────────────────────
    print(f"\n{'─'*70}")
    print("ASSET MUSICALI / SONORI (Stage D2)")
    print(f"{'─'*70}")

    flags_total = 0
    critical_total = 0

    for cid, asset_meta in sorted(all_assets.items(), key=lambda x: (x[1].get("type",""), x[0])):
        atype = asset_meta.get("type", "generic")
        master_path = Path(asset_meta.get("master_path", ""))

        prompt_info = prompts.get(cid, {})
        requested_duration = prompt_info.get("duration")

        analysis = analyze_audio(master_path, asset_type=atype, requested_duration=requested_duration)
        analysis["canonical_id"] = cid
        analysis["prompt"] = prompt_info.get("prompt", "")
        analysis["model_id"] = prompt_info.get("model_id", "")

        report["assets"][cid] = analysis

        m = analysis["metrics"]
        flags = analysis["flags"]
        n_red = sum(1 for f in flags if "🔴" in f)
        n_yel = sum(1 for f in flags if "🟡" in f)
        flags_total += n_red + n_yel
        critical_total += n_red

        status = "🔴" if n_red else ("🟡" if n_yel else "✅")
        print(f"\n[{atype.upper():8s}] {cid}")
        if m:
            print(f"  Durata: {m.get('duration_s','?')}s | RMS: {m.get('rms_db','?')} dBFS | "
                  f"Peak: {m.get('peak_db','?')} dBFS | Silence: {m.get('silence_ratio',0):.0%}")
            print(f"  Spectral centroid: {m.get('spectral_centroid_hz','?')} Hz | "
                  f"ZCR: {m.get('zero_crossing_rate','?')}")
            if atype in ("leitmotif", "pad", "sting"):
                print(f"  Chroma variance: {m.get('chroma_variance','?')}")
            if atype == "sfx":
                print(f"  Onset strength: max={m.get('onset_strength_max','?')} "
                      f"mean={m.get('onset_strength_mean','?')}")
        for f in flags:
            print(f"  {f}")
        if analysis.get("prompt"):
            print(f"  Prompt: {analysis['prompt'][:80]}")

        # PAD: verifica stem
        if atype == "pad":
            stems_dir = master_path.parent / "stems" / cid
            stem_names = ["bass", "drums", "guitar", "other", "piano", "vocals"]
            stems_ok = [s for s in stem_names if (stems_dir / f"{s}.wav").exists()]
            stems_missing = [s for s in stem_names if s not in stems_ok]
            analysis["stems"] = {"present": stems_ok, "missing": stems_missing}
            if stems_missing:
                print(f"  🟡 STEM_MANCANTI: {stems_missing}")
            else:
                print(f"  ✅ Stem: {stems_ok}")

    # ── Voce (Stage D) ────────────────────────────────────────────────────────
    print(f"\n{'─'*70}")
    print("TRACCIA VOCALE (Stage D)")
    print(f"{'─'*70}")

    voice_scenes = load_voice_scenes(project_root, chunk)
    scenes_ok = 0
    scenes_missing = 0
    voice_rms_list = []

    for scene in voice_scenes:
        wav_path = scene.get("wav_path")
        if wav_path is None:
            scenes_missing += 1
            analysis = {"flags": ["🔴 WAV_MISSING"], "metrics": {}}
        else:
            analysis = analyze_audio(
                Path(wav_path), asset_type="voice",
                requested_duration=scene.get("estimated_duration")
            )
            if analysis["metrics"].get("rms_db"):
                voice_rms_list.append(analysis["metrics"]["rms_db"])
            scenes_ok += 1

        scene_report = {**scene, "analysis": analysis}
        scene_report["wav_path"] = str(wav_path) if wav_path else None
        report["voice_scenes"].append(scene_report)

        flags = analysis["flags"]
        n_red = sum(1 for f in flags if "🔴" in f)
        n_yel = sum(1 for f in flags if "🟡" in f)
        flags_total += n_red + n_yel
        critical_total += n_red

        if n_red or n_yel:
            m = analysis["metrics"]
            status = "🔴" if n_red else "🟡"
            print(f"  {status} {scene['scene_id']} | {scene['speaker']} | {scene['emotion']}")
            print(f"     testo: {scene['text'][:60]}")
            for f in flags:
                if "✅" not in f:
                    print(f"     {f}")

    print(f"\n  Scene vocali: {scenes_ok}/{len(voice_scenes)} WAV presenti | "
          f"{scenes_missing} mancanti")
    if voice_rms_list:
        print(f"  RMS voce: media={np.mean(voice_rms_list):.1f} dBFS | "
              f"min={np.min(voice_rms_list):.1f} | max={np.max(voice_rms_list):.1f}")

    # ── Mix Stage E ───────────────────────────────────────────────────────────
    print(f"\n{'─'*70}")
    print("MIX FINALE (Stage E)")
    print(f"{'─'*70}")

    mix_outputs = load_mix_outputs(project_root, chunk)
    for mix_name, mix_path in mix_outputs.items():
        analysis = analyze_audio(mix_path, asset_type="mix")
        report["mix"][mix_name] = analysis
        m = analysis["metrics"]
        flags = analysis["flags"]
        print(f"\n  [{mix_name.upper()}] {mix_path.name}")
        if m:
            print(f"  Durata: {m.get('duration_s','?')}s | RMS: {m.get('rms_db','?')} dBFS | "
                  f"Peak: {m.get('peak_db','?')} dBFS")
        for f in flags:
            print(f"  {f}")

    # ── Summary ───────────────────────────────────────────────────────────────
    report["summary"] = {
        "assets_analyzed":   len(all_assets),
        "voice_scenes_ok":   scenes_ok,
        "voice_scenes_missing": scenes_missing,
        "voice_scenes_total": len(voice_scenes),
        "total_flags":       flags_total,
        "critical_flags":    critical_total,
        "clap_available":    False,
        "clap_note":         "msclap non installato — CLAP score non disponibile",
    }

    print(f"\n{'═'*70}")
    print("SUMMARY")
    print(f"  Asset analizzati:    {len(all_assets)}")
    print(f"  Scene vocali:        {scenes_ok}/{len(voice_scenes)} ok")
    print(f"  Flag totali:         {flags_total} ({critical_total} critici 🔴)")
    print(f"  CLAP score:          non disponibile (pip install msclap torch)")
    print(f"{'═'*70}\n")

    # ── Salvataggio ───────────────────────────────────────────────────────────
    qa_dir = project_root / "stages" / "stage_qa"
    qa_dir.mkdir(parents=True, exist_ok=True)

    json_out = qa_dir / f"qa_report_chunk-{chunk}.json"
    json_out.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str))
    print(f"💾 Report JSON: {json_out}")

    md_out = qa_dir / f"qa_report_chunk-{chunk}.md"
    _write_markdown(report, md_out)
    print(f"💾 Report MD:   {md_out}\n")

    return report


def _write_markdown(report: dict, path: Path):
    lines = [
        f"# QA Report — chunk-{report['chunk']}",
        f"**Progetto**: {report['project_id']}  ",
        f"**Generato**: {report['generated_at']}",
        "",
        "## Asset Musicali / Sonori",
        "",
        "| Asset | Tipo | Durata | RMS (dBFS) | Peak | Silence | Flag |",
        "|---|---|---|---|---|---|---|",
    ]
    for cid, a in report["assets"].items():
        m = a.get("metrics", {})
        flags_str = " ".join(a.get("flags", []))
        atype = report["assets"][cid].get("type", cid.split("_")[0] if "_" in cid else "?")
        # Try to get type from asset meta
        lines.append(
            f"| {cid} | {m.get('duration_s','?')}s | {m.get('rms_db','?')} | "
            f"{m.get('peak_db','?')} | {m.get('silence_ratio',0):.0%} | {flags_str} |"
        )

    lines += ["", "## Traccia Vocale", ""]
    missing = [s for s in report["voice_scenes"] if s["analysis"]["flags"] == ["🔴 WAV_MISSING"]]
    problems = [s for s in report["voice_scenes"] if any("🔴" in f or "🟡" in f
                for f in s["analysis"]["flags"]) and "WAV_MISSING" not in str(s["analysis"]["flags"])]

    if missing:
        lines.append(f"**Scene mancanti ({len(missing)}):**")
        for s in missing:
            lines.append(f"- {s['scene_id']} | {s['speaker']} | {s['text'][:60]}")
        lines.append("")
    if problems:
        lines.append(f"**Scene con problemi ({len(problems)}):**")
        for s in problems:
            flags_str = " ".join(s["analysis"]["flags"])
            lines.append(f"- {s['scene_id']} | {s['speaker']} | {flags_str}")
        lines.append("")

    s = report["summary"]
    lines += [
        "## Summary",
        f"- Asset analizzati: {s['assets_analyzed']}",
        f"- Scene vocali ok: {s['voice_scenes_ok']}/{s['voice_scenes_total']}",
        f"- Flag totali: {s['total_flags']} ({s['critical_flags']} critici)",
        f"- CLAP: {s['clap_note']}",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="DIAS Stage QA — Quality Report")
    parser.add_argument("project_id", help="ID del progetto")
    parser.add_argument("--chunk", default="000", help="Chunk label (default: 000)")
    args = parser.parse_args()
    run_qa(args.project_id, args.chunk)
