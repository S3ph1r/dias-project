#!/usr/bin/env python3
"""
Runner Stage E — Mixdown Engine

Esegue il mixdown per uno o più macro-chunk di un progetto DIAS.
Legge il MasterTimingGrid di Stage D, i MacroCue/MicroCue di Stage B2
e gli asset audio di Stage D2 per produrre il master WAV finale.

Flags:
  --chunk CHUNK_ID   Processa solo questo chunk (es. "000"). Default: tutti.
  --cleanup          Cancella output Stage E esistenti prima di partire.
  --dry-run          Verifica che tutti i file di input siano presenti senza mixare.
"""

import sys
import json
import shutil
import argparse
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.common.persistence import DiasPersistence
from src.stages.stage_e_mixdown import StageEMixdown


# ─────────────────────────────────────────────────────────────────────────────
# Chunk discovery
# ─────────────────────────────────────────────────────────────────────────────

def discover_chunks(persistence: DiasPersistence) -> list:
    """Ritorna la lista ordinata di chunk_id (es. ['000', '001']) dalla timing grid."""
    grid_path = persistence.project_root / "stages" / "stage_d" / "master_timing_grid.json"
    if not grid_path.exists():
        print(f"❌ MasterTimingGrid non trovata: {grid_path}")
        return []
    with open(grid_path, encoding="utf-8") as f:
        grid = json.load(f)
    chunks = sorted(grid.get("macro_chunks", {}).keys())
    # Estrae solo l'ID numerico: "chunk-000" → "000"
    return [c.replace("chunk-", "") for c in chunks]


# ─────────────────────────────────────────────────────────────────────────────
# Dry-run: verifica prerequisiti
# ─────────────────────────────────────────────────────────────────────────────

def dry_run_check(project_id: str, chunk_ids: list) -> bool:
    persistence = DiasPersistence(project_id=project_id)
    project_root = persistence.project_root
    stage_b2_out = project_root / "stages" / "stage_b2" / "output"
    stage_d_out  = project_root / "stages" / "stage_d"  / "output"
    stage_d2_dir = project_root / "stages" / "stage_d2"

    print(f"\n🔍 Dry-run check per {len(chunk_ids)} chunk...")
    all_ok = True

    for chunk_id in chunk_ids:
        chunk_label = f"chunk-{chunk_id}"
        print(f"\n  ── {chunk_label} ──")

        # MasterTimingGrid (già verificata in discover_chunks)
        grid_path = project_root / "stages" / "stage_d" / "master_timing_grid.json"
        _check(grid_path, "MasterTimingGrid")

        # MacroCue
        macro_cue = stage_b2_out / f"{project_id}-{chunk_label}-macro-cue.json"
        ok = _check(macro_cue, "MacroCue")
        all_ok = all_ok and ok

        # PAD asset
        if macro_cue.exists():
            with open(macro_cue, encoding="utf-8") as f:
                mc = json.load(f)
            pad_id = mc.get("pad", {}).get("canonical_id") or mc.get("pad_canonical_id", "")
            if pad_id:
                pad_wav = stage_d2_dir / "assets" / "pad" / f"{pad_id}.wav"
                # Prova anche il path con subdirectory
                if not pad_wav.exists():
                    pad_wav = stage_d2_dir / "assets" / "pad" / pad_id / f"{pad_id}.wav"
                ok = _check(pad_wav, f"PAD WAV [{pad_id}]")
                all_ok = all_ok and ok

                # Stems Demucs (opzionali — warning, non errore)
                for stem in ("bass", "drums", "other"):
                    stem_path = stage_d2_dir / "assets" / "pad" / "stems" / pad_id / f"{stem}.wav"
                    if stem_path.exists():
                        print(f"    ✅  Stem {stem}: {stem_path.name}")
                    else:
                        print(f"    ⚠   Stem {stem} assente — verrà usato master PAD come fallback")
            else:
                print("    ❌  pad.canonical_id mancante nel MacroCue")
                all_ok = False

        # MicroCue files
        micro_files = sorted(stage_b2_out.glob(f"{project_id}-{chunk_label}-micro-*-micro-cue.json"))
        if micro_files:
            print(f"    ✅  MicroCue: {len(micro_files)} file trovati")
        else:
            print(f"    ⚠   Nessun MicroCue trovato — duck automation disabilitata")

        # Voice WAV (controlla solo che Stage D output esista)
        if stage_d_out.exists():
            voice_files = list(stage_d_out.glob(f"{project_id}-scene-*.wav"))
            print(f"    {'✅' if voice_files else '⚠ '}  Voice WAV: {len(voice_files)} file in Stage D output")
        else:
            print(f"    ⚠   Stage D output dir non trovata: {stage_d_out}")

    return all_ok


