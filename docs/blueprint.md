# DIAS - Distributed Immersive Audiobook System
## Master Blueprint v7.0 (Sound-on-Demand, Director/Engineer Architecture)

**Data**: 17 Aprile 2026
**Status**: In Produzione (Stage 0-D validati E2E, Stage B2 Sound-on-Demand v4.1 validato)
**Target Hardware**: Brain (LXC 190 Backend) + PC Gaming (ARIA GPU Worker, PC 139, RTX 5060 Ti 16GB)
**NH-Mini Compliance**: Pienamente aderente a `.project-context` e `description-contracts.mdc`

---

### 1. Vision e Architettura

DIAS (Distributed Immersive Audiobook System) è un **Regista Narrativo** che orchestra una pipeline distribuita per trasformare testi letterari in audiobook teatrali di qualità cinematografica. Il benchmark qualitativo di riferimento è la **BBC Radio Drama degli anni '80** e **Star Wars Audio Drama (NPR, 1981)**: la musica non accompagna la narrazione, è un personaggio invisibile che respira con essa.

### 1.1 Architettura "Universal State Bus" (Redis 120)

Il sistema si basa su Redis (LXC 120) come bus di stato universale tra il Brain (LXC 190) e i Worker (PC 139):

- **Il Brain (Ruolo: Regia)**: Gestisce il ciclo di vita dell'opera (Stadi 0-E). Utilizza un Master Registry per tracciare il progresso.
- **Project-Centric Management**: Ogni libro vive in una sandbox isolata in `data/projects/{project-id}/`.
- **L'Infrastruttura (Ruolo: Stato)**: Redis ospita le code e i registri globali, punto di incontro agnostico tra Brain e Worker.
- **Il Worker (Ruolo: Esecuzione)**: ARIA (PC 139) è il motore di inferenza GPU. Serve qualsiasi client tramite le code Redis.
- **Flessibilità di Deployment**: Ogni ruolo è totalmente disaccoppiato. La posizione fisica dei nodi è definita dalla configurazione (`.env`, `dias.yaml`).

### 1.2 Orchestrazione "Serial Handshake"

La pipeline adotta un approccio a **Handshake Seriale**: uno stadio non inizia finché lo stadio precedente non ha completato tutti i chunk e persistito i risultati su disco. Il modulo `orchestrator.py` funge da supervisore.

---

### 2. Architettura della Pipeline (10 Stadi)

| Stage | Nome | Compito Principale |
| :--- | :--- | :--- |
| **Stage 0** | Intel | Protocollo 0.1 (Discovery strutturale) + 0.2 (DNA creativo, Casting). Produce `fingerprint.json` e `preproduction.json`. |
| **Stage A** | TextIngester | Scomposizione a imbuto: Macro-chunk (~2500 parole) + Micro-chunk (~300 parole). |
| **Stage B** | SemanticAnalyzer | Analisi emotiva macro (valence/arousal/tension), Mood Propagation verso i micro-chunk. |
| **Stage C** | SceneDirector | Segmentazione per Emotional Beat, Tag Splitting, istruzioni TTS Qwen3. |
| **Stage D** | VoiceGenerator | TTS per ogni scena → file WAV fisici + Master Timing Grid. |
| **Stage B2-Macro** | Musical Director | Produce MacroCue (PadRequest + PadArc) per ogni macro-chunk. |
| **Stage B2-Micro** | Sound Designer (monolitico) | Produce IntegratedCueSheet + SoundShoppingList per ogni micro-chunk (ARCHITETTURA LEGACY, ancora attiva). |
| **Stage B2-Micro-Director** | Narrative Event Extractor | Estrae eventi fisici narrativi → SoundEventScore in linguaggio naturale. (Split v1.0) |
| **Stage B2-Micro-Engineer** | ACE-Step Spec Generator | Converte SoundEventScore in spec ACE-Step → IntegratedCueSheet. (Split v1.0) |
| **Stage D2** | Sound Factory Client | Invia la SoundShoppingList aggregata ad ARIA → produce tutti gli asset audio (PAD, AMB, SFX, STING) via ACE-Step. |
| **Stage E** | Mixdown | Assembla voce (WAV Stage D) + PAD stems (da HTDemucs) + AMB/SFX/STING → traccia finale mixata. |

---

### 3. Stage B2: Architettura Sound-on-Demand v4.1

