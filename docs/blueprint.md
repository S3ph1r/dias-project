# DIAS - Distributed Immersive Audiobook System
## Master Blueprint v6.0 (Agnostic Architecture & Deep Logic)

**Data**: 7 Marzo 2026  
**Status**: In Produzione (Stage A-C completati, Stage D E2E validato)  
**Target Hardware**: Brain (LXC Backend) + PC Gaming (ARIA GPU Worker)  
**NH-Mini Compliance**: Pienamente aderente a `.project-context` e `description-contracts.mdc`

---

### 1. Vision e Architettura

DIAS (Distributed Immersive Audiobook System) è concepito come un **Regista Narrativo** che orchestra una pipeline distribuita per trasformare testi letterari in prodotti audio cinematografici.

### 1.1 Architettura "Linked-but-Independent" (Brain vs Worker)
> Il sistema si basa su una "Fede Comune" in Redis (LXC 120) come bus di stato universale tra il Brain (LXC 190) e i Worker (Node 139).
Il sistema segue una separazione netta tra la gestione del progetto e la fornitura di servizi di inferenza:
- **Il Brain (Ruolo: Regia)**: Gestisce il ciclo di vita dell'opera (Stadi A-G). Utilizza un **Master Registry** per tracciare il progresso. Può essere ospitato su qualsiasi nodo Linux (es. LXC).
- **L'Infrastruttura (Ruolo: Stato)**: Il "sistema nervoso" centrale (Redis). Ospita le code e i registri globali. Funge da punto di incontro agnostico.
- **Il Worker (Ruolo: Esecuzione)**: Il motore di inferenza (ARIA, GPU). Vive indipendentemente e serve qualsiasi client tramite le code Redis.
- **Flessibilità di Deployment**: Ogni ruolo è totalmente disaccoppiato. La posizione fisica dei nodi (LXC, PC dedicati, Cloud) è definita dalla configurazione (`.env`, `dias.yaml`) e non influisce sulla logica del codice.

DIAS trasforma un manoscritto in un'esperienza audio immersiva, comportandosi come un regista automatizzato. Non si limita a leggere il testo, ma lo **direziona**: individua i battiti emotivi, isola i titoli per dare respiro, impiega normalizzazioni fonetiche avanzate, e infine delega l'esecuzione a motori specializzati remoti.

DIAS opera con un **Design Pattern "Agnostic Proxy"**: DIAS è il cervello (Brain), l'istanza ARIA remota è la "gola" e "l'orchestra" (GPU). DIAS concepisce i payload; ARIA esegue il calcolo neurale sui modelli (Qwen3, Fish, ecc). 

**Architettura Sequenziale a 7 Stadi**:
1.  **[A] TextIngester**: Estrazione da PDF/EPUB e chunking grezzo (CPU).
2.  **[B] SemanticAnalyzer**: Analisi emotiva macro e marker narrativi (API Gemini).
3.  **[C] SceneDirector**: Segmentazione dinamica per *Emotional Beats*, fonetica e script TTS agnostico (API Gemini).
4.  **[D] VoiceGenProxy**: Impacchettamento payload e delega ad ARIA via code Redis. Nessuna esecuzione locale.
5.  **[E] MusicGenerator**: Produzione colonna sonora adattiva all'emozione (via ARIA GPU).
6.  **[F] AudioMixer**: Mixaggio stem voce/musica/sfx con ducking (FFmpeg, CPU).
7.  **[G] MasteringEngine**: Finalizzazione MP3, metadati e Loudness -16 LUFS (CPU).

---

### 2. Principi Fondamentali di Stabilità e Self-Healing

#### 2.1 Gemini Global Rate Limiting
Per prevenire i blocchi sull'API Google (Flash-Lite), DIAS usa un `GeminiRateLimiter` globale:
- **Cooldown Attivo**: Minimo 30 secondi di offset forzato tra chiamate.
- **Lockout per 429 ("Too Many Requests")**: Se Google respinge la chiamata per saturazione, DIAS attiva un blocco totale di **24 ore** sull'intero sistema, mettendo in pausa i workers prima di ritentare.

