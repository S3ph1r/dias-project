# DIAS Sound Pipeline — Refactoring Specification
## Versione 1.0 — Aprile 2026
**Autori**: Roberto + Claude Sonnet 4.6 (sessione di analisi 18 Aprile 2026)
**Scope**: Gap analysis completo + specifiche implementative per Stage 0.5, B2-Macro arc alignment, Stage E Mixdown.

---

## 1. Stato Attuale — Cosa Funziona e Cosa Manca

### 1.1 Cosa è già corretto

| Componente | Stato | Note |
|---|---|---|
| `master_timing_grid.json` | ✅ Completo | Per-scena: `start_offset`, `voice_duration`, `pause_after`. Per micro-chunk e macro-chunk: `start_offset`, `duration`. Tutte misure WAV reali da Stage D. |
| B2-Macro legge durata reale | ✅ | `_get_chunk_total_duration()` legge dal timing grid → PAD duration è accurata |
| D2 genera LRC corretto | ✅ | `_build_lyrics_from_pad_arc()` usa `start_s + 1.0` in formato `[MM:SS.xx]` |
| ARIA wrapper relay | ✅ | Relay 120s chunk, tonal lock, SoX crossfade, HTDemucs stems |
| IntegratedCueSheet formato | ✅ | Ha `pad_volume_automation`, `pad_duck_depth`, `amb_id`, `sfx_id`, `sting_id` per scena |
| Pipeline Redis DIAS↔ARIA | ✅ | Job ID deterministico (MD5 hash), callback pattern |

### 1.2 Cosa manca (gap da chiudere, in ordine di priorità)

| Gap | Descrizione | Impatto | Priorità |
|---|---|---|---|
| **Gap 1 — Stage 0.5** | `project_sound_palette` non esiste in preproduction.json. Il prompt B2-Macro lo referenzia ma riceve sempre "(Nessun Brand Sound definito)". Leitmotif mai generati. | Ogni capitolo ha un PAD stilisticamente diverso. Nessuna continuità timbrica tra capitoli. | ALTA |
| **Gap 2 — Arc alignment** | I segmenti del pad_arc hanno timestamp proporzionali ma non allineati ai confini dei micro-chunk. Le transizioni di intensità possono avvenire nel mezzo di una scena narrata. | Transizioni musicali disallineate rispetto alla struttura narrativa | MEDIA |
| **Gap 3 — Stage E** | Non esiste. I WAV ARIA sono prodotti, il manifest è prodotto, ma nessuno assembla la traccia finale. | Senza Stage E nessun output finale è producibile | ALTA |
| **Gap 4 — AMB/SFX/STING su modello alternativo** | Tutti e 4 i tipi vanno su ACE-Step. AMB 4s richiede ~4.5 min. | Produzione lenta per asset brevi | BASSA (fase 2) |

---

## 2. Gap 1 — Stage 0.5: Theme Factory (Leitmotif Generator)

### 2.1 Razionale

Il prompt B2-Macro v4.0 ha già la sezione:
```
BRAND SOUNDS DEL PROGETTO (Leitmotif obbligatori, se presenti):
{project_sound_palette}
```
e la logica:
```
2. LEITMOTIF: Se project_sound_palette contiene un canonical_id adatto, USA QUELLO.
   Imposta is_leitmotif: true e copia il canonical_id esattamente.
```

La struttura è pronta. Manca l'implementazione di Stage 0.5 che popola `project_sound_palette` in `preproduction.json`.

### 2.2 Cosa produce Stage 0.5

Un set di temi musicali brevi (8-15s) generati una sola volta per progetto, prima di Stage A.
Vengono salvati come asset ARIA permanenti del progetto.

**Temi da generare per ogni progetto:**

| Canonical ID pattern | Durata | Descrizione | Usato da B2 quando |
|---|---|---|---|
| `leitmotif_{palette}_neutral` | 12s | Tema neutro/narrativo del progetto | Capitoli di esposizione, low tension |
| `leitmotif_{palette}_tension` | 10s | Tema tensione crescente | Capitoli con emozione primaria paura/suspense |
| `leitmotif_{palette}_climax` | 10s | Tema climax | Capitoli con emozione primaria terrore/confronto |
| `leitmotif_{palette}_resolution` | 12s | Tema risoluzione/malinconia | Capitoli di aftermath, conclusione |

