# DIAS - Distributed Immersive Audiobook System

Sistema distribuito per la produzione automatizzata di audiolibri cinematografici e radiodrammi con AI locale.
DIAS gestisce la trasformazione del testo grezzo (PDF/EPUB) in una produzione audio multi-voce, curando la regia emotiva, il casting vocale (Dialogue Atomization), gli effetti sonori e il mastering finale.

## 📚 Navigazione Documentazione (Bussola)

Tutta l'ingegnerizzazione e le specifiche tecniche di DIAS sono centralizzate nella directory `/docs`. 
**Per orientarti, inizia sempre dal Blueprint.**

- 🏗️ **[docs/blueprint.md](docs/blueprint.md)**: Il documento madre. Contiene l'inquadramento Architetturale completo, i diagrammi di flusso e la persistenza Redis.
- 🗂️ **[docs/00_DIAS_INDEX.md](docs/00_DIAS_INDEX.md)**: Indice rapido e mappato di tutta la documentazione.
- 🎭 **[docs/handoff_theatrical_audio.md](docs/handoff_theatrical_audio.md)**: Studio dell'integrazione HTTP/Redis tra DIAS (Stage C) e ARIA (Stage D) per l'audio teatrale.
- 🎬 **[docs/preproduction-guide.md](docs/preproduction-guide.md)**: Guida su come impostare il casting e le temperature del modello vocale nel `preproduction.json`.
- 🤖 **[docs/qwen3_technical_guide.md](docs/qwen3_technical_guide.md)**: Guida al prompt engineering (es. standard v1.9) per pilotare il motore Qwen3-TTS.
- ⚙️ **[docs/technical-reference.md](docs/technical-reference.md)** & **[docs/dias-component-inventory.md](docs/dias-component-inventory.md)**: Riferimenti pratici per gli sviluppatori e inventario tecnico del codice python.

## 🏗️ Architecture Pipeline

La produzione è gestita in modo resiliente dal `SerialOrchestrator` attraverso una pipeline a 7 stadi sequenziali:

```text
PDF/EPUB → [A] Ingestion → [B] MacroAnalysis → [C] SceneDirector
         → [D] VoiceGen → [E] MusicGen → [F] Mixing → [G] Mastering → MP3
```

| Stadio | Funzione | Worker Primario | Modello / Backend |
|--------|-----------|-----------|------|
| **A** | Text Ingestion | `CT120` (CPU) | PyMuPDF |
| **B** | Macro Analysis | `CT120` (API) | Gemini Flash-Lite (Semantic Registry) |
| **C** | Scene Director | `CT120` (API) | Gemini Flash-Lite (Dialogue Atomization v1.9) |
| **D** | Voice Generator | `ARIA Node` | Qwen3-TTS o Fish S1-mini |
| **E** | Music Generator | `ARIA Node` | AudioCraft MusicGen |
| **F** | Audio Mixer | `CT120` (CPU) | FFmpeg 7.0+ (Ducking/Pan) |
| **G** | Mastering Engine | `CT120` (CPU) | FFmpeg (Loudness Norm) |

## 🌐 Dual-Node Infrastructure

DIAS si basa su un'architettura distribuita resiliente (Gateway Pattern + Redis Semaphore) per aggirare i limiti hardware:

- **Brain (LXC 190 / CT120)**: `192.168.1.120` — Ospita il server Redis, il `SerialOrchestrator`, la Dashboard UI e i worker CPU (Stadi A, B, C, F, G).
- **GPU Inference (PC 139 / ARIA)**: `192.168.1.139` — Server Windows 11 asincrono. Riceve le code Redis, gestisce il VRAM Manager in base al carico, genera l'audio (Qwen3) e lo salva su storage condiviso.

## 🚀 Quick Start

```bash
# Entra nell'ambiente del progetto (Framework NH-Mini)
cd /home/Projects/NH-Mini/sviluppi/dias

# 1. Analisi Iniziale
# (Inizia lo smontaggio del libro e genera dossier pre-produzione)
./start_pipeline.sh

# 2. Ripristino / Avvio Produzione Teatrale (da Dashboard via Redis)
# Espone la UI Desktop su: http://192.168.1.120:5173
./start_dashboard_hub.sh
```
