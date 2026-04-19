# DIAS - Stage B2 (The Spotter) Handover Document
**Data**: 05 Aprile 2026  
**Ambiente**: LXC 190 (Brain/Regia) -> LXC 120 (Redis) -> PC 139 (ARIA)

## 🎯 Obiettivo Corrente
Implementare lo **Stage B2 (The Spotter)** nella pipeline DIAS per l'automazione del sound design (Pads e Stings) tramite matching dinamico con il catalogo ARIA.

---

## 🔍 Analisi degli Input (Rilevati da Progetto Campione)

Il sistema opera su **Micro-Chunks** (es. `chunk-000-micro-000`):

1.  **Stage B (Semantic Analysis)**:
    - Fornisce la **Macro-Emozione** (`primary_emotion`: es. "paura") e il **Setting** (es. "Caverna aliena").
    - **Ruolo per B2**: Determina quale **Pad** (tappeto sonoro continuo) scegliere dal catalogo ARIA.

2.  **Stage C (Scene Director)**:
    - Fornisce l'**Array di Scene Micro**. Ogni scena ha il testo completo e metadati.
    - **Ruolo per B2**: Identifica i "cue point" (es. Scena 10: *"battuto il palmo sul masso"*) per l'inserimento di **Stings** (effetti sonori brevi).

3.  **ARIA Asset Registry (Redis 120)**:
    - Chiave: `aria:registry:master` (Hash Redis).
    - Contenuto: Lista degli asset audio generati o disponibili con relativi tag e IDs (es. `pad_dark_tension_01`, `sting_rock_impact_04`).

---

## 🏗️ Architettura dello Stage B2

### 1. Posizionamento Pipeline
La catena è seriale e non deve essere alterata:  
`Stage A (Ingest) -> B (Semantic) -> C (Regia) -> D (Voice) -> **B2 (Spotter)** -> E (Mixdown)`

### 2. Logica di Prompt (Gemini Sound Director)
Lo Stage B2 utilizzerà Gemini (via `GatewayClient`) per il **Matching Semantico (85%)**:
- **Input nel Prompt**: JSON B + JSON C + Elenco Asset ARIA.
- **Compito LLM**:
    - Selezionare l'asset migliore per il Pad globale.
    - Cercare onomatopee o azioni fisiche nelle scene e associarle a Stings esistenti.
    - Se un suono è narrativamente essenziale ma manca nel catalogo -> Generare Shopping List.

### 3. Struttura Output
- **Cue Sheet (per Stage E/F)**: Mappa definitiva `SceneID` -> `AssetID` + `Volume`.
- **Shopping List (per ARIA)**: Richieste di nuovi asset necessari non trovati nel registro.

---

## 🛠️ Stato dei Lavori e Prossimi Passi

### Operazioni Compiute:
- [x] Analisi della relazione semantica B-C basata sui file JSON reali.
- [x] Identificazione del registro ARIA su Redis 120.
- [x] Creazione bozza `BaseStage` per B2 (ancora da scrivere su file).
- [x] Aggiornamento `QueuesConfig` in `src/common/config.py` con la coda `spotter`.

### Task Immediati (Nuova Chat):
1.  **Verifica Shell**: Assicurarsi che `run_command` funzioni per interrogare Redis 120.
2.  **Implementazione Stage B2**: Creare `src/stages/stage_b2_spotter.py` ereditando da `BaseStage`.
3.  **Prompt YAML**: Definire `config/prompts/stage_b2/v1.0_spotter.yaml`.
4.  **Handoff Stage D**: Modificare `output_queue` dello Stage D verso lo Stage B2.

---

## ⚠️ Nota Infrastrutturale: Terminal Hang-up
Durante la sessione corrente, lo strumento `run_command` è risultato bloccato nonostante il basso carico di sistema e il riavvio del container LXC 190. Gli strumenti `list_dir` e `view_file` sono invece funzionanti. Potrebbe trattarsi di un problema di connettività SSH o allocazione PTY dell'IDE.

---
**Firmato**: Antigravity (AI Coding Assistant)
