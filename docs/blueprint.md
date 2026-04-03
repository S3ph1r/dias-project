# DIAS - Distributed Immersive Audiobook System
## Master Blueprint v6.3 (ARIA Gateway & Cloud Decoupling)

**Data**: 03 Aprile 2026  
**Status**: In Produzione (Stage 0-D validati E2E con Serial Orchestrator)  
**Target Hardware**: Brain (LXC Backend) + PC Gaming (ARIA GPU Worker)  
**NH-Mini Compliance**: Pienamente aderente a `.project-context` e `description-contracts.mdc`

---

### 1. Vision e Architettura

DIAS (Distributed Immersive Audiobook System) è concepito come un **Regista Narrativo** che orchestra una pipeline distribuita per trasformare testi letterari in prodotti audio cinematografici.

### 1.1 Architettura "Universal State Bus" (Redis 120)
> Il sistema si basa sulla centralizzazione assoluta di Redis (LXC 190 -> 120) come bus di stato universale e memoria condivisa tra il Brain (LXC 190) e i Worker (Node 139).

Il sistema segue una separazione netta tra la gestione del progetto e la fornitura di servizi di inferenza:
- **Il Brain (Ruolo: Regia)**: Gestisce il ciclo di vita dell'opera (Stadi 0-G). Utilizza un **Master Registry** per tracciare il progresso. Può essere ospitato su qualsiasi nodo Linux (es. LXC).
- **Project-Centric Management (v6.5)**: Ogni libro vive in una sandbox isolata in `data/projects/{project-id}/`. L'accesso è gestito via API Hub con risoluzione case-insensitive per garantire compatibilità tra Web e OS Linux. (Vedi [Guida Pre-produzione](./preproduction-guide.md)).
- **L'Infrastruttura (Ruolo: Stato)**: Il "sistema nervoso" centrale (Redis). Ospita le code e i registri globali. Funge da punto di incontro agnostico.
- **Il Worker (Ruolo: Esecuzione)**: Il motore di inferenza (ARIA, GPU). Vive indipendentemente e serve qualsiasi client tramite le code Redis.
- **Flessibilità di Deployment**: Ogni ruolo è totalmente disaccoppiato. La posizione fisica dei nodi (LXC, PC dedicati, Cloud) è definita dalla configurazione (`.env`, `dias.yaml`) e non influisce sulla logica del codice.

### 1.2 Orchestrazione "Serial-Serial Handshake" (Marzo 2026)
A differenza del modello streaming concorrente (v6.1), la v6.2 adotta un approccio a **Handshake Seriale**:
- **Consistenza Totale**: Uno stadio non inizia a processare un libro finché lo stadio precedente non ha completato **tutti** i chunk e li ha persistiti correttamente su disco.
- **Brain Orchestrator**: Il modulo `orchestrator.py` funge da supervisore, avviando i worker necessari, monitorando lo stato delle code Redis e confermando il passaggio di mano tra stadi (es. Stage B FINITO -> Stop Stage B -> Start Stage C).
- **Resilienza NAT**: Questo approccio è ottimale per ambiente LXC e previene la congestione delle code in caso di interruzioni di rete o crash del PC Gaming.

---

### 2. Architettura Sequenziale a 9 Stadi (Intelligence Driven)

0.  **[Stage 0] BookIntelligence**: Estrazione "DNA" del libro: mappa capitoli, personaggi parlanti (18+) e palette sonore. (Vedi [Inventory](./dias-component-inventory.md)).
1.  **[A] TextIngester**: Estrazione da PDF/EPUB e chunking grezzo (CPU).
2.  **[B] SemanticAnalyzer**: Analisi emotiva macro, speaking styles e marker narrativi.
3.  **[B2] SoundDirector**: Analisi strutturale per il soundscape: individua i *Structural Anchors*.
4.  **[C] SceneDirector**: Segmentazione dinamica per *Emotional Beat* e fonetica.
5.  **[D] VoiceGenProxy**: Impacchettamento payload e delega ad ARIA.
6.  **[E] MusicGenerator**: Produzione soundscape a tre livelli: Tappeto Atmosferico, Leitmotif e Sting.
7.  **[F] AudioMixer**: Mixaggio multi-stem voce/musica/sfx con ducking adattivo.
8.  **[G] MasteringEngine**: Finalizzazione MP3, metadati e Loudness -16 LUFS.

