# DIAS — Analisi Qualitativa Pipeline Voce (v1)

**Data analisi:** 29 Aprile 2026  
**Scope:** Pipeline voce-only (Stage 0 → A → B → C → D). Versione 1 — musica, ambient, SFX esclusi.  
**Obiettivo v1:** Audiolibro professionale con massima qualità di narrazione e dialoghi.

---

## Obiettivo e vincoli di design

Il prodotto finale di DIAS v1 è una serie di file WAV — uno per micro-scena — che uniti producono un audiolibro dove:
- Ogni personaggio ha una voce fisicamente distinta e coerente per tutto il libro
- Il narratore modula tono e ritmo in base all'emozione dominante della scena
- Le pause tra i WAV seguono la semantica del testo (cambio battuta ≠ fine paragrafo ≠ stacco narrativo)
- Il TTS riceve per ogni scena una direzione autonoma e autosufficiente (Qwen3-TTS è zero-shot amnesico)

Il vincolo architetturale più importante: **Qwen3-TTS 1.7B non ha memoria tra le scene**. Ogni WAV deve portare con sé tutto il contesto vocale necessario nel campo `qwen3_instruct`. Non può "ricordare" come ha parlato un personaggio nella scena precedente. Questo vincolo guida ogni scelta progettuale degli stage upstream.

---

## Logica del carico cognitivo per stage

La pipeline è strutturata per **distribuire il carico cognitivo** su modelli diversi con task progressivamente più specifici. Ogni stage lavora su una granularità diversa del testo.

| Stage | Modello | Granularità input | Task cognitivo |
|-------|---------|-------------------|----------------|
| 0 | Gemini Flash | Intero libro (multi-block) | Struttura + intelligenza narrativa globale |
| A | Regole | Capitoli → chunk (10K char) | Segmentazione deterministica |
| B | Gemini Flash Lite | Macro-chunk (~10K char) | Analisi emotiva e narrativa per blocco |
| C | Gemini Flash Lite | Micro-chunk (~500 char) | Regia TTS per scena |
| D | Qwen3-TTS 1.7B | Scena singola | Sintesi vocale |

La progressione è deliberata: non si può chiedere a un singolo LLM di fare analisi narrativa + segmentazione + direzione TTS su 1M di caratteri. Ogni stage riduce il problema alla sua forma minima senza perdere il contesto necessario.

---

## Analisi per stage

### Stage 0 — Foundation

**Produce:**
- `fingerprint.json`: `chapters_list`, `metadata` (incl. `book_language`), `punctuation_style`
- `preproduction.json`: `characters_dossier` con `vocal_profile` fisico per personaggio, `casting`, `palette_choice`, `global_voice`

**Perché è critico:**

Il `vocal_profile` di ogni personaggio (es. "voce baritonale, stentorea, ritmo lento") è il dato più prezioso di tutta la pipeline voce. Stage C lo traduce in inglese acustico nel `qwen3_instruct` di ogni dialogo (es. "Deep baritone voice, commanding projection.") — ed è l'unico meccanismo che mantiene la coerenza vocale di un personaggio attraverso centinaia di scene in un TTS amnesico.

Il `punctuation_style` estratto da Stage 0 viene usato da Stage 0.1.5 per normalizzare il testo sorgente PRIMA che Stage A lo ingesti. Questo significa che tutta la pipeline downstream lavora su testo pulito senza doverlo sapere — architettura corretta.

**Rischio principale:** Se Stage 0 produce un `vocal_profile` vago ("voce normale") o manca un personaggio secondario, Stage C è costretto a inventare l'anchor vocale — perdita di qualità silenziosa.

---

### Stage A — Trasparente

Segmentazione deterministica. Usa `chapters_list` da fingerprint per non spezzare i capitoli a metà. Produce sia macro-chunk (~10K char, uno per blocco testuale) che micro-chunk (~500 char, sotto-divisioni per Stage C).

Nessun rischio qualitativo — è puramente strutturale.

---

### Stage B — Analisi emotiva e narrativa

**Produce per ogni macro-chunk:**

```
block_analysis:
  primary_emotion, secondary_emotion  → registro emotivo del blocco intero
  valence, arousal, tension            → intensità numerica (0.0–1.0)
  narrator_base_tone                   → tono fisico del narratore (in inglese)
  subtext                              → cosa NON viene detto (intento nascosto)
  narrative_arc                        → come cambia la tensione nel blocco
  setting                              → luogo fisico

entities[]:
  text (nome canonico)
  speaking_style                       → stile recitativo in inglese PER QUESTA SCENA

narrative_markers[]:
  relative_position, event, mood_shift → punti di svolta con posizione relativa
```

