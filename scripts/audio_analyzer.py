#!/usr/bin/env python3
"""
DIAS Audio Analyzer — ElevenLabs vs Qwen3-TTS Comparative Report
================================================================
Produces a full acoustic comparison between two WAV files:
  • Pitch Contour (F0)
  • Energy RMS
  • Pause Distribution
  • Spectral Centroid
  • MFCCs similarity

Usage:
    python3 scripts/audio_analyzer.py \
        --el  analysis/el_vs_qwen3/EL_reference.wav \
        --dias analysis/el_vs_qwen3/DIAS_comparison.wav \
        --out  analysis/el_vs_qwen3/report/

Output:
    analysis/el_vs_qwen3/report/
        ├── 01_waveform.png
        ├── 02_pitch_contour.png
        ├── 03_energy_rms.png
        ├── 04_spectrogram.png
        ├── 05_spectral_centroid.png
        ├── 06_mfcc_heatmap.png
        └── summary.txt
"""

import argparse
import sys
from pathlib import Path

import numpy as np
import librosa
import librosa.display
import matplotlib
matplotlib.use("Agg")  # headless rendering
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import soundfile as sf
from scipy.stats import pearsonr

# --- Palette ---
COLOR_EL   = "#00C896"   # ElevenLabs — verde acqua
COLOR_DIAS = "#FF7043"   # DIAS/Qwen3 — arancio caldo


def load(path: Path, target_sr: int = 22050):
    """Load WAV and return (y, sr)."""
    y, sr = librosa.load(str(path), sr=target_sr, mono=True)
    print(f"  ✓ Loaded '{path.name}' | duration={len(y)/sr:.1f}s | sr={sr}")
    return y, sr


def plot_waveform(y_el, y_dias, sr, out_dir):
    t_el   = np.linspace(0, len(y_el)   / sr, len(y_el))
    t_dias = np.linspace(0, len(y_dias) / sr, len(y_dias))

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 5), sharex=False)
    fig.suptitle("Waveform Comparison", fontsize=13, fontweight="bold")
    ax1.plot(t_el,   y_el,   color=COLOR_EL,   linewidth=0.4, alpha=0.8)
    ax1.set_title("ElevenLabs Reference")
    ax1.set_ylabel("Amplitude")
    ax2.plot(t_dias, y_dias, color=COLOR_DIAS, linewidth=0.4, alpha=0.8)
    ax2.set_title("DIAS / Qwen3-TTS")
    ax2.set_ylabel("Amplitude")
    ax2.set_xlabel("Time (s)")
    plt.tight_layout()
    fig.savefig(out_dir / "01_waveform.png", dpi=150)
    plt.close(fig)
    print("  ✓ 01_waveform.png")


def pitch_stats(y, sr):
    """Extract fundamental frequency using pyin."""
    f0, voiced_flag, _ = librosa.pyin(
        y, fmin=librosa.note_to_hz("C2"), fmax=librosa.note_to_hz("C7"), sr=sr
    )
    f0_voiced = f0[voiced_flag]
    if len(f0_voiced) == 0:
        return f0, {"mean": 0, "std": 0, "range": 0, "voiced_ratio": 0.0}
    stats = {
        "mean":          float(np.nanmean(f0_voiced)),
        "std":           float(np.nanstd(f0_voiced)),
        "range":         float(np.nanmax(f0_voiced) - np.nanmin(f0_voiced)),
        "voiced_ratio":  float(np.sum(voiced_flag) / len(voiced_flag)),
    }
    return f0, stats


def plot_pitch(y_el, y_dias, sr, out_dir):
    f0_el,   s_el   = pitch_stats(y_el,   sr)
    f0_dias, s_dias = pitch_stats(y_dias, sr)

    t_el   = librosa.times_like(f0_el,   sr=sr)
    t_dias = librosa.times_like(f0_dias, sr=sr)

    fig, axes = plt.subplots(2, 1, figsize=(14, 6), sharex=False)
    fig.suptitle("Pitch Contour (F0) Comparison", fontsize=13, fontweight="bold")

    for ax, t, f0, color, label, stats in [
        (axes[0], t_el,   f0_el,   COLOR_EL,   "ElevenLabs", s_el),
        (axes[1], t_dias, f0_dias, COLOR_DIAS, "DIAS/Qwen3", s_dias),
    ]:
        ax.plot(t, f0, color=color, linewidth=0.8, alpha=0.9, label=label)
        ax.axhline(stats["mean"], color=color, linestyle="--", linewidth=1, alpha=0.6,
                   label=f"Mean={stats['mean']:.0f}Hz")
        ax.set_title(f"{label} | mean={stats['mean']:.0f}Hz | std={stats['std']:.0f}Hz "
                     f"| range={stats['range']:.0f}Hz | voiced={stats['voiced_ratio']*100:.1f}%")
        ax.set_ylabel("Hz")
        ax.legend(fontsize=8)
        ax.set_ylim(0, 400)

    axes[1].set_xlabel("Time (s)")
    plt.tight_layout()
    fig.savefig(out_dir / "02_pitch_contour.png", dpi=150)
    plt.close(fig)
    print("  ✓ 02_pitch_contour.png")
    return s_el, s_dias


