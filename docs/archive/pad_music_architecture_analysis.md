> **[ARCHIVIATO — 2026-04-17]**
> Documento di analisi progettuale che ha guidato la progettazione del sistema PAD a 3 layer
> (Identità / Arco / Respiro). Il contenuto concettuale è stato assorbito in `blueprint.md`,
> `technical-reference.md` e nei prompt `b2_macro_v4.0.yaml`. Non aggiornare.

---

# DIAS — Architettura della Musica di Sfondo (PAD)
## Documento di Analisi e Decisione Progettuale — Aprile 2026
> **Scopo**: Cristallizzare le connessioni tra input, contesti e livelli di controllo musicale.
> **Da integrare in**: `stage_b2_d2_sound_on_demand_v4.md`

---

## 1. L'Obiettivo Qualitativo di Riferimento

Il benchmark di qualità per la musica di DIAS sono i **radiodrammi BBC** degli anni '70-'90 e le produzioni di **Star Wars Audio Drama** (NPR, 1981). La loro caratteristica comune non è la qualità tecnica degli strumenti — è il fatto che la musica sembra un **personaggio invisibile**: reagisce, respira, anticipa, accompagna il silenzio.

Questo si ottiene con tre caratteristiche tecniche specifiche:

1. **L'Identità Coerente**: Un'opera ha una "voce musicale" riconoscibile dall'inizio alla fine. Non si cambia genere tra un capitolo e l'altro.
2. **L'Arco Dinamico**: La musica ha un'intensità che sale e scende nel tempo, sincronizzata con la drammaturgia — non è un wallpaper piatto.
3. **Il Respiro Scena per Scena**: La musica si abbassa naturalmente sui dialoghi pesanti, emerge nelle pause, cresce prima dei climax. L'ascoltatore non lo "sente" come tecnica — lo sente come emozione.

Questi tre livelli corrispondono esattamente ai tre layer informativi della nostra pipeline.

---

## 2. I Tre Layer di Controllo Musicale

### Layer 1 — L'Identità (Livello Progetto)