Per "Retro-Futurismo Orchestrale" i canonical_id sarebbero:
- `leitmotif_retro_futurismo_neutral`
- `leitmotif_retro_futurismo_tension`
- `leitmotif_retro_futurismo_climax`
- `leitmotif_retro_futurismo_resolution`

### 2.3 Come vengono usati

Questi temi **non vengono mai sentiti direttamente** dall'ascoltatore. Vengono usati come `reference_audio` (`audio_cover_strength: 0.4`) da ARIA nel relay PAD:
- Danno continuità timbrica: i PAD di tutti i capitoli "suonano" come parte della stessa opera
- Garantiscono che la stessa palette (Retro-Futurismo Orchestrale) sia riconoscibile in ogni capitolo

Quando B2-Macro trova nel `project_sound_palette` un tema con `is_leitmotif: true`, non genera un nuovo PAD — riutilizza quello esistente come base per la generazione del capitolo corrente.

### 2.4 Struttura `project_sound_palette` da aggiungere a preproduction.json

```json
"project_sound_palette": {
  "leitmotif_retro_futurismo_neutral": {
    "canonical_id": "leitmotif_retro_futurismo_neutral",
    "description": "Tema neutro del progetto — Retro-Futurismo Orchestrale, narrativo",
    "palette": "Retro-Futurismo Orchestrale",
    "emotion_affinity": ["neutral", "curiosity", "contemplation"],
    "local_path": "stages/stage_d2/assets/leitmotif/leitmotif_retro_futurismo_neutral.wav",
    "aria_url": "http://192.168.1.139:8082/assets/sound_library/pad/d2-pad-{hash}/d2-pad-{hash}.wav",
    "is_leitmotif": true,
    "duration_s": 12.4
  },
  "leitmotif_retro_futurismo_tension": { ... },
  ...
}
```

### 2.5 Implementazione Stage 0.5

**Nuovo file**: `src/stages/stage_0_5_theme_factory.py`

```
Input:
  - preproduction.json (palette_choice, characters_dossier, theatrical_standard)
  - fingerprint.json (sound_design.palette_proposals)

Processo:
  1. Per ogni tema (neutral/tension/climax/resolution):
     a. Costruisce prompt ACE-Step da palette + emozione del tema
     b. Invia a ARIA via Redis (queue: aria:q:mus:local:acestep-1.5-xl-sft:dias)
     c. Aspetta callback + scarica WAV (12s, run_demucs=False)
  2. Salva WAV in stages/stage_d2/assets/leitmotif/
  3. Aggiorna preproduction.json con project_sound_palette

Output:
  - preproduction.json aggiornato con project_sound_palette
  - 4 WAV brevi in stages/stage_d2/assets/leitmotif/
```

**Quando eseguirlo**: dopo Stage 0 (preproduction), prima di Stage A. Deve essere idempotente — se `project_sound_palette` è già popolato, salta.

**CLI**:
```bash
python tests/stages/run_theme_factory.py <project_id>
```

### 2.6 Prompt ACE-Step per leitmotif (esempio — Retro-Futurismo Orchestrale, tension)

```json
{
  "output_style": "pad",
  "duration": 12.0,
  "prompt": "1970s orchestral sci-fi, low strings ostinato, vintage analog synthesizer, tense atmosphere, minor key, slow tempo, Bernard Herrmann influence, no vocals, instrumental",
  "lyrics": "",
  "thinking": false,
  "run_demucs": false,
  "guidance_scale": 7.0,
  "inference_steps": 60,
  "seed": 42
}
```

---

## 3. Gap 2 — Arc Alignment ai Confini Micro-Chunk

### 3.1 Problema attuale

B2-Macro divide la durata totale del capitolo in segmenti con timestamp che Gemini calcola proporzionalmente al testo. I confini dei segmenti non coincidono con i confini dei micro-chunk.

