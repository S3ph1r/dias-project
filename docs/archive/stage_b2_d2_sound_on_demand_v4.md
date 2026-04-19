> **[ARCHIVIATO — 2026-04-17]**
> Piano progettuale del cambio di paradigma da "Libreria Universale" a "Sound-on-Demand".
> Spiega il PERCHÉ della scelta architetturale (non-determinismo LLM nel matching semantico).
> L'architettura descritta è ora implementata e documentata in `blueprint.md` e `dias-workflow-logic.md`.
> Mantenuto per riferimento storico/decisionale. Non aggiornare.

---

# Stage B2 + Stage D2 — Sound-on-Demand Architecture
## Versione 4.0 — Aprile 2026
> **Status**: Nuova Architettura Approvata
> **Paradigma**: Sound-on-Demand (da "Libreria Universale" a "Produzione su Misura")
> **Sostituisce**: `stage_b2_spotter_implementation_plan_v3.md` (v3.0 — Catalogo + Matching)

---

## 1. Il Cambio di Paradigma: Perché Abbandoniamo il Catalogo

### 1.1 Il Problema del Matching Semantico

L'architettura v3 era basata su un assunto: che un LLM fosse in grado di fare **matching affidabile** tra l'asset di cui ha bisogno e quelli già prodotti nel catalogo ARIA.

In pratica, questo assunto si è dimostrato fragile per due ragioni:

1. **Non-Determinismo dell'LLM**: Per lo stesso testo `"la creatura aliena volò sulla testa del capitano"`, due run successive di Gemini possono produrre ID leggermente diversi: `sfx_alien_flying_creature` vs `sfx_creature_flight_alien`. I due ID sono semanticamente identici, ma come stringhe divergono abbastanza da far fallire qualsiasi match diretto.

2. **L'Allucinazione della Mancanza**: Anche quando il catalogo veniva passato esplicitamente nel prompt, Gemini a volte richiedeva come "mancante" un asset che gli avevamo appena mostrato. Lo sforzo cognitivo del matching competeva con lo sforzo della direzione artistica, degradando la qualità di entrambi.

### 1.2 La Soluzione: Separazione Totale delle Responsabilità

La nuova architettura si ispira al funzionamento già adottato per le voci (Stage C/D):

- **Stage C** non cerca voci nel catalogo. Descrive *come* recitare ogni riga.
- **Stage D** produce la voce fisica per quella riga, con quel timbro, e la salva in locale con un ID deterministico.
- **Stage E** trova la voce esattamente dove si aspetta di trovarla.

Allo stesso modo, per il suono:

- **Stage B2** non cerca suoni nel catalogo. Descrive *quali* suoni servono e *quando*.
- **Stage D2** produce ogni suono fisicamente, lo scarica in locale con il `canonical_id` come nome file.
- **Stage E** trova il suono esattamente dove si aspetta di trovarlo.

### 1.3 Cosa Rimane del Concetto di "Brand Sonoro"

L'unico caso in cui il catalogo universale aveva un vantaggio reale era il **Leitmotif**: un suono o un tema musicale strettamente legato a un personaggio o a un luogo ricorrente. Non ha senso che il rombo del propulsore della nave *Intrepid* suoni diverso al capitolo 4 e al capitolo 19.

Questo concetto viene preservato nella nuova architettura con il meccanismo del **`project_sound_palette`**: un dizionario `canonical_id → production_prompt` costruito da Stage 0 nella fase di preproduzione per i suoni "brand" del progetto. Stage B2-Macro può consultarlo e imporre quei canonical_id nel copione, garantendo coerenza senza passare dal catalogo Redis.

---

## 2. La Nuova Architettura della Pipeline

