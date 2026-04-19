# DIAS Workflow Logic: Pipeline e Flusso Dati
## Revisione v10.0 — Aprile 2026

Questo documento definisce l'intera pipeline di produzione DIAS: ordine di esecuzione, dipendenze, input/output di ogni stadio e flusso dati specifico per Stage B2 (Sound-on-Demand v4.1).

---

## 1. Mappatura degli Stage (Catena di Montaggio)

La pipeline opera in modo **seriale e deterministico**. Ogni stadio inizia solo dopo che quello precedente ha completato e persistito i risultati su disco.

| Stage | Nome | Compito Principale | Input | Output |
| :--- | :--- | :--- | :--- | :--- |
| **Stage 0** | Intel | Estrae struttura (0.1) e DNA creativo + Casting (0.2). | Libro (.epub/.txt) | `fingerprint.json`, `preproduction.json` |
| **Stage A** | TextIngester | Scomposizione a imbuto: Macro (~2500w) + Micro (~300w). | Libro (.txt) | Macro-chunk + Micro-chunk (.json) |
| **Stage B** | SemanticAnalyzer | Analisi emotiva macro, Mood Propagation nei micro-chunk. | Macro-chunk | `ChunkAnalysis` per ogni macro-chunk |
| **Stage C** | SceneDirector | Tag Splitting, istruzioni TTS Qwen3, segmentazione per Emotional Beat. | Micro-chunk + analisi B | Scenes file (array scene per micro-chunk) |
| **Stage D** | VoiceGenerator | Sintesi TTS per ogni scena → file WAV + durate fisiche. | Scenes file | WAV + `MasterTimingGrid` |
| **Stage B2-Macro** | Musical Director | PAD per ogni macro-chunk (PadRequest + PadArc). | ChunkAnalysis + TimingGrid | `MacroCue` per ogni macro-chunk |
| **Stage B2-Micro** | Sound Designer | AMB/SFX/STING e PAD breathing per ogni micro-chunk. | MacroCue + Scenes + TimingGrid | `IntegratedCueSheet` per ogni micro-chunk |
| **Stage D2** | Sound Factory Client | Invia SoundShoppingList aggregata ad ARIA → produce WAV. | `sound_shopping_list_aggregata.json` | Asset audio (PAD + AMB + SFX + STING) |
| **Stage E** | Mixdown | Assembla voce + PAD stems + AMB/SFX/STING sulla timeline. | WAV Stage D + IntegratedCueSheet + MacroCue + asset D2 | Traccia finale mixata per capitolo |

---

## 2. Il Master Clock: La Voce Detta il Tempo

Il problema storico dell'audio AI è il disallineamento tra musica/effetti e voce, causato dall'imprevedibilità della durata sintetizzata. DIAS risolve questo con una sequenza precisa:

1. **Stage D** genera i WAV fisici e misura ogni durata al millisecondo. La durata cessa di essere "battute testuali" e diventa millisecondi hardware.
2. **Stage B2** lavora **dopo** Stage D: non stima le durate, le legge dalla `MasterTimingGrid`.
3. **Stage E** carica i WAV di Stage D, calcola la timeline assoluta di ogni scena, poi piazza i suoni del copione B2 perfettamente a tempo.

---

## 3. Flusso Stage B2 — Due Modalità

Stage B2 è orchestrato da `tests/stages/run_b2_pipeline.py` in tre fasi:

### FASE 1 — B2-Macro (sempre eseguita)
Per ogni macro-chunk, in sequenza:
1. Carica `ChunkAnalysis` (Stage B), testo (Stage A), `MasterTimingGrid` (Stage D), `preproduction.json` (Stage 0).
2. Chiama Gemini → produce `MacroCue` con `PadRequest` + `PadArc`.
3. Salva su disco: `{project_id}-chunk-{N}-macro-cue.json`.

### FASE 2 — B2-Micro (due varianti)

**Modalità Monolitica (default)**
```
run_b2_pipeline.py <project_id>
```
Per ogni micro-chunk: una singola chiamata Gemini produce direttamente `IntegratedCueSheet` (scenes_automation + sound_shopping_list).

