> **[ARCHIVIATO — Aprile 2026]**
> Roadmap di sviluppo Stage B2 con la fase pre-Sound-on-Demand. La Master Timing Grid
> e la re-architecture B2-Macro/B2-Micro sono ora implementate come descritto in `blueprint.md`.
> Per lo stato corrente, vedere `blueprint.md` e `dias-workflow-logic.md`.

# Roadmap: Stage B2 Sound Orchestration & Timing Grid

Questo documento traccia la rotta per l'evoluzione di DIAS dai metadati testuali alla regia sonora professionale, integrando la "Fisica del Suono" dello Stage D con l' "Intelligenza Artistica" di B2.

---

## 🏗️ Visione Architetturale: L'Orologio Universale

Il cuore pulsante dei prossimi sviluppi è la **Master Timing Grid**. Senza una misura precisa del tempo reale (prodotta da ARIA e recepita da Stage D), non è possibile costruire un montaggio di qualità.

### Fase 1: Fondamenta Temporali (The Master Timing Grid)
**Obiettivo**: Aggregare le durate atomiche dello Stage D in un asset unico.

1.  **Script di Consolidamento**: Sviluppare un tool (es. `create_timing_grid.py`) che scansi le scene di un micro-chunk e calcoli gli `start_offset` cumulativi (Vocal + Pause).
2.  **Integrazione Stage D**: Rendere questa funzione parte integrante del worker di Stage D (o come pre-processore di Stage B2).
3.  **Hierarchy**: La griglia deve supportare tre livelli:
    *   **Macro**: Durata totale del blocco da 2500 parole (per B2-Macro).
    *   **Micro**: Durata totale del micro-chunk da 300 parole (per B2-Micro).
    *   **Scene**: Durata e pause millimetriche (per lo spotting chirurgico).

---

## 🎼 Fase 2: Re-Architecture dello Stage B2

Lo Stage B2 deve evolvere seguendo la filosofia **"Architect & Sculptor"**.

### B2-Macro (L'Architetto della Palette)
*   **Ruolo**: Analizza il blocco da 2500 parole.
*   **Decisione**: Sceglie il tema musicale (MUS) e l'ambiente (AMB) dominante (Default Ambience).
*   **New Power**: Se la Timing Grid indica un blocco molto lungo e Stage B (Semantic) suggerisce un cambio di setting, può definire una transizione tra due atmosfere.

### B2-Micro (Lo Scultore della Dinamica)
*   **Ruolo**: Regia chirurgica sulle micro-scene.
*   **Automazione Volumi (Ducking/Swell)**: Usa la Timing Grid per alzare la musica nelle pause e abbassarla durante il parlato.
*   **Spotting di Precisione**: Colloca SFX e Stings con offset in secondi (es. "Lampo a +1.2s").
*   **Ambience Overrides**: Può attivare "bolle ambientali" locali (es. una telefonata, un rumore di fondo specifico) sopra il tappeto del Macro.

---

## 📜 Fase 3: Il Copione Artistico (Cue Sheet)

Dobbiamo distinguere tra due flussi di output:
1.  **Shopping List**: Elenco degli asset mancanti che ARIA deve generare (Stage E).
2.  **Production Cue Sheet**: Lo spartito definitivo per il Mixer (Stage G). Viene iniziato da Macro, arricchito da Micro e conterrà ogni istruzione temporale per la cucitura finale.

---

## 🏭 Fase 4: Stage E (Sound Factory) e Oltre

*   **Stage E**: Produrrà i WAV mancanti basandosi sui "Universal Prompts" generati da B2, rispettando la durata esatta richiesta dalla Timing Grid.
*   **Stage G**: Riceverà il `Production Cue Sheet` e la `Timing Grid` per eseguire il montaggio bit-perfect.

---

> [!IMPORTANT]
> **Prossimo Step Operativo**: Implementare `scripts/tools/create_timing_grid.py` e validarne i calcoli su un progetto reale, prima di aggiornare i prompt di B2 per consumare questi nuovi dati temporali.

---
*Documento di Handover - 8 Aprile 2026*