```
Stage 0 ──────────────────────────────┐
(Preproduzione: fingerprint, palette, │
 project_sound_palette opzionale)     │
                                       │
Stage A ──► Stage B ──► Stage C ──► Stage D
(Chunking)  (Emozione)  (Scene+Regia) (Voci WAV)
                │                        │
                │                        ▼
                │                  Master Timing Grid
                │                        │
                ▼                        │
          B2-MACRO ◄───────────────────┘
          (Sceglie PAD, descrive AMB)
                │
                ▼
          B2-MICRO (una call per micro-chunk)
          (Scrive copione: AMB/SFX/STING + PAD Breathing)
          (Compila Sound Shopping List con production_prompt)
                │
          ┌─────┴──────────────┐
          ▼                    ▼
   IntegratedCueSheet    Sound Shopping
   (copione artistico)    List Aggregata
          │                    │
          │               Stage D2
          │          (Sound-on-Demand)
          │          Richiede ogni asset
          │          ad ARIA SoundFactory
          │          Scarica asset in locale
          │          con canonical_id come nome
          │                    │
          └─────────►  Stage E (Mixdown)
                       Carica voci + asset locali
                       Esegue copione artistico
```

---

## 3. Stage B2 — Il Sound Director (v4.0)

### 3.1 Principi Fondamentali (Invariati)

1. **Il Silenzio è il Default.** Il suono deve guadagnarsi il diritto di esistere.
2. **La Musica Respira.** Il Pad non è un loop fisso: scende sulle voci, sale durante le pause, cresce per anticipare i climax (Radio Drama Effect).
3. **Un Asset è un Fenomeno Fisico.** Ogni `production_prompt` descrive frequenze, materiali, durata, intensità — mai narrativa.
4. **Il Copione è una Partitura Eseguibile.** Stage E non interpreta. Esegue.

### 3.2 Cosa Cambia Rispetto alla v3

| Aspetto | v3 (Catalogo) | v4 (Sound-on-Demand) |
| :--- | :--- | :--- |
| **Contesto del prompt** | Catalogo Redis passato a Gemini | Tassonomia fisica come riferimento |
| **Logica decisionale** | Cerca nel catalogo, se non trova chiede | Scrive sempre il `canonical_id` migliore | 
| **Shopping List** | Solo gli asset MANCANTI dal catalogo | TUTTI gli asset richiesti |
| **Blocco pipeline** | Stop se shopping list non vuota | Nessun blocco — D2 produce tutto |
| **Redis** | Parte integrante del flow | Non più coinvolto nel B2 |
| **Complessità cognitiva per Gemini** | Alta (matching + direzione artistica) | Bassa (solo direzione artistica) |

### 3.3 B2-MACRO — Il Direttore Musicale

#### Responsabilità
Assegna il **Pad Musicale Portante (PAD)** per l'intero Macro-Chunk. Il Pad è la "firma musicale" del capitolo. La scelta avviene in base alla Palette Artistica scelta in Stage 0 e all'emozione primaria del blocco.

#### Inputs

| Fonte | File | Contenuto Usato |
| :--- | :--- | :--- |
| **Stage 0** | `preproduction.json` | `palette_choice`, `sound_design.palette_proposals[]`, `project_sound_palette{}` |
| **Stage B** | `{project_id}-chunk-{id}.json` | `block_analysis.primary_emotion`, `.setting`, `audio_cues[]` |
| **Stage D** | `master_timing_grid.json` | Durata totale del chunk in secondi |

> [!NOTE]
> Redis non è più un input di B2-Macro. La sezione "Catalogo Asset" viene rimossa dal prompt.

#### Logica Decisionale

1. **Palette First**: La scelta del Pad deve suonare come la Palette artistica del progetto. Questa è una regola non negoziabile.
2. **Emozione Second**: Il Pad deve supportare l'emozione primaria del chunk.
3. **Project Sound Palette (Brand Sonoro)**: Se Stage 0 ha definito un PAD specifico per questo tipo di emozione/setting nel `project_sound_palette`, B2-Macro **deve** usarlo per garantire la continuità del brand. Questo è il meccanismo che preserva il Leitmotif.
4. **Libertà Creativa**: Se non c'è un brand sound, Gemini definisce liberamente un `canonical_id` semantico e scrive il `production_prompt` fisico.

#### Output (Macro-Cue v4)

