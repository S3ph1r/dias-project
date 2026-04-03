# Guida Tecnica: Ottimizzazione Qwen3-TTS per il Teatro

Questa guida condensa le ricerche sulla documentazione ufficiale di Fish Speech (architettura alla base di Qwen3-TTS) e i risultati dei nostri test sul campo per massimizzare la qualità attoriale e la stabilità del clone.

## 1. Architettura dei Parametri

Qwen3-TTS opera in due fasi: **Thinker** (genera i token semantici) e **Talker/Subtalker** (genera l'audio acustico).

| Parametro | Ambito | Effetto sulla Voce | Standard Teatrale (Win) |
| :--- | :--- | :--- | :--- |
| **`temperature`** | Thinker | Variazione della prosodia globale e del ritmo. | **0.7** (Mantiene la coerenza senza essere monotono) |
| **`subtalker_temp`**| Talker | **"Grana" e calore della voce.** | **0.75** (Il punto di massima espressività umana) |
| **`voice_ref_text`**| Allineamento | Metronomo temporale e fonetico. | **Enabled** (Usa sempre il testo del prologo) |

---

## 2. Il "Sunto" dell'Oscar: Lo Standard Teatrale

Dopo una sessione intensiva di benchmarking, abbiamo isolato la combinazione perfetta per la recitazione.

### La Formula Magica
- **Subtalker Temperature: 0.75**
- **Voice Reference Text: Attivo** (Deve corrispondere esattamente al campione `ref_padded.wav`)
- **Instruct Style: "Natural Narrative"** (Istruzioni emotive in Inglese)
- **Punteggiatura**: Trattino lungo ` - ` al posto di `:` o `...`

---

## 3. Laboratorio di Benchmarking (Log Storico)

Confronto effettuato sul paragrafo "Il suo appartamento" (Scenes 009-012) contro ElevenLabs (Rif: 49.16s).

| Test | Configurazione | Durata | Enfasi (Energy) | Recitazione (Pitch) | Risultato |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **A** | Ref_text + 0.6 | 48.57s | 0.901 | 0.658 | Molto solido, ritmo perfetto. |
| **B** | X-Vector + 0.7 | 53.12s | 0.898 | 0.685 | Più "anima", ma perde il ritmo. |
| **C** | **Ref_text + 0.75** | **48.73s** | **0.906** | **0.736** | **VINCITORE: Oscar per la recitazione.** |

> [!IMPORTANT]
> Il **Test C** dimostra che alzando la temperatura del subtalker a 0.75 e forzando l'allineamento con il `ref_text`, il modello raggiunge una correlazione melodica (**0.73**) quasi identica a un attore umano.

---

## 4. Diagnostica: Acting Inspector

Per verificare la qualità di una scena, usiamo lo strumento di analisi basato su **Dynamic Time Warping (DTW)**.

**Comando:**
```bash
python scripts/acting_inspector.py --el path/to/elevenlabs.wav --dias path/to/dias.wav --out path/to/report/
```

**Metriche di Successo:**
*   **Energy Correlation (>0.85)**: L'enfasi sulle parole è corretta.
*   **Pitch Correlation (>0.60)**: La melodia della voce è espressiva.

---

## 5. Il Problema del Riferimento (`ref_padded` & `ref.txt`)

Il sistema di cloning utilizza il file di riferimento come un "prefisso" di contesto.

1.  **`ref.txt` Critico**: Deve contenere **esattamente** quello che viene detto nel file audio (incluse eventuali esitazioni, "ehm", "uhm"). Se c'è discrepanza, il modello si "disallinea" e inizia a tagliare le parole a fine frase.
2.  **Il Bug della Collisione**: Se il testo da recitare è **identico** al testo nel `ref.txt`, il modello entra in loop o si ferma subito. 
    *   **Perché?** L'attenzione del trasformatore vede che il target è già stato "completato" nel prefisso e tronca l'audio. 
    *   **Soluzione**: Non usare mai un sample di riferimento che contiene le stesse parole del testo target.

---

## 3. Strategie di Prompting per la Recitazione

Qwen3-TTS supporta il **Natural Language Instruct** tramite tag `[...]`.

### Mood vs Micro-management
Dai nostri test (v10 vs v13), è emerso che:
*   **SBAGLIATO**: Dare troppi dettagli fisici (es. *"accentua la sillaba di me-tal-li-co"*, *"fai un respiro qui"*). Il modello diventa meccanico.
*   **GIUSTO**: Dare un **Mood Dominante** (es. *"Una narrazione calda, professionale e riflessiva"*). Il modello ha abbastanza "intelligenza" per dedurre l'enfasi corretta dalla semantica del testo.

### Tabella delle Tecniche Interpretative

| Obiettivo | Tecnica di Punteggiatura | Istruzione (Instruct Tag) |
| :--- | :--- | :--- |
| **Pausa Strategica** | Trattino lungo ` - ` o virgola `,` | `[slow, unhurried]` |
| **Sospetti/Mistero** | Evitare `...` (creano artefatti), usare `,` | `[whispery, intimate tone]` |
| **Enfasi Forte** | Mettere la parola tra virgolette o CAPITALS | `[authoritative, focused energy]` |
| **Narratore Epico** | Frasi brevi terminate da punto `.` | `[deep cinematic resonance, slow pace]` |
| **Ironia/Fatica** | Virgole frequenti | `[exhausted clarity, faint irony]` |

---

## 4. Esempi di Punteggiatura Ottimizzata

| Effetto Desiderato | Testo Esempio |
| :--- | :--- |
| **Attesa Drammatica** | *"L'Architetto dei Fantasmi - era finalmente arrivato."* |
| **Elenco Cadenzato** | *"C'era cemento, luce, e storie. Molte storie."* |
| **Sospensione Inquieta** | *"Si diceva che Neo-Kyoto non dormisse mai, ma non era vero."* |

> [!IMPORTANT]
> **I puntini di sospensione (`...`) sono pericolosi.** In Qwen3 spesso innescano un rumore di "clicking" o un respiro troncato male. Meglio sostituirli con un trattino ` - ` per forzare una pausa pulita senza artefatti.