**Esempio attuale (chunk-000, 470.4s):**
```
Arc segmento 1: 0s - 150s    (low) → confine a 150s
Arc segmento 2: 150s - 350s  (mid) → confine a 350s
Arc segmento 3: 350s - 420s  (high) → confine a 420s
Arc segmento 4: 420s - 470s  (low) → fine
```

**Micro-chunk boundaries reali (da timing grid):**
```
micro-000: 0s    - 84.7s    (13 scene)
micro-001: 84.7s - 168.4s   (N scene)
micro-002: ...
```

Il confine di arco a 150s cade nel mezzo di un micro-chunk → la musica cambia carattere mentre la narrazione è nel pieno di una sequenza.

### 3.2 Fix: B2-Macro usa micro-chunk boundaries come snap points

B2-Macro deve caricare anche la struttura dei micro-chunk dalla timing grid e usare i loro confini come vincoli per i segmenti dell'arco.

**Modifica a `_get_chunk_total_duration()`** → estendere in `_get_chunk_timing_data()`:

```python
def _get_chunk_timing_data(self, chunk_label: str) -> dict:
    """
    Ritorna durata totale + lista di micro-chunk boundaries per snap dell'arc.
    """
    grid_file = self.persistence.project_root / "stages" / "stage_d" / "master_timing_grid.json"
    if not grid_file.exists():
        return {"duration": 900.0, "micro_boundaries": []}
    with open(grid_file) as f:
        grid = json.load(f)
    macro_data = grid.get("macro_chunks", {}).get(chunk_label, {})
    micro_chunks = macro_data.get("micro_chunks", {})
    boundaries = sorted([
        v["start_offset"] for v in micro_chunks.values()
        if "start_offset" in v
    ])
    return {
        "duration": float(macro_data.get("duration", 900.0)),
        "micro_boundaries": boundaries,  # es: [0.0, 84.7, 168.4, ...]
    }
```

**Modifica al prompt B2-Macro**: aggiungere una sezione con i micro-chunk boundaries:

```
CONFINI MICRO-CHUNK (usa questi come snap points per i segmenti dell'arc):
{micro_chunk_boundaries}
I segmenti dell'arc DEVONO iniziare e terminare a uno di questi timestamp.
Questo garantisce che la musica cambi carattere solo tra scene, mai nel mezzo di una scena.
```

### 3.3 Impatto

Piccolo miglioramento di qualità percepita. Non è critico per il funzionamento ma migliora la coerenza narrativa. **Priorità: MEDIA — fare dopo Stage E.**

---

## 4. Gap 3 — Stage E: Mixdown Engine

### 4.1 Input di Stage E

Stage E riceve, per ogni capitolo:

**Da Stage D** (voce, già esistente):
```
stages/stage_d/output/{project_id}-{chunk}-{micro}-scene-{N}.wav
stages/stage_d/output/{project_id}-{chunk}-{micro}-scene-{N}.json  (con voice_duration_seconds, pause_after_ms)
```

**Da Stage D2** (asset musicali, già esistente):
```
stages/stage_d2/manifest.json  → mappa canonical_id → local_paths
stages/stage_d2/assets/pad/{canonical_id}.wav
stages/stage_d2/assets/pad/stems/bass.wav, drums.wav, other.wav
stages/stage_d2/assets/amb/{canonical_id}.wav
stages/stage_d2/assets/sfx/{canonical_id}.wav
stages/stage_d2/assets/sting/{canonical_id}.wav
```

**Da Stage B2** (partitura, già esistente):
```
stages/stage_b2/output/{project_id}-{chunk}-{micro}-integrated-cue-sheet.json
stages/stage_b2/output/{project_id}-{chunk}-macro-cue.json
```

**Da Stage D** (timing grid, già esistente):
```
stages/stage_d/master_timing_grid.json
```

### 4.2 Algoritmo Stage E