```json
{
  "project_id": "...",
  "chunk_label": "chunk-000",
  "pad": {
    "canonical_id": "pad_retro_sci_fi_tension_01",
    "production_prompt": "Orchestral retro-futuristic tension. Heavy brass swells, 70s analog string pads with heavy chorus, dissonant chord clusters, no rhythm, slow motion. Dark, claustrophobic. Duration: 3-5 min seamless loop.",
    "duration_s": 900,
    "is_loop": true
  },
  "music_justification": "La palette Retro-Futurismo Orchestrale e l'emozione primaria di tensione claustrofobica richiedono un tappeto oscuro e sintetico. L'assenza di ritmo permette alla voce di guidare il tempo.",
  "leitmotif_used": false
}
```

> [!IMPORTANT]
> Non c'è più `selected_pad_id` che punta a un asset esistente. C'è sempre un `pad.canonical_id` e un `pad.production_prompt`. Se è un brand sound (leitmotif), `leitmotif_used: true` e `production_prompt` è ereditato dal `project_sound_palette`.

---

### 3.4 B2-MICRO — Il Sound Designer di Dettaglio

#### Responsabilità
Opera scena per scena sul Micro-Chunk (~300-500 parole, 8-20 scene). Eredita il PAD da B2-Macro e decide tutto il resto: **Ambiente (AMB)**, **Effetti Fisici (SFX)**, **Accenti Drammatici (Sting)** e la **Curva di Automazione del Volume**.

#### Inputs

| Fonte | File | Contenuto Usato |
| :--- | :--- | :--- |
| **B2-Macro** | `{chunk_label}-macro-cue.json` | `pad.canonical_id`, `pad.production_prompt` |
| **Stage C** | `{micro_block_id}-scenes.json` | Testo, speaker, tipo per ogni scena |
| **Stage D** | `master_timing_grid.json` | `voice_duration_s`, `pause_after_s`, `start_offset_s` fisici per ogni scena |

> [!NOTE]
> Redis non è più un input neanche per B2-Micro. La Tassonomia Sonora incorporata nel prompt è il solo riferimento per i canonical_id.

#### L'Albero Decisionale (Invariato nella logica, cambia l'esito)

Le regole dell'Albero Decisionale v3 per AMB, SFX e Sting sono perfette così come sono e vengono mantenute integralmente. La differenza fondamentale è nell'esito:

- **v3**: Se il suono è in catalogo → usa il `canonical_id` dal catalogo. Se no → shopping list.
- **v4**: Definisci sempre il `canonical_id` migliore dalla Tassonomia. Aggiungi sempre alla Sound Shopping List con il `production_prompt` fisico.

In altre parole: **il copione artistico e la Sound Shopping List vengono prodotti nella stessa call, sono le due facce della stessa moneta**.

#### La Respirazione del Pad (PAD Breathing — Invariata)

La logica di `pad_volume_automation` / `pad_duck_depth` / `pad_fade_speed` è invariata dalla v3. È la componente più valida e matura dell'architettura esistente.

```
pad_volume_automation:
  "ducking" → -12dB medium (default dialogo), -6dB shallow (narrazione), -18dB deep (intimità)
  "build"   → +crescita progressiva (USARE nella scena PRIMA del climax)
  "neutral" → volume pieno (pause, transizioni, climax)

pad_fade_speed:
  "snap"   → 0.3s (entrata brusca, azione)
  "smooth" → 1.0s (default)
  "slow"   → 2.5s (pausa lunga, la musica respira)
```

**La Regola dell'Anticipazione**: La scena *precedente* al climax riceve `build/slow`. La scena del climax riceve `neutral`. Dopo: `ducking/smooth`.

#### Output B2-Micro (IntegratedCueSheet v4)

