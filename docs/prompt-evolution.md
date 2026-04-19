# DIAS Prompt Evolution Registry

Questo documento traccia l'evoluzione dei prompt di regia AI (Stage B e Stage C), spiegando le sfide affrontate e il motivo dei passaggi di versione.

---

## 🔍 Stage 0: Intel (Protocollo 0.1/0.2)

Lo Stage 0 è la fase di analisi "fredda" del libro, dove viene estratta la struttura e il DNA artistico.

| Versione | Focus | Rationale |
| :--- | :--- | :--- |
| **Discovery v1.0** | Capitoli e Titoli | Mappatura grezza 1:1 della struttura fisica del libro. |
| **Discovery v1.1** | Marcatori Stilistici | Analisi dei simboli usati per dialoghi e pensieri (em-dash vs virgolette). |
| **Discovery v1.2** | **Scansione Ossea** | Introdotta la distinzione tra `toggle_paragraph` e `enclosed_pair` per la normalizzazione. |
| **Intelligence v1.0** | **Creative DNA** | Fusione dell'analisi strutturale con Casting esaustivo e Palette sonore per la Dashboard. |


## 🎭 Stage B: Semantic & Emotional Analyzer

L'obiettivo dello Stage B è estrarre il "mood" macroscopico del testo per guidare la musica e lo stile di narrazione globale.

| Versione | Focus | Rationale |
| :--- | :--- | :--- |
| **v1.0 (Base)** | Emozioni base | Estrazione di Valence, Arousal, Tension e Primary Emotion. |
| **v1.1 (Director)** | **Dubbing Director** | Introduzione del ruolo di "Regista del Doppiaggio". Analisi del **Subtext** (intento nascosto), `narrator_base_tone` e **Mood Propagation** per prevenire il flickering tonale. |
| **v1.1 (Logic)** | **Mediterranean** | Adozione della strategia bilingue: ragionamento in IT (comprensione sfumature) e output in EN (compatibilità tecnica). |

---

## 🎬 Stage C: Scene Director (Regia Fine)

Lo Stage C è il modulo più critico: trasforma il testo in scene atomiche pronte per il TTS.

| Versione | Milestone | Cambiamenti Chiave | Rationale |
| :--- | :--- | :--- | :--- |
| **v1.1** | Archetipo | Prima versione stabile con segmentazione base. | - |
| **v1.5** | Theatrical | Introduzione del Mediterranean Prompting (Istruzioni in IT + Acustica in EN). | Migliorare la prosodia di Qwen3. |
| **v2.0** | Structural | Regole rigide per titoli, capitoli e "punzonatura" dei tag di dialogo. | Evitare che il narratore si "fondesse" con i titoli. |
| **v2.3** | Monastic | Divieto assoluto di modificare verbi, pronomi e struttura delle frasi. | Risolto il bug delle allucinazioni (es. cambio pronomi "lo" -> "la"). |
| **v2.3.2** | **Universal** | Sostituzione esempi specifici con modelli generici (Marco/Julia). | Evitare bias del modello sul libro corrente e migliorare la segmentazione dei tag. |

---

---

## Stage B2: Sound Director

### B2-Macro

| Versione | Milestone | Cambiamenti Chiave | Rationale |
| :--- | :--- | :--- | :--- |
| **v1.0-v3.x** | Warehouse-First | Redis catalog lookup, matching semantico all'85%, stop-on-missing. | Architettura ormai archiviata (Sound Library). |
| **v4.0 (file: b2_macro_v4.0.yaml)** | Sound-on-Demand | Zero catalogo Redis. PAD prodotto ex-novo da ACE-Step. PadRequest completo + PadArc. | Eliminare dipendenza dalla sound library. |
| **v4.2 (versione interna)** | ACE-Step Ready | Arc proporzionality (segmenti durata proporzionale al capitolo). Pre-build rule (segmento `low` prima di ogni `high`). Qwen3 vocabulary integrato nel prompt. `roadmap_item` per structural roadmap ACE-Step. | Fix del problema dei segmenti arc di durata uniforme (non rispettavano la narrativa). Vocabolario Qwen3 per evitare prompt drift. |