```python
def mix_chapter(macro_chunk_id: str):

    # 1. Costruisci timeline assoluta da timing grid
    timeline = build_timeline(macro_chunk_id)
    # timeline[scene_id] = {t_start, t_end, voice_wav, ...}

    # 2. Carica PAD per questo macro-chunk (da macro-cue.json)
    pad_canonical_id = load_macro_cue(macro_chunk_id).pad.canonical_id
    pad_stems = load_pad_stems(pad_canonical_id)  # bass, drums, other WAV

    # 3. Per ogni micro-chunk in ordine
    for micro_chunk_id in get_micro_chunks(macro_chunk_id):
        cue_sheet = load_integrated_cue_sheet(micro_chunk_id)

        for scene_automation in cue_sheet.scenes_automation:
            scene = timeline[scene_automation.scene_id]
            t_start = scene["t_start"]
            t_end   = scene["t_end"]

            # 3a. Piazza voce
            mixer.place(scene["voice_wav"], t=t_start, track="voice", volume=0.0)

            # 3b. PAD ducking durante la voce
            duck_db = duck_depth_to_db(scene_automation.pad_duck_depth)
            # duck_depth: "light"=-8dB, "medium"=-15dB, "heavy"=-22dB
            mixer.automate_volume("pad_other", t_start, t_end, duck_db,
                                  fade_ms=fade_speed_to_ms(scene_automation.pad_fade_speed))
            mixer.automate_volume("pad_drums", t_start, t_end, duck_db - 5,
                                  fade_ms=fade_speed_to_ms(scene_automation.pad_fade_speed))
            # bass: sempre presente, mai duckato (fondamenta armoniche)
            mixer.automate_volume("pad_bass", t_start, t_end, -3.0)

            # 3c. AMB (se presente)
            if scene_automation.amb_id:
                amb_wav = get_asset_path(scene_automation.amb_id, "amb")
                t_amb = t_start + scene_automation.amb_offset_s
                mixer.place(amb_wav, t=t_amb, track="amb",
                            volume=LEVELS["amb"])  # -25dB default

            # 3d. SFX (se presente)
            if scene_automation.sfx_id:
                sfx_wav = get_asset_path(scene_automation.sfx_id, "sfx")
                t_sfx = t_start + scene_automation.sfx_offset_s
                mixer.place(sfx_wav, t=t_sfx, track="sfx",
                            volume=LEVELS["sfx"])  # -12dB default

            # 3e. STING (se presente)
            if scene_automation.sting_id:
                sting_wav = get_asset_path(scene_automation.sting_id, "sting")
                t_sting = t_start + scene_automation.sting_offset_s
                mixer.place(sting_wav, t=t_sting, track="sting",
                            volume=LEVELS["sting"])  # -6dB default

    # 4. PAD stem sempre presente per tutta la durata del capitolo
    pad_duration = timeline_total_duration(macro_chunk_id)
    mixer.place(pad_stems["bass"],  t=0, track="pad_bass",  volume=-3.0,  duration=pad_duration)
    mixer.place(pad_stems["drums"], t=0, track="pad_drums", volume=-6.0,  duration=pad_duration)
    mixer.place(pad_stems["other"], t=0, track="pad_other", volume=-9.0,  duration=pad_duration)

    # 5. Master mix e normalizzazione
    output_wav = mixer.render(target_lufs=-23.0)  # EBU R128 per audiolibri
    return output_wav
```

### 4.3 Livelli di mix di riferimento (EBU R128 target -23 LUFS)

| Track | Volume base | Duck durante voce | Note |
|---|---|---|---|
| voice | 0 dB | — | Reference |
| pad_bass | -20 dB | mai duckato | Fondamenta armoniche |
| pad_drums | -23 dB | -35 dB (light), -40 dB (heavy) | Più aggressivo, disturba la voce |
| pad_other | -20 dB | -28 dB (light), -35 dB (heavy) | Melodia/armonia, duckato moderatamente |
| amb | -30 dB | -33 dB | Quasi sempre sotto la voce |
| sfx | -15 dB | — | Puntuale, non si duca |
| sting | -9 dB | — | Puntuale, impatto drammatico |

### 4.4 Libreria di riferimento per implementazione