```json
{
  "integrated_cue_sheet": {
    "project_id": "...",
    "block_id": "chunk-000-micro-000",
    "pad_canonical_id": "pad_retro_sci_fi_tension_01",
    "scenes_automation": [
      {
        "scene_id": "chunk-000-micro-000-scene-001",
        "pad_volume_automation": "ducking",
        "pad_duck_depth": "medium",
        "pad_fade_speed": "snap",
        "amb_id": "amb_enclosed_spaceship_01",
        "amb_offset_s": 0.0,
        "amb_duration_s": 45.0,
        "sfx_id": null,
        "sfx_timing": null,
        "sfx_offset_s": 0.0,
        "sting_id": null,
        "sting_timing": null,
        "reasoning": "Prima scena a bordo dell'Intrepid. AMB che copre le prossime 5 scene. Dialogo fitto → ducking medium."
      },
      {
        "scene_id": "chunk-000-micro-000-scene-007",
        "pad_volume_automation": "neutral",
        "pad_duck_depth": null,
        "pad_fade_speed": "smooth",
        "amb_id": null,
        "sfx_id": "sfx_impact_explosion_near_01",
        "sfx_timing": "middle",
        "sfx_offset_s": 2.5,
        "sting_id": "sting_reveal_shock_01",
        "sting_timing": "end",
        "reasoning": "Climax: esplosione fisica (SFX) + rivelazione narrativa (Sting). Musica già alta."
      }
    ]
  },
  "sound_shopping_list": [
    {
      "type": "amb",
      "canonical_id": "amb_enclosed_spaceship_01",
      "production_prompt": "Interior spacecraft ambient. Low-frequency engine hum 40-80Hz, air filtration white noise, metallic resonance. Constant, non-rhythmic. Stereo wide. Duration: seamless loop 60s+.",
      "scene_id": "chunk-000-micro-000-scene-001"
    },
    {
      "type": "sfx",
      "canonical_id": "sfx_impact_explosion_near_01",
      "production_prompt": "Close-range explosion. Immediate bass impact 60-120Hz + pressure wave. Debris scatter mid-freq. Total duration 2-3s. Dry, no long reverb tail.",
      "scene_id": "chunk-000-micro-000-scene-007"
    },
    {
      "type": "sting",
      "canonical_id": "sting_reveal_shock_01",
      "production_prompt": "Orchestral shock sting. Single sharp dissonant chord, full orchestra, immediate attack, 1.5s sustain then cut. No reverb tail. High intensity.",
      "scene_id": "chunk-000-micro-000-scene-007"
    }
  ]
}
```

> [!NOTE]
> Nota il suffisso `_01` nei canonical_id. In Sound-on-Demand, lo stesso tipo di suono può avere variazioni per progetto (`_01`, `_02`). Il PAD del capitolo potrebbe avere un'intensità diversa da quello del capitolo successivo, anche se sono entrambi `pad_retro_sci_fi_tension`.

---

## 4. Stage D2 — The Sound Factory Client (Nuovo Stage)

### 4.1 Responsabilità

Stage D2 è il simmetrico di Stage D per il suono. Stage D riceve la lista di scene e produce un file `.wav` vocale per ognuna. Stage D2 riceve la **Sound Shopping List aggregata** e produce un file audio per ogni asset richiesto, scaricandolo in locale nella cartella del progetto con il `canonical_id` come nome file.

### 4.2 Architettura Interna

```
Sound Shopping List Aggregata
           │
           ▼
   Deduplicazione per canonical_id
   (rimuove duplicati se più scene chiedono lo stesso asset)
           │
           ▼
   Raggruppamento per tipo (pad | amb | sfx | sting)
   (perché ARIA potrebbe usare modelli diversi per ogni tipo)
           │
     ┌─────┼──────────────┐
     ▼     ▼     ▼        ▼
   PAD   AMB   SFX     STING
     │     │     │        │
     └─────┴─────┴────────┘
           │
           ▼
   Per ogni asset: chiamata ad ARIA SoundFactory API (ACE-Step or Stable Audio)
   con production_prompt per generare pad_master, amb, sfx, sting...
           │
           ▼
   Processamento Audio Locale (Solo per i PAD)
   (Esegue HTDemucs su pad_master.wav per isolare Bass, Melody, Drums)
           │
           ▼
   Salvataggio in:
   {project_root}/stages/stage_d2/assets/{type}/{canonical_id}*.wav
           │
           ▼
   Manifest Locale:
   {project_root}/stages/stage_d2/manifest.json
   (mappa canonical_id → percorsi dei file fisici e stem pronti per Stage E)
```

### 4.3 Il Manifest degli Asset (Input per Stage E)

Il manifest è il cuore del decoupling. Stage E ignora completamente se il PAD è stato scaricato da Internet o generato o ritagliato. Legge un JSON pulito e carica i file.

