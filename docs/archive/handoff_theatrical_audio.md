# DIAS Handoff: Theatrical Audio Standard (Qwen3-TTS)

## 🎯 Obiettivo del Progetto
Elevare la qualità della narrazione DIAS a uno standard teatrale sovrapponibile a ElevenLabs, integrando i parametri validati nella pipeline di produzione automatizzata (Stage A-D).

## 🏆 Le Scoperte: La "Formula Oscar"
Dopo intensi benchmark (A/B/C), abbiamo identificato i parametri per la massima naturalezza espressiva:

*   **`subtalker_temperature`**: **0.75** (Il "punto magico" per grana umana e sospiri).
*   **`temperature`**: **0.7** (Bilanciamento tra fedeltà e variazione).
*   **`voice_ref_text`**: **MANDATORIO**. Deve coincidere con il testo parlato nel file di riferimento (`ref_padded.wav`).
*   **Punteggiatura**: Uso del trattone (` - `) per pause drammatiche e virgole extra per il respiro.
*   **Prompting "Natural Narrative"**: Istruzioni fisiche in inglese (es. *Philosophical, resonant chest voice*) pilotate da istruzioni registiche in italiano (**Mediterranean Prompting**).

## 📂 Struttura Asset (PC 139)
Ogni voce in `/home/Projects/NH-Mini/sviluppi/ARIA/data/assets/voices/{voice_id}/` deve contenere:
- `ref.txt`: Il testo di riferimento.
- `ref_padded.wav`: Il campione audio di riferimento.

## 🛠️ Stato del Lavoro e Roadmap
Abbiamo appena definito un approccio **Dossier-Centric**. Invece di risolvere i parametri in corsa, devono vivere nel registro di pre-produzione del progetto.

### 1. Automazione Dossier (STABILE)
- **File**: `preproduction.json` in ogni cartella progetto.
- **Task**: Deve contenere i default `subtalker: 0.75`, `temp: 0.7` e i percorsi assoluti ai file `ref.txt` e `ref_padded.wav` per ogni voce del casting.

### 2. Stage D (Voice Gen Proxy)
- **Modifica richiesta**: Semplificare `stage_d_voice_gen.py` affinché legga i parametri direttamente dal dossier di pre-produzione. Se il dossier ha i campi `voice_ref_text`, lo Stage D li passa a Redis.

### 3. Prompt Engineering (Versionati)
- **Stage B v1.1 (Nuance)**: Estrazione sottotesto e intento narrativo.
- **Stage C v1.5 (Theatrical)**: Regole rigide anti-allucinazione fonetica (accenti solo se ambigui) e vocaboli acustici avanzati.

## 🧪 Piano di Verifica
1.  **Update Dossier**: Verificare che i file JSON di `Cronache-del-Silicio` e `dan-simmons-hyperion` siano aggiornati con i nuovi campi.
2.  **E2E Test**: Far girare una scena e monitorare il payload su Redis (deve contenere `subtalker_temperature: 0.75`).

---

## 💬 Cosa dire al nuovo Agent
Copia e incolla questo messaggio nella nuova chat:

> "Ciao! Sto lavorando all'ottimizzazione audio della pipeline DIAS. Abbiamo definito uno 'Standard Teatrale' basato su Qwen3-TTS (Subtalker 0.75, Ref_text, Natural Narrative). Leggi il file `/root/.gemini/antigravity/brain/d0367575-8d86-428a-a4e8-39481e6fb9b9/handoff_theatrical_audio.md` per il briefing completo. Il tuo compito è completare l'integrazione 'Dossier-Centric' negli Stage 0 e D, aggiornare i dossier dei progetti esistenti e verificare la qualità finale con un test E2E."
