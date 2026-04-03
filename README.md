# DIAS - Distributed Immersive Audiobook System

Sistema distribuito per la produzione automatizzata di audiolibri cinematografici e radiodrammi con AI locale.
DIAS gestisce la trasformazione del testo grezzo (PDF/EPUB) in una produzione audio multi-voce, curando la regia emotiva, il casting vocale (Dialogue Atomization), gli effetti sonori e il mastering finale.

---

## 🏗️ Workflow Operativo (Sintetico)

| Fase | Componente | Descrizione | Stato |
| :--- | :--- | :--- | :--- |
| **1. Intel** | **Stage 0** | Analisi "DNA" del libro (Capitoli, Personaggi). | ✅ **Produzione** |
| **2. Regia** | **Dossier** | Casting vocale e parametri tecnici (Dashboard). | ✅ **Produzione** |
| **3. Ingest** | **Stage A** | Estrazione testo e chunking. | ✅ **Produzione** |
| **4. Scena** | **Stage B/C** | Regia emotiva e segmentazione chirurgica (Prompt Monastico). | ✅ **Produzione** |
| **5. Sintesi** | **Stage D** | Generazione audio con Qwen3-TTS (Formula Oscar). | ✅ **Produzione** |
| **6. Music** | **Stage E** | Generazione soundscape cinematico. | 🚧 *Sviluppo* |
| **7. Final** | **Stage F/G** | Mixing multi-stem e Mastering broadcast. | 🚧 *Sviluppo* |

---

## 📚 Navigazione Documentazione (Bussola)

Tutta la conoscenza tecnica di DIAS è centralizzata qui. **Inizia dal Blueprint per l'architettura o dallo Standard di Produzione per la qualità.**

### 🏛️ Architettura e Core
- 🏗️ **[docs/blueprint.md](docs/blueprint.md)**: Il documento madre. Architettura Master, gestione Redis, Pipeline A-G e persistenza.
- ⚙️ **[docs/technical-reference.md](docs/technical-reference.md)**: Manuale Sviluppatore (Log, Debug, Systemd, SOPS).
- 🗂️ **[docs/dias-inventory.md](docs/dias-inventory.md)**: Inventario universale di moduli, dashboard e tools.

### 🎭 Produzione e Qualità (Recitazione da Oscar)
- 🏆 **[docs/production-standard.md](docs/production-standard.md)**: **LO STANDARD.** Formula Oscar (0.75), parametri tecnici, fonetica e punteggiatura audio.
- 🎬 **[docs/preproduction-guide.md](docs/preproduction-guide.md)**: Guida pratica al casting e al file `preproduction.json`.
- 📜 **[docs/prompt-evolution.md](docs/prompt-evolution.md)**: Storia e registro delle versioni dei prompt (Stage B/C).

---

## 🌐 Dual-Node Infrastructure

DIAS si basa su un'architettura distribuita resiliente tra Brain e Worker:
- **Brain (LXC 190 / CT120)**: `192.168.1.120` — Orchestrazione, Redis, Dashboard e Worker CPU.
- **Worker GPU (PC 139 / ARIA)**: `192.168.1.139` — Inferenza AI (Qwen3, MusicGen) su Windows 11.

---

## 🚀 Quick Start

```bash
# Entra nell'ambiente del progetto
cd /home/Projects/NH-Mini/sviluppi/dias

# 1. Avvio Dashboard Hub (Interfaccia di Regia)
./start_dashboard_hub.sh

# 2. Avvio Pipeline (Esecuzione)
./start_pipeline.sh
```

---
*Ultimo aggiornamento: 03 Aprile 2026*