```json
{
  "project_id": "...",
  "generated_at": "2026-04-09T10:00:00Z",
  "assets": {
    "pad_retro_sci_fi_tension_01": {
      "type": "pad",
      "master_path": "stages/stage_d2/assets/pad/pad_retro_sci_fi_tension_01_master.wav",
      "stems": {
         "bass": "stages/stage_d2/assets/pad/pad_retro_sci_fi_tension_01_bass.wav",
         "melody": "stages/stage_d2/assets/pad/pad_retro_sci_fi_tension_01_melody.wav",
         "drums": "stages/stage_d2/assets/pad/pad_retro_sci_fi_tension_01_drums.wav"
      },
      "duration_s": 243.5,
      "status": "ready"
    },
    "amb_enclosed_spaceship_01": {
      "type": "amb",
      "local_path": "stages/stage_d2/assets/amb/amb_enclosed_spaceship_01.wav",
      "duration_s": 62.1,
      "status": "ready"
    },

    "sfx_impact_explosion_near_01": {
      "type": "sfx",
      "local_path": "stages/stage_d2/assets/sfx/sfx_impact_explosion_near_01.wav",
      "duration_s": 2.4,
      "is_loop": false,
      "status": "ready"
    }
  }
}
```

Stage E carica questo manifest e risolve ogni `canonical_id` nel copione artistico con il percorso locale. **Zero ambiguità, zero lookup remoti durante il mixdown.**

### 4.4 Gestione del PAD (Leitmotif e Brand Sonoro)

Il PAD è speciale: è l'unico asset per cui ha senso una forma di "riuso cross-capitolo". La logica è la seguente:

1. **Prima occorrenza**: Stage D2 produce il PAD e lo salva con il suo `canonical_id`.
2. **Occorrenza successiva (stesso `canonical_id` in un altro capitolo)**: Stage D2 verifica se l'asset esiste già nella cartella `stage_d2/assets/pad/`. Se esiste, **non lo riproduce** ma lo copia o crea un symlink. Questo è il solo punto di "riuso" nell'intera pipeline.
3. **Brand Sound (da `project_sound_palette`)**: Funziona esattamente come il punto 2 — una volta prodotto, viene riutilizzato in tutti i capitoli che lo richiedono.

Questo è il modo in cui preserviamo il Leitmotif senza il peso di un catalogo Redis da mantenere.

---

## 5. I Nuovi Prompt (v4.0)

### 5.1 Prompt B2-Macro v4.0

Il prompt viene **snellito** rimuovendo la Sezione C (Catalogo ARIA).
Viene **arricchito** con l'istruzione per il brand sound.

**Struttura:**
- Sezione A: Linea Editoriale e Palette (Stage 0)
- Sezione B: Contesto Narrativo (Stage B)  
- ~~Sezione C: Catalogo ARIA~~ ← **RIMOSSA**
- Sezione C (nuova): Brand Sound del Progetto (opzionale, da `project_sound_palette`)
- Sezione D: Regole Decisionali (semplificate)
- Sezione E: Formato Output JSON

**Istruzione chiave per il canonical_id PAD:**
> *"Definisci un `canonical_id` semantico che descriva il CARATTERE SONORO di questo capitolo. Usa il formato: `pad_{stile}_{emozione}_{variante_numerica}`. Non usare mai nomi di personaggi o luoghi specifici del libro nell'ID."*

### 5.2 Prompt B2-Micro v4.0

Il prompt viene **snellito** rimuovendo le sezioni "Catalogo Asset ARIA Disponibili".
Viene **rafforzato** con una regola esplicita sulla Sound Shopping List.

**Struttura:**
- Sezione A: Contesto (PAD ereditato dal Macro)
- Sezione B: Il Testo delle Scene (con timing fisico)
- ~~Catalogo Asset~~ ← **RIMOSSO**
- Sezione C: Albero Decisionale AMB → SFX → STING (invariato)
- Sezione D: PAD Breathing (invariato)
- Sezione E: Tassonomia Sonora (come riferimento per i canonical_id)
- Sezione F: Formato Output JSON (doppio: cue_sheet + shopping_list)

