# DIAS - Master Inventory (Codebase, Prompt, Modelli)
## Versione 2.0 — Aprile 2026

Inventario tecnico definitivo di tutti i componenti DIAS: file Python, prompt YAML, modelli Pydantic e dipendenze.

---

## 0. Prompt Asset (`config/prompts/`)

Tutti i prompt sono versionati e isolati dal codice. Un cambio di prompt non richiede modifiche al codice del worker.

### `stage_0/`
| File | Versione | Funzione |
| :--- | :--- | :--- |
| `0.1_discovery_v1.2.yaml` | v1.2 | Scansione strutturale: capitoli, stile dialogo, marcatori stilistici. |
| `0.2_intelligence_v1.0.yaml` | v1.0 | DNA creativo: casting, profili vocali, palette sonore per Dashboard. |

### `stage_b/`
| File | Versione | Funzione |
| :--- | :--- | :--- |
| `b_semantic_v1.1.yaml` | v1.1 | Dubbing Director: emozione macro, subtext, narrator_base_tone, Mood Propagation. |

### `stage_b2/`
| File | Versione Interna | Funzione |
| :--- | :--- | :--- |
| `b2_macro_v4.0.yaml` | **v4.2** | Musical Director: PAD selection, production_tags ACE-Step, PadArc con roadmap_item, regola di proporzionalità segmenti, Qwen3 vocabulary. |
| `b2_micro_v4.0.yaml` | **v4.1** | Sound Designer monolitico: AMB/SFX/STING + PAD breathing → IntegratedCueSheet. Paradigma BBC/Star Wars, albero AMB rewriting, SFX test 0, STING rules. |
| `b2_micro_director_v1.0.yaml` | **v1.0** | Narrative Event Extractor: eventi fisici in linguaggio naturale → SoundEventScore. Zero vocabolario ACE-Step. |
| `b2_micro_engineer_v1.0.yaml` | **v1.0** | ACE-Step Spec Generator: converte SoundEventScore in production_tags Qwen3 → IntegratedCueSheet. |

### `stage_c/`
| File | Versione | Funzione |
| :--- | :--- | :--- |
| `c_monastic_v2.3.yaml` | v2.3 | Scene Director: segmentazione Emotional Beat, Tag Splitting, fidelità monastica, istruzioni Qwen3-TTS. |

---

## 1. Core Codebase (`src/`)

### `src/common/` — Fondamenta Condivise

| Modulo | Classe/Funzione Principale | Funzione |
| :--- | :--- | :--- |
| `base_stage.py` | `BaseStage` | Foundation di tutti gli stage: config, logging, Pydantic validation, retry logic 429. |
| `config.py` | `DiasConfig` | Loader configurazione `dias.yaml` e variabili d'ambiente via Pydantic. |
| `gateway_client.py` | `GatewayClient` | Bridge RPC verso ARIA Smart Gateway su Redis (PC 139). |
| `persistence.py` | `DiasPersistence` | Gestore filesystem project-centric (`data/projects/{id}/`). |
| `registry.py` | `MasterRegistry` | Gestore stato task in Redis (`PENDING`, `IN_FLIGHT`, `COMPLETED`). |
| `redis_factory.py` | `get_redis_client` | Switch automatico tra `MockRedisClient` (offline) e `DiasRedis` (produzione). |
| `models.py` | — | Tutti i modelli Pydantic inter-stadio (vedi sezione 3). |
| `audio_utils.py` | — | Utility audio: concatenazione, silenzi, metadati. |
| `logging_setup.py` | `get_logger` | Logger strutturato per ogni worker. |

### `src/stages/` — Operatori di Pipeline

