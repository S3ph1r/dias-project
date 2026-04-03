# 📚 DIAS Documentation Index

Questo documento serve come punto di ingresso (Bussola) per navigare rapidamente tutta la documentazione di progetto di DIAS. I file sono elencati in base alla loro priorità logica.

> *Ultimo aggiornamento Indice: 30 Marzo 2026*

---

## 🏗️ 1. Architettura Core (I Fondamentali)

*   **[blueprint.md](blueprint.md)** 
    *   **Data Ultima Modifica:** 28 Marzo 2026
    *   **Funzione:** Il documento principale. Contiene le specifiche architetturali "Master", i diagrammi di flusso di DIAS, la definizione della pipeline A-G e la gestione della resilienza con Redis. **Inizia sempre da qui per capire il progetto.**
*   **[README.md](../README.md)** 
    *   **Data Ultima Modifica:** 27 Marzo 2026
    *   **Funzione:** Overview di alto livello per il setup, l'installazione rapida e i comandi base (`start_pipeline.sh`, ecc.).
*   **[dias-component-inventory.md](dias-component-inventory.md)** 
    *   **Data Ultima Modifica:** 27 Marzo 2026
    *   **Funzione:** Lista dettagliata e mappata di tutti i singoli script Python e servizi che compongono DIAS. Utile se non sai dove trovare un pezzo di codice.

---

## 🎭 2. Audio Teatrale e Integrazione ARIA (Sprint Recenti)

*   **[handoff_theatrical_audio.md](handoff_theatrical_audio.md)** 
    *   **Data Ultima Modifica:** 28 Marzo 2026
    *   **Funzione:** Descrive il protocollo di comunicazione (Redis Gateway) tra DIAS (Stage C) e ARIA (Stage D) per la generazione di audio teatrale, incluso lo standard di prompt "strutturato".
*   **[qwen3_technical_guide.md](qwen3_technical_guide.md)** 
    *   **Data Ultima Modifica:** 28 Marzo 2026
    *   **Funzione:** Come far parlare in modo espressivo Qwen3-TTS. Contiene il vocabolario per la sintesi teatrale e le regole per la punteggiatura e gli accenti, essenziale per il prompt engineering dello Stage C.
*   **[preproduction-guide.md](preproduction-guide.md)** 
    *   **Data Ultima Modifica:** 27 Marzo 2026
    *   **Funzione:** Spiega come compilare e gestire il file `preproduction.json` per assegnare le voci al cast, scegliere il tono base del narratore e la `temperature` del modello.

---

## ⚙️ 3. Sviluppo e Stato Avanzamento

*   **[technical-reference.md](technical-reference.md)** 
    *   **Data Ultima Modifica:** 27 Marzo 2026
    *   **Funzione:** Regole per sviluppatori (variabili d'ambiente, best practices di logging, uso di `DiasPersistence`).
*   **[dias_workflow_status.md](dias_workflow_status.md)** 
    *   **Data Ultima Modifica:** 27 Marzo 2026
    *   **Funzione:** Checklist dello stato di avanzamento. Cosa è in produzione, cosa è prototipato, cosa manca.

---
*Nota: La cartella `archive/` contiene documenti tecnici obsoleti o proposte superate. Consultali solo per ragioni storiche.*
