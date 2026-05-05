# DIAS Production Quality Audit - "Cronache del Silicio"

Questo documento traccia la transizione dalla "Run Standard" (interrotta) alla "Run Premium" (configurata il 22 Aprile 2026).

## 🚩 Stato Pre-Reset (Mancanze Rilevate)

| Stage | Problema Rilevato | Causa | Impatto Artistico |
| :--- | :--- | :--- | :--- |
| **Stage B (Semantic)** | Assenza campi `subtext`, `narrative_arc`, `narrator_base_tone`. | Prompt v1.1 non ancora sincronizzato su LXC 201. | Analisi emotiva piatta, basata solo su Valence/Arousal/Tension. |
| **Stage C (Director)** | Errore `UnboundLocalError: local variable 'json'`. | Bug nel codice Python di caricamento preproduction. | Gemini non riceve i profili vocali fisici dei personaggi. |
| **Stage C (Director)** | Istruzioni `qwen3_instruct` generiche. | Mancanza dei dati di contesto dello Stage B e del dossier. | Le voci dei personaggi mancano di "ancoraggio fisico" (es. timbro, età, cadenza). |

## 🧪 Criteri di Validazione (Prossima Run)

### Stage B: Verifica Metadati Enriched
Il JSON di output deve contenere obbligatoriamente nella chiave `block_analysis`:
- [ ] `subtext`: descrizione dell'intento non detto.
- [ ] `narrative_arc`: descrizione della curva di tensione.
- [ ] `narrator_base_tone`: istruzione acustica per il narratore (in inglese).

### Stage C: Verifica Caricamento Dossier
- [ ] Log: Assenza di `Could not load characters_vocal_profiles`.
- [ ] Log: Presenza di `Stage C prompt v2.4.0 loaded`.
- [ ] JSON: Le istruzioni `qwen3_instruct` devono contenere riferimenti ai tratti fisici del dossier (es. "resonant voice", "hushed tone", "gravelly texture").

---
*Creato il 22 Aprile 2026 alle 17:36 — Fase di Reset Totale.*
