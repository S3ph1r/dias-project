# 🎬 DIAS Pre-production & Project Architecture

Questo documento descrive la struttura a progetto di DIAS e il funzionamento della fase di **Intelligence (Stage 0)** e della **Dashboard di Regia**.

---

## 🏗️ Project-Centric Structure
A partire dal 2026, DIAS utilizza una struttura isolata per ogni progetto (libro). Tutti i dati sono contenuti in:
`data/projects/{project_id}/`

### Gerarchia Directory
| Path | Descrizione |
|------|-------------|
| `source/` | Contiene il PDF originale e il file `.txt` estratto. |
| `stages/` | Output intermedi per ogni stage (A, B, C, D, etc.). |
| `logs/` | Log specifici delle analisi LLM per questo progetto. |
| `final/` | Risultati finali della produzione (audio e JSON pronti). |

---

## 🧠 Stage 0: Intelligence Analysis
Lo Stage 0 è il "Cervello" preventivo che analizza il libro prima che inizi la produzione di massa.

### Documenti Chiave
1.  **`fingerprint.json`** (Sola Lettura - Prodotto dall'IA):
    *   **Chapter Map**: Mappatura di tutti i capitoli con titoli e parole chiave.
    *   **Character Dossier**: Estrazione di tutti i personaggi con profilo vocale e tratti.
    *   **Sound Design Palette**: 3 proposte stilistiche per l'atmosfera.
2.  **`preproduction.json`** (Scrittura - Prodotto dal Regista):
    *   **casting**: Mappa Nome Personaggio -> Voice ID (es. `Kaelen -> luca`).
    *   **global_voice**: Il Voice ID selezionato come narratore master.
    *   **soundtrack**: Lo stile musicale o il brano selezionato.

3.  **Future Proofing (Long Books - v6.8)**: **Sequential Contextual Injection**
    *   **Problema**: Libri > 800k caratteri sforano i limiti di quota (429) e di finestra di contesto.
    *   **Soluzione**: Divisione in blocchi da ~400k gestiti in modo ricorsivo.
    *   **Meccanismo**: Ogni blocco riceve il `Summary` e il `JSON` dei blocchi precedenti come "Preamble".
    *   **Vantaggio**: Mantiene la coerenza del Casting Bible ed evita duplicazioni.
    *   **Case Study (Hyperion)**: Validata la necessità tramite compressione manuale e patch di pausa (60s) per rispettare i limiti TPM.

---

## 🎨 Dashboard "Digital Director"
La tab **Pre-production** è il centro di comando estetico del progetto.

### Componenti Principali
-   **3D Cyber-Ring Carousel**: Selezione della **Global Voice** con rotazione 3D e anteprime audio. Le voci sono caricate dal Registry ARIA (Redis).
-   **Casting Table**: Popolata dallo **Stage 0**, permette l'assegnazione chirurgica dei doppiatori per ogni personaggio.
-   **Atmosphere Selection**: Permette di scegliere il "mood" del progetto.
-   **💾 Salva Dossier**: Scrive le scelte in `preproduction.json`.

### ⚖️ Logica di Precedenza Vocale (Stage D)
Durante la generazione audio, lo Stage D risolve la voce da usare seguendo questa gerarchia:
1.  **Casting Personaggio**: Se il personaggio ha una voce assegnata nel dossier, questa ha la massima priorità.
2.  **Global Voice**: Se la scena è narrativa o il personaggio non è mappato, viene usata la voce selezionata nel carosello 3D.
3.  **System Default**: In assenza di configurazione, il sistema ripiega sul narratore standard (`luca`).

---

## 💾 Persistenza e Sincronizzazione
-   **Salvataggio**: I dati sono salvati localmente al progetto per garantire portabilità.
-   **Consumo**: Lo Stage D legge il dossier all'inizio di ogni task per applicare le direttive del regista.

> [!IMPORTANT]
> Lo Stage 0 (Intelligence) deve essere completato per popolare la lista dei personaggi, ma la **Global Voice** può essere configurata e salvata in qualsiasi momento.
