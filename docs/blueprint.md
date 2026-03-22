# DIAS - Distributed Immersive Audiobook System
## Master Blueprint v6.3 (ARIA Gateway & Cloud Decoupling)

**Data**: 13 Marzo 2026  
**Status**: In Produzione (Stage A-D validati E2E con Serial Orchestrator su "Cronache del Silicio")  
**Target Hardware**: Brain (LXC Backend) + PC Gaming (ARIA GPU Worker)  
**NH-Mini Compliance**: Pienamente aderente a `.project-context` e `description-contracts.mdc`

---

### 1. Vision e Architettura

DIAS (Distributed Immersive Audiobook System) è concepito come un **Regista Narrativo** che orchestra una pipeline distribuita per trasformare testi letterari in prodotti audio cinematografici.

### 1.1 Architettura "Universal State Bus" (Redis 120)
> Il sistema si basa sulla centralizzazione assoluta di Redis (LXC 190 -> 120) come bus di stato universale e memoria condivisa tra il Brain (LXC 190) e i Worker (Node 139).
Il sistema segue una separazione netta tra la gestione del progetto e la fornitura di servizi di inferenza:
- **Il Brain (Ruolo: Regia)**: Gestisce il ciclo di vita dell'opera (Stadi A-G). Utilizza un **Master Registry** per tracciare il progresso. Può essere ospitato su qualsiasi nodo Linux (es. LXC).
- **L'Infrastruttura (Ruolo: Stato)**: Il "sistema nervoso" centrale (Redis). Ospita le code e i registri globali. Funge da punto di incontro agnostico.
- **Il Worker (Ruolo: Esecuzione)**: Il motore di inferenza (ARIA, GPU). Vive indipendentemente e serve qualsiasi client tramite le code Redis.
- **Flessibilità di Deployment**: Ogni ruolo è totalmente disaccoppiato. La posizione fisica dei nodi (LXC, PC dedicati, Cloud) è definita dalla configurazione (`.env`, `dias.yaml`) e non influisce sulla logica del codice.

### 1.2 Orchestrazione "Serial-Serial Handshake" (Marzo 2026)
A differenza del modello streaming concorrente (v6.1), la v6.2 adotta un approccio a **Handshake Seriale**:
- **Consistenza Totale**: Uno stadio non inizia a processare un libro finché lo stadio precedente non ha completato **tutti** i chunk e li ha persistiti correttamente su disco.
- **Brain Orchestrator**: Il modulo `orchestrator.py` funge da supervisore, avviando i worker necessari, monitorando lo stato delle code Redis e confermando il passaggio di mano tra stadi (es. Stage B FINITO -> Stop Stage B -> Start Stage C).
- **Resilienza NAT**: Questo approccio è ottimale per ambiente LXC e previene la congestione delle code in caso di interruzioni di rete o crash del PC Gaming.

DIAS trasforma un manoscritto in un'esperienza audio immersiva, comportandosi come un regista automatizzato. Non si limita a leggere il testo, ma lo **direziona**: individua i battiti emotivi, isola i titoli per dare respiro, impiega normalizzazioni fonetiche avanzate, e infine delega l'esecuzione a motori specializzati remoti.

DIAS opera con un **Design Pattern "Agnostic Proxy"**: DIAS è il cervello (Brain), l'istanza ARIA remota è la "gola" e "l'orchestra" (GPU). DIAS concepisce i payload; ARIA esegue il calcolo neurale sui modelli (Qwen3, Fish, ecc). 

**Architettura Sequenziale a 8 Stadi** (v6.4 - Cinematic Soundscape):
1.  **[A] TextIngester**: Estrazione da PDF/EPUB e chunking grezzo (CPU).
2.  **[B] SemanticAnalyzer**: Analisi emotiva macro, speaking styles e marker narrativi. Utilizza prompt esterni versionati (`config/prompts/stage_b/`).
3.  **[B2] SoundDirector**: Analisi strutturale per il soundscape: individua i *Structural Anchors* (bridge musicali) e definisce la *Global Sound Palette* del capitolo (via ARIA Cloud Gateway). Stage dedicato, non integrato in B per preservare la qualità del prompt.
4.  **[C] SceneDirector**: Segmentazione dinamica per *Emotional Beat* e fonetica. Utilizza la logica **Anchor + Variation (v1.4)** basata sul contesto di Stage B e prompt esterni versionati (`config/prompts/stage_c/`).
5.  **[D] VoiceGenProxy**: Impacchettamento payload e delega ad ARIA. Utilizza configurazioni centralizzate per backend, voci e parametri tecnici (`dias.yaml`).
6.  **[E] MusicGenerator**: Produzione soundscape a tre livelli: Tappeto Atmosferico (Stem A), Leitmotif tematici (Stem B) e Sting per i Bridge (Stem C) (via ARIA GPU).
7.  **[F] AudioMixer**: Mixaggio multi-stem voce/musica/sfx con ducking adattivo e sospensione voce per i Structural Anchors (FFmpeg, CPU).
8.  **[G] MasteringEngine**: Finalizzazione MP3, metadati e Loudness -16 LUFS (CPU).