**Istruzione chiave per evitare duplicati nel doppio output:**
> *"REGOLA ASSOLUTA: se una scena ha `amb_id: 'X'`, allora `sound_shopping_list` DEVE contenere un item con `canonical_id: 'X'`. Il copione artistico e la shopping list sono la stessa decisione, espressa in due formati. Non possono essere in contraddizione."*

---

## 6. La Tassonomia Sonora (v2.0)

La tassonomia è il **vocabolario comune** tra Stage B2 (che battezza i suoni) e Stage D2 (che li produce). Non è un catalogo di asset esistenti — è un dizionario di tipi di fenomeni fisici.

La versione 2.0 aggiunge varianti numeriche per indicare che lo stesso tipo di suono può avere caratteristiche leggermente diverse (intensità, durata, variante) nell'ambito di un singolo libro.

```yaml
# Formato: canonical_id: "Descrizione fisica del fenomeno"
# I suffissi _01, _02 vengono aggiunti da Gemini per distinguere varianti
# dello stesso tipo di suono nello stesso progetto.

PAD:
  pad_orchestral_tension:   "Tensione orchestrale. Corde gravi, fiati lunghi, dissonanza crescente."
  pad_retro_sci_fi_tension: "Tensione retro-fantascientifica. Archi analogici '70s, synth drone, niente ritmo."
  pad_ambient_mystery:      "Mistero ambientale. Tessiture elettroniche, risonanze metalliche, lentissimo."
  pad_epic_drama:           "Dramma epico. Ottoni pieni, coro lontano, percussioni gravi."
  pad_intimate_sorrow:      "Malinconia intima. Pianoforte solo, archi morbidi, silenzio tra le note."

AMB_ENCLOSED:
  amb_enclosed_spaceship:   "Ronzio motori, aria filtrata, risonanza metallica sottile."
  amb_enclosed_cave:        "Eco profondo, gocce rade, silenzio pesante, pietra."
  amb_enclosed_bunker:      "Ventilazione meccanica, risonanza metallica acuta, isolamento."
  amb_enclosed_lab:         "Elettronica sommessa, bip periodici, ventilazione controllata."
  amb_enclosed_vessel:      "Legno che lavora, pressione d'acqua, scricchiolii lenti."
  amb_enclosed_prison:      "Silenzio oppressivo, eco su pietra, metallo distante."

AMB_OPEN:
  amb_open_space_void:      "Silenzio quasi assoluto. Hiss cosmico impercettibile."
  amb_open_forest:          "Vento tra foglie, uccelli lontani, rumori organici casuali."
  amb_open_city_day:        "Traffico diffuso, voci lontane, clacson sporadici."
  amb_open_city_night:      "Traffico ridotto, sirene lontane, silenzio pesante."
  amb_open_desert:          "Vento secco, calore percepibile, nessun suono organico."
  amb_open_alien:           "Texture non terrestri, frequenze inusuali, sensorialmente inesplorato."
  amb_open_ocean:           "Moto ondoso lento, schiuma, vento costante, vastità."

SFX_IMPACT:
  sfx_impact_glass_hard:    "Vetro su superficie dura. Crack 2-4kHz + frammenti. 0.5-1s. Asciutto."
  sfx_impact_glass_soft:    "Vetro su morbido. Impatto attutito, pochi frammenti. 0.5s."
  sfx_impact_metal_heavy:   "Metallo pesante. Colpo secco + risonanza 200-800Hz. 1-2s."
  sfx_impact_metal_light:   "Metallo leggero. Tintinnio acuto, breve coda. 0.3s."
  sfx_impact_body_fall:     "Corpo umano su superficie dura. Impatto sordo 100-400Hz. 0.5s."
  sfx_impact_explosion_near: "Esplosione vicina. Bass impact 60Hz + pressione. 2-3s."
  sfx_impact_explosion_far: "Esplosione lontana. Rimbombo basso, ritardato. 3-5s."
  sfx_impact_shatter_large: "Struttura grande che crolla. Frantumazione prolungata 2-6s."

SFX_MECHANICAL:
  sfx_mechanical_door_heavy: "Portellone pesante. Apertura/chiusura lenta, cardini, risonanza."
  sfx_mechanical_door_light: "Porta leggera. Cigolìo, chiusura secca. 0.5s."
  sfx_mechanical_weapon_fire: "Sparo singolo. Impatto percussivo, breve coda. 0.3s."
  sfx_mechanical_weapon_reload: "Ricarica arma. Meccanismo metallico, click finale."
  sfx_mechanical_engine_start: "Avvio motore. Turbina/propulsore da spento a regime. 3-5s."
  sfx_mechanical_alarm:     "Allarme elettronico. Ripetitivo, urgente, 800-1200Hz."
  sfx_mechanical_console:   "Pannello controlli. Click tattili, bip conferma. 0.5-1s."

SFX_BIOLOGICAL:
  sfx_bio_creature_large:   "Creatura grande. Movimento corporeo, peso, basso 80-200Hz."
  sfx_bio_creature_swarm:   "Sciame/moltitudine. Ronzio collettivo, movimento di massa."
  sfx_bio_creature_vocal:   "Verso non umano. Alieno/animale, indistinto, inquietante."

STING:
  sting_tension_low:        "Accumulo lento. Corde gravi, dissonanza crescente 3-5s."
  sting_tension_high:       "Tensione acuta improvvisa. Orchestra completa, impatto istantaneo."
  sting_reveal_shock:       "Rivelazione scioccante. Colpo breve e acuto, senza coda. 1-2s."
  sting_reveal_mystery:     "Svelamento lento. Armonia ambigua, senso di scoperta inquieta."
  sting_release:            "Risoluzione/liberazione. Tensione che si scioglie, respiro lungo."
```