---

### 3. Workflow Tecnico Dettagliato (v6.8)

| Fase | Componente | Azione Dashboard | Backend / Codebase | Output / Persistenza | Consumatore |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **0. Intel** | **Stage 0** | `New Project` | Gemini analizza il testo intero | `fingerprint.json` | Regista (Casting) |
| **1. Regia** | **Dossier** | `Save Casting` | Dashboard UI (Svelte) | `preproduction.json` | Stage D |
| **2. Ingest** | **Stage A** | `Resume` | PDF → TXT → Chunk (~2500 parole) | `stages/stage_a/output/` | Stage B |
| **3. Semant.** | **Stage B** | Automatico | Analisi emozionale macro | `stages/stage_b/output/` | Stage C |
| **4. Anchor** | **Stage B2** | Automatico | Identifica punti di stacco musicali | `stages/stage_b2/output/` | Stage E |
| **5. Scena** | **Stage C** | Automatico | Segmentazione Emotional Beats | `stages/stage_c/output/` | Stage D |
| **6. Sintesi** | **Stage D** | Automatico | **Voice Proxy (ARIA/Qwen3)** | `.wav` in `stage_d/` | Stage F |
| **7. Music** | **Stage E** | Automatico | **Music Proxy (ARIA/MusicGen)** | `.wav` in `stage_e/` | Stage F |
| **8. Final** | **Stage F/G** | Automatico | Mixing multi-stem & Mastering | `final/{id}.mp3` | Utente Finale |

---

### 4. Navigazione Conoscenza (Index Integrato)

Tutta la conoscenza tecnica di DIAS è centralizzata qui:
- 🏆 **[production-standard.md](./production-standard.md)**: **LO STANDARD.** Formula Oscar (0.75), parametri tecnici, fonetica e punteggiatura audio.
- 📜 **[prompt-evolution.md](./prompt-evolution.md)**: Storia e registro delle versioni dei prompt (Stage 0, B, C).
- 🗂️ **[inventory.md](./dias-inventory.md)**: Inventario universale di moduli, dashboard e tools.
- 🎬 **[preproduction-guide.md](./preproduction-guide.md)**: Guida pratica al casting e al file `preproduction.json`.
- ⚙️ **[technical-reference.md](./technical-reference.md)**: Manuale Sviluppatore (Log, Debug, Systemd, SOPS).

---

### 5. Principi Fondamentali di Stabilità e Self-Healing

#### 5.1 Gemini Quota & Rate Limiting (v2.0 - ARIA Delegated)
Per prevenire i blocchi sull'API Google (Flash-Lite) e gestire il Free Tier in modo intelligente, DIAS ha **delegato interamente** la logica ad ARIA:
- **ARIA Smart Gateway**: ARIA (LXC 139) centralizza il pacing (30s tra chiamate) e il lockout globale (10m su errore 429).
- **Dumb Client**: DIAS non possiede più API Key. Invia i task a Redis e ARIA si occupa della conformità alle quote.
- **Extended Resilience**: DIAS attende fino a 20 minuti una risposta da ARIA, permettendo al Gateway di gestire i periodi di cooldown senza far fallire la pipeline.

