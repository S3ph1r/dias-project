# 🏛️ DIAS Holistic Workflow Status (v6.6)

Questo documento riassume il funzionamento della pipeline DIAS, confrontando il design teorico (Docs) con l'implementazione reale (Codebase).

---

## 🔄 End-to-End Workflow

| Fase | Componente | Azione Dashboard | Backend / Codebase | Output / Persistenza | Stato |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **0. Setup** | Project Manager | `New Project` + PDF | Crea `/data/projects/{id}/` | PDF in `source/` | ✅ |
| **1. Intel** | **Stage 0** | `Start Analysis` | Gemini analizza il testo intero | `fingerprint.json` | ✅ |
| **2. Regia** | **Dossier Tab** | `Casting` + `3D Ring` | L'utente associa voci ai personaggi | `preproduction.json` | ✅ |
| **3. Ingest** | **Stage A** | `Resume Pipeline` | PDF → TXT → Chunk (~2500 parole) | `stages/stage_a/output/` | ✅ |
| **4. Semant.** | **Stage B** | (Automatico) | Analisi emozionale e arc narrativo | `stages/stage_b/output/` | ✅ |
| **5. Anchor** | **Stage B2** | (Automatico) | Identifica punti di stacco musicali | `stages/stage_b2/output/` | ✅ |
| **6. Scena** | **Stage C** | (Automatico) | Segmentazione in scene (Emotional Beats) | `stages/stage_c/output/` | ✅ |
| **7. Sintesi** | **Stage D** | (Automatico) | **Risoluzione Voce (Casting > Global)** | `.wav` in `stage_d/` | ✅ |
| **8. Music** | **Stage E** | (Pianificato) | Generazione soundscape cinematico | `.wav` in `stage_e/` | 🚧 |
| **9. Final** | **Stage F/G** | (Pianificato) | Mixing multi-stem e Mastering | `final/{id}.mp3` | 🚧 |

---

## 🧠 Le Tre Verità (Precedenza Vocale)

Abbiamo appena validato e implementato la **Gerarchia di Risoluzione** nello Stage D. Quando la pipeline incontra una scena, decide la voce così:

1.  **Casting Personaggio**: Controlla `preproduction.json` → `casting`. Se lo speaker è mappato, vince lui.
2.  **Global Voice**: Se non c'è mapping specifico, usa la voce scelta nel **3D Cyber-Ring**.
3.  **System Default**: Fallback estremo su `luca` (ARIA Narrator).

---

## 📊 Stato della Codebase vs Documentazione

### **Cosa Funziona Realmente (Codebase Validata)**
*   **Isolamento Progetto**: Ogni libro vive nella sua sandbox. Non c'è più collisione di dati.
*   **Regia Persistente**: Il tasto "Salva" della dashboard è ora il "Telecomando" dello Stage D.
*   **3D Carousel**: Visualizzazione premium e anteprime audio integrate nel flusso.
*   **Stage 0-D**: La catena di montaggio dalla "DNA extraction" alla "Voice Synthesis" è saldata e funzionante.

### **Cosa Manca / Da Testare**
*   **E2E Re-Test**: Con le nuove modifiche alla gerarchia dei parametri, è consigliabile far girare un intero capitolo di "Cronache del Silicio" per verificare l'applicazione dei casting.
*   **Stage E/F/G**: Questi sono documentati nel blueprint ma il codice è ancora in fase di prototipazione (non sono inclusi nell'orchestratore seriale di produzione).

---

## 🎯 Prossimi Passi Consigliati
1.  **Validazione E2E**: Avviare la pipeline su un progetto pulito per confermare che `fingerprint.json` -> `preproduction.json` -> `Stage D` funzioni senza intoppi.
2.  **Rafforzamento Stage 0**: Verificare che l'estrazione personaggi di Gemini 1.5 Flash sia abbastanza precisa per il casting (attualmente è molto buona ma può essere raffinata).
