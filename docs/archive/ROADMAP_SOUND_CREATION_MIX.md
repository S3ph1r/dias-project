> **[ARCHIVIATO — Aprile 2026]**
> Questo documento descrive il sistema B2 con sound library Redis, matching semantico, workflow
> "Warehouse-First" e stop-on-missing. Tale approccio è stato **sostituito** dal paradigma
> **Sound-on-Demand v4.1**: nessun blocco sulla shopping list, nessun catalogo Redis, produzione
> JIT via ACE-Step. La sezione sui 4 layer sonori (AMB/MUS/SFX/STING) e il concetto di
> Master Clock rimangono validi come riferimento concettuale.
> Per la logica corrente, vedere `blueprint.md` e `dias-workflow-logic.md`.

# ROADMAP SOUND_CREATION_MIX: Il Radiofilm Deterministico DIAS
## Revisione v9.0 — Strategia e Architettura Audio Consolidata

Questo documento costituisce l'Unica Fonte di Verità (Single Source of Truth) concettuale per la regia sonora (Stage B2), la gestione del catalogo suoni (ARIA Sound Library) e l'assemblaggio finale (Stage E/Mixdown) della pipeline DIAS.
(Sostituisce e consolida: *DIAS StageB2 e Soundlibrary.md*, *aria-sound-semantic-method.md*, *dias-workflow-logic.md*).

---

## 1. OBIETTIVO E LA SFIDA
Creare un audio in formato radiodramma / audio-teatrale (stile NPR/BBC), dove la Voce non è schiacciata dal suono, e la musica non è un generico sottofondo in loop, ma una traccia dinamica che guida l'emozione con un'architettura **Dichiarativa e Deterministica**.

### Sfide Risolte:
1. **Carico Cognitivo dell'AI:** Impossibile per l'LLM concentrarsi sulle emozioni di 15 minuti di testo e, contemporaneamente, collocare uno sparo al millisecondo in un unico prompt.
2. **Sincronismo (Master Clock):** Poiché l'audio sintetizzato non ha una durata matematica prevedibile, è infattibile sincronizzare file prima di aver scaricato le tracce vocali definitive.
3. **Scalabilità Orizzontale (I Macro-Capitoli):** Gestire produzioni massive (>30 ore di audio) mantenendo la fluidità acustica nei punti di giuntura, anche in assenza di capitoli letterali.

---

## 2. IL MASTER CLOCK: LA VOCE DETTA IL TEMPO
La difficoltà maggiore dell'audio generato da AI è che misurare la durata testuale è inaffidabile.
**La Soluzione DIAS:** La Voce è il "Master Clock". 
* Lo **Stage D (Voice Gen)** viene eseguito *prima* dello *Stage E (Mixdown)*, quindi quando arriviamo al mixaggio, noi abbiamo già l'esatta lunghezza (in ms) di ogni singola scena.
* Lo **Stage E** allinea i WAV vocali di un Macro-chunk (es. + Pause relative) e fissa la **Timeline Assoluta**.
* Qualsiasi evento sonoro deciso dallo Stage B2 viene agganciato a uno specifico "Scene-ID" (es. `chunk-000-micro-001-scene-012`). Al momento del mix, lo Stage E sa matematicamente che l'effetto inizia a `00:01:23.450`.

---

## 3. I 4 LIVELLI (LAYERS) DEL SOUND DESIGN
Abbandonata l'idea del "tappeto tuttofare con ducking", il radiodramma è mixato in 4 STEM nativi:

1. **AMB (Ambience) - Il Mondo:** 
   * Suono dello spazio fisico (es. vento su Tatooine, ronzio sala motori). 
   * **Mix:** Volume costante realistico. NESSUN Ducking automatico sui dialoghi (distruggerebbe l'immersione testuale all'orecchio).
2. **MUS (Music Score) - L'Emozione:** 
   * Tema musicale (pad/drone/leitmotif) legato all'azione. 
   * **Mix:** Traccia dinamica. Gode di manovre volute (`ducking` durante un sussurro intimo, `build`/`swell` durante le esplosioni).
3. **SFX (Sound Effects) - L'Azione:** 
   * Suoni foley puntuali e letterali (accensione spada laser, spari, passi). 
   * **Mix:** Chirurgico, posizionato sulla parola o pausa in scena. Deve "bucare" il mix.