#### 5.2 Stage 0 Hardening (v6.8 - Sequential Strategy)
Per gestire libri di grandi dimensioni senza perdere il contesto globale o sforare le quote:
- **Recursive Processing**: Divisione in blocchi con iniezione del riassunto e del JSON precedente come "Context Preamble".
- **Coerenza Identitaria**: Il Character Bible viene costruito incrementalmente, garantendo che ogni nuovo blocco rispetti i casting già definiti.
- **Prompts Esternalizzati**: Ogni stadio (0, B, C) utilizza template YAML versionati (`config/prompts/`), permettendo di affinare la qualità della regia senza modificare il codice sorgente del sistema.
- **Pacing Manuale**: Inserimento di pause tecniche (60s) tra gli step ad alto consumo di token. (Vedi dettagli in **[Guida Pre-produzione](./preproduction-guide.md)**).

#### 5.3 Master Registry: Il Sistema a "Tripla Verifica"
Per garantire resilienza a crash e riavvii, DIAS convalida ogni task incrociando tre fonti:
1.  **Filesystem (Realtà Fisica)**: Il file `.wav` o `.json` finale esiste davvero su disco?
2.  **Redis Registry (Stato Volatile)**: Il task è mappato nell'Hash `dias:registry:{book_id}` come `COMPLETED`? (Stati: `PENDING`, `IN_FLIGHT`, `COMPLETED`, `FAILED`).
3.  **Redis Queues (Trasporto)**: Il messaggio è fisicamente presente nella coda di ARIA?

#### 5.4 Architettura "Linked-but-Independent" (DIAS vs ARIA)
DIAS è il **Narrative Director** (LXC Brain), ARIA è il **Cuore Esecutivo** (Windows GPU).
- **Separazione Netta**: DIAS gestisce il Libro (Stadi A-G), ARIA gestisce l'Inferenza (GPU, VRAM, Modelli).
- **Universal Bus**: La comunicazione avviene via Redis. Se DIAS crasha, ARIA finisce il lavoro. Se ARIA crasha, DIAS rileva lo "Zombie Task" (>20m `IN_FLIGHT`) e lo riaccoda.
- **Agnostic Proxy**: DIAS non ha API Key; invia task "agnostici" e riceve risultati, permettendo di cambiare backend (es. da Qwen3 a Fish) senza toccare la pipeline.

#### 5.5 Master Registry & Skipping Logic (Idempotenza Blindata)
Se un processo si interrompe, DIAS non riparte da zero. La decisione di "cosa fare" è basata sul **Master Registry (Redis Hash)**:
- **ActiveTaskTracker**: Usato in Stage B, C e D per tracciare ogni chunk/scena (`PENDING`, `IN_FLIGHT`, `COMPLETED`).
- **Tripla Verifica**: Prima di agire, DIAS controlla:
    1. Se il file esiste fisicamente su disco (Filesystem).
    2. Se il task è segnato come `COMPLETED` nel registro (Redis).
    3. Se il risultato è già presente nella casella postale (Mailbox).
- Se il file esiste, lo carica istantaneamente, salta l'esecuzione dell'LLM (risparmiando token) e passa allo stadio successivo.

#### 5.6 File Naming Convention
I file seguono *esclusivamente* lo standard `hyphenated`:
`{BookID}-chunk-{000}-scenes-{YYYYMMDD_HHMMSS}.{json|wav}`

---

### 6. Approfondimento degli Stage Core

