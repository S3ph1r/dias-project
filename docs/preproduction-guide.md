# DIAS Pre-production & Project Architecture

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

## 🧠 Stage 0: Intelligence Analysis (Protocollo 0.1/0.2)
Lo Stage 0 è il "Cervello" preventivo che opera tramite un protocollo a due chiamate LLM (Gemini 1.5 Flash-Lite) per mappare il libro. Tutti i prompt sono gestiti su **DIAS (LXC 190)** e versionati in `dias-inventory.md`.

### 🦿 Stage 0.1: Discovery (La Scansione Ossea)
*   **Obiettivo**: Identificare i confini fisici del libro e lo stile di punteggiatura dell'autore.
*   **Azione**: Gemini analizza il testo per estrarre la mappa dei capitoli e le regole di dialogo (es. trattini vs virgolette).
*   **Output: `fingerprint.json`**:
    *   **Chapter Map**: ID e nomi dei capitoli essenziali per lo Stage A.
    *   **Stylistic Markers**: Regole per il `SourceNormalizer` (vedi [Production Standard](./production-standard.md)).

### 🎭 Stage 0.2: Intelligence (L'Anima del Libro)
*   **Obiettivo**: Estrarre il potenziale artistico e proporre un casting.
*   **Azione**: Gemini riceve la struttura consolidata dallo 0.1 e analizza i contenuti per creare i profili dei personaggi.
*   **Output: `preproduction.json`**:
    *   **Character Bible**: Lista esaustiva (Primary/Secondary/Tactical) con profili vocali (Età, Sesso, Timbro). È la fonte autoritativa per gli **Speaker ID** dello Stage C.
    *   **Sound Design Palette**: 3 proposte di mood sonoro per la Dashboard.
*   **Stage C Integration**: I profili dei personaggi qui definiti vengono iniettati nello Stage C (via Stage B), permettendo alla Regia Artistica di assegnare correttamente lo `speaking_style` e di separare le battute dal narratore.
*   **Dashboard Interaction**: I dati popolano la **Casting Table**. Una volta che il Regista umano assegna i Voice ID e clicca "Salva", il `preproduction.json` diventa il contratto definitivo per lo **Stage D (Voice Proxy)**.

3.  **Future Development (Long Books)**: **Sequential Contextual Injection**
    *   **Problema**: Libri > 800k caratteri sforano i limiti di quota (429) e di finestra di contesto.
    *   **Soluzione**: Divisione in blocchi da ~400k gestiti in modo ricorsivo.
    *   **Meccanismo**: Ogni blocco riceve il `Summary` e il `JSON` dei blocchi precedenti come "Preamble".
    *   **Vantaggio**: Mantiene la coerenza del Casting Bible ed evita duplicazioni.
    *   **Case Study (Hyperion)**: Validata la necessità tramite compressione manuale e patch di pausa (60s) per rispettare i limiti TPM.

---

## 🎨 Dashboard "Digital Director"
La tab **Pre-production** è il centro di comando estetico del progetto.

-   **3D Cyber-Ring Carousel**: Selezione della **Global Voice** con rotazione 3D e anteprime audio. Le voci sono caricate dal Registry ARIA (Redis 120).
-   **Casting Table**: Popolata dai risultati dello **Stage 0.2**, permette l'assegnazione chirurgica dei doppiatori per ogni personaggio rilevato.
-   **Atmosphere Selection**: Scelta del mood sonoro tra le 3 palette proposte dall'Intelligence.
-   **💾 Salva Dossier**: Pulsante critico che scrive le scelte definitive dell'utente in `preproduction.json`.

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