### B2-Micro (Monolitico)

| Versione | Milestone | Cambiamenti Chiave | Rationale |
| :--- | :--- | :--- | :--- |
| **v4.0 (file: b2_micro_v4.0.yaml)** | Sound-on-Demand | Zero catalogo Redis. Shopping list diretta per ARIA ACE-Step. | Eliminare dipendenza dalla sound library. |
| **v4.1 (versione interna)** | BBC/Star Wars Paradigm | AMB paradigm rewrite: cambio fisico solo tra scene consecutive, max 1, 3-5s, non loop. SFX test 0 (la domanda è "c'è un momento culminante?", non "c'è un'azione?"). STING rules: solo rivelazioni irreversibili, timing middle/end. | Rispettare il paradigma BBC Radio Drama: silenzio come default, ogni suono deve guadagnarsi il diritto di esistere. |

### B2-Micro-Director (Split Architecture)

| Versione | Milestone | Cambiamenti Chiave | Rationale |
| :--- | :--- | :--- | :--- |
| **v1.0 (file: b2_micro_director_v1.0.yaml)** | Separazione ruoli | LLM analizza solo eventi fisici in linguaggio naturale. Zero production_tags, zero canonical_id, zero spec ACE-Step. Output: SoundEventScore con AmbientEvent/SfxEvent/StingEvent. | Il problema della modalità monolitica: l'LLM deve fare decisioni narrative E tecniche simultaneamente → errori di consistenza canonical_id. Separando i ruoli, il Director vede solo il testo narrativo. |

### B2-Micro-Engineer (Split Architecture)

| Versione | Milestone | Cambiamenti Chiave | Rationale |
| :--- | :--- | :--- | :--- |
| **v1.0 (file: b2_micro_engineer_v1.0.yaml)** | Conversione tecnica | LLM riceve SoundEventScore e produce production_tags in vocabolario Qwen3. Shopping list costruita PRIMA delle scenes_automation. Tabella vietato/ammesso nel prompt. | Strutturalmente impossibile il canonical_id mismatch: la shopping list è la fonte di verità per i canonical_id, le automazioni la consumano. Vocabolario Qwen3 impone conversione sistematica dei termini sound designer → musicista. |

---

## Lezioni Apprese

### Il Pattern "Monastico" (Stage C)
Dare troppa libertà all'LLM (es. *"pulisci il testo per il TTS"*) portava a piccole allucinazioni grammaticali. La versione Monastica impone all'IA di trattare il testo come "testo sacro", limitandosi alla segmentazione e alla normalizzazione fonetica senza toccare la sostanza letteraria.

### L'Isolamento dei Tag (Stage C)
I "speech tags" (`disse lui`, `replicò Chen`) devono essere rimossi dalla battuta e spostati in una scena Narratore separata. Il clone vocale del personaggio non legge descrizioni di se stesso.

### Il Problema del Vocabolario Qwen3 (Stage B2)
ACE-Step usa Qwen3 come LM interno, addestrato su metadata di canzoni e sound recordings, non su manuali di sound engineering. Termini come "spring reverb", "tape saturation" o "ARP 2600" vengono riscritti internamente da Qwen3, portando a "prompt drift": il suono generato deriva dal prompt semplificato di Qwen3, non da quello originale. La soluzione è usare vocabolario da musicista (materiali fisici, ambienti reali, strumenti comuni).

### Il Canonical_id Mismatch (Stage B2-Micro)
Nella modalità monolitica, l'LLM doveva generare la shopping list e le automazioni in un unico output, con il rischio che un canonical_id presente nelle automazioni non fosse presente nella shopping list (o viceversa). La modalità split risolve strutturalmente questo problema: l'Engineer costruisce prima la shopping list (stabilendo i canonical_id), poi le automazioni le referenziano.

---
*Ultimo aggiornamento: 17 Aprile 2026 — aggiunto Stage B2 (b2_macro v4.2, b2_micro v4.1, b2_micro_director v1.0, b2_micro_engineer v1.0).*