#### Stage C: Scene Director (La "Regia Fine")
Lo Stage C è il cuore qualitativo di DIAS.
- **Limiti e Efficienza (ARIA Cloud Gateway)**: Il sistema è ottimizzato per il Free Tier di Google (**20 chiamate/giorno**). La gestione delle quote e del rate limiting è ora delegata interamente ad ARIA tramite il `GatewayClient`.
- **Emotional Beats**: Non suddivide i blocchi testuali meccanicamente (es. a 2500 parole), ma delega a Gemini di spezzare la narrazione nei momenti in cui avviene un cambio netto di tono (es. da riflessione a dialogo teso).
- **Master JSON & Scene Splitting**: Lo Stage C produce inicialmente un unico **Master JSON** contenente l'array di tutte le scene individuate nel chunk. Questo file viene poi processato per generare i task individuali per lo Stage D.
- **Isolamento Strutturale**: Obbliga ad isolare titoli di libri o capitoli in scene singole (per evitare che il TTS li legga a velocità sostenuta incollati al primo paragrafo).
- **Normalizzazione Fonetica Assoluta**: Il testo generato (`clean_text`) non contiene alcun tag in linea. I numeri vengono decodificati in lettere ("2042" → "duemilaquarantadue") e le pronunce ambigue vengono assistite da accenti testuali (es. "pàtina", "futòn").
- **Standard Teatrale Qwen3-TTS (v1.7b)**: Implementa la "Formula C" (**Ref_text + Subtalker 0.75**) per una prosodia sovrapponibile a ElevenLabs. Vedi la [Guida Tecnica](./production-standard.md) per i dettagli del benchmark.
- **Istruzioni Qwen3-TTS (v1.5 Theatrical)**: Implementa la struttura **Anchor + Variation**. Ogni istruzione inizia con un'ancora vocale fissa (`narrator_base_tone`) per stabilizzare il tono del modello, seguita da variazioni fisiche e ritmiche basate sul contesto di Stage B (arc narrativo, speaking styles).
- **Prompting Esternalizzato**: I template di regia sono isolati in file YAML (`config/prompts/stage_c/v1.4_contextual.yaml`), permettendo A/B testing e modifiche "hot" senza toccare il codice.
- **Supporto Dialoghi**: Individua i cambi di speaker e genera `dialogue_notes` per aiutare il TTS a differenziare le voci.

#### Stage D: Voice Generator Proxy (La Delega ad ARIA)
Lo Stage D risolve dinamicamente la voce e le istruzioni TTS basandosi sul **Dossier di Pre-produzione** e sugli instruct generati dallo Stage C.
- **Ruolo di Proxy**: Non esegue inferenza LLM propria; riceve il campo `qwen3_instruct` (o `fish_instruct`) già confezionato dallo Stage C per garantire coerenza espressiva.
- **Logica di Precedenza Vocale (v6.6)**: Risolve il `voice_id` con la seguente priorità:
    1. **Casting Personaggio**: Se lo speaker della scena ha una voce assegnata in `preproduction.json`.
    2. **Global Voice**: Se la scena è narrativa o lo speaker non è mappato, usa il Narratore scelto nel carosello 3D.
    3. **System Default**: Fallback su `luca` se nessuna configurazione è presente.
- **Routing Dinamico**: Il backend di target è definito da `model_id` (es. `qwen3-tts-1.7b`).
- **Configurabilità Centralizzata (v2.2)**: Legge parametri tecnici (Temperature, Top_P) direttamente da `dias.yaml`.
- **Resilienza e Callback**: Inserisce nel payload `callback_key` ed entra in uno stato `BRPOP` congelato, attendendo il file da ARIA (PC 139).

#### Stage E: Music Generator Proxy (La Colonna Sonora Cinematica)
Lo Stage E implementa un modello a **tre stem** per un soundscape cinematico:
- **Stem A — Tappeto Atmosferico**: File lungo (~10 min/chunk), generato una volta per capitolo da `primary_emotion` + `setting` di Stage B. Crea il "pavimento" sonoro continuo.
- **Stem B — Leitmotif**: Micro-stem (15-30s) associati a personaggi/luoghi specifici, inseriti nelle scene dove il personaggio è protagonista (da `entities` di Stage B).
- **Stem C — Sting da Bridge**: File corti evocativi (3-8s) generati solo per i `structural_anchors` di **Stage B2** — i momenti dove la voce si sospende e la musica parla da sola.
- **Agnostic Music Proxy**: Come Stage D, DIAS delega il calcolo ad ARIA via coda `gpu:queue:music:musicgen-small`.
- **Resilienza e Skipping**: *Skipping Logic* garantisce che i file già generati non vengano riprocessati.
- **→ Vedi [Sound Design Blueprint](./sound_design_blueprint.md) per la specifica completa.**