**Carico cognitivo:** Alto — 8 tipi di estrazione in un unico prompt. La struttura Mediterranean Prompting (analisi in lingua del libro, campi tecnici in inglese) è la scelta giusta per evitare code-switching involontario nel modello.

**Punto di forza:** `narrator_base_tone` e `speaking_style` per entità sono contestuali alla scena specifica, non assoluti. Un personaggio può avere speaking_style diversi in capitoli diversi a seconda dell'emozione dominante — e questo è esattamente ciò che serve al TTS.

**Punto di attenzione:** I valori `valence`, `arousal`, `tension` vengono estratti correttamente ma nella v2.4.0 di Stage C non venivano consumati. Con Stage C v2.5.0 sono ora disponibili nel prompt come contesto numerico.

**Il contesto che Stage B passa a Stage C** (via `_distribute_micro_chunks`): il macro `block_analysis` viene applicato a tutti i micro-chunk del blocco. Questo significa che Stage C usa lo stesso `narrator_base_tone` per tutti i ~5-8 micro-chunk di un blocco da 10K char. È un compromesso accettabile: la granularità emotiva di Stage B è sul blocco, non sulla singola frase. Stage C affina questo nella direzione micro-scena.

---

### Stage C — Regia TTS

Stage C è il punto dove si decide la qualità finale del WAV. Riceve:

```
narrator_base_tone         ← da Stage B (base tono narratore per il blocco)
primary_emotion            ← da Stage B
secondary_emotion          ← da Stage B  
narrative_arc              ← da Stage B
subtext                    ← da Stage B
entities_speaking_styles   ← da Stage B (per i personaggi presenti nel blocco)
characters_vocal_profiles  ← da preproduction.json (fisico, globale per tutto il libro)
tension / arousal / valence ← da Stage B (disponibili da v2.5.0)
text_content               ← il testo del micro-chunk (~500 char)
```

**Architettura del `qwen3_instruct`:**

Struttura obbligatoria: `[Vocal anchor]. [Acting direction].`

- **Anchor** = fisica della voce (da `characters_vocal_profiles` per i dialoghi, libero per il narratore)
- **Direction** = stato emotivo specifico della battuta

Questa separazione è corretta: l'anchor garantisce la coerenza di identità vocale (costante per personaggio), la direction garantisce la variazione emotiva (cambia scena per scena).

**Segmentazione per tipologia testuale:**

```
"virgolette doppie"  → DIALOGO      → speaker = personaggio
'virgolette singole' → PENSIERO     → speaker = personaggio  
tutto il resto       → NARRAZIONE   → speaker = Narratore
```

Funziona perché Stage 0.1.5 ha già normalizzato la punteggiatura in questo standard. La rigidità della regola ("fidati dei simboli anche quando il contesto sembra suggerire altro") è una scelta deliberata per evitare che il modello interpreti e sbagli.

---

## Valutazione qualitativa complessiva (analisi aprile 2026)

### Cosa funziona bene ✅

| Aspetto | Valutazione |
|---------|------------|
| vocal_profile fisico → anchor in qwen3_instruct | Meccanismo corretto per TTS amnesico |
| speaking_style per-scena da Stage B | Variazione emotiva corretta per personaggio |
| narrator_base_tone con fallback quality-floor | Qualità minima garantita anche senza Stage B |
| subtext/narrative_arc come contesto direzionale | Livello di analisi raro nei sistemi TTS automatizzati |
| Segmentazione tipografica stretta | Correttezza dialogo/narrazione/pensiero |
| Progressione cognitiva per stage | Ogni LLM opera al livello di complessità appropriato |

### Gap identificati e fixes applicati ✅

| Gap | Fix | Versione |
|-----|-----|---------|
| `book_language` hardcoded "ITALIANO" in Stage B | Lettura da `fingerprint.json → metadata.language` | Stage B v1.3.0 |
| Stage B non ribadisce la lingua anche su testo misto | "Rispondi SEMPRE in {book_language} anche se il testo contiene altre lingue" | Stage B v1.3.0 |

### Gap residui aperti

