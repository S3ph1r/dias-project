# DIAS - Distributed Immersive Audiobook System

Sistema distribuito per la produzione automatizzata di audiolibri cinematografici con AI locale.

## Quick Start

```bash
# Questo progetto opera sotto NH-Mini framework
# Leggi docs/blueprint.md per le specifiche complete
```

## Architecture

Pipeline sequenziale a 7 stadi:

```
PDF/EPUB → [A] Ingestion → [B] MacroAnalysis → [C] SceneDirector
         → [D] VoiceGen → [E] MusicGen → [F] Mixing → [G] Mastering → MP3
```

| Stadio | Componente | Dove gira | Tool |
|--------|-----------|-----------|------|
| A | TextIngester | CT120 (CPU) | PyMuPDF |
| B | MacroAnalyzer | CT120 (API) | Gemini Flash-Lite |
| C | SceneDirector | CT120 (API) | Gemini Flash-Lite |
| D | VoiceGenerator | GPU Worker | Qwen3-TTS 1.7B |
| E | MusicGenerator | GPU Worker | AudioCraft MusicGen |
| F | AudioMixer | CT120 (CPU) | FFmpeg 7.0+ |
| G | MasteringEngine | CT120 (CPU) | FFmpeg |

## Infrastructure

- **Brain (CT120)**: 192.168.1.120 — Redis + stadi CPU
- **GPU Worker**: PC gaming Win11 — stadi GPU (on-demand)
- **Storage**: NFS share per audio assets
- **Framework**: [NH-Mini](../../../.cursorrules)
