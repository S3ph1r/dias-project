# DIAS Workflow Logic: L'Architettura Generale della Pipeline
## Revisione v9.0 — Aprile 2026

Questo documento definisce l'intera pipeline di produzione DIAS, tracciando il percorso del testo dal libro grezzo fino al radiodramma (Radiofilm) finale mixato. 
Serve come mappa globale per comprendere l'ordine di esecuzione, le dipendenze e gli input/output di ogni singolo stadio.

---

## 1. Mappatura degli Stage (La Catena di Montaggio)

La pipeline opera in modo **Seriale** e **Deterministico**. Per garantire la sincronizzazione perfetta tra voce, effetti e musica, la struttura segue l'ordine tassativo qui sotto.

| Stage | Nome in Codice | Compito Principale | Input Primario | Output Primario |
| :--- | :--- | :--- | :--- | :--- |
| **Stage 0** | L'Occhio Supremo | Estrae il concept narrativo, identikit personaggi, voci e "Casting". | Libro Grezzo intero (.epub/.txt) | Dossier di Pre-Produzione (JSON) |
| **Stage A** | Lo Spaccapietre | Taglia il libro in blocchi gestibili in memoria (~2500 parole). Ignora i capitoli. | Libro Grezzo (.txt) | Array di **Macro-Chunk** (.json) |
| **Stage B** | Lo Psicologo | Analizza l'emozione globale del Macro, poi lo divide in Micro-sezioni. | Macro-Chunk (Testo) | Analisi Emotiva Globale + **Micro-Chunks** (~300 par) |
| **Stage C** | Il Regista Vocale | Identifica chi parla. Spacca il Micro-chunk in singole frasi. Dà istruzioni all'attore. | Micro-Chunk (Testo) | File **Scenes** (Array di frasi con Istruzioni TTS) |
| **Stage D** | L'Attore Isolato | Sintetizza fisicamente le voci. Genera un singolo file audio per ogni scena. | File Scenes | **Clip Vocali Fisiche (.wav)** |
| **Stage B2** | **Il Regista Sonoro** | Decide i tappeti sonori, gli accenti e i volumi. Se mancano asset, li richiede (Shopping List). | Dati Stage B/C + Registry ARIA | **Copione Sonoro (Cue Sheet)** |
| **Stage E** | Il Tecnico del Mix | Allinea i WAV di Stage D creando la timeline. Esegue il Copione Sonoro piazzando musica ed effetti. | Voci (Wav) + Copione Sonoro | **Macro-Chunk Audio Mixato (.wav)** |
| **Stage F** | Il Mastering | Concatena i Macro-Chunk Audio mixati in un unico prodotto fluido, normalizza livelli (LUFS). | Array di Macro-Chunk Mixati | **Audiolibro/Radiodramma Finale** |

---

## 2. Il "Master Clock" e la Sincronizzazione

Il problema storico dei sistemi AI-Audio è il disallineamento tra musica/effetti e voce, causato dall'imprevedibilità della durata vocale. DIAS risolve questo collocando lo **Stage D (Sintesi Vocale) PRIMA dello Stage E (Mixdown)** e parallelamente alla regia sonora finale:

1. Lo **Stage D** genera l'audio fisico. Il tempo smette di essere misurato in "battute testuali" e diventa "millisecondi" hardware.
2. Lo **Stage B2 (Lo Spotter)** non mixa nulla fisicamente. Scrive un copione basato sugli ID delle scene, indicando *cosa* deve succedere e a quale *scena*.
3. Lo **Stage E (Il Mixer)** usa i `.wav` di Stage D per calcolare quando inizia esattamente ogni scena sulla timeline assoluta. Poi legge il copione di B2 e piazza i suoni musicali (`.wav` ambientali, stings, sfx) perfettamente a tempo.

---

## 3. Dinamiche dello Stage B2 (Approfondimento Sound Design)

Lo **Stage B2** lavora in *due tempi* per gestire il carico cognitivo dell'Intelligenza Artificiale:

*   **Macro-Spotter (Respiro Lungo):** Legge l'analisi emotiva dello Stage B associata all'intero Macro-Chunk (15 min di audio). Assegna la traccia musicale portante (**MUS**) e il mondo di fondo (**AMB**).
*   **Micro-Spotter (Respiro Corto):** Legge le singole scene testuali di Stage C (10-15 frasi). Assegna colpi chirurgici (**SFX**, **STNG**) e varia il volume musicale (ducking sulle voci, build nei climax drammatici).

Se l'asset sonoro richiesto da B2 non esiste nel database ARIA (Master Registry in Redis), il sistema interrompe l'elaborazione del progetto e aggrega le richieste in una **Shopping List**, obbligando l'operatore umano a produrre quegli specifici suoni su server ARIA prima della fase di Mixdown.

---
*Per la logica musicale estesa e l'architettura dei layer sonori, vedi: `ROADMAP_SOUND_CREATION_MIX.md`*