#### 2.2 Skipping Logic (Idempotenza Intelligente)
Se un processo si interrompe, DIAS non riparte da zero.
- Prima di chiamare Gemini o ARIA, controlla il file JSON o WAV atteso su disco (`/data/stage_X/output/`).
- Se il file esiste, lo carica istantaneamente, salta l'esecuzione dell'LLM (risparmiando token o cicli GPU), e spara il risultato nella coda dello Stage successivo.

#### 2.3 File Naming Convention
I file seguono *esclusivamente* lo standard `hyphenated`:
`{BookID}-chunk-{000}-scenes-{YYYYMMDD_HHMMSS}.{json|wav}`

---

### 3. Approfondimento degli Stage Core

#### Stage C: Scene Director (La "Regia Fine")
Lo Stage C è il cuore qualitativo di DIAS.
- **Limiti e Efficienza (Gemini Quota)**: Il sistema è ottimizzato per il Free Tier di Google (**20 chiamate/giorno**). Per massimizzare la resa, DIAS esegue **una sola chiamata API per ogni chunk** sia in Stage B che in Stage C.
- **Emotional Beats**: Non suddivide i blocchi testuali meccanicamente (es. a 2500 parole), ma delega a Gemini di spezzare la narrazione nei momenti in cui avviene un cambio netto di tono (es. da riflessione a dialogo teso).
- **Master JSON & Scene Splitting**: Lo Stage C produce inizialmente un unico **Master JSON** contenente l'array di tutte le scene individuate nel chunk. Questo file viene poi processato per generare **un file JSON individuale per ogni scena**, facilitando il tracciamento e la ripresa del lavoro in Stage D.
- **Isolamento Strutturale**: Obbliga ad isolare titoli di libri o capitoli in scene singole (per evitare che il TTS li legga a velocità sostenuta incollati al primo paragrafo).
- **Normalizzazione Fonetica Assoluta**: Il testo generato (`clean_text`) non contiene alcun tag in linea. I numeri vengono decodificati in lettere ("2042" → "duemilaquarantadue") e le pronunce ambigue vengono assistite da accenti testuali (es. "pàtina", "futòn").
- **Costruzione del Parametro "Instruct"**: Genera un parametro multivariabile in lingua inglese basato su *Tone*, *Rhythm* e *Attitude* (ad es. `Tone: Dark. Rhythm: Fast. Attitude: Hesitant.`). 

#### Stage D: Voice Generator Proxy (La Delega ad ARIA)
Lo Stage D non conosce l'infrastruttura di hosting dei modelli. Costruisce un payload SOA v2.0 per ARIA. 
- La coda di target è `gpu:queue:tts:qwen3-tts-1.7b`.
- **Logica di Distributed Callback**: Inserisce nel payload `callback_key = "dias:callback:stage_d:{job}:{scene}"` ed entra in uno stato `BRPOP` congelato, attendendo pazientemente (fino a 900s) che ARIA generi l'audio.
- **Resilienza e Timeout (Self-Healing)**: Se il PC ARIA è spento o il timeout di 15m scade, lo Stage D logga un errore e **non salva** il file di output per quella scena. Grazie alla *Skipping Logic*, al riavvio successivo del sistema, DIAS rileverà la mancanza del file e riaccoderà automaticamente la scena per una nuova generazione, garantendo che nessun contenuto venga saltato permanentemente.
- **Persistenza Code**: I messaggi inviati ad ARIA rimangono nella coda Redis finché ARIA non li consuma, rendendo il sistema resiliente a spegnimenti temporanei dei lavoratori GPU.

