# DIAS — Distributed Immersive Audiobook System
## Blueprint V3.0 — "Audiofilm" Vision
**Data**: 25 Marzo 2026  
**Status**: In Sviluppo (Sprint 4)  
**Autore**: Roberto + Antigravity (Google DeepMind)  
**Sostituisce**: `blueprint.md` (v6.3) — questa versione ridefinisce la visione di prodotto.

---

## 1. L'Obiettivo Finale — Il "Radiofilm"

### 1.1 Cosa stiamo costruendo (e cosa non stiamo costruendo)

DIAS non è un text-to-speech avanzato. Non stiamo producendo "un libro letto bene con musica di sottofondo". Stiamo costruendo qualcosa di radicalmente diverso: un **Radiofilm**.

Il riferimento culturale è la **BBC Radio Drama** o una **Serie Netflix adattata per l'audio**: un'opera in cui il suono non accompagna la narrazione, ma **è** la narrazione. Ogni elemento acustico — la voce del narratore, le voci dei personaggi, la musica, gli effetti ambientali — lavora insieme come una regia orchestrata.

**Come suona un Radiofilm in pratica:**

Il protagonista apre una porta in un vicolo buio. La voce narrante si ferma. Per quattro secondi, la musica sale — un accordo basso e metallico che riempie lo spazio. Poi la voce riprende, più bassa. Nel sottofondo, appena percettibile, il rumore della pioggia sul cemento e il ronzio di un neon.

Più avanti, un dialogo tra due personaggi. La voce cambia: non è più il narratore. È un'altra voce — più rauca, più urgente — che appartiene solo a quel personaggio. Quando risponde l'antagonista, la voce è di nuovo diversa. La musica si è abbassata quasi a zero. Il silenzio tra le battute è deliberato, tenuto.

Questo è il risultato che DIAS V3 deve produrre.

---

### 1.2 Il Contrasto: Romanzo d'Avventura vs Paper Tecnico

DIAS V3 è progettato per l'eccellenza su narrativa letteraria, ma deve saper gestire qualsiasi tipo di testo. La differenza non è una limitazione — è una **modalità operativa**.

| Aspetto | Romanzo / Narrativa | Saggio / Paper Tecnico |
|---|---|---|
| **Voce** | Narratore + voci personaggi | Solo narratore |
| **Musica** | Colonna sonora adattiva, emotiva | Neutro di sottofondo (opzionale, disattivabile) |
| **Effetti sonori** | Ancoraggio contestuale alle scene | Assenti |
| **Casting** | 3-8 voci da assegnare ai personaggi | Nessuno |
| **B2 (Sound Director)** | Attivo, produce 3 stem musicali | Disabilitato o in modalità "ambient read" |
| **Stage F (Mixer)** | Mixaggio multi-stem complesso | Pass-through semplice voce + eventuale tappeto |
| **Output finale** | Radiofilm immersivo | Audiolibro professionale ma sobrio |

La **Pre-Analisi del Libro** (Stage 0) determina automaticamente il profilo del documento e suggerisce la modalità operativa.

---

## 2. Il Flusso Utente — La Pre-Produzione in Dashboard

Prima di avviare la pipeline di produzione, l'utente interagisce con la Dashboard per configurare il progetto. Questo avviene **una sola volta per libro**.

### 2.1 Fase 1: Caricamento e Fingerprinting del Libro

L'utente carica il PDF/EPUB/DOCX. Il sistema esegue immediatamente una **Book Intelligence Analysis** (Stage 0) — una lettura veloce dell'intero testo (campionamento: intro, fine di ogni capitolo, sezioni di dialogo) per produrre:

- **Profilo del documento**: narrativa/saggio/tecnico (con confidenza)
- **Mappa dei capitoli**: titoli, lunghezze, struttura
- **Personaggi identificati**: nome, ruolo (protagonista, secondario, antagonista), stile di dialogo
- **3 proposte di Sound Palette** per la colonna sonora (es. *"Neo-Classical Tension"*, *"Organic Acoustic Warmth"*, *"Industrial Cyberpunk"*) — con una breve descrizione testuale di ciascuna

### 2.2 Fase 2: Il Pannello di Pre-Produzione

La Dashboard mostra un pannello di configurazione strutturato:

**A. Casting Vocale**
```
Narratore:       [ Luca ▾ ]   (voce principale del libro)

Personaggi identificati:
  → Eva Morales   protagonista   [ Eleven ▾ ]
  → Marcus Thane  antagonista    [ Luca ▾  ]
  → Dr. Reyes     secondario     [ Usa Narratore ▾ ]

[ + Aggiungi Personaggio Manuale ]
```

