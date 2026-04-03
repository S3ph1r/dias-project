# DIAS Dashboard V3 — Specifica Tecnica
## "Studio di Produzione Digitale" — Web Interface Completa

**Data**: 25 Marzo 2026  
**Versione**: 3.0  
**Complementa**: `blueprint_v3.md`  
**Stack attuale**: SvelteKit + Vite + FastAPI (API Hub) + Redis

---

## 1. Stato Attuale (V2 — Baseline)

La dashboard esistente è un'applicazione SvelteKit single-page (`/src/dashboard/src/routes/+page.svelte`) che offre già:

| Funzionalità | Stato | API Hub Endpoint |
|---|---|---|
| Lista progetti disponibili | ✅ | `GET /projects` |
| Dettaglio progetto + progresso stage | ✅ | `GET /projects/{id}` |
| Resume pipeline con voice override | ✅ | `POST /projects/{id}/resume` |
| Reset di uno stage | ✅ | `DELETE /projects/{id}/stages/{stage}` |
| Info voci disponibili (ARIA) | ✅ | `GET /info/voices` |
| Quota Gemini giornaliera | ✅ | `GET /info/quota` |
| Nodi ARIA online | ✅ | `GET /aria/nodes` |
| Push singola scena a Stage D | ✅ | `POST /projects/{id}/push_scene` |
| Chapter Timeline (Navigazione) | ✅ | `GET /projects/{id}/chapters` |
| Persistent Audio Player (Global) | ✅ | `--` |
| Audio Inspector (Waveform & QC) | ✅ | `GET /.../metrics` |
| **Project Upload & Stage 0** | ⚙️ | `POST /projects/upload` |
| **Casting & Character Analysis** | ⏳ | -- |

**Limitazione principale:** tutto è in un'unica pagina. Non c'è navigazione per capitolo, nessuna visualizzazione audio, nessuna pre-produzione interattiva. La V3 mantiene questa base e la espande con un sistema di## 2. Architettura dei Dati — Multi-Progetto Isolata

A partire dallo Sprint 4, DIAS adotta una struttura **Project-Centric** in cui ogni libro è un'entità isolata nel filesystem. Questo elimina le cartelle globali per stage e previene collisioni tra progetti diversi.

### 2.1 Struttura della Cartella Progetto
Tutti i dati risiedono in `data/projects/{project_id}/`:

```text
data/projects/{project_id}/
├── source/               # File originale caricato via Dashboard (PDF, EPUB, DOCX)
├── stages/               # Dati elaborati (Pipeline Output)
│   ├── stage_a/          # Testo estratto e chunked (JSON)
│   ├── stage_b/          # Analisi Semantica (JSON) e Profili Capitolo
│   ├── stage_c/          # Scene Scripts (Regia Audio)
│   ├── stage_d/          # Voice Gen (WAV + Metadata JSON)
│   ├── stage_e/          # Musica (Stem A, B, C) [NEW V3]
│   └── stage_f/          # Capitoli Mixati (WAV) [NEW V3]
├── config.json           # Configurazione progetto (Stato, Fingerprint)
├── casting.json          # Mappa Attore -> Voce (Assegnazioni Project-wide)
└── sound_palette.json    # Sound Identity e Palette musicale scelta
```

### 2.2 Accesso ai Media
L'API Hub (`main.py`) monta la root dei progetti come static asset server su `/static/projects/`. 
Esempio di URL dell'audio per una scena:
`/static/projects/Cronache-del-Silicio/stages/stage_d/output/cap-001-scene-001.wav`
└── Cronache-del-Silicio/
│       ├── project.json                           ← config, casting, palette scelta
│       ├── casting.json                           ← voce per ogni personaggio
│       ├── soundplan.json                         ← palette + sound identity
│       └── book_fingerprint.json                  ← output di Stage 0
│
└── uploads/                                       ← [NEW V3] PDF/EPUB caricati via web
    └── Cronache-del-Silicio.pdf