| Stage | File | Classe Principale | Funzione |
| :--- | :--- | :--- | :--- |
| **0** | `stage_0_intel.py` | — | Intelligence: Discovery (0.1) + Creative DNA (0.2). |
| **A** | `stage_a_text_ingester.py` | — | Text Ingest: estrazione PDF/EPUB, scomposizione Macro/Micro. |
| **B** | `stage_b_semantic_analyzer.py` | — | Semantic Analysis: emozione macro, Mood Propagation, Subtext. |
| **C** | `stage_c_scene_director.py` | — | Scene Director: segmentazione, Tag Splitting, qwen3_instruct. |
| **D** | `stage_d_voice_gen.py` | — | Voice Proxy: sintesi TTS via ARIA, MasterTimingGrid. |
| **B2-Macro** | `stage_b2_macro.py` | `StageB2Macro` | Musical Director: MacroCue + PadArc via prompt `b2_macro_v4.0.yaml`. |
| **B2-Micro** | `stage_b2_micro.py` | `StageB2Micro` | Sound Designer monolitico: IntegratedCueSheet via `b2_micro_v4.0.yaml`. |
| **B2-Director** | `stage_b2_micro_director.py` | `StageB2MicroDirector` | Narrative Event Extractor: SoundEventScore via `b2_micro_director_v1.0.yaml`. |
| **B2-Engineer** | `stage_b2_micro_engineer.py` | `StageB2MicroEngineer` | ACE-Step Spec Generator: IntegratedCueSheet via `b2_micro_engineer_v1.0.yaml`. |
| **D2** | `stage_d2_sound_factory.py` | — | Sound Factory Client: invia SoundShoppingList aggregata ad ARIA. |

File legacy presenti ma non usati in produzione:
- `stage_b2_macro_v3_old.py` — versione pre-Sound-on-Demand con Redis catalog.
- `stage_b2_micro_v3_old.py` — versione pre-Sound-on-Demand con Redis catalog.

### `tests/stages/` — Orchestratori e Runner

| File | Funzione |
| :--- | :--- |
| `run_b2_pipeline.py` | Orchestratore pipeline B2 v4.1: Macro → Micro (monolitico o split) → Aggregazione. Flag: `--split`, `--macro-only`, `--cleanup`. |

---

## 2. Dashboard e API (`src/dashboard/`, `src/api/`)

Interfaccia SvelteKit + Backend FastAPI (`src/api/main.py`).

| Componente | Funzione |
| :--- | :--- |
| `VoiceCarousel.svelte` | Selezione Global Voice con anteprima audio. |
| `CastingTable.svelte` | Assegnazione voci ai personaggi rilevati da Stage 0. |
| `AudioInspector.svelte` | Analisi visuale (waveform/spectrogram) delle scene prodotte. |
| `UploadModal.svelte` | Caricamento manoscritti e inizializzazione progetto. |

---

## 3. Modelli Pydantic (`src/common/models.py`)

### Stage A Output
| Modello | Prodotto da | Campi Principali |
| :--- | :--- | :--- |
| `BookMetadata` | Stage A | `book_id`, `title`, `author`, `word_count`, `chapter_count` |
| `IngestionBlock` | Stage A | `job_id`, `book_id`, `chapter_id`, `block_id`, `block_text`, `word_count` |

### Stage B Output
| Modello | Prodotto da | Campi Principali |
| :--- | :--- | :--- |
| `BlockAnalysis` | Stage B | `valence`, `arousal`, `tension`, `primary_emotion`, `setting`, `audio_cues` |
| `NarrativeMarker` | Stage B | `relative_position`, `event`, `mood_shift` |
| `SemanticEntity` | Stage B | `entity_id`, `text`, `entity_type`, `speaking_style` |
| `MacroAnalysisResult` | Stage B | `block_analysis`, `narrative_markers`, `entities` |
| `ChapterAnalysis` | Stage B | `avg_valence`, `avg_arousal`, `avg_tension`, `dominant_emotion` |

### Stage C/D Output
| Modello | Prodotto da | Campi Principali |
| :--- | :--- | :--- |
| `SceneScript` | Stage C | `scene_id`, `text_content`, `voice_direction`, `audio_layers`, `tts_backend` |
| `VoiceDirection` | Stage C | `emotion_description`, `pace_factor`, `energy` |
| `TimingScene` | Stage D | `scene_id`, `start_offset`, `voice_duration`, `pause_after` |
| `TimingMicroChunk` | Stage D | `micro_chunk_id`, `start_offset`, `duration`, `scenes[]` |
| `TimingMacroChunk` | Stage D | `macro_chunk_id`, `start_offset`, `duration`, `micro_chunks{}` |
| `MasterTimingGrid` | Stage D | `project_id`, `total_duration_seconds`, `macro_chunks{}` |

