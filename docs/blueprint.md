\*\*DIAS \- Distributed Immersive Audiobook System\*\*

\*Sistema distribuito per la produzione automatizzata di audiolibri cinematografici con intelligenza artificiale locale\*

\---

\#\#\# La Visione

DIAS trasforma un manoscritto in un'esperienza audio immersiva, simile a un film sonoro. Non si limita a "leggere" il testo, ma lo \*direziona\*: assegna emotività alla voce narrante, compone colonne sonore adattive al mood della storia e inserisce effetti sonori contestuali, il tutto in modo completamente automatico.

\#\#\# Il Problema

Creare un audiolibro di qualità professionale oggi richiede settimane di lavoro in studio (costi elevati) o l'uso di servizi cloud (abbonamenti costosi, privacy compromessa, lock-in del fornitore). Gli strumenti software esistenti producono risultati meccanici, privi della profondità emotiva che rende immersiva una narrazione.

\#\#\# La Soluzione

DIAS opera come uno \*\*studio cinematografico domestico\*\* costituito da due entità collaborative:

1\. \*\*Il Regista\*\* (sistema centrale sempre attivo): coordina il lavoro, gestisce le richieste degli utenti e mantiene la memoria di tutti i progetti in corso. funziona su hardware a basso consumo ed è sempre disponibile, anche quando la potenza di calcolo principale è offline.

2\. \*\*Il Motore Creativo\*\* (sistema di produzione audio): utilizza l'hardware grafico ad alte prestazioni (il PC gaming) per generare voci, musica ed effetti. Questo componente si attiva \*solo quando la macchina non è utilizzata per altro\* (gaming, lavoro), garantendo priorità assoluta alle attività dell'utente.

Il sistema legge il manoscritto, ne analizza la struttura narrativa e compone un \*\*copione audio tecnico\*\* che guida la generazione di ogni elemento sonoro. La voce si adatta all'emozione del testo, la musica cambia in base alla tensione della scena, e il tutto viene bilanciato in un mix finale pronto per l'ascolto.

\#\#\# L'Esperienza

Per l'utente, il processo è estremamente semplice: si carica il libro e si sceglie la voce (anche clonando la propria con pochi secondi di registrazione). Il sistema lavora in background, capitolo per capitolo, notificando il completamento. Non è richiesta attesa davanti al computer: si può spegnere il dispositivo e ritrovare l'audiolibro pronto il giorno successivo.

Il risultato è un file audio di alta qualità, privo di costi ricorrenti, generato interamente all'interno della propria rete domestica, garantendo totale privacy sui contenuti letterari.

\# DIAS Pipeline v3.0 \- Specifiche Funzionali Complete  
\#\# Sistema di Produzione Audiobook Cinematico Distribuito

\*\*Versione\*\*: 3.0 Final    
\*\*Data\*\*: Gennaio 2026    
\*\*Target Hardware\*\*: RTX 5060 Ti 16GB VRAM / 32GB RAM / MiniPC Brain    
\*\*Stack API\*\*: Google GenAI SDK (Gemini 2.5 Flash-Lite)    
\*\*Stack Locale\*\*: Qwen3-TTS 1.7B, AudioCraft MusicGen Small, FFmpeg    
\*\*Middleware\*\*: Redis (Queues \+ State Management)    
\*\*Resilienza\*\*: Checkpointing tra stadi, nessuna perdita dati su crash

\---

\#\# 1\. Architettura Generale

Il sistema implementa una pipeline \*\*strettamente sequenziale\*\* a 7 stadi. Ogni stadio consuma da una coda Redis dedicata, processa atomicamente, e produce output nella coda successiva solo al completamento assoluto del predecessore.