**B. Sound Palette**
```
Scegli la palette musicale per questo libro:
  ○ Neo-Classical Tension       "Violoncelli e pianoforte in minore. Atmosfera cerebrale e seria."
  ● Industrial Cyberpunk        "Droni sintetici, ritmi metallici. Tensione tecnologica."
  ○ Organic Acoustic Warmth     "Chitarre acustiche, fiati. Calore umano e intimità."

[ ANTEPRIMA 30s ]
```

**C. Livello di Produzione**
```
  ○ Semplice       Solo voce
  ○ Standard       Voce + Tappeto musicale
  ● Radiofilm      Voce + Musica + Effetti Sonori + Voci Personaggi
```

Solo dopo questa configurazione si avvia la pipeline vera e propria.

---

## 3. L'Architettura della Pipeline V3

La pipeline V3 si articola su **tre livelli di granularità simultanei**:

```
LIBRO          ─────── COERENZA GLOBALE ─────
                       Sound Identity
                       Casting delle Voci
                       
CAPITOLO       ─── COERENZA NARRATIVA ───────
                   Profilo Semantico Aggregato
                   Sound Palette per Capitolo
                   Structural Anchors
                   
SCENA          ─ GRANULARITÀ ESECUTIVA ───────
                 Regia Vocale
                 Assegnazione Voce per Dialogo
                 Effetti Sonori Contestuali
```

Questi tre livelli non sono stage sequenziali — sono **layer di memoria** che i vari stage consultano mentre operano sul loro granulo specifico.

### 3.1 Schema della Pipeline Completa

```
INPUT
  │
  ▼
[Stage 0]  Book Intelligence       → Profilo Libro, Personaggi, Palette Candidati
  │                                   (Analisi a campione, una volta sola)
  │  DASHBOARD: Configurazione Pre-Produzione
  │
  ▼
[Stage A]  Capitolo-Aware Ingester → Sub-Chunk (con chapter_id + is_partial)
  │
  ▼
[Stage B]  Semantic Analyzer       → Analisi per Sub-Chunk
  │        + Aggregator             → Profilo per Capitolo (quando chunk finiti)
  │
  ▼
[Stage B2] Sound Director          → Sound Plan per Capitolo
  │        (legge profilo capitolo)   (palette + anchor + leitmotif per personaggio)
  │
  ▼
[Stage C]  Scene Director          → Script per ogni Scena
  │        (legge profilo capitolo    (voce, emozione, effetti, voice_id personaggio)
  │         + casting + B2 anchors)
  │
  ▼
[Stage D]  Voice Generator         → WAV per ogni Scena (multi-voce)
  │        (rispetta voice_id)        (narratore o voce personaggio via ARIA)
  │
  ▼
[Stage E]  Music Generator         → Set di Stem per ogni Capitolo
  │        (legge Sound Plan B2)      (Stem A: atmosfera, B: leitmotif, C: stings)
  │
  ▼
[Stage E2] SFX Selector            → File audio effetti per Scene selezionate
           (legge audio_cues B)       (solo quando narrativamente significativi)
  │         
  ▼
[Stage F]  Audio Mixer             → Capitolo mixato (voce + musica + sfx)
  │        (legge anchors da B2)      (ducking adattivo, voice suspension sugli anchor)
  │
  ▼
[Stage G]  Mastering Engine        → MP3 finale con metadati e chapter markers
```

## 4. Architettura dei Dati e Isolamento Progetti (Sprint 4)

A partire dallo Sprint 4, DIAS adotta una struttura **Project-Centric**. Ogni libro è un'entità isolata nel filesystem, eliminando le cartelle globali per stadio.

### 4.1 Struttura Directory
Tutti i dati risiedono in `data/projects/{project_id}/`:

```text
data/projects/{project_id}/
├── source/               # File originale (PDF, EPUB, DOCX)
├── stages/               # Dati elaborati dalla pipeline
│   ├── stage_a/          # Output del Text Ingester
│   ├── stage_b/          # Analisi Semantica
│   ├── stage_c/          # Scene Scripts (Regia)
│   └── stage_d/          # Voice Gen (WAV + JSON metadata)
└── config.json           # Configurazione locale (Casting, Palette, etc.)
```

### 4.2 Routing dei Worker
I worker (Stadi A-G) sono ora **Project-Aware**. Non utilizzano più path globali statici, ma instanziano un contesto di persistenza dinamico per ogni messaggio ricevuto:
1. Il worker riceve un task da Redis contenente il `book_id`.
2. Viene istanziato `DiasPersistence(project_id=book_id)`.
3. Tutte le operazioni di I/O (caricamento input dello stadio precedente e salvataggio output corrente) vengono automaticamente instradate nella sottocartella del progetto.