---

### 2. Principi Fondamentali di Stabilità e Self-Healing

#### 2.1 Gemini Quota & Rate Limiting (v2.0 - ARIA Delegated)
Per prevenire i blocchi sull'API Google (Flash-Lite) e gestire il Free Tier in modo intelligente, DIAS ha **delegato interamente** la logica ad ARIA:
- **ARIA Smart Gateway**: ARIA (LXC 139) centralizza il pacing (30s tra chiamate) e il lockout globale (10m su errore 429).
- **Dumb Client**: DIAS non possiede più API Key. Invia i task a Redis e ARIA si occupa della conformità alle quote.
- **Extended Resilience**: DIAS attende fino a 20 minuti una risposta da ARIA, permettendo al Gateway di gestire i periodi di cooldown senza far fallire la pipeline.

#### 2.2 Master Registry & Skipping Logic (Idempotenza Blindata)
Se un processo si interrompe, DIAS non riparte da zero. La decisione di "cosa fare" è basata sul **Master Registry (Redis Hash)**:
- **ActiveTaskTracker**: Usato in Stage B, C e D per tracciare ogni chunk/scena (`PENDING`, `IN_FLIGHT`, `COMPLETED`).
- **Tripla Verifica**: Prima di agire, DIAS controlla:
    1. Se il file esiste fisicamente su disco (Filesystem).
    2. Se il task è segnato come `COMPLETED` nel registro (Redis).
    3. Se il risultato è già presente nella casella postale (Mailbox).
- Se il file esiste, lo carica istantaneamente, salta l'esecuzione dell'LLM (risparmiando token) e passa allo stadio successivo.

#### 2.3 File Naming Convention
I file seguono *esclusivamente* lo standard `hyphenated`:
`{BookID}-chunk-{000}-scenes-{YYYYMMDD_HHMMSS}.{json|wav}`

---

### 3. Approfondimento degli Stage Core

#### Stage C: Scene Director (La "Regia Fine")
Lo Stage C è il cuore qualitativo di DIAS.
- **Limiti e Efficienza (ARIA Cloud Gateway)**: Il sistema è ottimizzato per il Free Tier di Google (**20 chiamate/giorno**). La gestione delle quote e del rate limiting è ora delegata interamente ad ARIA tramite il `GatewayClient`.
- **Emotional Beats**: Non suddivide i blocchi testuali meccanicamente (es. a 2500 parole), ma delega a Gemini di spezzare la narrazione nei momenti in cui avviene un cambio netto di tono (es. da riflessione a dialogo teso).
- **Master JSON & Scene Splitting**: Lo Stage C produce inicialmente un unico **Master JSON** contenente l'array di tutte le scene individuate nel chunk. Questo file viene poi processato per generare i task individuali per lo Stage D.
- **Isolamento Strutturale**: Obbliga ad isolare titoli di libri o capitoli in scene singole (per evitare che il TTS li legga a velocità sostenuta incollati al primo paragrafo).
- **Normalizzazione Fonetica Assoluta**: Il testo generato (`clean_text`) non contiene alcun tag in linea. I numeri vengono decodificati in lettere ("2042" → "duemilaquarantadue") e le pronunce ambigue vengono assistite da accenti testuali (es. "pàtina", "futòn").
- **Istruzioni Qwen3-TTS (v1.4 Anchor Logic)**: Implementa la struttura **Anchor + Variation**. Ogni istruzione inizia con un'ancora vocale fissa (`narrator_base_tone`) per stabilizzare il tono del modello, seguita da variazioni fisiche e ritmiche basate sul contesto di Stage B (arc narrativo, speaking styles).
- **Prompting Esternalizzato**: I template di regia sono isolati in file YAML (`config/prompts/stage_c/v1.4_contextual.yaml`), permettendo A/B testing e modifiche "hot" senza toccare il codice.
- **Integrazione Stage B Context**: Utilizza l'intera `macro_analysis` di Stage B per iniettare nel prompt dettagli su personaggi, arco emotivo e stili di dialogo, garantendo coerenza narrativa tra scene distanti.
- **Supporto Dialoghi**: Individua i cambi di speaker e genera `dialogue_notes` per aiutare il TTS a differenziare le voci.