#### Stage E: Music Generator Proxy (La Colonna Sonora Agnostica)
Lo Stage E applica la stessa filosofia di delega dello Stage D:
- **Agnostic Music Proxy**: DIAS non genera musica localmente. Lo Stage E invia un payload alla coda `gpu:queue:music:musicgen-small` monitorata da ARIA.
- **Input Narrativo (Stage B & C)**: I prompt musicali non sono casuali ma derivano dal profilo emotivo calcolato in **Stage B** (es. tensione, malinconia) e dalle durate esatte delle scene fissate in **Stage C**.
- **Resilienza e Skipping**: Anche la musica segue la *Skipping Logic*. Se al riavvio della pipeline il file musicale per una scena è già presente su disco, lo stadio lo carica saltando la delega ad ARIA.
- **Payload & Callback**: Utilizzerà un meccanismo di callback identico allo Stage D, garantendo che il Brain (DIAS) sappia esattamente quando ARIA ha terminato la composizione.

#### Stage F/G: Mixing e Mastering (Post-Produzione)
- **Intensity Curves**: Il MusicGen genera tappeti basati sull'emozione (es. `intensity_curve: [0.2, 0.3, 0.5]`).
- **Mixaggio Sidechain (Ducking)**: Lo Stage F applica un *Sidechain Ducking* automatico tramite FFmpeg (`filter_complex`). Quando la voce interviene, la traccia musicale abbassa il gain (8-15dB) per garantire massima intelligibilità.
- **Mastering Finale**: Normalizzazione a -16 LUFS e output MP3 320kbps costante.

---

### 4. Flusso Operativo e Troubleshooting

### 4. Flusso Operativo e Troubleshooting

#### 4.1 File System Layout (Lo Stato Persistente)
Il filesystem non è solo un deposito, ma funge da "Database di Stato" decentralizzato. La struttura è gerarchica e speculare agli stadi:
- `data/stage_A/output/`: Contiene i `.json` dei chunk di testo estratti (Input per B/C).
- `data/stage_B/output/`: Contiene le analisi semantiche (Input per C).
- `data/stage_C/output/`: Contiene sia i *Master JSON* (array) che le singole scene `.json` (Input per D).
- `data/stage_D/output/`: Contiene i risultati delle callback ARIA con i path dei `.wav`.

**Vantaggio**: Ogni file ha un nome deterministico basato su `{BookID}` e `{ChunkID}`. Questo permette alla **Skipping Logic** di funzionare: se lo Stage D trova un file in `data/stage_D/output/` per la Scena 05, non invierà alcun compito ad ARIA, ma leggerà il path del file audio già esistente.

#### 4.2 Filosofia "Offline-First" e Debugging
Il sistema è progettato per essere sviluppato e testato anche senza connessione internet o API attive:
- **Mock Services**: Tramite la variabile `MOCK_SERVICES=true`, DIAS simula le chiamate Redis e API, permettendo di testare la logica di controllo.
- **Iniezione di JSON manuali**: In caso di blocco delle API Google (quota esaurita), è possibile prendere un vecchio file JSON dello Stage C, modificarlo a mano (es. cambiare un'istruzione di regia) e salvarlo nella cartella di output. Al riavvio, il sistema "berrà" il nuovo file ignorando la necessità di chiamare Gemini.
- **Isolamento dei Guasti**: Se lo Stage D fallisce (es. ARIA offline), i file degli stadi A, B e C restano validi e intatti. Non c'è mai bisogno di rifare un'analisi semantica costosa se il problema è solo nella sintesi vocale.
- **Ripristino Manuale**: Se un file JSON risulta corrotto, basta cancellarlo: la Skipping Logic lo noterà e forzerà il sistema a rigenerare solo quel pezzo specifico.

### 5. Deployment e Dashboard (Roadmap)
In ottica di rilascio, DIAS esporrà su NH-Mini un'interfaccia **FastAPI / Streamlit / React (LXC 190)**.
Questa Dashboard offrirà:
1. Controllo totale sul "Resume" (utilizzando la Skipping Logic per riavvii a freddo).
2. Upload dei PDF in Stage A.
3. Lettura dei checkpoint Redis per il progresso di avanzamento in tempo reale (barra percentuale per chunk processato in B, C, e D).
