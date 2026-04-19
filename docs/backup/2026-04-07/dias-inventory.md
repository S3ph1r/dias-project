# 📋 DIAS - Master Inventory (Codebase, Dashboard & Tools)

Questo documento rappresenta l'inventario definitivo e dettagliato di tutti i componenti del sistema DIAS, utile per la manutenzione, il debug e lo sviluppo di nuovi stadi.

---

## 🎯 Panoramica Architettura
DIAS (Distributed Immersive Audiobook System) è una pipeline di elaborazione documenti AI con architettura a stage.  
**Filosofia chiave**: Config-driven development con zero-code-change per switch tra ambienti mock/real tramite `MOCK_SERVICES=true/false`.

---

## 📦 1. Core Codebase (`src/`)

### **`src/common/` - Fondamenta e Logica Condivisa**
Moduli trasversali utilizzati da tutti gli stage per garantire coerenza e portabilità.

| Modulo | Classe/Funzione | Funzionalità |
| :--- | :--- | :--- |
| **`base_stage.py`** | `BaseStage` | Foundation di tutti gli stage: gestisce config, logging, Pydantic validation e retry logic per errori 429. |
| **`config.py`** | `DiasConfig` | Loader della configurazione `dias.yaml` e delle environment variables via Pydantic. |
| **`gateway_client.py`** | `GatewayClient` | Bridge RPC verso l'ARIA Smart Gateway su Redis (PC 139). |
| **`persistence.py`** | `DiasPersistence` | Gestore del File System "Project-Centric" (`data/projects/{id}/`). |
| **`registry.py`** | `MasterRegistry` | Gestore dello stato dei task in Redis (`PENDING`, `IN_FLIGHT`, `COMPLETED`). |
| **`redis_factory.py`** | `get_redis_client` | Switch automatico tra `MockRedisClient` (offline) e `DiasRedis` (produzione). |
| **`models.py`** | - | Definizioni dei contratti dati (JSON schemas) tra gli stage. |
| **`audio_utils.py`** | - | Utility di basso livello per manipolazione audio (concatenazione, silenzi, metadati). |

### **`src/stages/` - Operatori di Pipeline**
Ogni file rappresenta un'unità di elaborazione isolata che comunica via Redis o FileSystem.

| Stage | File | Funzione Core |
| :--- | :--- | :--- |
| **0** | `stage_0_intel.py` | **Intelligence**: Discovery strutturale e "DNA" artistico del libro (Fingerprint). |
| **A** | `stage_a_text_ingester.py` | **Text Ingest**: Conversione PDF/EPUB -> TXT e chunking intelligente. |
| **B** | `stage_b_semantic_analyzer.py`| **Semantic Analysis**: Analisi emotiva e narrativa con Gemini. |
| **C** | `stage_c_scene_director.py` | **Scene Director**: Segmentazione cinematografica e regia TTS (Formula Oscar). |
| **D** | `stage_d_voice_gen.py` | **Voice Proxy**: Delega ad ARIA la sintesi e attende il loopback audio. |

---

## 🖥️ 2. DIAS Dashboard (`src/dashboard/`)

Interfaccia **SvelteKit** + Backend **FastAPI Hub** (`src/api/main.py`).

### **Componenti UI Core (`src/lib/components/`)**:
- **`VoiceCarousel.svelte`**: Selezione vocale 3D con anteprime audio dei Master (Luca, Isabella, ecc.).
- **`CastingTable.svelte`**: Interfaccia per assegnare voci ai personaggi rilevati dallo Stage 0.
- **`AudioInspector.svelte`**: Analisi visuale (waveform/spectrogram) delle scene prodotte.
- **`UploadModal.svelte`**: Caricamento nuovi manoscritti e inizializzazione progetto.

---

## 🎙️ 3. Tool di Produzione e Ingestion (`scripts/`)

> [!IMPORTANT]
> **Owner**: DIAS gestisce la ricerca e "preparazione" dei campioni vocali. Gli asset pronti vengono poi pushati verso ARIA per la produzione.

- **`trigger_ingestion.py`**: Automazione download da YouTube/Source.
- **`voice_slicer.py`**: Slicing automatico e cleanup silenzi dai campioni grezzi.
- **`whisper_transcriber`**: Generazione automatica dei file `.txt` (ref_text) per Qwen3.
- **`sync_vocal_assets.py`**: Allineamento dei campioni voce tra LXC (Brain) e PC (Worker).
- **`milestone_chapter_stitcher.py`**: Concatena le scene prodotte in capitoli finali.
- **`unlock_pipeline.py`**: Manutenzione Redis (reset progetti e sblocco code).

---

## 🧪 4. Tool di Analisi e Quality Control (`analysis/`)

Strumentazione per il benchmark Qwen3 vs ElevenLabs.
- **`audio_analyzer.py`**: Calcolo metriche F0 (Pitch), RMS (Energia) e Spectral Centroid.
- **`compare_stitcher.py`**: Creazione di file audio A/B sincronizzati per test ciechi.
- **Librerie**: `librosa`, `scipy`, `matplotlib`, `pydub`, `soundfile`.

---

## 🛠️ 5. Dipendenze Core (`requirements.txt`)

- **AI Engine**: `google-generativeai` (Gemini Flash-Lite), `google-genai`.
- **Communication**: `redis`, `fastapi`, `websockets`, `httpx`.
- **Audio Core**: `pydub`, `librosa`, `soundfile`, `audioread`, `soxr`.
- **NLP / Processing**: `spacy`, `nltk`, `PyMuPDF` (PDF), `EbookLib` (EPUB).
- **Data Architecture**: `pydantic`, `PyYAML`, `orjson`.

---
*Ultimo aggiornamento: 03 Aprile 2026 — Master Inventory V1.0.*