#### Gap V1-1 — Pause semantiche uniformi (priorità: alta)
**Problema:** Stage C v2.4.0 produceva pause prevalentemente nel range 100-200ms per qualsiasi transizione. Non distingueva cambio-battuta (50ms), fine-paragrafo (500ms), stacco-narrativo (1000ms).

**Fix applicato:** Stage C v2.5.0 introduce tassonomia pause con 6 livelli semantici nel §1 del prompt. La regola 2000ms per i titoli di capitolo (già presente) è invariata.

**Nota:** Il fix è nel prompt — non richiede modifiche al codice parser di Stage C. I valori `pause_after_ms` prodotti da Stage C vengono passati direttamente a Stage D per l'assemblaggio.

#### Gap V1-2 — valence/arousal/tension non usati (priorità: media)
**Problema:** Stage B estrae tre metriche numeriche di intensità emotiva (valence, arousal, tension 0.0-1.0) che erano presenti nel contesto di Stage C ma non nel prompt. Stage C non poteva usarli per calibrare il ritmo.

**Fix applicato:** Stage C v2.5.0 espone `{tension}`, `{arousal}`, `{valence}` nel blocco CONTESTO. Aggiunta linea guida: alta tensione/arousal → pause più brevi; scena riflessiva → pause più lunghe.

**Implementazione code:** `stage_c_scene_director.py` — aggiunta lettura e sostituzione variabili nel blocco template replacement.

#### Gap V1-3 — has_dialogue sempre True per Narratore (priorità: bassa)
**Problema:** Nel codice Stage C: `scene["has_dialogue"] = scene.get("speaker") is not None`. Il Narratore ha `speaker = "Narratore"` (non None), quindi tutte le scene narrative risultano `has_dialogue: true`. Se Stage D usa questo campo per routing o processing path, potrebbe generare comportamento inatteso.

**Fix necessario:** Cambiare logica a `scene["has_dialogue"] = scene.get("speaker") not in (None, "Narratore")`. Da valutare dopo aver verificato come Stage D usa effettivamente il campo.

#### Gap V1-4 — Name matching fragile per voice routing (priorità: media)
**Problema:** Stage D cerca `casting["nome_personaggio"]` in preproduction.json usando il campo `speaker` prodotto da Stage C. Se Stage C produce `speaker = "Anya Sharma"` ma preproduction.json ha `casting["Anya"]`, il routing fallisce silenziosamente e il personaggio viene letto dalla voce di default.

**Fix necessario:** Normalizzazione del nome speaker in Stage C (o Stage D) confrontando con i keys di `casting` in preproduction.json. Potrebbe usare fuzzy match sui cognomi.

---

## Impatto delle pause sul prodotto finale

Le pause (`pause_after_ms`) sono l'unico parametro di timing che Stage C controlla. Stage D le usa per inserire silenzio tra i WAV nell'assemblaggio finale. Il loro impatto percettivo è:

- Pause troppo corte tra Narratore e dialogo: suona come flusso di coscienza, perde la "presenza scenica"
- Pause troppo uniformi tra le battute: ritmo meccanico, non naturale
- Pause mancanti dopo stacchi narrativi: il listener non ha tempo di ricollocarsi nel nuovo contesto
- Pause corrette: l'audiobook respira, i personaggi "entrano" nella scena, le transizioni hanno peso

La tassonomia introdotta in v2.5.0 non è l'ottimale definitivo — è il primo passo verso pause semanticamente corrette. Il passo successivo sarebbe validarla ascoltando campioni audio prodotti con v2.5.0 vs v2.4.0 e calibrare i range.

---

## Priorità di sviluppo qualitativo (voce v1)

1. **Validare Stage C v2.5.0** — produrre campioni audio e confrontare ritmo delle pause con v2.4.0
2. **Fix has_dialogue (Gap V1-3)** — verificare prima come Stage D usa il campo
3. **Fix name matching (Gap V1-4)** — analizzare quanti mismatch esistono su Hyperion/Cronache
4. **Qualità Stage 0 vocal_profile** — audit dei profili vocali prodotti su libri reali, verificare specificità
5. **narrator_base_tone a granularità micro** — attualmente è lo stesso per tutti i micro-chunk di un macro-blocco; in futuro Stage B potrebbe produrre tone-map per segmento

---

*Documento creato: 2026-04-29 — mantenere aggiornato dopo ogni sessione di analisi qualitativa.*
