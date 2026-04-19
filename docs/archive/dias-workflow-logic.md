# DIAS Workflow Logic: L'Architettura del Radiofilm Deterministico
## Revisione v8.2 "B2 Technical Specification" — Aprile 2026

Questo documento definisce la pipeline di produzione DIAS e l'integrazione con il magazzino ARIA.

---

## 1. Mappatura degli Stage (Nomi e Funzioni)

| Stage | Nome in Codice | Input Primario | Output Primario |
| :--- | :--- | :--- | :--- |
| **Stage 0** | L'Occhio Supremo | Libro Grezzo | Casting Concept (JSON) |
| **Stage A** | Lo Spaccapietre | Libro Grezzo | Micro-chunks (~500 parole) |
| **Stage B** | Lo Psicologo | Testo Macro | Analisi Emotiva (primary_emotion) |
| **Stage C** | Il Regista Vocale | Micro-chunk | Istruzioni per Scene (Array JSON) |
| **Stage B2** | **Lo Spotter** | **Stage B + Stage C** | **Cue Sheet + Shopping List** |
| **Stage D** | L'Attore Isolato | Scene (Stage C) | Clip Vocali (.wav) |
| **Stage E/F** | MIXDOWN Fisico | Wav (D) + Cue Sheet (B2) | Radiofilm Finale (.wav) |

---

## 2. Focus Stage B2: Il "Casting Director" Sonoro

Lo **Stage B2** è il ponte tra la regia testuale e il magazzino ARIA.

### A. Input (Dati da riconciliare):
*   **Contesto Emotivo (Stage B)**: Es. `"primary_emotion": "scifi_dread"`.
*   **Struttura Scene (Stage C)**: L'array di battute con ID scena e tempi respiratori.
*   **Discovery (ARIA)**: Il registro Redis `aria:registry:master` (su `{ARIA_NODE_IP}`).

### B. Compiti Logici (Cosa deve fare):
1.  **Pescaggio Pad**: Matchare la `primary_emotion` con i tag dei "Pads" di ARIA.
2.  **Spotting Stings**: Analizzare il testo delle scene alla ricerca di onomatopee o azioni fisiche che richiedano uno "Sting".
3.  **Semantic Match**: Validazione (accettazione solo se aderenza > 85%).
4.  **Generazione Ordini**: Se un suono manca, scriverlo nella `Shopping List`.

### C. Output (Technical Schema):
*   **Cue Sheet (Per Stage E/F)**:
    ```json
    {
      "global_pad": "pad_scifi_dread_01",
      "overrides": [
        { "target_scene_id": "015", "action": "inject_sting", "asset_id": "sting_metal_slam" }
      ]
    }
    ```
*   **Shopping List (Per ARIA)**:
    ```json
    {
      "missing_assets": [
        { "category": "stings", "description": "Schiaffo secco con eco", "context": "Scena 022" }
      ]
    }
    ```

---

## 🏁 Roadmap Operativa: Next Steps (LXC 190)

1. **Implementare il Client Redis** in Stage B2 per leggere `{ARIA_NODE_IP} = 192.168.1.139`.
2. **Sviluppare il Matcher Semantico** (Algoritmo 85%).
3. **Formalizzare l'esportazione del Cue Sheet** per la pipeline di Mixdown.

---
*Status: Specifiche B2 Finalizzate — 05/04/2026*