**Opzione A — pydub** (più semplice, nessuna dipendenza esterna):
```python
from pydub import AudioSegment
# overlay() per posizionare, apply_gain() per volume, fade_in/fade_out()
```

**Opzione B — librosa + soundfile** (più controllo su automazione volume):
```python
import librosa, soundfile as sf, numpy as np
# Gestione campione per campione per automazione volume precisa
```

**Raccomandazione**: pydub per prototipo, librosa per versione finale con automazione volume fluida.

### 4.5 Output di Stage E

```
stages/stage_e/output/
  {project_id}-{chunk}-master.wav          # Traccia finale capitolo (EBU R128)
  {project_id}-{chunk}-master.mp3          # Versione compressa distribuzione
  {project_id}-{chunk}-mix-report.json     # Log timing eventi, livelli
```

### 4.6 File: `src/stages/stage_e_mixdown.py`

**CLI**:
```bash
python tests/stages/run_stage_e.py <project_id> [chunk_id]
```

---

## 5. Struttura dati aggiornata: `pad_duck_depth` → dB

Il campo `pad_duck_depth` nell'IntegratedCueSheet ha valori stringa. Stage E li converte:

```python
DUCK_DEPTH_MAP = {
    "none":   0.0,    # PAD pieno, nessun dialogo
    "light":  -8.0,   # Dialogo soft, musica presente
    "medium": -15.0,  # Dialogo standard (default B2)
    "heavy":  -22.0,  # Dialogo intenso, musica quasi assente
}

FADE_SPEED_MAP = {
    "instant": 50,    # ms
    "smooth":  150,   # ms (default B2)
    "slow":    400,   # ms — per transizioni cinematografiche
}
```

---

## 6. Ordine di Implementazione Raccomandato

```
Fase 1 (CRITICA — sblocca pipeline completa):
  [LXC 190] Stage E Mixdown Engine
    → src/stages/stage_e_mixdown.py
    → tests/stages/run_stage_e.py
    → Usa: pydub + timing grid + IntegratedCueSheet + D2 manifest

Fase 2 (QUALITÀ — coerenza inter-capitolo):
  [LXC 190] Stage 0.5 Theme Factory
    → src/stages/stage_0_5_theme_factory.py
    → tests/stages/run_theme_factory.py
    → Aggiorna preproduction.json con project_sound_palette
    → 4 WAV leitmotif generati via ARIA

Fase 3 (QUALITÀ — arc precision):
  [LXC 190] B2-Macro arc alignment ai micro-chunk boundaries
    → Modifica stage_b2_macro.py: _get_chunk_timing_data()
    → Modifica config/prompts/stage_b2/b2_macro_v4.0.yaml: aggiunge micro_boundaries
    → Aggiorna b2_macro_v4.1.yaml

Fase 4 (PERFORMANCE — fase 2):
  [PC 139 ARIA] Backend alternativo per AMB/SFX/STING
    → Nuovo backend (AudioCraft/EzAudio) per asset brevi < 5s
    → Tempo generazione: 15s vs 4.5min attuali
```

---

## 7. Note Tecniche per Implementazione su LXC 190

### Dipendenze Python da aggiungere

```bash
# Per Stage E
pip install pydub  # audio mixing
apt-get install ffmpeg  # backend pydub per WAV/MP3

# Opzionale per versione avanzata
pip install librosa soundfile
```

### Test di integrazione Stage E

Prima di integrare nella pipeline completa, testare Stage E standalone:
```bash
python tests/stages/run_stage_e.py urania_n_1610_john_scalzi_uomini_in_rosso_mondadori_09_2014_ita 000
```
Verificare che il WAV di output:
- Ha la durata corretta (= timing grid macro-chunk duration)
- La voce è udibile e prevalente
- Il PAD è presente in sottofondo e si abbassa durante le battute
- Non ci sono click o pop ai punti di giunzione

### Test di integrazione Stage 0.5 (Theme Factory)