---

## 5. Approfondimento dei Singoli Stage

### Stage 0 — Book Intelligence *(Nuovo in V3)*
**Granularità:** Libro intero (campionamento)  
**Scopo:** Capire cosa stiamo per produrre prima di produrlo.  

Analizza l'intero testo in modo intelligente. **Lo Stage viene attivato manualmente dalla Dashboard** (tasto "Start Intelligence") per permettere all'utente di controllare i costi e configurare il casting prima della produzione.

**Caratteristiche tecniche:**
- **Modello**: Gemini 1.5 Flash Lite (ottimizzato per context window di 1M+ token).
- **Prompt**: Esternalizzato in `config/prompts/stage_0/intelligence.yaml`.
- **Workflow**: Upload -> Analisi -> Casting (Manual/Auto).

**Output (Fingerprint JSON):**
- **Metadata**: Titolo, Autore, Genere, Tono emotivo.
- **Chapter Map**: Riassunti narrativi e mappe strutturali.
- **Casting Profiles**: Identificazione personaggi con descrizioni psicologiche e **profili vocali** (timbro, ritmo, età).
- **Sound Proposals**: Suggerimento di palette musicali (Sound Design).

### Aria Voice Profiling (R&D)
Per abilitare il casting automatico, le voci esposte da ARIA devono essere arricchite con un profilo descrittivo (es. *timbro, età stimata, genere*). Il sistema potrà così suggerire il "Best Match" tra il profilo vocale estratto dallo Stage 0 e le voci disponibili nel pool Aria.

### Stage A — Capitolo-Aware Ingester *(Evoluzione)*
**Granularità:** Sub-Chunk (max 2500 parole) con chapter_id  
**Scopo:** Trasformare il testo grezzo in unità processabili dall'LLM, rispettando i confini narrativi.

La logica di chunking nell'ordine:
1. Divide per capitolo usando i marker tipografici
2. Se capitolo > 3.500 parole: divide in sub-chunk con tag `is_partial: true`
3. Se capitolo < 600 parole: aggrega con il successivo (stessa chapter_id composita)
4. Preserva sempre il confine di capitolo — nessun sub-chunk taglia un cambio capitolo

Ogni output ha: `chapter_id`, `sub_chunk_index`, `is_partial`, `chapter_title`.

### Stage B — Semantic Analyzer + Aggregator *(Evoluzione)*
**Granularità:** Sub-Chunk (analisi LLM) → Capitolo (aggregazione automatica)  
**Scopo:** Produrre la comprensione emotiva e narrativa a due livelli.

Funziona in due fasi:
1. **Analisi del Sub-Chunk:** Identica a oggi — emozioni, entità, setting, audio_cues
2. **Aggregazione Capitolo:** Quando tutti i sub-chunk dello stesso `chapter_id` sono completati, calcola il profilo aggregato: emozione dominante pesata per word_count, unificazione entità, arco emotivo (inizio/picco/fine), setting dominante. Produce un JSON `chapter_profile`.

Il `chapter_profile` è il documento di regia condiviso da Stage B2, C e F.

### Stage B2 — Sound Director *(Nuovo in V3)*
**Granularità:** Capitolo  
**Scopo:** Tradurre l'analisi semantica in un piano sonoro concreto per lo Stage E.

Riceve il `chapter_profile` da Stage B e produce un `sound_plan` con:
- **`global_palette`**: conferma la palette scelta dall'utente + parametri (tempo BPM, tonalità, strumentazione primaria)
- **`chapter_anchor`**: l'Emotional Anchor specifico del capitolo (es. "Malinconia urbana sotto tensione latente")
- **`structural_anchors[]`**: array di punti in cui la voce si sospende e la musica entra — con posizione relativa nel capitolo, tipo (`dramatic_pivot`, `topos_shift`, ecc.) e durata della sospensione in secondi
- **`leitmotifs[]`**: per ogni personaggio presente nel capitolo, un breve prompt per Stage E (es. "sparse cello, cold, distant, for Marcus Thane scenes")

### Stage C — Scene Director *(Evoluzione significativa)*
**Granularità:** Scena  
**Scopo:** Produrre la sceneggiatura esecutiva completa per ogni scena.