4. **STNG (Stings) - L'Impatto:** 
   * Effetto/Sottolineatura musicale squisitamente teatrale (un colpo di timpano improvviso per uno shock narrativo). Usati con severa parsimonia.

---

## 4. L'ARCHITETTURA "A DUE VELOCITÀ" (STAGE B2 SPOTTER)
Per evitare il sovraccarico cognitivo, il **"Regista Sonoro" B2** deve operare a due livelli di zoom, producendo un "Copione Sonoro" a doppia firma (Un Inventario Titolare + Un'Automazione di Mix).

### FASE 1: Il Macro-Spotter (Respiro Lungo)
*   **Contesto:** Analizza globalmente il file `[id]-chunk-000.json` (2500 parole, output Stage B).
*   **Task:** Riconosce la `primary_emotion` e il grande `setting`.
*   **Output:** Genera l'"Inventario" del Macro Chunk. Seleziona **UN'AMB base** e **UN Tema MUS**. 

### FASE 2: Il Micro-Spotter (Respiro Corto)
*   **Contesto:** Analizza l'output dettagliato di Stage C (`...scenes.json`), scene per scene (10-20 frasi).
*   **Task:** Riceve il Tema Musicale (MUS) e l'Ambiente (AMB) decisi dalla FASE 1. Lavora "di fino".
*   **Output:** Genera l'"Automazione" o la Timeline Relativa. Non cambia la canzone, ma le altera il volume (`action: ducking / action: build`). Piazza chirurgicamente gli ID di **SFX** e **STNG** legandoli alla riga di scena corretta.

### Flusso Inter-Capitolare (Libri infiniti)
I Macro-chunks generati (che equivalgono a ~15 min di audio effettivo) vengono computati singolarmente e chiusi. Al momento del concatenamento finale in *Mastering*, l'eredità ambientale è garantita perché la FASE 1 del Macro-Spotter tenderà a non cambiare la colonna sonora e l'ambiente se l'analisi semantica successiva è medesima.

---

## 5. ARIA SOUND LIBRARY: IL METODO E LA PRODUZIONE

Il Magazzino dei Suoni su ARIA Client (Redis 120 / PC 139) usa il **Paradigma del Riuso Universale Semantico**.

* **Nessun suono è ad-hoc:** Non esiste il file `sparo_di_chen.wav`, ma `sparo_pistola_impulsi_secco.wav`. L'App Stage B2 pesca i suoni incrociando lo scenario con l'attributo `tags` o `semantic_description` riportato nel file `sound_catalog.json` del magazzino.

### Workflow Produttivo "Fabbrica":
1. **PADS & AMBIENCES (STEM A / STEM MUS):** Generazioni di lunghissima durata (2-3 minuti min.). Preferite librerie Royalty-Free statiche, o output di *Stable Audio Open*. Vanno dentro `/pads` o `/ambiences`.
2. **STINGS & MUSIC MOTIFS (STEM C / THEMES):** Generazioni per MusicGen / AudioCraft. Brevi (4-10 secondi) con altissima specificità su tensione, paura, transizioni (Swoosh, Risers, Bass Drops). Vanno dentro `/stings`.
3. **SFX:** Librerie Foley Royalty-free (Epidemic/Freesound). Vanno dentro `/sfx`.

---

## 6. LOGICA DI VALIDAZIONE BATCH: LA SHOPPING LIST

Il design system impone un sistema **Stop-on-Missing a Livello di Lavoro Batch**:
1. Il Macro-Spotter e/o Micro-Spotter in Stage B2 verificano su Redis se ogni singolo suono che voglio usare *esiste fisicamente a magazzino*.
2. Se il tag esatto non esiste o difetta di aderenza all'85%, lo segnano all'interno di una log memory.
3. Il Worker termina l'elaborazione di **TUTTI** i chunk disponibili per il progetto. 
4. Valuta: Se la lista dei non-trovati non è vuota, crea `master_shopping_list.json` nella root del progetto e forza lo stato **PAUSED**.
5. Il Produttore umano attiva PC 139, apre la lista, genera massivamente tramite Script i nuovi files .wav richiesti e li ricarica. Al riavvio dell'Orchestratore, lo Stage B2 validato troverà i file esaudendo lo Spotting. 