```bash
python tests/stages/run_theme_factory.py urania_n_1610_john_scalzi_uomini_in_rosso_mondadori_09_2014_ita
# Verifica: preproduction.json contiene project_sound_palette con 4 voci
# Verifica: 4 WAV presenti in stages/stage_d2/assets/leitmotif/
# Verifica: B2-Macro usa is_leitmotif=true per capitoli con emozione affine
```

---

## 8. Riferimenti

- `dias-workflow-logic.md` — pipeline completa, regole AMB/SFX/STING
- `dias-to-aria-integration-spec.md` — protocollo Redis DIAS↔ARIA, gap A/B wrapper
- `ARIA_TEST_GUIDE_PC139.md` — test manuali ARIA
- `master_timing_grid.json` — struttura timing reale per-scena
- `b2_macro_v4.0.yaml` — prompt attuale B2-Macro (da aggiornare in v4.1 per arc alignment)
- `stage_d2_sound_factory.py` — D2 Sound Factory, `_build_lyrics_from_pad_arc()`
- `stage_b2_macro.py` — B2-Macro, `_get_chunk_total_duration()` da estendere

---

*Ultimo aggiornamento: 18 Aprile 2026 — v1.1*
*Sessione di analisi: Roberto + Claude Sonnet 4.6 su PC 139 / ARIA*

---

## 9. Stato Implementazione — Aggiornamento v1.1 (18 Aprile 2026)

### Completato in questa sessione

| Item | Stato | File |
|---|---|---|
| **Stage E — Mixdown Engine** | ✅ Implementato | `src/stages/stage_e_mixdown.py` |
| **Stage E — Runner** | ✅ Implementato | `tests/stages/run_stage_e.py` |
| **Multi-mode export** | ✅ `--mode voice/music/music+fx/full/all` | runner + engine |
| **ARIA wrapper — 4 fix qualità** | ✅ | `backends/acestep/aria_wrapper_server.py` |
| **Symlink modelli ACE-Step** | ✅ | vae + Qwen3-Embedding → fuori da checkpoints |
| **PAD chunk-000 Urania** | ✅ Generato (1872s, 470.2s output) | ARIA PC 139 |

### Note implementative Stage E

- Layer separati: `_layer_voice()`, `_layer_music()`, `_layer_fx()` — composizione via `render(mode)`
- Ducking PAD **off** per mode `music` e `music+fx` (si sente il PAD a piena intensità)
- Ducking PAD **on** solo in mode `full` (voce presente nel mix)
- `process_chunk()` e `export_voice_track()` mantenuti come alias per retrocompatibilità
- Normalizzazione: -1 dBFS peak per `voice`, -3 dBFS per tutti gli altri mode
- SR rilevato automaticamente dal PAD o dal primo voice WAV disponibile

### Cosa manca prima del primo test end-to-end di Stage E

1. **PAD WAV scaricato in locale** — il file è su ARIA (`http://192.168.1.139:8082/assets/sound_library/pad/d2-pad-1f227b79b8/d2-pad-1f227b79b8.wav`) ma non ancora in `stages/stage_d2/assets/pad/`
2. **D2 manifest.json** — non esiste ancora; Stage E fa fallback su `dry_run_payloads.json` (AMB/SFX/STING non ancora prodotti)
3. **HTDemucs stems** — assenti dal callback PAD (HTDemucs fallisce silenziosamente su ARIA); Stage E usa master PAD come fallback per tutti e 3 gli stem

### Prossimi passi in ordine

```
[IMMEDIATO] Scaricare il PAD generato da ARIA → stage_d2/assets/pad/d2-pad-1f227b79b8.wav
[IMMEDIATO] Run Stage E --mode voice (test senza dipendenze ARIA, solo WAV Stage D)
[BREVE]     Run Stage E --mode music (richiede PAD scaricato)
[BREVE]     Indagare HTDemucs su ARIA (perché stems assenti)
[MEDIO]     Fase 2 — Stage 0.5 Theme Factory (leitmotif)
[MEDIO]     Fase 3 — B2-Macro arc alignment ai micro-chunk boundaries
[LUNGO]     Fase 4 — Backend alternativo per AMB/SFX/STING brevi
```