Stage B2 è il cuore del sound design. Opera in modalità **Sound-on-Demand**: zero dipendenze da catalogo Redis, zero sound library pre-esistente. Ogni asset viene prodotto ex-novo da ARIA su richiesta.

#### 3.1 B2-Macro (Musical Director)

Analizza il macro-chunk (emozione, setting, arco narrativo) e produce:
- **PadRequest**: canonical_id + production_prompt + production_tags (vocabolario Qwen3) + negative_prompt + parametri ACE-Step.
- **PadArc**: partitura emotiva sequenza di segmenti `{start_s, end_s, intensity, note, roadmap_item}`. Stage E usa il PadArc per gestire dinamicamente i 4 stem HTDemucs (`bass/drums/vocals/other`).

Prompt: `b2_macro_v4.0.yaml` (versione interna v4.2).

#### 3.2 B2-Micro: Modalità Monolitica (Legacy)

Una singola chiamata LLM per micro-chunk. Produce direttamente `IntegratedCueSheet` (scenes_automation + sound_shopping_list). Ancora funzionante e validata. Prompt: `b2_micro_v4.0.yaml` (versione interna v4.1).

#### 3.3 B2-Micro: Modalità Split Director/Engineer (v1.0)

Due chiamate LLM separate per micro-chunk, attivata con il flag `--split`:

1. **B2-Micro-Director** (`stage_b2_micro_director.py`): analizza il testo in linguaggio naturale, identifica eventi fisici (AMB/SFX/STING) e comportamento PAD. Output: `SoundEventScore`. Nessun vocabolario tecnico.
2. **B2-Micro-Engineer** (`stage_b2_micro_engineer.py`): converte il SoundEventScore in spec ACE-Step (`production_tags`, `canonical_id`, `guidance_scale`, `duration_s`). Output: `IntegratedCueSheet` (identico al formato monolitico — compatibile con Stage D2 e Stage E).

Vantaggio chiave della modalità split: la shopping list viene costruita prima delle scenes_automation, rendendo strutturalmente impossibile il canonical_id mismatch.

---

### 4. Principi di Sound Design (Paradigma BBC/Star Wars)

#### PAD (Tappeto Musicale)
- Prodotto da ACE-Step 1.5 XL SFT, durata ~8-20 minuti per capitolo (stesso del contenuto vocale).
- ARIA esegue HTDemucs per separare 4 stem: `bass` (frequenze basse), `drums` (elementi percussivi), `vocals` (contenuto vocale/coro), `other` (melodia, pad, archi, tutto il resto).
- Stage E gestisce i 4 stem dinamicamente via PadArc:
  - `low` = solo bass
  - `mid` = bass + other
  - `high` = bass + other + drums (+ vocals se presenti)
- Ducking locale (respiro micro) gestito da `MicroCueAutomation.pad_volume_automation`.

#### AMB (Ambiente — cambio di scena)
- Cue transitionale breve: **3-5 secondi**. Non è un loop.
- Segna il cambio di ambientazione fisica tra scene consecutive (interno → esterno, silenzio → folla).
- **Max 1 per micro-chunk**. Spesso zero.
- Si applica solo alla scena in cui avviene il cambio.