def rms_stats(y, sr, frame_length=2048, hop_length=512):
    rms = librosa.feature.rms(y=y, frame_length=frame_length, hop_length=hop_length)[0]
    t   = librosa.times_like(rms, sr=sr, hop_length=hop_length)
    return t, rms, {
        "mean": float(np.mean(rms)),
        "std":  float(np.std(rms)),
        "max":  float(np.max(rms)),
        "dynamic_range_db": float(20 * np.log10(np.max(rms) / (np.mean(rms) + 1e-8))),
    }


def plot_energy(y_el, y_dias, sr, out_dir):
    t_el,   rms_el,   s_el   = rms_stats(y_el,   sr)
    t_dias, rms_dias, s_dias = rms_stats(y_dias, sr)

    fig, axes = plt.subplots(2, 1, figsize=(14, 5), sharex=False)
    fig.suptitle("Energy (RMS) Comparison", fontsize=13, fontweight="bold")

    for ax, t, rms, color, label, stats in [
        (axes[0], t_el,   rms_el,   COLOR_EL,   "ElevenLabs", s_el),
        (axes[1], t_dias, rms_dias, COLOR_DIAS, "DIAS/Qwen3", s_dias),
    ]:
        ax.plot(t, rms, color=color, linewidth=0.8)
        ax.fill_between(t, 0, rms, alpha=0.3, color=color)
        ax.set_title(f"{label} | mean={stats['mean']:.4f} | std={stats['std']:.4f} "
                     f"| dynamic_range={stats['dynamic_range_db']:.1f}dB")
        ax.set_ylabel("RMS")

    axes[1].set_xlabel("Time (s)")
    plt.tight_layout()
    fig.savefig(out_dir / "03_energy_rms.png", dpi=150)
    plt.close(fig)
    print("  ✓ 03_energy_rms.png")
    return s_el, s_dias


def plot_spectrogram(y_el, y_dias, sr, out_dir):
    fig, axes = plt.subplots(1, 2, figsize=(16, 5))
    fig.suptitle("Log-Mel Spectrogram Comparison", fontsize=13, fontweight="bold")

    for ax, y, color, label in [
        (axes[0], y_el,   COLOR_EL,   "ElevenLabs"),
        (axes[1], y_dias, COLOR_DIAS, "DIAS/Qwen3"),
    ]:
        S = librosa.feature.melspectrogram(y=y, sr=sr, n_mels=128, fmax=8000)
        S_dB = librosa.power_to_db(S, ref=np.max)
        img = librosa.display.specshow(S_dB, sr=sr, x_axis="time", y_axis="mel",
                                       fmax=8000, ax=ax, cmap="magma")
        ax.set_title(label)
        fig.colorbar(img, ax=ax, format="%+2.0f dB")

    plt.tight_layout()
    fig.savefig(out_dir / "04_spectrogram.png", dpi=150)
    plt.close(fig)
    print("  ✓ 04_spectrogram.png")


def centroid_stats(y, sr):
    sc = librosa.feature.spectral_centroid(y=y, sr=sr)[0]
    t  = librosa.times_like(sc, sr=sr)
    return t, sc, {
        "mean": float(np.mean(sc)),
        "std":  float(np.std(sc)),
    }