---

## 7. Logging e Tracciabilità

Il sistema di log è invariato nella struttura, ma i messaggi si semplificano: scompare il log `[ASSET MANCANTE]` (perché ora tutti gli asset sono "da produrre"). Al suo posto, B2-Micro logga ogni item prodotto nella shopping list.

```
============================================================
[2026-04-09 10:30:00] [SESSION] START PIPELINE B2 v4.0 - Project: urania_n_1610...
============================================================
[2026-04-09 10:30:00] [MACRO] Chunk: chunk-000 | Palette: Retro-Futurismo Orchestrale
[2026-04-09 10:30:35] [MACRO] PAD Assegnato: pad_retro_sci_fi_tension_01
[2026-04-09 10:30:35] [MACRO] Leitmotif: No (asset nuovo)
[2026-04-09 10:31:45] [MICRO] Blocco: chunk-000-micro-000 | 13 scene | PAD ereditato: pad_retro_sci_fi_tension_01
[2026-04-09 10:32:30] [MICRO] Scena 001: AMB=amb_enclosed_spaceship_01 [→ shopping] | ducking/medium/snap
[2026-04-09 10:32:30] [MICRO] Scena 006: build/slow (anticipazione climax scena-007)
[2026-04-09 10:32:30] [MICRO] Scena 007: SFX=sfx_impact_explosion_near_01 [→ shopping] | neutral/smooth + STING=sting_reveal_shock_01 [→ shopping]
[2026-04-09 10:32:30] [MICRO] Shop items questo blocco: 3 (1 amb, 1 sfx, 1 sting)
============================================================
[2026-04-09 10:45:00] [SESSION] FINE B2 - Sound Shopping List: 12 asset unici → D2 Stage
============================================================
```

---

## 8. Flow Completo: Da Stage B2 a Stage E

```
1. B2 Pipeline run
   └── Produce: IntegratedCueSheet per ogni micro-blocco
   └── Produce: sound_shopping_list_aggregata.json (tutti i micro blocchi)

2. D2 Stage run
   └── Legge: sound_shopping_list_aggregata.json
   └── Deduplica per canonical_id
   └── Chiama ARIA SoundFactory per ogni asset
   └── Aspetta completamento (polling)
   └── Scarica asset in locale
   └── Produce: stage_d2/manifest.json

3. Stage E run
   └── Per ogni micro-blocco, carica IntegratedCueSheet e pad.arc (Macro)
   └── Per ogni canonical_id nel copione, risolve i path locali via manifest.json
   └── Se PAD: carica Bass, Melody, Drums su tracce separate e automatizza il volume via pad.arc
   └── Carica i WAV vocali (Stage D) e li allinea sulla timeline
   └── Piazza PAD_master_ducking, AMB, SFX, STING secondo la partitura micro
   └── Esporta il macro-chunk mixato (.wav)
```