#### SFX (Effetto Puntuale)
- Effetto fisico puntuale: **0.3-2 secondi**.
- Solo per momenti culminanti della scena (l'azione accade, non la preparazione).
- **Max 1 per scena**. Meno è meglio.
- `sfx_timing`: start | middle | end.

#### STING (Accento Orchestrale)
- Sottolineatura drammatica: **2-4 secondi**.
- Solo per rivelazioni narrative irreversibili (svolta, morte, tradimento confermato).
- **Max 1 per micro-chunk**. Mai all'inizio di una scena.
- `sting_timing`: middle | end (mai start).

#### ARIA Sound Factory
- Modello unico: **ACE-Step 1.5 XL SFT** per tutti gli asset (PAD, AMB, SFX, STING).
- Hardware: PC 139, RTX 5060 Ti 16GB VRAM.
- Timing: ~4.5 minuti per 30 secondi di output generato (LM ~240s + DiT ~35s).
- Queue Redis: `aria:q:mus:local:acestep-1.5-xl-sft:dias`.
- Output type: `pad | amb | sfx | sting`.

---

### 5. Flusso Dati B2 Completo

```
Stage B (SemanticAnalyzer)
  → ChunkAnalysis (emozione, setting, arco)
       ↓
Stage B2-Macro
  → MacroCue {PadRequest + PadArc}
       ↓
Stage B2-Micro [monolitico] → IntegratedCueSheet {scenes_automation + shopping_list}
       oppure
Stage B2-Micro-Director → SoundEventScore {scene → eventi fisici}
       ↓
Stage B2-Micro-Engineer → IntegratedCueSheet {scenes_automation + shopping_list}
       ↓
Aggregatore (run_b2_pipeline.py) → sound_shopping_list_aggregata.json
       ↓
Stage D2 (Sound Factory Client) → invia assets ad ARIA → WAV files
       ↓
Stage E (Mixdown) → voce + PAD stems + AMB/SFX/STING → traccia finale
```

---

### 6. Modelli Dati Chiave (Stage B2)

| Modello | Prodotto da | Consumato da |
| :--- | :--- | :--- |
| `MacroCue` | B2-Macro | B2-Micro, Stage E |
| `PadRequest` | B2-Macro (dentro MacroCue) | Stage D2 (produzione PAD) |
| `PadArcSegment` | B2-Macro (dentro PadRequest) | Stage E (gestione stem) |
| `SoundEventScore` | B2-Micro-Director | B2-Micro-Engineer |
| `SceneEvent` | B2-Micro-Director | B2-Micro-Engineer |
| `AmbientEvent` | B2-Micro-Director | B2-Micro-Engineer |
| `SfxEvent` | B2-Micro-Director | B2-Micro-Engineer |
| `StingEvent` | B2-Micro-Director | B2-Micro-Engineer |
| `IntegratedCueSheet` | B2-Micro (mono o Engineer) | Stage E |
| `MicroCueAutomation` | B2-Micro (dentro IntegratedCueSheet) | Stage E |
| `SoundShoppingItem` | B2-Micro (dentro IntegratedCueSheet) | Stage D2 |

---

### 7. Principi di Stabilità

#### 7.1 Idempotenza Blindata (Master Registry)
Ogni stadio controlla tre fonti prima di agire:
1. **Filesystem**: il file output esiste su disco?
2. **Redis Registry**: il task è `COMPLETED` nell'Hash `dias:registry:{book_id}`?
3. **Redis Queues**: il messaggio è presente nella coda?

Se il file esiste, lo carica e salta l'esecuzione LLM.

#### 7.2 Architettura "Linked-but-Independent" (DIAS vs ARIA)
- **DIAS** è il Narrative Director (LXC Brain). Gestisce il ciclo di vita del libro.
- **ARIA** è il Cuore Esecutivo (Windows GPU). Gestisce inferenza e produzione audio.
- La comunicazione avviene via Redis. I crash su un nodo non bloccano l'altro.

#### 7.3 File Naming Convention
I file seguono lo standard `hyphenated`:
`{BookID}-chunk-{000}-scenes-{YYYYMMDD_HHMMSS}.{json|wav}`

#### 7.4 Resilienza Gemini (Rate Limiting)
ARIA centralizza il pacing. DIAS attende fino a 20 minuti una risposta, permettendo ad ARIA di gestire i periodi di cooldown (429/503) senza far fallire la pipeline.

---

### 8. Navigazione Documentazione

| Documento | Contenuto |
| :--- | :--- |
| [dias-workflow-logic.md](./dias-workflow-logic.md) | Mappatura completa degli stage, flusso B2 con le due modalità |
| [dias-inventory.md](./dias-inventory.md) | Inventario tecnico di tutti i file Python, prompt YAML, modelli |
| [technical-reference.md](./technical-reference.md) | Specifiche low-level: deployment, SOPS/Age, Redis, schemi JSON |
| [production-standard.md](./production-standard.md) | Standard qualità voce (Formula Oscar), punteggiatura audio, sound design quantitativo |
| [dias-aria-integration-master.md](./dias-aria-integration-master.md) | Contratto tecnico DIAS-ARIA: ACE-Step, queue Redis, timing, HTDemucs |
| [preproduction-guide.md](./preproduction-guide.md) | Guida pratica Stage 0, Casting, Dashboard |
| [prompt-evolution.md](./prompt-evolution.md) | Storia e registro versioni prompt (Stage 0, B, B2, C) |

---

*Ultimo aggiornamento: 17 Aprile 2026 — v7.0: Sound-on-Demand v4.1, architettura Director/Engineer, rimozione riferimenti ai vecchi sistemi (Redis catalog, MusicGen, AudioLDM, sound library).*