**Modalità Split Director/Engineer**
```
run_b2_pipeline.py <project_id> --split
```
Per ogni micro-chunk, due chiamate Gemini sequenziali:
1. **B2-Micro-Director**: analizza il testo → `SoundEventScore` (eventi fisici in linguaggio naturale, nessuna spec tecnica).
2. **B2-Micro-Engineer**: converte `SoundEventScore` → `IntegratedCueSheet` con `production_tags` ACE-Step in vocabolario Qwen3.

L'output finale (`IntegratedCueSheet`) è identico tra le due modalità: compatibile con Stage D2 e Stage E.

### FASE 3 — Aggregazione (sempre eseguita)
Tutti i `SoundShoppingItem` da tutti i `MicroCue` + tutti i `PadRequest` dai `MacroCue` vengono aggregati (con deduplicazione per `canonical_id`) in:
`data/projects/{project_id}/sound_shopping_list_aggregata.json`

Questo file è il único input di Stage D2.

---

## 4. Flusso Dati Stage B2 (Schema)

```
MasterTimingGrid (Stage D)
  + ChunkAnalysis (Stage B)
  + preproduction.json (Stage 0)
        ↓
  Stage B2-Macro
        ↓
  MacroCue {pad: {canonical_id, production_tags, pad_arc[]}}
        ↓
  ┌────────────────────────────────────────────────────┐
  │ Modalità Monolitica           Modalità Split       │
  │                                                    │
  │ Stage B2-Micro                Stage B2-Micro-Dir  │
  │     ↓                               ↓             │
  │ IntegratedCueSheet       SoundEventScore           │
  │                               ↓                   │
  │                         Stage B2-Micro-Eng         │
  │                               ↓                   │
  │                         IntegratedCueSheet         │
  └────────────────────────────────────────────────────┘
        ↓
  Aggregatore → sound_shopping_list_aggregata.json
        ↓
  Stage D2 (Sound Factory Client → ARIA ACE-Step)
        ↓
  WAV assets (PAD + AMB + SFX + STING)
        ↓
  Stage E (Mixdown)
```

---

## 5. Regole AMB/SFX/STING (Paradigma BBC/Star Wars)

Il principio fondamentale: **il silenzio è il default. Un suono deve guadagnarsi il diritto di esistere.**

| Tipo | Durata | Limite per micro-chunk | Regola di attivazione |
| :--- | :--- | :--- | :--- |
| **AMB** | 3-5 secondi | Max 1 (spesso 0) | Solo se il testo descrive un cambio fisico di ambientazione tra scene consecutive. Non è un loop. |
| **SFX** | 0.3-2 secondi | Max 1 per scena | Solo per il momento culminante in cui l'azione fisica accade. Non per la preparazione o l'aftermath. |
| **STING** | 2-4 secondi | Max 1 (mai start) | Solo per rivelazioni narrative irreversibili (morte confermata, tradimento, svolta narrativa definitiva). Timing: middle o end. |

Il PAD (musica di fondo) è sempre presente e gestito tramite PadArc + ducking locale — non viene mai "azzerato" per fare spazio agli altri layer.

---

## 6. Flag CLI della Pipeline B2

```bash
# Esecuzione default (monolitico)
python tests/stages/run_b2_pipeline.py <project_id>

# Architettura Director/Engineer
python tests/stages/run_b2_pipeline.py <project_id> --split

# Solo Fase 1 (B2-Macro)
python tests/stages/run_b2_pipeline.py <project_id> --macro-only

# Fresh start (cancella output B2 esistenti)
python tests/stages/run_b2_pipeline.py <project_id> --cleanup

# Combinazioni
python tests/stages/run_b2_pipeline.py <project_id> --cleanup --split
```

---

*Ultimo aggiornamento: 17 Aprile 2026 — v10.0: Sound-on-Demand v4.1, architettura Director/Engineer, regole AMB/SFX/STING quantitative, rimozione riferimenti a Redis catalog e sound library.*