### Stage B2-Macro Output
| Modello | Prodotto da | Campi Principali |
| :--- | :--- | :--- |
| `PadArcSegment` | B2-Macro | `start_s`, `end_s`, `intensity` (low/mid/high), `note`, `roadmap_item` |
| `PadRequest` | B2-Macro | `canonical_id`, `production_prompt`, `production_tags`, `negative_prompt`, `guidance_scale`, `inference_steps`, `is_leitmotif`, `estimated_duration_s`, `pad_arc[]` |
| `MacroCue` | B2-Macro | `project_id`, `chunk_label`, `pad`, `music_justification` |

### Stage B2-Micro Output (Comune a entrambe le modalità)
| Modello | Prodotto da | Campi Principali |
| :--- | :--- | :--- |
| `MicroCueAutomation` | B2-Micro | `scene_id`, `pad_volume_automation`, `pad_duck_depth`, `pad_fade_speed`, `amb_id`, `sfx_id`, `sfx_timing`, `sting_id`, `sting_timing`, `reasoning` |
| `SoundShoppingItem` | B2-Micro | `type` (pad/amb/sfx/sting), `canonical_id`, `production_prompt`, `production_tags`, `negative_prompt`, `guidance_scale`, `duration_s` |
| `IntegratedCueSheet` | B2-Micro | `project_id`, `block_id`, `pad_canonical_id`, `scenes_automation[]`, `sound_shopping_list[]` |

### Stage B2-Micro-Director Output (solo modalità --split)
| Modello | Prodotto da | Campi Principali |
| :--- | :--- | :--- |
| `AmbientEvent` | B2-Director | `trigger_description`, `physical_description`, `estimated_duration_s` (3-5s) |
| `SfxEvent` | B2-Director | `trigger_description`, `physical_description`, `estimated_duration_s` (0.1-3s) |
| `StingEvent` | B2-Director | `trigger_description`, `revelation_type`, `estimated_duration_s` (1.5-4s) |
| `SceneEvent` | B2-Director | `scene_id`, `pad_behavior`, `pad_duck_depth`, `ambient_event`, `sfx_event`, `sting_event` |
| `SoundEventScore` | B2-Director | `project_id`, `block_id`, `pad_canonical_id`, `scenes[]`, `asset_summary[]` |

### Registry
| Modello | Usato da | Campi Principali |
| :--- | :--- | :--- |
| `RegistryEntry` | MasterRegistry | `task_id`, `status` (TaskStatus enum), `attempts`, `worker_id`, `output_path` |
| `TaskStatus` | MasterRegistry | `PENDING`, `IN_FLIGHT`, `COMPLETED`, `FAILED`, `TIMEOUT` |

---

## 4. Convenzione canonical_id

Formato universale EN: `{category}_{description}_{variant_num}`

| Categoria | Prefisso | Esempio valido | Esempio non valido |
| :--- | :--- | :--- | :--- |
| PAD | `pad_` | `pad_suspense_dark_orchestral_01` | `pad_dark_01` (troppo generico) |
| AMB | `amb_` | `amb_urban_street_night_01` | `amb_street_01` |
| SFX | `sfx_` | `sfx_door_slam_wooden_01` | `sfx_door_01` |
| STING | `sting_` | `sting_revelation_brass_01` | `sting_01` |

Il variant_num (`_01`, `_02`) è obbligatorio. Il codice in `stage_b2_micro_engineer.py` lo aggiunge automaticamente se mancante.

---

## 5. Dipendenze Core (`requirements.txt`)

| Categoria | Pacchetti |
| :--- | :--- |
| **AI Engine** | `google-generativeai`, `google-genai` (Gemini Flash-Lite) |
| **Communication** | `redis`, `fastapi`, `websockets`, `httpx` |
| **Audio Core** | `pydub`, `librosa`, `soundfile`, `audioread`, `soxr` |
| **NLP/Processing** | `spacy`, `nltk`, `PyMuPDF` (PDF), `EbookLib` (EPUB) |
| **Data** | `pydantic`, `PyYAML`, `orjson` |

---

*Ultimo aggiornamento: 17 Aprile 2026 — v2.0: aggiunto stage_b2_micro_director.py, stage_b2_micro_engineer.py, prompt director/engineer v1.0, modelli SoundEventScore/SceneEvent/AmbientEvent/SfxEvent/StingEvent, aggiornate versioni prompt.*