Riceve sub-chunk + `chapter_profile` + `casting` + `sound_plan` (da B2). Produce per ogni scena:
- `clean_text`: testo fonetico normalizzato
- `voice_id`: narratore o personaggio specifico (dal casting)
- `qwen3_instruct`: istruzione vocale calibrata su emozione, personaggio e anchor
- `pause_after_ms`: silenzio finale di regia
- `sfx_cues[]`: elenco di effetti sonori contestuali con posizione relativa nella scena
- `is_anchor_scene`: flag se la scena contiene o precede un Structural Anchor di B2

Il riconoscimento del dialogo avviene tramite analisi delle virgolette e dei marcatori (`disse`, `rispose`, `gridò`) per assegnare correttamente il `voice_id` senza ambiguità.

### Stage D — Voice Generator *(Evoluzione)*
**Granularità:** Scena  
**Scopo:** Produrre il WAV vocale per ogni scena, rispettando il casting.

Identico a oggi ma con un'evoluzione critica: legge il `voice_id` della scena. Se è un personaggio diverso dal narratore, invia ad ARIA la richiesta con il voice ID corrispondente. ARIA gestisce il pool di voci; DIAS non ha bisogno di sapere dove sono fisicamente.

**Fix Naming V3:** I file WAV e JSON sono nominati con schema `{book_id}-cap-{003}-scene-{015}` per garantire ordine e unicità.

### Stage E — Music Generator *(Nuovo in V3)*
**Granularità:** Capitolo  
**Scopo:** Produrre il materiale musicale grezzo per il capitolo, a tre livelli.

Legge il `sound_plan` di Stage B2 e invia ad ARIA (backend AudioCraft) tre set di richieste:
- **Stem A (Atmosfera):** Un unico brano lungo quanto il capitolo (es. 12 minuti). Durata stimata da Stage B in base al word count. Generato con il prompt dell'`chapter_anchor` + palette globale.
- **Stem B (Leitmotif):** Un brano breve (30-60s) per ogni `leitmotif` definito in B2, da riutilizzare ogni volta che quel personaggio è in scena.
- **Stem C (Stings):** Un brano cortissimo (3-8s) per ogni `structural_anchor` — la "sting" musicale che riempie il silenzio della voice suspension.

### Stage E2 — SFX Selector *(Nuovo in V3)*
**Granularità:** Scena  
**Scopo:** Selezionare e produrre gli effetti sonori per le scene che li richiedono.

Legge gli `sfx_cues` prodotti da Stage C. Un filtro di "rilevanza" scarta i cue troppo generici o frequenti: si producono effetti solo per eventi specifici e narrativamente evocativi (una porta che sbatte, il fischio di un treno, il crepitio di un fuoco). La selezione avviene da una libreria locale; se il cue non esiste, può inviare una richiesta speciale ad ARIA per la generazione on-demand.

### Stage F — Audio Mixer *(Nuovo in V3)*
**Granularità:** Capitolo  
**Scopo:** Assemblare tutti i materiali in una traccia coerente.

È il regista finale. Opera con FFmpeg e la mappa degli anchor di B2. Per ogni capitolo:
1. Allinea in timeline tutti i WAV di Scena (Stage D) in sequenza
2. Sovrappone lo Stem A (atmosfera) per tutta la durata
3. Inserisce gli Stem B (leitmotif) nelle scene dove è presente quel personaggio
4. Nei punti di Structural Anchor: sospende la voce, alza la musica, inserisce lo Stem C, poi rientra la voce con fade
5. Posiziona gli effetti SFX (Stage E2) nei punti definiti da Stage C
6. Applica ducking automatico: voce presente → musica a -20dB; pausa → musica a -10dB

### Stage G — Mastering Engine *(Nuovo in V3)*
**Granularità:** Libro  
**Scopo:** Produrre il file finale pronto per la distribuzione.

Concatena i capitoli mixati, normalizza a -16 LUFS (standard audiolibri), aggiunge silenzio di testa/coda, embed metadati ID3 con titolo, autore, narratore e chapter markers navigabili.

---

## 5. I Tre Fili della Coerenza

### Coerenza Vocale
Garantita da tre meccanismi:
1. **Casting fisso:** ogni personaggio ha sempre la stessa voce per tutto il libro
2. **`narrator_base_tone`:** il tono base del narratore è definito a livello di progetto e viene iniettato in ogni istruzione di Stage C
3. **Schema Ancora + Variazione:** le istruzioni di regia partono sempre dal tono base e aggiungono variazioni — mai istruzioni totalmente disconnesse tra scene

### Coerenza Musicale
Garantita da tre livelli:
1. **Sound Identity:** la palette scelta dall'utente è l'identità del libro — non cambia mai
2. **Chapter Anchor:** il mood specifico del capitolo modula la palette (stessa strumentazione, diversa intensità/velocità)
3. **Leitmotif:** i temi personaggio sono ricorrenti e riconoscibili — creano continuità psicologica per l'ascoltatore