---

## 9. Roadmap di Implementazione

### Fase 1 — Refactoring Stage B2 (Priorità: Alta)

- [ ] Eliminare la logica di fetch Redis da `stage_b2_macro.py` e `stage_b2_micro.py`
- [ ] Aggiornare i modelli Pydantic: `MacroCue` ottiene il campo `pad` (oggetto completo) invece di `selected_pad_id`; `IntegratedCueSheet` rinomina `sound_shopping_list`
- [ ] Riscrivere il prompt `b2_macro_v4.0.yaml` senza la sezione Catalogo ARIA
- [ ] Riscrivere il prompt `b2_micro_v4.0.yaml` senza la sezione Catalogo ARIA, con la regola di coerenza copione/shopping
- [ ] Aggiornare `run_b2_pipeline.py`: l'aggregatore non blocca più la pipeline, produce solo `sound_shopping_list_aggregata.json`

### Fase 2 — Creazione Stage D2 (Priorità: Alta)

- [ ] Creare `src/stages/stage_d2_sound_factory.py`
- [ ] Implementare deduplica e raggruppamento per tipo
- [ ] Integrare con le API di ARIA SoundFactory (richiesta audio generation)
- [ ] **Integrare Modulo `HTDemucs`** in Stage D2 per fare Stem split post-generazione (su PAD)
- [ ] Implementare download e salvataggio locale (WAV e stem separati)
- [ ] Implementare meccanismo di riuso PAD cross-capitolo (check locale prima di produrre)
- [ ] Produrre `stage_d2/manifest.json` con array dict paths per stems.

### Fase 3 — Aggiornamento Stage E (Priorità: Media)

- [ ] Aggiornare il loader di Stage E per usare `manifest.json` invece del registro Redis
- [ ] Verificare compatibilità con i nuovi campi (es. `pad_canonical_id` invece di `selected_pad_id`)

### Fase 4 — Pulizia Infrastruttura (Priorità: Bassa)

- [ ] Rimuovere dal registro Redis le chiavi relative alla Sound Library (mantenere solo quelle vocali)
- [ ] Eliminare la struttura di directory `soundlibrary/` su ARIA PC 139 (o archiviarla)
- [ ] Aggiornare `dias-workflow-logic.md` e la sitemap della documentazione

---

## 10. File Critici e Percorsi (v4.0)

| File | Percorso |
| :--- | :--- |
| **Tassonomia Sonora** | `config/sound_taxonomy.yaml` |
| **Prompt Macro v4** | `config/prompts/stage_b2/b2_macro_v4.0.yaml` |
| **Prompt Micro v4** | `config/prompts/stage_b2/b2_micro_v4.0.yaml` |
| **Worker Macro** | `src/stages/stage_b2_macro.py` |
| **Worker Micro** | `src/stages/stage_b2_micro.py` |
| **Stage D2 Worker** | `src/stages/stage_d2_sound_factory.py` |
| **Orchestratore B2** | `tests/stages/run_b2_pipeline.py` |
| **Orchestratore D2** | `tests/stages/run_d2_pipeline.py` |
| **Output Macro-Cue** | `stages/stage_b2/output/{project_id}-{chunk}-macro-cue.json` |
| **Output Micro-Cue** | `stages/stage_b2/output/{project_id}-{block}-micro-cue.json` |
| **Shopping List Aggregata** | `{project_root}/sound_shopping_list_aggregata.json` |
| **Manifest D2** | `{project_root}/stages/stage_d2/manifest.json` |
| **Asset PAD** | `stages/stage_d2/assets/pad/{canonical_id}.wav` |
| **Asset AMB** | `stages/stage_d2/assets/amb/{canonical_id}.wav` |
| **Asset SFX** | `stages/stage_d2/assets/sfx/{canonical_id}.wav` |
| **Asset STING** | `stages/stage_d2/assets/sting/{canonical_id}.wav` |
| **Log Decisionale** | `stages/stage_b2/output/b2_traceability.log` |