def plot_centroid(y_el, y_dias, sr, out_dir):
    t_el,   sc_el,   s_el   = centroid_stats(y_el,   sr)
    t_dias, sc_dias, s_dias = centroid_stats(y_dias, sr)

    fig, axes = plt.subplots(2, 1, figsize=(14, 5), sharex=False)
    fig.suptitle("Spectral Centroid (\"Brightness\") Comparison", fontsize=13, fontweight="bold")

    for ax, t, sc, color, label, stats in [
        (axes[0], t_el,   sc_el,   COLOR_EL,   "ElevenLabs", s_el),
        (axes[1], t_dias, sc_dias, COLOR_DIAS, "DIAS/Qwen3", s_dias),
    ]:
        ax.plot(t, sc, color=color, linewidth=0.7)
        ax.set_title(f"{label} | mean={stats['mean']:.0f}Hz | std={stats['std']:.0f}Hz")
        ax.set_ylabel("Hz")

    axes[1].set_xlabel("Time (s)")
    plt.tight_layout()
    fig.savefig(out_dir / "05_spectral_centroid.png", dpi=150)
    plt.close(fig)
    print("  ✓ 05_spectral_centroid.png")
    return s_el, s_dias


def mfcc_similarity(y_el, y_dias, sr, out_dir, n_mfcc=13):
    """Compute per-coefficient mean MFCCs and Pearson correlation."""
    m_el   = librosa.feature.mfcc(y=y_el,   sr=sr, n_mfcc=n_mfcc)
    m_dias = librosa.feature.mfcc(y=y_dias, sr=sr, n_mfcc=n_mfcc)

    mean_el   = np.mean(m_el,   axis=1)
    mean_dias = np.mean(m_dias, axis=1)

    corr, _ = pearsonr(mean_el, mean_dias)

    fig, ax = plt.subplots(figsize=(10, 4))
    x = np.arange(n_mfcc)
    width = 0.35
    ax.bar(x - width/2, mean_el,   width, label="ElevenLabs", color=COLOR_EL,   alpha=0.85)
    ax.bar(x + width/2, mean_dias, width, label="DIAS/Qwen3", color=COLOR_DIAS, alpha=0.85)
    ax.set_xticks(x)
    ax.set_xticklabels([f"MFCC-{i+1}" for i in range(n_mfcc)], rotation=45, ha="right")
    ax.set_title(f"MFCC Mean Coefficients | Pearson r = {corr:.3f}", fontsize=13, fontweight="bold")
    ax.set_ylabel("Mean Coefficient Value")
    ax.legend()
    plt.tight_layout()
    fig.savefig(out_dir / "06_mfcc_heatmap.png", dpi=150)
    plt.close(fig)
    print(f"  ✓ 06_mfcc_heatmap.png  (Pearson r={corr:.3f})")
    return float(corr), mean_el.tolist(), mean_dias.tolist()


def detect_pauses(y, sr, top_db=30):
    """Return list of (start_s, end_s, duration_s) for detected silent intervals."""
    intervals = librosa.effects.split(y, top_db=top_db)
    pauses = []
    for i in range(len(intervals) - 1):
        gap_start = intervals[i][1]   / sr
        gap_end   = intervals[i+1][0] / sr
        dur = gap_end - gap_start
        if dur > 0.05:
            pauses.append((gap_start, gap_end, dur))
    return pauses


