# DIAS Production Standard: Recitazione da Oscar (v2.3)

Questo documento definisce lo standard qualitativo per la produzione audio di DIAS, finalizzato a ottenere una narrazione teatrale sovrapponibile a ElevenLabs utilizzando il motore Qwen3-TTS.

---

## 🎯 Obiettivo: Lo Standard Teatrale
Elevare la qualità della narrazione a un livello cinematico, integrando i parametri validati nella pipeline automatizzata (Stage A-D).

## 🏆 La "Formula Oscar" (Parametri AI)
Dopo intensi benchmark comparativi (DTW, Energy, Pitch), abbiamo isolato la combinazione perfetta per la massima naturalezza espressiva:

| Parametro | Valore Target | Effetto sulla Voce |
| :--- | :--- | :--- |
| **`subtalker_temperature`** | **0.75** | Il "punto magico" per grana umana e sospiri. |
| **`temperature`** | **0.7** | Bilanciamento tra fedeltà linguistica e variazione prosodica. |
| **`top_p` / `top_k`** | **0.8+ / 50** | Parametri di campionamento stabili (viste come standard Qwen3). |
| **`voice_ref_text`** | **Mandatorio** | Metronomo fonetico. Deve corrispondere al `ref_padded.wav`. |

---

## 🎭 Regia e Punteggiatura Audio

Qwen3-TTS risponde a istruzioni registiche tramite tag `[...]` e punteggiatura specifica.

### 1. Istruzioni Interpreti (Instruct Style)
- **Natural Narrative**: Usare istruzioni fisiche in Inglese (es. *Philosophical, resonant chest voice*) pilotate da istruzioni registiche in Italiano (**Mediterranean Prompting**).
- **Mood vs Micro-management**: È preferibile fornire un **Mood Dominante** (es. *"Una narrazione calda, professionale e riflessiva"*) piuttosto che micro-istruzioni (es. *"respira qui"*), per evitare che il modello diventi meccanico.

### 2. Punteggiatura Ottimizzata
- **Tratto lungo (` - `)**: Usalo per pause drammatiche e sospensioni pulite. **Sostituisce i puntini di sospensione (`...`)**, che spesso causano artefatti (clicking).
- **Virgola extra (`,`)**: Usala per forzare il respiro naturale dell'interprete.
- **Virgolette o CAPITALS**: Usale per forzare l'enfasi su parole chiave.

### 3. Normalizzazione Fonetica
In Stage C, il testo viene "pulito" (clean_text) seguendo queste regole:
- **Numeri**: Convertiti sempre in lettere (es. *"2042"* → *"duemilaquarantadue"*).
- **Accenti**: Inseriti solo per parole ambigue (es. *"pàtina"*, *"scivolò"*).
- **Isolamento Titoli**: Ogni titolo di libro o capitolo deve essere isolato in una scena dedicata con un `pause_after_ms` di **2000ms**.

---

## 🛠️ Architettura Asset
Ogni voce in `/data/assets/voices/{voice_id}/` deve contenere:
- `ref.txt`: Il testo esatto pronunciato nel campione audio.
- `ref_padded.wav`: Il campione audio di riferimento (min 10-15s).

> [!CAUTION] 
> **Il Bug della Collisione**: Se il testo da recitare è **identico** al testo in `ref.txt`, il modello potrebbe andare in loop o troncare l'audio. Evita sempre di usare sample che contengano le parole della scena target.

---

## 🧪 Benchmarking e Qualità (KPIs)
Per quantificare la qualità, DIAS utilizza analisi basate su **librosa** e **scipy**:

| Metrica | Target | Strumento |
| :--- | :--- | :--- |
| **Pitch Correlation (F0)** | **> 0.60** | Similitudine melodica con il reference umano. |
| **Energy Correlation (RMS)** | **> 0.85** | Enfasi e sospiri coesi con l'intento narrativo. |
| **Speech Rate** | **~150 wpm** | Cadenza narrativa (non meccanica). |

---

## 🚀 Roadmap Evolutiva: Dynamic Tuning
Il prossimo passo verso l'Oscar è il **Dynamic Parameter Tuning**: lo Stage C suggerirà combinazioni diverse di parametri tecnici (`subtalker`, `temperature`) per ogni singola scena, basandosi sulla carica emotiva rilevata (es: temperatura più alta per urla e panico).