### Coerenza Narrativa
Garantita dall'architettura a due memorie:
1. **Memoria Corta (LLM):** il sub-chunk di 2500 parole che l'LLM analizza in un singolo contesto
2. **Memoria Lunga (File System + Redis):** il `chapter_profile` aggregato che ogni stage può consultare come "documento di regia del capitolo corrente"

---

## 6. Roadmap di Sviluppo V3

### ✅ Completato (Sprint 1-3)
- **Sprint 1:** Struttura a capitoli (ChapterTimeline) e navigazione multi-progetto.
- **Sprint 2:** Audio Player persistente e Scene Inspector dettagliato.
- **Sprint 3:** Audio Inspector con Waveform interattive e Quality Scoring (Pitch, RMS, Brightness).
- **Pipeline:** Fix stall orchestratore e naming coordinato Stage D.

### 🔧 In Sviluppo (Sprint 4)
- **Stage 0:** Book Intelligence (fingerprinting, estrazione personaggi, proposta palette).
- **Dashboard:** Upload PDF/EPUB via drag-and-drop con creazione cartella progetto.
- **Casting UI:** Pannello per assegnazione voci ai personaggi scoperti.

### 🆕 Da Sviluppare Ex Novo (V3)
1. **Stage 0:** Book Intelligence (fingerprinting, estrazione personaggi, proposta palette) ← **Priorità Alta**
2. **Stage B2:** Sound Director (sound plan per capitolo, anchor, leitmotif) ← **Priorità Alta**
3. **Stage E:** Music Generator Proxy (AudioCraft via ARIA, 3 stem) ← **Priorità Media**
4. **Stage E2:** SFX Selector (effetti sonori contestuali) ← **Priorità Bassa** (richiede libreria)
5. **Stage F:** Audio Mixer (FFmpeg multi-stem, ducking adattivo, anchor) ← **Priorità Media**
6. **Stage G:** Mastering Engine (FFmpeg, normalization, ID3, chapter markers) ← **Priorità Bassa**

### 📋 Sequenza Raccomandata

```
FASE 1 (ora)     → Completa Stage D su "Cronache del Silicio" (51 WAV vocali)
                   → Verifica qualità audio con voce Eleven

FASE 2 (prossima) → Stage 0: Book Intelligence + Dashboard Pre-Produzione
                    → Stage A V3: Capitolo-Aware Ingester
                    → Stage B V3: Aggregator capitolo

FASE 3           → Stage B2: Sound Director
                   → Stage C V3: Multi-voice + SFX Cues
                   → Stage D V3: Routing multi-voce

FASE 4           → Stage E: Music Generator (3 stem)
                   → Stage F: Audio Mixer

FASE 5           → Stage E2: SFX Library + Selector
                   → Stage G: Mastering e output finale
```

---

## 7. Note Implementative Chiave

### Sul Prompt Engineering
Ogni stage ha il proprio prompt versionato in `config/prompts/stage_X/`. La versione V3 introduce un nuovo vincolo: ogni prompt deve documentare esplicitamente quali campi del JSON in input utilizza, per garantire la compatibilità con le evoluzioni future.

### Sui Limiti LLM
Il context limit dell'LLM rimane il vincolo principale. La soluzione V3 non cerca di superarlo, ma lo gestisce elegantemente: il sub-chunk è l'unità di elaborazione LLM, il capitolo è l'unità di coerenza narrativa. I due livelli comunicano tramite il file system (memoria persistente) e Redis (stato in tempo reale).

### Sul Casting
Il casting viene risolto una sola volta in Stage 0. Viene serializzato in un file JSON di progetto (`casting.json`) che ogni stage successivo può leggere. Nessuno stage deve "scoprire" i personaggi autonomamente — la scoperta è centralizzata e avviene prima.

### Sul tipo di contenuto
Se Stage 0 classifica il documento come `technical` o `essay`:
- Il casting è vuoto (solo narratore)
- Stage B2 è disabilitato o usa la palette "Ambient Read" (musica neutra, bassa intensità, nessun anchor drammatico)
- Stage C non produce sfx_cues
- Stage F opera in modalità semplice: solo voce + eventuale tappeto uniforme
- Stage E produce solo Stem A (nessun leitmotif, nessuno sting)

---

*Fine del Blueprint V3.0 — DIAS "Radiofilm"*  
*Prossimo passo: Validare questo documento come base di riferimento e avviare la Fase 1 (completamento voce "Cronache del Silicio").*