#### Stage B2: Sound Director (Analisi Strutturale Sonora)
Stage dedicato (eseguito dopo B, prima di C) che usa un prompt LLM chirurgico per identificare i **Structural Anchors** — i punti dove la musica deve prendere il sopravvento sulla voce:
- **Trigger types**: `chapter_boundary`, `chronos_shift`, `topos_shift`, `dramatic_pivot`, `emotional_reversal`.
- **Regola di rarità**: Max 3-4 anchor per chunk (~2500 parole) per evitare la meccanicità.
- **Output**: `structural_anchors[]` + `global_sound_palette` per Stage E/F.
- **Separato da Stage B** per preservare la qualità del prompt semantico (Flash-Lite è sensibile al prompt overloading).

#### Stage F/G: Mixing e Mastering (Post-Produzione Cinematica)
- **Multi-Stem Mixing**: Voce + Stem A (Atmosfera) + Stem B (Leitmotif) + Stem C (Stings).
- **Ducking Adattivo**: -20dB durante narrazione, -14dB durante pause, voce **sospesa** durante Structural Anchors.
- **Silenzio come Strumento**: Fade a -30dB nei monologhi interni per massimizzare l'espressività.
- **Mastering Finale**: Normalizzazione a -16 LUFS e output MP3 320kbps.

---

### 7. Audio Analysis Layer (Roadmap)
DIAS integra `librosa` e `scipy` per il monitoraggio qualitativo:
- **Librerie**: `librosa`, `scipy`, `matplotlib`, `pydub`, `soundfile`.
- **Metriche**: Pitch Correlation (F0) > 0.60 e Energy Correlation (RMS) > 0.85 rispetto al reference umano.
- **Feature Future**: Silence Trimmer automatico, Breath Detection e Normalizzazione RMS adattiva pre-mixing.

---

### 8. Visione d'Insieme: Il "Radiofilm" (BBC Radio Drama Vision)
DIAS non è un semplice Text-to-Speech avanzato: è un **Radiofilm**. Il riferimento culturale è la **BBC Radio Drama** o una **Serie Netflix adattata per l'audio**. Il suono non accompagna la narrazione, ma **è** la narrazione stessa.
- **Esempio Pratico**: La voce narrante si ferma per 4 secondi, la musica sale in un accordo basso e metallico per sottolineare un momento di tensione, poi la voce riprende più bassa.
- **Layer di Memoria**: Il sistema opera su tre livelli (Libro, Capitolo, Scena) per garantire che ogni dettaglio acustico sia orchestrato dalla regia AI.

---

### 9. Strategia a Lungo Termine e Resilienza

#### 9.1 Pattern Architetturale: "Pipeline Stage Resiliente"
Il sistema DIAS ha consolidato un pattern riutilizzabile per ogni stadio:
- **Input asincrono**: Da coda Redis → Decodifica JSON.
- **Dumb Processing**: Esecuzione della logica senza gestione diretta delle API (delega ad ARIA).
- **Checkpointed Output**: Salvataggio su Filesystem + Aggiornamento Registro + Push in coda successiva.
- **Atomic Resume**: Capacità di saltare il lavoro già fatto analizzando lo stato del disco (Idempotenza).

#### 9.2 Analisi dei Rischi e Mitigazione
- **Saturazione VRAM**: Mitigata dalla gestione centralizzata delle code in ARIA (un solo modello in VRAM alla volta se necessario).
- **Quota Exhaustion**: Gestita dal lockout globale di 15m in ARIA e dalle pause manuali (60s) nello Stage 0.
- **Drift Semantico (Long Books)**: Mitigato dalla strategia di iniezione contestuale e riassunti sequenziali (v6.8).
- **Audio Quality Hallucinations**: Mitigata dal livello di analisi audio (`librosa`) per rilevare pause anomale o clipping.

---
*Ultimo aggiornamento: 03 Aprile 2026 — Restore integrale e integrazione workflow v6.8.*
