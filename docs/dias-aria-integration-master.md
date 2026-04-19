# DIAS & ARIA: Contratto di Integrazione
## Sound-on-Demand v4.1 — Aprile 2026

Questo documento definisce il contratto tecnico tra DIAS (Brain, LXC 190) e ARIA (GPU Worker, PC 139).

---

## 1. La Filosofia: Sound-on-Demand

ARIA è una **Sound Factory JIT (Just-In-Time)**: non esiste un catalogo pre-prodotto, non esiste matching semantico su Redis. Ogni asset viene prodotto ex-novo su richiesta di DIAS, basandosi sulle specifiche tecniche nel `SoundShoppingItem`.

- **DIAS**: Decide cosa serve (narrative director). Produce la `sound_shopping_list_aggregata.json`. Invia le richieste su coda Redis.
- **ARIA**: Produce l'audio fisico (GPU executor). Usa esclusivamente ACE-Step 1.5 XL SFT per tutti i tipi di asset.

Non esiste `aria:registry:master`, non esiste `profile.json` di catalogazione, non esiste matching all'85%.

---

## 2. Modello AI: ACE-Step 1.5 XL SFT (Unico)

ARIA usa un solo modello per tutti i tipi di asset:

| Campo | Valore |
| :--- | :--- |
| **Modello** | ACE-Step 1.5 XL SFT |
| **Hardware** | PC 139, RTX 5060 Ti 16GB VRAM |
| **Queue Redis** | `aria:q:mus:local:acestep-1.5-xl-sft:dias` |
| **Timing** | ~4.5 minuti per 30 secondi di output generato |
| **Timing breakdown** | LM ~240 secondi + DiT ~35 secondi |
| **Output types** | `pad` \| `amb` \| `sfx` \| `sting` |

Non esistono modelli separati per tipo di asset. Non si usa MusicGen, AudioLDM, Stable Audio Open o altri modelli. ACE-Step gestisce tutti e quattro i tipi con parametri differenziati (guidance_scale, duration_s, negative_prompt).

---

## 3. Parametri ACE-Step per Tipo di Asset

| Tipo | `guidance_scale` tipico | `duration_s` tipico | `negative_prompt` standard |
| :--- | :--- | :--- | :--- |
| **PAD** | 4.5 (vintage/realistico) | durata capitolo (~480-1200s) | `epic, cinematic, generic ai, polished pop` |
| **AMB** | 7.0 (netto/definito) | 4.0 (range 3-5s) | `music, melody, vocals, rhythm` |
| **SFX** | 7.0 | 0.5-1.5 (range 0.3-2s) | `music, melody, sustained, ambient` |
| **STING** | 6.0 | 3.0 (range 2-4s) | `ambient, sustained, loop, background` |

Per il PAD, il campo `inference_steps` (default 60) controlla la qualità della denoising. Non modificare senza benchmark.

---

## 4. Vocabolario Qwen3 (Obbligatorio)

Il LM interno di ACE-Step è Qwen3, addestrato su metadata di canzoni e sound recordings. Il `production_tags` deve usare vocabolario da musicista/fonico. Termini da studio di registrazione causano "prompt drift" (Qwen3 riscrive il prompt e il suono generato deriva).

| VIETATO (sound designer) | USA QUESTO (musicista/fonico) |
| :--- | :--- |
| spring reverb | analog reverb, vintage reverb |
| tape saturation | analog warmth, vintage recording |
| tape delay | vintage echo, analog delay |
| sub-bass drone | deep bass drone, low frequency bass |
| metallic percussive hits | metallic percussion, industrial hits |
| sidechain compression | (omettere — non visibile al LM) |
| wide stereo image | wide stereo, spacious |
| high-pass filter | (descrivere il risultato sonoro, non il filtro) |
| ARP 2600 | vintage analog synthesizer |
| spring reverb unit | reverb, room reverb |

Nomi di synth hardware specifici (ARP, Moog, Roland 808, etc.) devono essere sostituiti con descrizioni generiche del suono risultante.

---

## 5. HTDemucs: Stem Separation per il PAD

Per il PAD, ARIA esegue HTDemucs dopo la generazione ACE-Step:

- **Input**: file master WAV del PAD (~8-20 min).
- **Output**: 4 stem separati: `bass`, `drums`, `vocals`, `other`.
- **Distribuzione stem per intensity**:
  - `low` → solo `bass` (quasi silenzio musicale, solo frequenze basse)
  - `mid` → `bass` + `other` (melodia e armonia presenti, percussioni assenti)
  - `high` → `bass` + `other` + `drums` + `vocals` se presenti (massima intensità)
- Stage E carica i 4 stem e li gestisce dinamicamente usando il `pad_arc` del `MacroCue`.

---

## 6. Formato SoundShoppingItem (Contratto JSON)

Schema di ogni asset nella `sound_shopping_list_aggregata.json`:

```json
{
  "type": "pad | amb | sfx | sting",
  "canonical_id": "{category}_{description}_{variant_num}",
  "production_prompt": "Descrizione leggibile (fallback/traceability)",
  "production_tags": "Comma-separated EN keywords: genere, strumenti, mood, texture",
  "negative_prompt": "Comma-separated EN exclusions per CFG",
  "guidance_scale": 4.5,
  "duration_s": 30.0,
  "scene_id": "chunk-000-micro-001-scene-003"
}
```

Per il PAD, i campi aggiuntivi sono:
```json
{
  "inference_steps": 60,
  "estimated_duration_s": 900.0,
  "pad_arc": [
    {
      "start_s": 0,
      "end_s": 120,
      "intensity": "low",
      "note": "apertura silenziosa",
      "roadmap_item": "[00:00 - [intro]. Sparse textures, low energy]"
    }
  ]
}
```

---

## 7. Flusso Stage D2 → ARIA

1. Stage D2 legge `sound_shopping_list_aggregata.json`.
2. Per ogni asset, costruisce il payload e lo invia su `aria:q:mus:local:acestep-1.5-xl-sft:dias`.
3. ARIA preleva dalla coda, esegue ACE-Step, esegue HTDemucs (solo per PAD).
4. ARIA salva il WAV in `data/projects/{project_id}/stages/stage_d2/`.
5. ARIA pubblica il risultato su callback key.
6. Stage D2 scarica i file (master + 4 stem per PAD, solo master per AMB/SFX/STING).

---

## 8. Stato Implementazione

- [x] ACE-Step 1.5 XL SFT come unico modello audio (no MusicGen/AudioLDM/Stable Audio)
- [x] Queue Redis: `aria:q:mus:local:acestep-1.5-xl-sft:dias`
- [x] Vocabolario Qwen3 nei prompt B2-Macro e B2-Micro-Engineer
- [x] HTDemucs per stem separation del PAD (bass/drums/vocals/other)
- [x] `output_style`: `pad | amb | sfx | sting`
- [x] Zero Redis catalog, zero matching semantico, zero `aria:registry:master`
- [ ] Stage E: gestione dinamica 4 stem via PadArc (in sviluppo)

---

*Ultimo aggiornamento: 17 Aprile 2026 — v3.0: Sound-on-Demand v4.1, ACE-Step come unico modello, rimozione Redis catalog e JIT multi-model switching, HTDemucs stem separation, vocabolario Qwen3.*
