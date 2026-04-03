# DIAS Prompt Evolution Registry

Questo documento traccia l'evoluzione dei prompt di regia AI (Stage B e Stage C), spiegando le sfide affrontate e il motivo dei passaggi di versione.

---

## 🔍 Stage 0: Intelligence & Discovery

Lo Stage 0 è la fase di analisi "fredda" del libro, dove viene estratta la struttura e il DNA artistico.

| Versione | Focus | Rationale |
| :--- | :--- | :--- |
| **v1.0 (Archetipo)** | Capitoli e Titoli | Mappatura grezza 1:1 della struttura fisica del libro. |
| **v1.1 (Punctuation)** | Marcatori Stilistici | Analisi dei simboli usati per dialoghi e pensieri (em-dash vs virgolette). |
| **v1.2 (Structural)** | Logica di Paragrafo | Introdotta la distinzione tra `toggle_paragraph` e `enclosed_pair` per guidare la normalizzazione. |
| **Intelligence v1.0** | **Radiofilm DNA** | Fusione dell'analisi strutturale con Casting esaustivo, Mood globale e Palette sonore. |

---

## 🔍 Stage 0: Intelligence & Discovery

Lo Stage 0 è la fase di analisi "fredda" del libro, dove viene estratta la struttura e il DNA artistico.

| Versione | Focus | Rationale |
| :--- | :--- | :--- |
| **v1.0 (Archetipo)** | Capitoli e Titoli | Mappatura grezza 1:1 della struttura fisica del libro. |
| **v1.1 (Punctuation)** | Marcatori Stilistici | Analisi dei simboli usati per dialoghi e pensieri (em-dash vs virgolette). |
| **v1.2 (Structural)** | Logica di Paragrafo | Introdotta la distinzione tra `toggle_paragraph` e `enclosed_pair` per guidare la normalizzazione. |
| **Intelligence v1.0** | **Radiofilm DNA** | Fusione dell'analisi strutturale con Casting esaustivo, Mood globale e Palette sonore. |

---

## 🎭 Stage B: Semantic & Emotional Analyzer

L'obiettivo dello Stage B è estrarre il "mood" macroscopico del testo per guidare la musica e lo stile di narrazione globale.

| Versione | Focus | Rationale |
| :--- | :--- | :--- |
| **v1.0 (Base)** | Emozioni base | Estrazione di Valence, Arousal, Tension e Primary Emotion. |
| **v1.1 (Nuance)** | Sottotesto | Introduzione del "speaking_style" (in inglese) per i personaggi e analisi dell'intento narrativo profondo. |

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

## 💡 Lezioni Apprese

### Il Pattern "Monastico"
Dopo diversi test, abbiamo scoperto che dare troppa libertà all'LLM (es. *"pulisci il testo per il TTS"*) portava a piccole allucinazioni grammaticali. La versione **Monastica** impone all'IA di trattare il testo come "testo sacro", limitandosi alla segmentazione e alla normalizzazione fonetica senza toccare la sostanza letteraria.

### L'Isolamento dei Tag
I "speech tags" come *", replicò lui"* o *", disse Chen"* devono essere rimossi dalla battuta e spostati in una scena Narratore separata. Questo evita che il clone vocale del personaggio legga descrizioni di se stesso, mantenendo l'immersività cinematografica.

---
*Ultimo aggiornamento: 03 Aprile 2026*