#### Stage D: Voice Generator Proxy (La Delega ad ARIA)
Lo Stage D non conosce l'infrastruttura di hosting dei modelli, ma decide quale "variante" usare.
- **Routing Dinamico**: Il backend di target è definito da `model_id` (es. `qwen3-tts-1.7b` per Base o `qwen3-tts-custom` per CustomVoice).
- **Configurabilità Centralizzata (v2.2)**: Legge il modello attivo (`active_tts_backend`), le voci di default e i parametri tecnici (Temperature, Top_P) direttamente da `dias.yaml`, facilitando l'integrazione con la Dashboard per il setup del progetto.
- **Logica di Distributed Callback**: Inserisce nel payload `callback_key = "dias:callback:stage_d:{job}:{scene}"` ed entra in uno stato `BRPOP` congelato, attendendo pazientemente (fino a 900s) che ARIA generi l'audio. Per swap di modelli JIT, il timeout è esteso a 600s+ lato ARIA.
- **Resilienza e Timeout (Self-Healing)**: Se il PC ARIA è spento o il timeout scade, lo Stage D logga un errore. Grazie alla *Skipping Logic*, al riavvio del sistema il task verrà ri-accodato automaticamente.
- **Persistenza Code**: I messaggi inviati ad ARIA rimangono nella coda Redis finché ARIA non li consuma, rendendo il sistema resiliente a spegnimenti temporanei dei lavoratori GPU.

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

### 4. Flusso Operativo e Troubleshooting

### 4. Flusso Operativo e Troubleshooting

#### 4.1 File System Layout (Lo Stato Persistente)
Il filesystem non è solo un deposito, ma funge da "Database di Stato" decentralizzato. La struttura è gerarchica e speculare agli stadi:
- `data/stage_A/output/`: Contiene i `.json` dei chunk di testo estratti (Input per B/C).
- `data/stage_B/output/`: Contiene le analisi semantiche (Input per C).
- `data/stage_C/output/`: Contiene sia i *Master JSON* (array) che le singole scene `.json` (Input per D).
- `data/stage_D/output/`: Contiene i risultati delle callback ARIA con i path dei `.wav`.

**Self-Healing & Orchestrazione Avanzata**:
1. **Skipping Logic**: Se un file esiste già nel path di output, lo stage lo carica istantaneamente saltando l'inferenza.
2. **Serial Orchestrator**: Il driver `orchestrator.py` scansiona l'intero filesystem del progetto e ri-accoda automaticamente solo i task mancanti, garantendo una ripartenza "incrollabile" (Incrollabile Resume).
3. **Stage-level Retry**: Possibilità di resettare un singolo stadio via dashboard o riga di comando.

#### 4.2 Filosofia "Offline-First" e Debugging
Il sistema è progettato per essere sviluppato e testato anche senza connessione internet o API attive:
- **Mock Services**: Tramite la variabile `MOCK_SERVICES=true`, DIAS simula le chiamate Redis e API, permettendo di testare la logica di controllo.
- **Iniezione di JSON manuali**: In caso di blocco delle API Google (quota esaurita), è possibile prendere un vecchio file JSON dello Stage C, modificarlo a mano (es. cambiare un'istruzione di regia) e salvarlo nella cartella di output. Al riavvio, il sistema "berrà" il nuovo file ignorando la necessità di chiamare Gemini.
- **Isolamento dei Guasti**: Se lo Stage D fallisce (es. ARIA offline), i file degli stadi A, B e C restano validi e intatti. Non c'è mai bisogno di rifare un'analisi semantica costosa se il problema è solo nella sintesi vocale.
- **Ripristino Manuale**: Se un file JSON risulta corrotto, basta cancellarlo: la Skipping Logic lo noterà e forzerà il sistema a rigenerare solo quel pezzo specifico.

### 5. Deployment e Dashboard
DIAS espone un'interfaccia **SvelteKit (LXC 201)** moderna e reattiva che monitora il Brain in tempo reale.
La Dashboard offre:
1. **Monitoraggio Quota Gemini**: Visualizzazione della soglia giornaliera (es. 12/20) con barra di progresso e stato di blocco.
2. **Controllo Pipeline**: Tasto "Resume" globale per la ripresa automatica e tasti "Retry" (con warning) per il reset dei singoli stage.
3. **Gestione Voci (ARIA Bridge)**: Grazie all'heartbeat dinamico di ARIA, la Dashboard mostra le voci effettivamente presenti sui nodi (es. Angelo, Luca) e permette di iniettare un `voice_override` manuale per singole scene in Stage D.
4. **Project Monitor**: Barra percentuale di avanzamento globale e dettaglio dello stato di ogni file prodotto.