| | |
|---|---|
| **Chi lo decide** | Stage 0 (L'Occhio Supremo) |
| **Contesto in input** | L'intero libro (~80.000-120.000 parole) |
| **Granularità** | Un'intera opera |
| **Cosa produce** | `project_sound_identity` — il DNA stilistico della musica |

**Cosa viene stabilito qui:**
- Genere e strumentazione (es. *"Orchestrale anni '70, ottoni pesanti, synth analogici"*)
- Carattere emotivo di base (es. *"teso, malinconico, con momenti di respiro eroico"*)
- Le regole di variazione consentite (es. *"varianti possibili: tensione / sospensione / risoluzione"*)
- Eventuali Brand Sounds per personaggi/luoghi ricorrenti

**Perché il libro intero?**
Solo avendo letto l'intera opera si può capire se la musica deve "contenere" la promessa della risoluzione finale fin dal primo capitolo. Nei radiodrammi BBC, il compositore leggeva l'intero romanzo prima di scrivere una nota.

---

### Layer 2 — L'Arco del Capitolo (Livello Macro)

| | |
|---|---|
| **Chi lo decide** | B2-Macro |
| **Contesto in input** | Macro-chunk (~2500 parole) + analisi Stage B + durata totale |
| **Granularità** | Un capitolo / blocco (~15-20 min di audio) |
| **Cosa produce** | `pad_arc` — la partitura emotiva del capitolo nel tempo |

**Inputs dettagliati:**

| Input | File | Cosa Usiamo | Perché |
|---|---|---|---|
| **DNA Musicale** | `preproduction.json` → `sound_identity` | Palette, regole stilistiche, varianti ammesse | Vincola ogni scelta a rimanere dentro l'identità del progetto |
| **Emozione del Capitolo** | `stage_b/{chunk}.json` → `block_analysis` | `primary_emotion`, `secondary_emotion`, `emotional_arc`, `setting` | Indica quale *variante* dell'identità musicale usare (tensione vs. sospensione vs. risoluzione) |
| **Il Testo Stesso** | Macro-chunk (~2500 parole) | Il ritmo delle frasi, la densità dei dialoghi, la presenza di climax | Gemini "sente" il ritmo interno del capitolo leggendolo — frasi brevi e concitate vs. descrizioni lunghe e paesaggistiche |
| **Durata Fisica** | `master_timing_grid.json` → aggregato | `total_duration_s` del chunk | Permette di descrivere l'arco in termini temporali assoluti (es. "la musica sale dai secondi 200 ai 600") |

**Cosa produce B2-Macro — Il Concetto Chiave:**

B2-Macro non produce "quale musica". Produce **come la musica si muove nel tempo**.

Il risultato non è un singolo asset statico, ma una **partitura emotiva** espressa in linguaggio naturale che poi diventa il `production_prompt` per Stage D2:

```
Esempio di partitura emotiva per un capitolo:
- 0s–120s:   impercettibile, quasi silenzio, solo un drone bassissimo (apertura descrittiva)
- 120s–480s: crescita lenta e inesorabile, tensione che si accumula senza mai esplodere
- 480s–600s: climax — massima intensità, corde gravi + ottoni + percussioni
- 600s–900s: dissoluzione graduale verso un drone malinconico (atterraggio post-climax)
```

Questa partitura è il cuore dell'Opzione A.

---

### Layer 3 — Il Respiro Scena per Scena (Livello Micro)

| | |
|---|---|
| **Chi lo decide** | B2-Micro |
| **Contesto in input** | Micro-chunk (~300 parole) + scene singole con timing fisico |
| **Granularità** | Singola scena (5-30 secondi) |
| **Cosa produce** | `pad_breathing` — automazione volume per ogni scena |

**Inputs dettagliati:**

| Input | File | Cosa Usiamo | Perché |
|---|---|---|---|
| **Identità + Arco** | Output B2-Macro | `pad_canonical_id`, contesto dell'arco emotivo corrente | Sapere dove siamo nella partitura del capitolo per decidere il tipo di ducking |
| **Testo delle Scene** | `stage_c/{block}-scenes.json` | Tipo di scena (dialogo/narrazione/azione), speaker | Dialogo intimo → duck deep. Narrazione descrittiva → duck shallow. Azione → snap |
| **Timing Fisico Esatto** | `master_timing_grid.json` | `voice_duration_s`, `pause_after_s` per ogni scena | La pausa DOPO una scena è oro — se è > 2s, la musica può emergere |
| **Tipo di Scena (Stage C)** | `stage_c/{block}-scenes.json` | `scene_type`: `dialogue`, `narration`, `action`, `thought` | Colora la profondità del duck e la velocità del fade |

**La Regola d'Oro del Respiro:**

Il parametro più importante non è il volume della voce — sono le **pause**.

```
Pausa < 0.8s:  Transizione rapida, la musica non ha tempo di emergere → duck/snap
Pausa 0.8-1.5s: Pausa normale → smooth transition, musica appena percettibile
Pausa 1.5-3s:  Pausa drammatica → neutral, la musica emerge in primo piano
Pausa > 3s:    Silenzio teatrale → build o neutral pieno, la musica "respira" da sola
```

Nei radiodrammi BBC, le pause erano composte quasi come le note. Questo layer le sfrutta sistematicamente.

---

## 3. Stato dell'Arte dei Modelli Audio (Aprile 2026)

Questa analisi è necessaria per decidere tra l'Opzione A (PAD precomposto con arco) e l'Opzione B (PAD loop + automazione Stage E).

### 3.1 Modelli Disponibili

| Modello | Durata Max | Controllo Dinamico | Open Source | Note Rilevanti |
|---|---|---|---|---|
| **ACE-Step 1.5 XL (4B)** | **10 minuti** | Buono (LM planner) | ✅ Sì | "Stable Diffusion moment" per la musica. Gira su RTX 3090. Aprile 2026. |
| **Stable Audio 2.5** | 3 minuti | Buono (texture/design) | Parziale | Eccellente per amb e pad atmosferici. |
| **Udio** | Estendibile | Alto (inpainting sezione per sezione) | ❌ No | Workflow da DAW. Stem export. Ideale per composizioni articolate. |
| **AIVA** | Illimitato (MIDI) | Molto Alto (teoria armonica) | ❌ No | Motore MIDI. Il gold standard per scoring cinematografico. |
| **Google DeepMind Lyria 3 Pro** | Variabile (API) | Alto (orchestrale/jazz/cinema) | ❌ No | Qualità audio eccezionale. API-driven. |
| **Suno v5.5** | 4+ minuti | Medio (orientato ai vocals) | ❌ No | Generative DAW. Stem separation. Fortissimo sui brani vocali. |
| **MusicGen Large** | ~30-60s | Basso | ✅ Sì | Affidabile, ma datato per questo use case. |

### 3.2 Analisi per il Nostro Use Case

Il nostro use case specifico è: **musica strumentale cinematografica, senza vocali, con arco emotivo in 15-20 minuti**.

| Requisito | Soluzione Migliore |
|---|---|
| **Open source e locale** (PC 139 con GPU) | ACE-Step 1.5 XL — fino a 10 min, gira su RTX 3090 |
| **Qualità orchestrale massima** (senza vincoli di costo) | AIVA (MIDI → render) o Lyria 3 Pro (API Google) |
| **Controllo sull'arco emotivo** | AIVA (progettazione struttura) o ACE-Step (prompting naturale) |
| **Produzione di ambienti e texture** (AMB) | Stable Audio 2.5 |

---

## 4. La Decisione Ufficiale: Il Metodo "Stem Separation" (Traccia Singola, Multi-Layer)

### Il Limite delle Soluzioni Alternative

Durante l'analisi, abbiamo affrontato il problema fondamentale dell'AI generativa musicale (ACE-Step, MusicGen, ecc.): **l'assenza di memoria melodica tra una generazione e l'altra**.
Se chiediamo all'AI tre file separati via prompt ("pad_low_intensity", "pad_mid_intensity", "pad_high_intensity") usando lo stesso testo di base, il modello produrrà tre canzoni completamente diverse. Condivideranno il genere, ma avranno chiavi armoniche, melodie e ritmi differenti. Un crossfade tra questi file in fase di mixaggio genererebbe un disastro acustico (dissonanze e cacofonia).

L'alternativa del *looping per micro-chunk* (crossfade continui tra loop diversi) funziona solo per droni astratti, precludendoci la possibilità di avere temi orchestrali, ritmici o epici (alla Star Wars).

### La Soluzione Definitiva: Separazione Stem

La brillante soluzione architetturale adottata per DIAS si basa sul decoupling tra **Composizione** (ARIA AI) e **Arrangiamento** (Stage E), utilizzando un modello di scissione acustica.

**Ecco come funziona (Il "Come"):**

1.  **La Call Unica (Stage D2)**: B2-Macro chiede ad ARIA la generazione di **UN SOLO PAD** (es. `pad_master.wav` di 5 minuti) alla sua **massima intensità e maestosità** (il climax).
2.  **La Scissione (ARIA SoundFactory / D2)**: Immediatamente dopo la generazione, un modello open-source di stem separation (es. **HTDemucs**) elabora il `pad_master.wav` spaccandolo in 4 tracce isolate e perfettamente sincronizzate:
    *   `Vocals` (scartato/non usato)
    *   `Bass` (Le frequenze basse, il tappeto grave)
    *   `Other/Melody` (Archi, synth, arpeggiatori)
    *   `Drums` (Il ritmo formante, le percussioni)
3.  **L'Arrangiamento Dinamico (Stage E)**: Stage E non carica un singolo brano musicale, ma carica i 3 stem utili (`Bass`, `Melody`, `Drums`) su tre tracce parallele. La "respirazione" e la partitura emotiva diventano un semplice gioco di **Mute/Unmute o automazione volume su questi stem specfici**.

### Le Mappature di Intensità (Il "Cosa")

B2-Macro e B2-Micro continuano a descrivere la partitura emotiva in tre livelli (Low/Mid/High). Stage E traduce questi livelli in questa formula di mixaggio:

*   **Intensità LOW (Sottobosco / Tensione sotterranea)**: 
    Suona solo lo stem `Bass`. (Effetto: tappeto profondo, oscuro, che non disturba minimamente i dialoghi intimi o descrittivi).
*   **Intensità MID (Sviluppo / Narrazione attiva)**: 
    Suonano `Bass` + `Melody`. (Effetto: la musica "entra", si percepiscono le armonie e i synth, accompagna l'azione).
*   **Intensità HIGH (Climax / Rivelazione)**: 
    Suonano `Bass` + `Melody` + `Drums`. (Effetto: ingresso esplosivo delle percussioni, apice emotivo e ritmico).

### Il Vantaggio Tecnico (Il "Perché")

Questa scelta è la definitiva per la pipeline DIAS perché:
- **Zero Dissonanze**: L'armonia, la chiave musicale e il BPM sono gli stessi per tutti i layer. Il crossfade non esiste più: si "accendono e spengono" gli strumenti di una vera orchestra coesa.
- **Risparmio API**: Richiede una singola chiamata generativa pesante ad ARIA (ACE-Step), seguita da una passata leggera di HTDemucs che su GPU impiega secondi.
- **Effetto BBC Garantito**: Il suono respira esattamente come un vero compositore che aggiunge gli ottoni o la batteria solo quando l'eroe entra nella stanza.

---

## 5. Nuovo Flusso Dati Completo per il PAD (Stem Architecture)

```
Stage 0 (libro intero)
  └─► project_sound_identity: (Palette stilistica, Varianti, Leitmotif)
        
Stage B2-Macro (macro-chunk ~2500 parole)
  ├─ Legge: project_sound_identity, block_analysis, total_duration_s
  └─► Produce: macro-cue.json con:
        - pad.canonical_id
        - pad.production_prompt (descrive l'apice di intensità HIGH)
        - pad.arc: { 0s→120s: "low", 120s→480s: "mid", 480s→600s: "high", 600s→900s: "low" }
        
Stage D2 (Sound Factory Client & processor)
  ├─ Legge: sound_shopping_list_aggregata.json
  ├─ Genera UN SINGOLO asset musicale master: pad_master_{id}.wav via ACE-Step
  ├─ Esegue HTDemucs su pad_master_{id}.wav per lo splitting:
  │    ├─ {id}_bass.wav
  │    ├─ {id}_melody.wav
  │    └─ {id}_drums.wav
  └─► Produce: manifest.json (mappando il canonical_id a questi 3 path locali)
  
Stage B2-Micro (micro-chunk ~300 parole + scene)
  ├─ Eredita: pad.canonical_id e pad.arc
  └─► Produce: IntegratedCueSheet aggiungendo respiri locali:
        - pad_volume_automation per scena (applica ducking sul volume master dei layer attivi)
        
Stage E (Mixdown)
  ├─ Carica i 3 stem sincronizzati dal manifest
  ├─ Segue pad.arc di Macro per attivare/disattivare i layer (Bass/Melody/Drums) nel tempo
  ├─ Sopra questa base dinamica, applica il ducking master calcolato da B2-Micro per i dialoghi
  └─► Risultato: colonna sonora adattiva, perfettamente a tempo e in chiave, che respira col testo.
```

---

## 6. Modello Raccomandato per ARIA PC 139

Considerando che ARIA gira in locale su PC 139 (presumibilmente con GPU NVIDIA di fascia alta):

**Raccomandazione Primaria: ACE-Step 1.5 XL (4B parametri)**
- Open source, MIT license, nessun costo variabile
- Gira su RTX 3090 (< 10s per generazione)
- Fino a 10 minuti (sufficiente per quasi tutti i capitoli)
- Responsive al natural language prompting
- Supporta editing e variazioni (utile per i 3 stem)

**Raccomandazione Secondaria: Stable Audio 2.5**
- Eccellente per AMB e texture atmosferiche (non per PAD orchestrali)
- Ideale per i layer AMB di B2-Micro
- Audio-to-audio prompting (variazioni di un seed audio)

**Per qualità massima (senza vincoli di costo): Google Lyria 3 Pro (API)**
- Qualità orchestrale superiore
- Costo per generazione (API Google)
- Alternativa per produzioni premium

---

## 7. Decisioni Aperte

> [!IMPORTANT]
> **Decisione 1 — Modello ARIA**: Confermare quale modello è installato su PC 139. ACE-Step 1.5 è la raccomandazione, ma va verificata la compatibilità con l'infrastruttura esistente.

> [!IMPORTANT]
> **Decisione 2 — Numero di Stem**: Tre stem (low/mid/high) è la proposta. Si potrebbe semplificare a due (base/intense) o espandere a quattro (low/mid-low/mid-high/high). Da decidere in base alla varietà espressiva necessaria e alla complessità accettabile in Stage E.

> [!NOTE]
> **Decisione 3 — Brand Sounds (Leitmotif)**: Se il progetto richiede un tema musicale per un personaggio specifico, questo viene definito in Stage 0 e i relative stem vengono prodotti una volta sola in D2, riutilizzati in tutti i capitoli successivi.