def _check(path: Path, label: str) -> bool:
    if path.exists():
        size = path.stat().st_size
        size_str = f"{size / 1024 / 1024:.1f} MB" if size > 1024 * 1024 else f"{size / 1024:.1f} KB"
        print(f"    ✅  {label}: {path.name} ({size_str})")
        return True
    else:
        print(f"    ❌  {label}: NON TROVATO — {path}")
        return False


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="DIAS Stage E — Mixdown Engine")
    parser.add_argument("project_id",           help="ID del progetto")
    parser.add_argument("--chunk",              metavar="CHUNK_ID",
                        help="Processa solo questo chunk (es. '000'). Default: tutti.")
    parser.add_argument("--cleanup",            action="store_true",
                        help="Cancella output Stage E esistenti prima di partire")
    parser.add_argument("--dry-run",            action="store_true",
                        help="Verifica prerequisiti senza mixare")
    parser.add_argument("--mode",               default="full",
                        choices=["voice", "music", "music+fx", "full", "all"],
                        help=(
                            "voice    = voce + pause (no musica)\n"
                            "music    = solo PAD musicale (no effetti, no voce)\n"
                            "music+fx = PAD + AMB/SFX/STING (no voce)\n"
                            "full     = mix completo [default]\n"
                            "all      = produce tutti e 4 i file separati"
                        ))
    args = parser.parse_args()

    project_id = DiasPersistence.normalize_id(args.project_id)
    persistence = DiasPersistence(project_id=project_id)

    print(f"\n🎚  Stage E Mixdown Engine — {project_id}")
    print(f"    Project root: {persistence.project_root}")

    # Scopri chunk
    if args.chunk:
        chunk_ids = [args.chunk.zfill(3)]
    else:
        chunk_ids = discover_chunks(persistence)

    if not chunk_ids:
        print("❌ Nessun chunk trovato. Verificare Stage D output.")
        sys.exit(1)

    print(f"    Chunk da processare: {chunk_ids}")

    # Dry-run
    if args.dry_run:
        ok = dry_run_check(project_id, chunk_ids)
        print(f"\n{'✅ Tutti i prerequisiti OK.' if ok else '❌ Prerequisiti mancanti — correggere prima di eseguire.'}")
        sys.exit(0 if ok else 1)

    # Cleanup
    output_dir = persistence.project_root / "stages" / "stage_e" / "output"
    if args.cleanup and output_dir.exists():
        shutil.rmtree(output_dir)
        print(f"🧹 Cleanup Stage E output: {output_dir}")

    # Esecuzione
    stage = StageEMixdown(project_id)
    results = {}
    start_total = datetime.now()

    mode_labels = {
        "voice":    "VOICE EXPORT",
        "music":    "MUSIC EXPORT",
        "music+fx": "MUSIC + FX EXPORT",
        "full":     "FULL MIXDOWN",
        "all":      "ALL STEMS (4 file per chunk)",
    }
    print(f"\n{'─'*55}")
    print(f"🎚  {mode_labels.get(args.mode, args.mode.upper())}")
    print(f"{'─'*55}")

    for chunk_id in chunk_ids:
        chunk_label = f"chunk-{chunk_id}"
        print(f"\n  ▶ {chunk_label}...")
        t0 = datetime.now()
        ok = stage.render(chunk_id, args.mode)
        elapsed = (datetime.now() - t0).total_seconds()
        results[chunk_label] = {"ok": ok, "elapsed_s": round(elapsed, 1)}

        if ok:
            print(f"  ✅ {chunk_label} completato in {elapsed:.1f}s")
        else:
            print(f"  ❌ {chunk_label} FALLITO dopo {elapsed:.1f}s")

    # Riepilogo
    total_elapsed = (datetime.now() - start_total).total_seconds()
    n_ok    = sum(1 for r in results.values() if r["ok"])
    n_fail  = len(results) - n_ok

    print(f"\n{'─'*55}")
    print(f"📊 RIEPILOGO STAGE E")
    print(f"{'─'*55}")
    for label, r in results.items():
        status = "✅" if r["ok"] else "❌"
        print(f"  {status}  {label}  ({r['elapsed_s']}s)")
    print(f"\n  Completati: {n_ok}/{len(results)}  |  Totale: {total_elapsed:.1f}s")

    if n_ok > 0:
        out_dir = persistence.project_root / "stages" / "stage_e" / "output"
        print(f"\n  Output: {out_dir}")
        for f in sorted(out_dir.glob("*-master.wav")):
            size_mb = f.stat().st_size / 1024 / 1024
            print(f"    🎵 {f.name}  ({size_mb:.1f} MB)")

    if n_fail > 0:
        print(f"\n👉 {n_fail} chunk falliti — controllare i log di Stage E.")
        sys.exit(1)

    print(f"\n👉 Prossimo step: verifica ascolto e mastering finale.")


if __name__ == "__main__":
    main()