```

### 2.2 Gestione Multi-Progetto

Ogni progetto è **completamente isolato** dal suo `project_id`. Le code Redis usano il `project_id` come namespace:
```
dias:registry:{project_id}
dias:checkpoint:{project_id}
dias:control:{project_id}:*
```

La Dashboard lista tutti i progetti trovati scansionando `data/stage_a/output/` per i prefissi unici — questo è già implementato nell'API Hub (`GET /projects`). In V3, la fonte autoritativa diventa `projects/{project_id}/project.json`.

---

## 3. Architettura Dashboard V3 — Le Tre Aree

La Dashboard V3 si articola in tre aree di navigazione principali, accessibili via sidebar:

```
/                     → Home / Lista Progetti
/projects/[id]        → Progetto Attivo (routing principale)
  /pre-production     → Area 1: Pre-Produzione
  /studio             → Area 2: Cabina di Regia (produzione live)
  /qc                 → Area 3: Quality Control
/settings             → Configurazione nodi ARIA, quote, voci
```

### Area 1: Pre-Produzione (`/projects/[id]/pre-production`)

**Quando appare:** Prima dell'avvio della pipeline, quando `book_fingerprint.json` è stato generato da Stage 0 ma `casting.json` non è ancora confermato.

**Componenti UI:**

**BookMap:** Visualizzazione strutturale del libro. Ogni capitolo è una barra orizzontale proporzionale alla sua lunghezza in parole. Codice colore:
- 🔵 Lungo (verrà spezzato in sub-chunk)
- ⚪ Normale  
- 🟡 Breve (verrà aggregato con il successivo)

Click su un capitolo → rivelazione laterale con personaggi identificati in quel capitolo.

**CastingPanel:** Lista personaggi estratti da Stage 0 con frequenza stimata di battute. Per ogni personaggio: dropdown voce (le voci disponibili vengono da `GET /info/voices`), badge ruolo (protagonista/secondario/antagonista), pulsante "Preview 15s" che chiama un endpoint TTS live.

**SoundPaletteSelector:** Tre card con nome palette, descrizione testuale e un pulsante "Ascolta 30s" che genera un breve sample via ARIA/AudioCraft. L'utente ne sceglie una. Campo opzionale per descrizione custom.

**ProductionLevelToggle:** Semplice (solo voce) / Standard (voce + musica) / Radiofilm (voce + musica + effetti + multi-voce).

Alla conferma, il sistema scrive `casting.json` e `soundplan.json` e sblocca il pulsante "Avvia Pipeline".

---

### Area 2: Cabina di Regia (`/projects/[id]/studio`)

**Quando appare:** Durante e dopo la produzione. È la schermata principale di monitoring.

**ChapterTimeline (componente centrale):**
Una lista verticale di capitoli, ognuno con:
- Barra di progresso scene completate/totali
- Icone stato: ⬜ attesa → 🔵 elaborazione → 🟡 voce pronta → 🟢 completato
- Badge degli stage attivi (es. "B ✓ C ✓ D 12/38 E ⏳")
- Click → espansione con lista scene

**SceneTable (espansione capitolo):**
Per ogni scena:
- Numero scena, durata stimata, voce assegnata
- Status: pending / generated / mixed
- Mini-player audio (se WAV disponibile) con playback diretto
- Pulsante "Retry" per rigenerare solo quella scena
- Pulsante "Override Voce" per cambiare il voice_id senza riprocessare Stage C

**PipelineControl (sidebar destra):**
- Stato generale (Running / Paused / Idle)
- Pulsanti: Resume / Pause / Stop
- ARIA Node status: hostname, modello caricato, VRAM disponibile
- Gemini Quota bar con reset time
- Log stream in tempo reale (ultimi 20 messaggi da Redis pub/sub)

**AnchorMap (overlay opzionale su ChapterTimeline):**
Dopo che B2 ha processato un capitolo, i `structural_anchors` appaiono come marcatori verticali sulla timeline del capitolo con il tipo (pivot, shift, ecc.) e la durata della sospensione.

---

### Area 3: Quality Control (`/projects/[id]/qc`)

**Quando appare:** Non appena il primo WAV è disponibile. Usabile in parallelo alla produzione.

**SceneInspector (componente principale):**
Selezione scena da una dropdown. Carica:
- Player audio full-width con waveform visualizzata (SVG inline generata lato server)
- Pannello metriche:
  - **Pitch Contour** (curva F0 nel tempo)
  - **Energy RMS** (intensità)
  - **Pause Map** (barre verticali nei punti di silenzio con durata)

Se esiste un WAV di riferimento ElevenLabs nella cartella `analysis/`:
- Toggle "Confronto EL" → overlay delle metriche EL in rosso, DIAS in blu
- **AutoSuggest:** box con i suggerimenti automatici (come quelli del `summary.txt` esistente) — es. *"Pitch std < EL: aggiungi 'with natural pitch variation' all'istruzione"*
- Pulsante "Applica Suggerimento" → prepopola il campo `qwen3_instruct` override

**BatchReport (tab):**
Tabella di tutte le scene completate con score:
- `pitch_score`: deviazione standard del pitch (più alta = più espressivo)
- `pause_count`: numero di pause
- `dynamic_range_db`: dinamica vocale
- `quality_flag`: 🟢 OK / 🟡 Attenzione (pause anomale) / 🔴 Problema (silenzio eccessivo)

Filtro per capitolo, voce, flag. Permette di identificare batch di scene da rigenerare.

**WaveformBatch (tab):**
Griglia miniaturizzata delle waveform di tutte le scene di un capitolo. Colpo d'occhio visivo: se una waveform è "piatta" è immediatamente visibile.

---

## 4. Caricamento File da Remoto

### 4.1 Flusso Upload

Endpoint da aggiungere: `POST /projects/upload`

Il frontend mostra un drop-zone che accetta PDF/EPUB/DOCX. Il file viene caricato sul server, salvato in `uploads/{project_id}/` e viene triggerato Stage 0 (Book Intelligence). Una progress bar mostra lo stato dell'analisi preliminare (in genere 30-60 secondi per un romanzo).

```typescript
// api.ts — nuovo endpoint
export async function uploadBook(file: File): Promise<{ project_id: string; status: string }> {
    const form = new FormData();
    form.append('file', file);
    const res = await fetch(`${API_BASE}/projects/upload`, { method: 'POST', body: form });
    return res.json();
}
```

### 4.2 Accesso Remoto

La Dashboard è già esposta su `0.0.0.0:5173` — accessibile da qualsiasi browser nella rete locale (e tramite VPN/tunnel per accesso remoto). Non è necessaria autenticazione per uso domestico; per deploy pubblico si può aggiungere un layer di Basic Auth via Nginx in reverse proxy.

L'API Hub (`0.0.0.0:8000`) serve sia la Dashboard che eventuali client REST esterni. I file audio prodotti sono serviti direttamente via `GET /projects/{id}/output/{filename}` per il playback nel browser.

---

## 5. Nuovi Endpoint API Hub Necessari

| Endpoint | Metodo | Scopo |
|---|---|---|
| `/projects/upload` | POST | Carica PDF/EPUB, avvia Stage 0 |
| `/projects/{id}/fingerprint` | GET | Risultato Stage 0 (personaggi, capitoli) |
| `/projects/{id}/casting` | PUT | Salva configurazione casting voci |
| `/projects/{id}/soundplan` | PUT | Salva palette scelta |
| `/projects/{id}/chapters` | GET | Mappa capitoli con stato per ChapterTimeline |
| `/projects/{id}/chapters/{cap}/scenes` | GET | Lista scene di un capitolo con status |
| `/projects/{id}/scenes/{scene_id}/audio` | GET | Stream WAV per mini-player |
| `/projects/{id}/scenes/{scene_id}/metrics` | GET | Metriche acustiche (pitch, RMS, pauses) |
| `/projects/{id}/scenes/{scene_id}/retry` | POST | Rigenera una singola scena |
| `/projects/{id}/scenes/{scene_id}/override` | PATCH | Applica override instruct/voice_id |
| `/projects/{id}/qc/batch` | GET | Report qualità aggregato tutte le scene |

---

## 6. Stack Tecnico — Nessun Cambio Architetturale

- **Frontend:** SvelteKit (esistente) — si aggiungono route e componenti
- **Backend API:** FastAPI (esistente) — si aggiungono endpoint
- **Analisi Audio:** `librosa` + `scipy` + `matplotlib` già installati nel `.venv`
- **Charts:** SVG inline generati lato server in Python (nessuna dipendenza JS aggiuntiva)
- **Upload:** `python-multipart` per FastAPI (da aggiungere ai requirements)
- **WebSocket/Streaming:** FastAPI supporta SSE (Server-Sent Events) per il log stream in tempo reale — da aggiungere per la cabina di regia

---

## 7. Roadmap Incrementale — 5 Sprint

### Sprint 1 — Multi-Progetto e Navigazione *(priorità immediata)*

**Obiettivo:** Dalla singola pagina a un'app con routing e gestione multi-progetto.

Cosa si aggiunge:
- Routing SvelteKit: `/projects`, `/projects/[id]/studio`
- Sidebar di navigazione con lista progetti
- ChapterTimeline (senza player audio — solo stati)
- API: `GET /projects/{id}/chapters` con aggregazione per capitolo dei file esistenti in `data/stage_c/`

**Impatto sulla produzione:** Nessuno — è solo un miglioramento visivo. Il Resume continua a funzionare esattamente come prima.

---

### Sprint 2 — Mini-Player e Scene Detail *(dopo completamento voce)*

**Obiettivo:** Dare all'utente il controllo fine sulla singola scena.

Cosa si aggiunge:
- SceneTable con mini-player (chiama `GET /projects/{id}/scenes/{id}/audio`)
- Pulsante Override Voce per ogni scena
- Pulsante Retry scena singola
- API: endpoint scene, audio streaming, override

**Impatto sulla produzione:** Sblocca il workflow di quality check post-generazione. L'utente può ascoltare e correggere senza dover rieseguire tutta la pipeline.

---

### Sprint 3 — Quality Control (Audio Inspector) *(dopo Sprint 2)*

**Obiettivo:** Integrare nella Dashboard il lavoro di analisi già fatto in `analysis/el_vs_qwen3/`.

Cosa si aggiunge:
- SceneInspector con waveform + pitch + energy + pauses
- BatchReport con quality score automatico
- API: `GET /projects/{id}/scenes/{id}/metrics` (wrappa `librosa` lato server)
- AutoSuggest sul `qwen3_instruct` basato sulle metriche

**Impatto sulla produzione:** Permette di ottimizzare sistematicamente le istruzioni Qwen3 basandosi su dati oggettivi, non solo sull'ascolto.

---

### Sprint 4 — Pre-Produzione (Stage 0 + Casting) *(quando Stage 0 è implementato)*

**Obiettivo:** Dare all'utente il controllo creativo prima dell'avvio.

Cosa si aggiunge:
- Upload PDF/EPUB via drag-and-drop
- BookMap con struttura capitoli
- CastingPanel con anteprima voci
- SoundPaletteSelector con sample audio
- API: upload, fingerprint, casting, soundplan

**Impatto sulla produzione:** Abilita il workflow multi-voce di V3. Senza questo sprint, le voci dei personaggi non possono essere configurate.

---

### Sprint 5 — Musica e Mix *(quando Stage E/F sono implementati)*

**Obiettivo:** Estendere la Dashboard per la produzione musicale.

Cosa si aggiunge:
- AnchorMap sulle timeline dei capitoli (visualizza structural_anchors di B2)
- StemPlayer: player multi-traccia per ascoltare voce / atmosfera / leitmotif separatamente
- MixPreview: ascolto del capitolo mixato da Stage F
- Controlli mix: regolazione manuale volume stem per capitolo

**Impatto sulla produzione:** Rende il mixing trasparente e controllabile dall'utente senza accedere a FFmpeg direttamente.

---

## 8. Integrazione con la Pipeline — Il Data Contract

La Dashboard non è mai "read-only". Può influenzare la pipeline in tre momenti:

**Pre-avvio** (Prima di Stage A):
Dashboard scrive → `projects/{id}/casting.json` e `soundplan.json`
Pipeline legge → Stage C usa il casting, Stage B2 usa la palette

**Durante la produzione** (Override in-flight):
Dashboard scrive → Redis: `dias:control:{id}:voice_override`
Pipeline legge → Stage D al prossimo ciclo applica il nuovo voice_id

**Post-generazione** (Quality correction):
Dashboard scrive → `data/stage_c/output/{scene}.json` (campo `qwen3_instruct` aggiornato)
Pipeline legge → Stage D, su comando di retry, rilancia quella scena specifica

Questo contratto a tre livelli permette all'utente di intervenire in qualsiasi momento senza dover riavviare l'intera pipeline.

---

*Fine della Specifica Tecnica Dashboard V3*  
*Documento complementare a `blueprint_v3.md` — da usare come riferimento per lo sviluppo incrementale degli Sprint.*