def write_summary(out_dir, el_path, dias_path, p_el, p_dias,
                  rms_el, rms_dias, sc_el, sc_dias,
                  mfcc_corr, pauses_el, pauses_dias):
    lines = [
        "=" * 65,
        "  DIAS Audio Analyzer — Comparative Summary Report",
        "=" * 65,
        f"  EL  : {el_path}",
        f"  DIAS: {dias_path}",
        "",
        "─── PITCH (F0) ─────────────────────────────────────────────",
        f"  EL   | mean={p_el['mean']:.0f}Hz  std={p_el['std']:.0f}Hz  "
        f"range={p_el['range']:.0f}Hz  voiced={p_el['voiced_ratio']*100:.1f}%",
        f"  DIAS | mean={p_dias['mean']:.0f}Hz  std={p_dias['std']:.0f}Hz  "
        f"range={p_dias['range']:.0f}Hz  voiced={p_dias['voiced_ratio']*100:.1f}%",
        "",
        "─── ENERGY (RMS) ────────────────────────────────────────────",
        f"  EL   | mean={rms_el['mean']:.4f}  std={rms_el['std']:.4f}  "
        f"dynamic_range={rms_el['dynamic_range_db']:.1f}dB",
        f"  DIAS | mean={rms_dias['mean']:.4f}  std={rms_dias['std']:.4f}  "
        f"dynamic_range={rms_dias['dynamic_range_db']:.1f}dB",
        "",
        "─── SPECTRAL CENTROID (Brightness) ──────────────────────────",
        f"  EL   | mean={sc_el['mean']:.0f}Hz  std={sc_el['std']:.0f}Hz",
        f"  DIAS | mean={sc_dias['mean']:.0f}Hz  std={sc_dias['std']:.0f}Hz",
        "",
        "─── MFCC SIMILARITY ─────────────────────────────────────────",
        f"  Pearson correlation (mean MFCCs): {mfcc_corr:.3f}",
        "  (1.0 = identical timbral profile, 0 = completely different)",
        "",
        "─── PAUSE DISTRIBUTION ──────────────────────────────────────",
        f"  EL   | {len(pauses_el)} pauses | "
        f"avg={np.mean([d for *_, d in pauses_el]):.2f}s | "
        f"max={max((d for *_, d in pauses_el), default=0):.2f}s" if pauses_el else
        f"  EL   | no pauses detected",
        f"  DIAS | {len(pauses_dias)} pauses | "
        f"avg={np.mean([d for *_, d in pauses_dias]):.2f}s | "
        f"max={max((d for *_, d in pauses_dias), default=0):.2f}s" if pauses_dias else
        f"  DIAS | no pauses detected",
        "",
        "─── INTERPRETATION GUIDE ────────────────────────────────────",
        "  Pitch std     >> EL > DIAS → Qwen3 is too monotone → add 'with natural",
        "                               pitch variation' to qwen3_instruct",
        "  Voiced ratio  >> EL > DIAS → Qwen3 has more silence → may need shorter pauses",
        "  Dynamic range >> EL > DIAS → Qwen3 lacks emphasis → add 'with strong emphasis",
        "                               on key words' to qwen3_instruct",
        "  Brightness    >> EL > DIAS → EL is 'brighter'/crisper → Qwen3 may sound",
        "                               darker; consider 'clear warm tone'",
        "  MFCC corr     >> High (>0.7) = similar timbre; Low (<0.4) = very different",
        "=" * 65,
    ]

    summary_path = out_dir / "summary.txt"
    summary_path.write_text("\n".join(lines), encoding="utf-8")
    print("\n" + "\n".join(lines))
    print(f"\n  ✓ summary.txt saved to {summary_path}")


def main():
    parser = argparse.ArgumentParser(description="DIAS Audio Analyzer: EL vs Qwen3 comparison")
    parser.add_argument("--el",   required=False,
                        default="analysis/el_vs_qwen3/EL_reference.wav",
                        help="Path to ElevenLabs WAV")
    parser.add_argument("--dias", required=False,
                        default="analysis/el_vs_qwen3/DIAS_comparison.wav",
                        help="Path to DIAS/Qwen3 WAV")
    parser.add_argument("--out",  required=False,
                        default="analysis/el_vs_qwen3/report",
                        help="Output directory for plots and summary")
    args = parser.parse_args()

    el_path   = Path(args.el)
    dias_path = Path(args.dias)
    out_dir   = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    if not el_path.exists():
        sys.exit(f"ERROR: EL file not found: {el_path}")
    if not dias_path.exists():
        sys.exit(f"ERROR: DIAS file not found: {dias_path}")

    print("\n🎙️  DIAS Audio Analyzer")
    print("─" * 50)
    print("Loading audio files...")
    y_el,   sr = load(el_path)
    y_dias, _  = load(dias_path)

    print("\nGenerating plots...")
    plot_waveform   (y_el, y_dias, sr, out_dir)
    p_el, p_dias    = pitch_stats(y_el, sr)[1], pitch_stats(y_dias, sr)[1]
    plot_pitch      (y_el, y_dias, sr, out_dir)
    rms_el, rms_dias = rms_stats(y_el, sr)[2], rms_stats(y_dias, sr)[2]
    plot_energy     (y_el, y_dias, sr, out_dir)
    plot_spectrogram(y_el, y_dias, sr, out_dir)
    sc_el, sc_dias  = centroid_stats(y_el, sr)[2], centroid_stats(y_dias, sr)[2]
    plot_centroid   (y_el, y_dias, sr, out_dir)
    mfcc_corr, _, _ = mfcc_similarity(y_el, y_dias, sr, out_dir)

    print("\nDetecting pauses...")
    pauses_el   = detect_pauses(y_el,   sr)
    pauses_dias = detect_pauses(y_dias, sr)
    print(f"  EL:   {len(pauses_el)} pauses")
    print(f"  DIAS: {len(pauses_dias)} pauses")

    write_summary(out_dir, el_path, dias_path,
                  p_el, p_dias, rms_el, rms_dias,
                  sc_el, sc_dias, mfcc_corr,
                  pauses_el, pauses_dias)

    print(f"\n✅  Done! All outputs in: {out_dir.resolve()}")


if __name__ == "__main__":
    main()