\*\*Principi Fondamentali\*\*:  
1\. \*\*One Model at a Time\*\*: I modelli AI locali vengono caricati in VRAM uno alla volta, utilizzati per tutti i task della loro categoria, poi scaricati completamente (\`torch.cuda.empty\_cache()\`) prima del passaggio successivo  
2\. \*\*Gentle API Consumption\*\*: massimo 1 chiamata ogni 30 secondi a Gemini Flash-Lite (fallback a 120s in caso di rate limiting)  
3\. \*\*Stato Immutabile\*\*: Ogni operazione scrive su Redis prima di ACK del messaggio; i crash non perdono progressi  
4\. \*\*Locking Distribuito\*\*: Redis gestisce l'accesso esclusivo a risorse (API, GPU) tra processi multipli

\---

\#\# 2\. Topologia Redis

\#\#\# 2.1 Code di Lavoro (Redis Lists \- BRPOP)  
Chiave | Stadio | Consumer  
\---|---|---  
\`dias:queue:1:ingestion\` | A: TextIngester | Brain VM (CPU)  
\`dias:queue:2:macro\_analysis\` | B: MacroAnalyzer | Brain VM (API)  
\`dias:queue:3:scene\_director\` | C: SceneDirector | Brain VM (API)  
\`dias:queue:4:voice\_gen\` | D: VoiceGenerator | GPU Worker (Locale)  
\`dias:queue:5:music\_gen\` | E: MusicGenerator | GPU Worker (Locale)  
\`dias:queue:6:mixing\` | F: AudioMixer | Brain VM (CPU)  
\`dias:queue:7:mastering\` | G: MasteringEngine | Brain VM (CPU)

\#\#\# 2.2 State Management (Redis Hashes)  
\`\`\`  
dias:state:book:{book\_id}               \# Metadata globali  
dias:state:chapter:{chapter\_id}         \# Stato progresso capitolo  
dias:state:scene:{scene\_id}             \# Asset generati per scena  
dias:state:block:{block\_id}             \# Risultati analisi parziali  
dias:checkpoint:{book\_id}               \# Ultimo stadio completato  
\`\`\`

\#\#\# 2.3 Locking e Rate Limiting (Redis Strings con TTL)  
\`\`\`  
dias:lock:api:google\_gemini             \# "1" TTL 30s/120s  
dias:lock:gpu:qwen3tts                  \# "1" TTL 24h (fino a completamento)  
dias:lock:gpu:musicgen                  \# "1" TTL 24h  
dias:lock:gpu:sfxgen                    \# "1" TTL 24h  
dias:throttle:api:google                \# Timestamp ultima chiamata  
\`\`\`

\---

\#\# 3\. Specifiche Componenti

\#\#\# COMPONENTE A: TextIngester (CPU \- Brain VM)  
\*\*Input\*\*: Upload file (PDF/EPUB/DOCX)    
\*\*Output\*\*: Blocchi testuali suddivisi    
\*\*Queue\*\*: \`dias:queue:1:ingestion\` → \`dias:queue:2:macro\_analysis\`

\*\*Logica\*\*:  
1\. Estrazione testo (Marker/PyMuPDF)  
2\. Split per capitoli (regex \`/^(Capitolo|Chapter)\\s+\\d+/i\`)  
3\. Se capitolo \>3000 parole: split in blocchi da 2500 parole con overlap 100 parole (per mantenere context narrativo)  
4\. Pubblicazione messaggio per ogni blocco

\*\*Schema Output\*\*:  
\`\`\`json  
{  
  "job\_id": "550e8400-e29b-41d4-a716-446655440000",  
  "book\_id": "7d9a3c1e-5f4a-4b8e-9c2d-1a3b5c7d9e0f",  
  "chapter\_id": "ch-003",  
  "chapter\_number": 3,  
  "chapter\_title": "La Scoperta del Sottoscala",  
  "block\_id": "ch-003-blk-00",  
  "block\_text": "Il mattino del terzo giorno William si svegliò... \[2500 parole\]",  
  "word\_count": 2480,  
  "block\_index": 0,  
  "total\_blocks\_in\_chapter": 2,  
  "timestamp": "2026-01-15T09:30:00Z"  
}  
\`\`\`

\---

\#\#\# COMPONENTE B: MacroAnalyzer (API Google \- Rate Limited)  
\*\*Modello\*\*: \`gemini-2.5-flash-lite-preview-06-17\`    
\*\*SDK\*\*: \`google-genai\`    
\*\*Input\*\*: Singolo blocco testuale (max 2500 parole)    
\*\*Output\*\*: Analisi emotiva strutturata    
\*\*Queue\*\*: Consume \`dias:queue:2:macro\_analysis\` → Aggrega → Produce \`dias:queue:3:scene\_director\`

\*\*Rate Limiting Implementation\*\*:  
\`\`\`python  
\# Pseudocodice per il consumer  
while True:  
    \# 1\. Rate limiting  
    last\_call \= redis.get("dias:throttle:api:google")  
    if last\_call and (now \- last\_call) \< 30:  
        sleep(30 \- (now \- last\_call))  
        continue  
      
    \# 2\. Acquisizione lock  
    if not redis.set("dias:lock:api:google\_gemini", "1", nx=True, ex=30):  
        sleep(10)  
        continue  
      
    \# 3\. Processa  
    try:  
        result \= call\_gemini\_api(payload)  
        redis.set("dias:throttle:api:google", now\_timestamp)  
    except RateLimitError:  
        redis.setex("dias:lock:api:google\_gemini", 120, "1")  \# Penalty 2min  
        continue  
\`\`\`

\*\*Prompt System\*\*:  
\`\`\`  
Sei un analista narrativo cinematografico. Analizza il testo fornito e restituisci   
un JSON valido che descriva:  
1\. Emozioni prevalenti (valence, arousal, tension 0.0-1.0)  
2\. Archi emotivi (inizio, sviluppo, climax)  
3\. Ambientazioni rilevate  
4\. Segnali sonori descritti (door\_creak, rain, footsteps)  
5\. Presenza dialoghi

Sei conservatore: assegna valori emotivi solo se supportati dal testo esplicito.  
\`\`\`

\*\*Schema Output\*\*:  
\`\`\`json  
{  
  "job\_id": "550e8400-e29b-41d4-a716-446655440000",  
  "block\_analysis": {  
    "valence": 0.25,  
    "arousal": 0.75,  
    "tension": 0.90,  
    "primary\_emotion": "suspense",  
    "secondary\_emotion": "curiosity",  
    "setting": "interior/monastery\_library",  
    "has\_dialogue": false,  
    "audio\_cues": \["pages\_turning", "candle\_flicker", "distant\_bell"\]  
  },  
  "narrative\_markers": \[  
    {  
      "relative\_position": 0.15,  
      "event": "discovery",  
      "mood\_shift": "neutral\_to\_tense"  
    },  
    {  
      "relative\_position": 0.85,  
      "event": "clue\_revelation",  
      "mood\_shift": "tense\_to\_shock"  
    }  
  \]  
}  
\`\`\`

\*\*Aggregazione Capitolo\*\*:  
\- Accumula in \`dias:state:chapter:{chapter\_id}\` hash  
\- Quando \`completed\_blocks \== total\_blocks\`, calcola:  
  \- \`avg\_valence \= weighted\_average(valence \* word\_count)\`  
  \- \`dominant\_setting \= mode(settings)\`  
  \- Unifica \`audio\_cues\` (deduplica)  
\- Pubblica messaggio unico su Queue 3 con testo capitolo completo e profilo emotivo aggregato

\---

\#\#\# COMPONENTE C: SceneDirector (API Google \- Rate Limited)  
\*\*Modello\*\*: \`gemini-2.5-flash-lite-preview-06-17\`    
\*\*Input\*\*: Capitolo completo \+ analisi macro    
\*\*Output\*\*: Audio Script per ogni scena individuata    
\*\*Queue\*\*: Consume \`dias:queue:3:scene\_director\` → Produce \`dias:queue:4:voice\_gen\` (N messaggi, uno per scena)

\*\*Logica Segmentazione\*\*:  
Il modello divide il capitolo in Scene basandosi su:  
\- Cambio luogo (\>2 ore narrative o cambio fisico)  
\- Shift emotivo \>0.3 tra paragrafi  
\- Transizione dialogo ↔ narrazione estesa  
\- Cambio POV (Point of View)

\*\*Schema Output\*\* (uno per riga nella coda 4):  
\`\`\`json  
{  
  "job\_id": "660e8400-e29b-41d4-a716-446655440001",  
  "book\_id": "7d9a3c1e-5f4a-4b8e-9c2d-1a3b5c7d9e0f",  
  "chapter\_id": "ch-003",  
  "scene\_id": "scene-ch003-00",  
  "scene\_number": 0,  
  "text\_content": "Il mattino del terzo giorno William si svegliò con il sapore della polvere d'archivio sulle labbra...",  
  "start\_char\_index": 0,  
  "end\_char\_index": 1840,  
  "word\_count": 320,  
  "voice\_direction": {  
    "emotion\_description": "whispered\_curiosity\_with\_tension",  
    "pace\_factor": 0.82,  
    "pitch\_shift": \-1,  
    "energy": 0.4,  
    "recommended\_silence\_before\_ms": 800,  
    "recommended\_silence\_after\_ms": 1200  
  },  
  "timing\_estimate": {  
    "estimated\_duration\_seconds": 142,  
    "words\_per\_minute": 135  
  },  
  "audio\_layers": {  
    "ambient": {  
      "type": "continuous",  
      "soundscape\_tag": "monastery\_morning\_cold",  
      "volume\_db": \-22,  
      "fade\_in\_ms": 3000,  
      "fade\_out\_ms": 4000,  
      "frequency\_focus": "low\_mids"  
    },  
    "spot\_effects": \[  
      {  
        "trigger\_anchor": "polvere d'archivio",  
        "effect\_name": "soft\_page\_rustle",  
        "offset\_from\_scene\_start\_ms": 4500,  
        "duration\_ms": 800,  
        "volume\_db": \-18,  
        "spatial\_position": "center"  
      },  
      {  
        "trigger\_anchor": "sapore della polvere",  
        "effect\_name": "subtle\_throat\_clear",  
        "offset\_from\_scene\_start\_ms": 3200,  
        "volume\_db": \-24  
      }  
    \],  
    "music": {  
      "prompt\_for\_musicgen": "Gregorian choir ambient, distant, cold stone atmosphere, minor key, slow tempo 70bpm, mysterious, no percussion, cinematic reverb",  
      "intensity\_curve": \[0.2, 0.3, 0.5\],  
      "entry\_point": "with\_voice",  
      "ducking\_db": \-8,  
      "ducking\_attack\_ms": 200,  
      "ducking\_release\_ms": 800  
    },  
    "transitions": {  
      "from\_previous": "fade\_in\_1000ms",  
      "to\_next": "crossfade\_1500ms\_or\_hard\_cut\_if\_dialogue\_starts"  
    }  
  }  
}  
\`\`\`

\---

\#\#\# COMPONENTE D: VoiceGenerator (GPU Locale)  
\*\*Modello\*\*: \`Qwen3-TTS 1.7B\` (12Hz Base, non Flash)    
\*\*Ambiente\*\*: GPU Worker (Stato GREEN obbligatorio)    
\*\*Input\*\*: Messaggio dalla coda 4    
\*\*Output\*\*: WAV 48kHz mono per scena    
\*\*Queue\*\*: Consume \`dias:queue:4:voice\_gen\` → Produce stato per Queue 5

\*\*Gestione VRAM\*\*:  
\`\`\`python  
\# Pattern implementativo  
if acquire\_lock("dias:lock:gpu:qwen3tts", ttl=86400):  
    load\_model("Qwen3-TTS-1.7B")  \# \~6-8GB VRAM  
      
    while msg := redis.blpop("dias:queue:4:voice\_gen", timeout=60):  
        process\_scene(msg)  
        update\_state(scene\_id, voice\_path, duration)  
      
    unload\_model()  \# torch.cuda.empty\_cache()  
    release\_lock()  
\`\`\`

\*\*Coerenza Tra Scene\*\*:  
\- Utilizzare voice cloning con campione utente (3-30s)  
\- Mantenere \`last\_speaker\_embedding\` in memoria tra iterazioni  
\- Per scena N\>1: passare \`context\_audio\` \= ultimi 0.5s della scena precedente come "continuation prompt"  
\- Se scena \>300 parole: split in chunk 250 parole, generare sequenzialmente, concatenare con crossfade 50ms (match energia/pitch)

\*\*Output\*\*:  
\- File: \`/storage/audio/voice/{book\_id}/{scene\_id}.wav\`  
\- Aggiornamento Redis:  
  \`\`\`  
  HSET dias:state:scene:{scene\_id} \\  
    voice\_path "/storage/..." \\  
    voice\_duration\_seconds 142.5 \\  
    voice\_status "completed"  
  \`\`\`

\---

\#\#\# COMPONENTE E: MusicGenerator (GPU Locale)  
\*\*Modello\*\*: \`AudioCraft MusicGen Small\` (2.3B, \~4GB VRAM)    
\*\*Input\*\*: Graceful pull quando coda 4 è vuota    
\*\*Output\*\*: WAV stereo 48kHz    
\*\*Queue\*\*: Logicamente dipendente dallo stato delle scene

\*\*Processo\*\*:  
1\. Attende che \`dias:queue:4\` sia vuota (tutte le voci generate)  
2\. Acquisisce lock \`dias:lock:gpu:musicgen\`  
3\. Carica MusicGen (unload Qwen3-TTS precedente)  
4\. Per ogni scena con \`voice\_path\` esistente:  
   \- Durata target \= \`voice\_duration\_seconds \+ 5s\` (margini fade)  
   \- Se \>30s: genera loop con continuation fino a durata esatta  
   \- Salva: \`/storage/audio/music/{book\_id}/{scene\_id}\_bgm.wav\`  
   \- Aggiorna \`dias:state:scene:{scene\_id}\` campo \`music\_path\`

\---

\#\#\# COMPONENTE F: AudioMixer (CPU \- Brain VM)  
\*\*Tool\*\*: FFmpeg 7.0+ con filter\_complex    
\*\*Input\*\*: Lista scene completate (voice \+ music \+ sfx)    
\*\*Output\*\*: Scene stem mixate    
\*\*Queue\*\*: \`dias:queue:6:mixing\`

\*\*FFmpeg Filter Complex Example\*\*:  
\`\`\`bash  
ffmpeg \-i voice.wav \-i music.wav \-i sfx.wav \\  
  \-filter\_complex "  
    \[1:a\]volume=-8dB,adelay=0|0,afade=t=in:ss=0:d=2\[music\];  
    \[2:a\]adelay=4500|4500,volume=-18dB\[sfx\];  
    \[0:a\]\[music\]amix=inputs=2:duration=first:dropout\_transition=0.8\[tmp\];  
    \[tmp\]\[sfx\]amix=inputs=2:duration=first\[voice\_music\];  
    \[voice\_music\]loudnorm=I=-23:LRA=7\[final\]  
  " \\  
  \-map "\[final\]" output\_scene.wav  
\`\`\`

\*\*Note\*\*: Ducking automatico music sidechain when voice RMS \> \-40dB.

\---

\#\#\# COMPONENTE G: MasteringEngine (CPU)  
\*\*Input\*\*: Capitolo completo (tutte le scene \`\_mixed.wav\`)    
\*\*Output\*\*: MP3 320kbps con metadati    
\*\*Queue\*\*: \`dias:queue:7:mastering\`

\*\*Processo\*\*:  
1\. Concatenazione scena per scena in ordine \`scene\_number\`  
2\. Loudness normalization a \-16 LUFS (standard audiolibro)  
3\. Silenzio testa 2s, coda 3s  
4\. Embed cover art (se presente in \`dias:state:book:{id}\`)  
5\. ID3 tags: title, artist (narratore), album (titolo libro), track number

\---

\#\# 4\. Esempio di Flusso Completo (Caso Reale)

\*\*Libro\*\*: "Il Manoscritto di Avila" (fittizio) \- Capitolo 3 "La Biblioteca Proibita"    
\*\*Input\*\*: 2.800 parole

\#\#\# Step 1: Ingestion (CPU)  
\- Input: \`cap3.pdf\`  
\- Output: 2 blocchi (1500 \+ 1300 parole)  
\- Redis: 2 messaggi in \`queue:1\` → processati → 2 messaggi in \`queue:2\`

\#\#\# Step 2: MacroAnalysis (API \- 2 chiamate)  
\- \*\*Call 1\*\* (t=0s): Blocco 1 (introduzione biblioteca)  
  \- Output: \`valence:0.3, arousal:0.6, setting:library\`  
\- \*\*Call 2\*\* (t=30s): Blocco 2 (scoperta segreta)  
  \- Output: \`valence:0.2, arousal:0.9, setting:library\_hidden\_room\`  
\- \*\*Aggregazione\*\*: Capitolo \= suspense crescente, setting dominante \= library  
\- \*\*Output\*\*: 1 messaggio in \`queue:3\` con testo completo \+ profilo emotivo

\#\#\# Step 3: SceneDirector (API \- 1 chiamata)  
\- Input: Testo completo 2800 parole  
\- Output: 3 scene identificate  
  \- Scene 0: Ingresso biblioteca (800 parole, mood: curiosità)  
  \- Scene 1: Ricerca nel buio (1200 parole, mood: tensione)  
  \- Scene 2: Scoperta manoscritto (800 parole, mood: shock)  
\- \*\*Output\*\*: 3 messaggi in \`queue:4\`

\#\#\# Step 4: VoiceGeneration (GPU \- Sequenziale)  
\- \*\*Load Qwen3-TTS\*\* (t=0, VRAM 7GB occupati)  
\- Scene 0: Generata in 90s (durata output: 142s)  
\- Scene 1: Generata in 135s (durata output: 198s)  
\- Scene 2: Generata in 95s (durata output: 152s)  
\- \*\*Unload Qwen3-TTS\*\* (VRAM liberata)  
\- \*\*Output\*\*: Aggiornamento stato Redis per tutte e 3

\#\#\# Step 5: MusicGeneration (GPU \- Sequenziale)  
\- \*\*Load MusicGen\*\* (t=0)  
\- Scene 0: 142s audio generato (prompt: "curious ambient, light strings")  
\- Scene 1: 198s audio generato (prompt: "dark ambient, tension drones")  
\- Scene 2: 152s audio generato (prompt: "shock reveal, orchestral hit")  
\- \*\*Unload MusicGen\*\*

\#\#\# Step 6: Mixing (CPU)  
\- Scene 0: voice.wav \+ music.wav (ducking \-8dB) \+ page\_rustle.sfx  
\- Scene 1: voice.wav \+ music.wav (ducking \-12dB)  
\- Scene 2: voice.wav \+ music.wav \+ dramatic\_hit.sfx  
\- \*\*Output\*\*: 3 file \`\_mixed.wav\`

\#\#\# Step 7: Mastering (CPU)  
\- Concatenazione: scene0 \+ scene1 \+ scene2 \= 492s totali (\~8min)  
\- Normalizzazione: \-16 LUFS  
\- Output: \`il\_manoscritto\_di\_avila\_cap03.mp3\`  
\- \*\*Stato Finale\*\*: \`dias:state:book:{id}\` \= \`completed\`

\---

\#\# 5\. Schemi JSON Dettagliati e Validabili

\#\#\# Schema 1: MacroAnalysisResult  
\`\`\`json  
{  
  "$schema": "http://json-schema.org/draft-07/schema\#",  
  "type": "object",  
  "required": \["job\_id", "block\_analysis"\],  
  "properties": {  
    "job\_id": {"type": "string", "format": "uuid"},  
    "block\_analysis": {  
      "type": "object",  
      "required": \["valence", "arousal", "tension", "primary\_emotion"\],  
      "properties": {  
        "valence": {"type": "number", "minimum": 0, "maximum": 1},  
        "arousal": {"type": "number", "minimum": 0, "maximum": 1},  
        "tension": {"type": "number", "minimum": 0, "maximum": 1},  
        "primary\_emotion": {"enum": \["neutral", "joy", "sadness", "anger", "fear", "suspense", "curiosity"\]},  
        "secondary\_emotion": {"type": "string"},  
        "setting": {"type": "string", "pattern": "^(interior\\|exterior)/\[a-z\_\]+$"},  
        "has\_dialogue": {"type": "boolean"},  
        "audio\_cues": {  
          "type": "array",  
          "items": {"type": "string", "pattern": "^\[a-z\_\]+$"}  
        }  
      }  
    },  
    "narrative\_markers": {  
      "type": "array",  
      "items": {  
        "type": "object",  
        "properties": {  
          "relative\_position": {"type": "number", "minimum": 0, "maximum": 1},  
          "event": {"type": "string"},  
          "mood\_shift": {"type": "string"}  
        }  
      }  
    }  
  }  
}  
\`\`\`

\#\#\# Schema 2: SceneScript (Audio Script)  
\`\`\`json  
{  
  "$schema": "http://json-schema.org/draft-07/schema\#",  
  "type": "object",  
  "required": \["scene\_id", "text\_content", "voice\_direction", "audio\_layers"\],  
  "properties": {  
    "scene\_id": {"type": "string", "pattern": "^scene-ch\[0-9\]+-\[0-9\]+$"},  
    "text\_content": {"type": "string", "minLength": 50},  
    "word\_count": {"type": "integer", "minimum": 1},  
    "voice\_direction": {  
      "type": "object",  
      "required": \["emotion\_description", "pace\_factor"\],  
      "properties": {  
        "emotion\_description": {"type": "string", "maxLength": 100},  
        "pace\_factor": {"type": "number", "minimum": 0.5, "maximum": 1.5},  
        "pitch\_shift": {"type": "integer", "minimum": \-5, "maximum": 5},  
        "energy": {"type": "number", "minimum": 0, "maximum": 1},  
        "recommended\_silence\_before\_ms": {"type": "integer", "minimum": 0},  
        "recommended\_silence\_after\_ms": {"type": "integer", "minimum": 0}  
      }  
    },  
    "audio\_layers": {  
      "type": "object",  
      "properties": {  
        "ambient": {  
          "type": "object",  
          "properties": {  
            "soundscape\_tag": {"type": "string"},  
            "volume\_db": {"type": "number", "minimum": \-60, "maximum": 0},  
            "fade\_in\_ms": {"type": "integer", "minimum": 0},  
            "fade\_out\_ms": {"type": "integer", "minimum": 0}  
          }  
        },  
        "music": {  
          "type": "object",  
          "required": \["prompt\_for\_musicgen"\],  
          "properties": {  
            "prompt\_for\_musicgen": {"type": "string", "minLength": 10, "maxLength": 500},  
            "intensity\_curve": {  
              "type": "array",  
              "items": {"type": "number", "minimum": 0, "maximum": 1},  
              "minItems": 3,  
              "maxItems": 3  
            },  
            "ducking\_db": {"type": "number", "minimum": \-30, "maximum": 0}  
          }  
        },  
        "spot\_effects": {  
          "type": "array",  
          "items": {  
            "type": "object",  
            "required": \["effect\_name", "offset\_from\_scene\_start\_ms"\],  
            "properties": {  
              "effect\_name": {"type": "string"},  
              "offset\_from\_scene\_start\_ms": {"type": "integer", "minimum": 0},  
              "volume\_db": {"type": "number", "minimum": \-60, "maximum": 0}  
            }  
          }  
        }  
      }  
    }  
  }  
}  
\`\`\`

\---

\#\# 6\. Gestione Errori e Recovery

\#\#\# API Rate Limit (HTTP 429\)  
1\. Cattura eccezione con status 429  
2\. Imposta \`dias:lock:api:google\_gemini\` con TTL 120s  
3\. Log: "Rate limit hit, backing off for 120s"  
4\. Non consumare il messaggio dalla coda (BLPOP lo rimetterà in testa)  
5\. Retry automatico dopo backoff

\#\#\# GPU OOM  
1\. Cattura \`torch.cuda.OutOfMemoryError\`  
2\. Salvare checkpoint in \`dias:state:scene:{id}\` con flag \`oom\_retry=true\`  
3\. Rilasciare lock e VRAM  
4\. Dividere automaticamente il testo in chunk più piccoli (split al punto più vicino a metà)  
5\. Riaccodare i due chunk come nuovi job

\#\#\# Stadio Interrotto (Crash)  
All'avvio del sistema:  
\`\`\`python  
for book\_id in get\_active\_books():  
    checkpoint \= redis.get(f"dias:checkpoint:{book\_id}")  
    last\_stage \= int(checkpoint or 0\)  
      
    if last\_stage \< 7:  
        \# Verifica stato intermedio  
        resume\_from\_stage(last\_stage \+ 1\)  
\`\`\`

\---

\#\# 7\. Configurazioni Environment

\`.env\` o \`config.yaml\`:

\`\`\`yaml  
\# Google GenAI Configuration  
google:  
  api\_key: "${GOOGLE\_API\_KEY}"  
  model\_flash\_lite: "gemini-2.5-flash-lite-preview-06-17"  
  rate\_limit\_seconds: 30  
  rate\_limit\_penalty\_seconds: 120  \# Su errore 429  
  max\_retries: 3  
  temperature: 0.2  
  response\_mime\_type: "application/json"

\# Local Models  
models:  
  qwen3\_tts:  
    path: "/models/Qwen3-TTS-12Hz-1.7B-Base"  
    device: "cuda"  
    max\_memory\_gb: 8  
    batch\_size: 1  
      
  musicgen:  
    path: "/models/musicgen-small"  
    device: "cuda"  
    max\_memory\_gb: 4

\# Redis  
redis:  
  host: "localhost"  
  port: 6379  
  db: 0  
  decode\_responses: true

\# Storage  
storage:  
  base\_path: "/mnt/dias/storage"  
  temp\_path: "/mnt/dias/temp"  
  voice\_output: "{base\_path}/audio/voice/{book\_id}"  
  music\_output: "{base\_path}/audio/music/{book\_id}"  
  final\_output: "{base\_path}/output/{book\_id}"

\# Processing  
pipeline:  
  max\_chunk\_words: 2500  
  chunk\_overlap\_words: 100  
  scene\_max\_words: 300  
  default\_voice\_sample: "/voices/default\_narrator.wav"  
    
\# Audio Standards  
audio:  
  sample\_rate: 48000  
  voice\_channels: 1  \# Mono  
  music\_channels: 2  \# Stereo  
  final\_bitrate: "320k"  
  target\_lufs: \-16  
  head\_silence\_seconds: 2  
  tail\_silence\_seconds: 3  
\`\`\`

\---

\#\# 8\. Appendice: Note per Antigravity (Google)

Quando implementi con Antigravity:  
1\. \*\*Struttura modulare\*\*: Crea un pacchetto Python per ogni Componente (A-G) con interfaccia comune \`process(message) \-\> result\`  
2\. \*\*Docker\*\*: Componenti A, F, G possono girare in container sul Brain; Componenti D, E devono avere accesso host alla GPU (runtime nvidia-docker)  
3\. \*\*Testing\*\*: Usa \`redis-cli\` per pushare messaggi di test manualmente nelle code e verificare il flusso  
4\. \*\*Monitoring\*\*: Espone metriche Prometheus su \`/metrics\` di ogni componente (queue depth, processing time, error rate)

Documento pronto per implementazione.  
\`\`\`  
