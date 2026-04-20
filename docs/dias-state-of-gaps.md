# DIAS — Gap Analysis & Sviluppi Aperti

*Aggiornato: 20 Aprile 2026 — post fix sessione.*

---

## ✅ Già implementato

1. **Stage 0.5 (Theme Factory):** `stage_0_5_theme_factory.py` — costruisce `project_sound_palette` via Gemini.
2. **Download Passivo D2:** `stage_d2_sound_factory.py` — fetching via `requests.get()` operativo.
3. **Leitmotif Stage E:** `_layer_leitmotif` presente nel mixdown engine.
4. **Director/Engineer split (B2-Micro):** Architettura a due LLM call separati. Elimina strutturalmente il canonical_id mismatch.

---

## ✅ Gap risolti in questa sessione

### Gap 1 — Arc Alignment B2-Macro ✅ FIXATO
**Problema originale:** B2-Macro conosceva solo `total_duration_s`. Il LLM posizionava i cambi di intensità del PAD senza sapere dove cadevano i confini delle scene — rischio di transizione a metà scena.

**Fix applicato (20/04/2026):**
- Aggiunto `_get_scene_boundaries(chunk_label)` in `stage_b2_macro.py` — legge la `master_timing_grid` e restituisce i timestamp di inizio di ogni micro-blocco.
- Aggiornato il prompt template `b2_macro_v4.0.yaml` — Sezione B include ora `CONFINI DEI MICRO-BLOCCHI` con timestamp MM:SS per ogni micro-chunk.
- Il LLM può ora allineare i `pad_arc` boundaries ai confini narrativi reali (es: 00:00, 01:24, 03:00, 04:45, 06:33 per chunk-000 di Scalzi).

**Nota:** Fix attivo per i prossimi run di B2-Macro. I MacroCue esistenti non vengono rigenerati automaticamente (idempotency check li skippa).

---

### Gap 1b — Vocabulary Mismatch Stage E / Engineer ✅ FIXATO

**Problema originale (trovato in questa sessione — non documentato):**
Due bug silenziosi nei field `pad_duck_depth` e `pad_fade_speed`:

1. **`pad_duck_depth`**: il prompt Engineer dichiarava `"shallow" | "medium" | "deep"`, ma `DUCK_DEPTH_MAP` in Stage E aveva solo `none | light | medium | heavy`. `"shallow"` e `"deep"` cadevano sul fallback `DUCK_MEDIUM`. Bug silenzioso.

2. **`pad_fade_speed`**: il prompt non enumerava i valori validi → il LLM produceva `"snap"` (visto nei micro-cue Scalzi), assente da `FADE_MS_MAP` → fallback 180ms. Bug silenzioso.

**Fix applicato:**
- `stage_e_mixdown.py`: aggiunti alias `"shallow" → DUCK_LIGHT`, `"deep" → DUCK_HEAVY`, `"snap" → 30ms` per retrocompatibilità con output esistenti.
- `b2_micro_engineer_v1.0.yaml`: corretti i valori enumerati — `pad_duck_depth = "none" | "light" | "medium" | "heavy"`, `pad_fade_speed = "instant" | "sharp" | "smooth" | "slow"`.

---

## 🟡 Gap residui

### Gap 2 — Multi-Evento per Scena / AMB Looping (priorità: bassa)
**Problema:** Stage E `_layer_fx` legge un solo `amb_id`, `sfx_id`, `sting_id` per scena. Non supporta array di eventi né AMB continuo attraverso più scene.

**Stato attuale:** Con l'architettura Director/Engineer (max 1 AMB, 1 SFX, 1 STING per scena per design), il vincolo di singolo evento non è attualmente bloccante. Il looping AMB è un nice-to-have per il futuro.

**Cosa serve per il fix:**
- `SceneAutomation` → aggiungere `sfx_events: List[SfxEntry]`, `amb_events: List[AmbEntry]` con `offset_s`.
- `_layer_fx` in Stage E → iterare array invece di singoli ID.
- Prompt Engineer → aggiornare formato output.

**Dipendenza:** Nessuna dipendenza bloccante. Da fare prima di Stage E con scene complesse (dialogo sovrapposto a SFX multipli).

---

### Gap 3 — Backend Ottimizzati ARIA per AMB/SFX (priorità: media — lato ARIA)
**Problema:** ACE-Step 1.5 XL ha ~4.5 min di overhead fisso per QUALSIASI durata. Produrre 0.4s di SFX richiede 270s.

**Stato attuale:** L'utente ha dichiarato di voler risolvere lato ARIA (modello alternativo per AMB/SFX). La decisione architetturale è aperta — candidati: EzAudio, AudioGen, Stable Audio Open.

**Impatto su DIAS:** Zero — DIAS manda già le code Redis con `output_style` corretto. Cambierà solo il routing lato ARIA (quale modello riceve quale `output_style`).

---

*Documento mantenuto manualmente — aggiornare dopo ogni sessione di fix.*
