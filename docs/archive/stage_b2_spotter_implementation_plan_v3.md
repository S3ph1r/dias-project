> **[ARCHIVIATO — Aprile 2026]**
> Piano di implementazione del B2 con architettura Catalogo + Matching semantico all'85%.
> Sostituito da `stage_b2_d2_sound_on_demand_v4.md` (ora implementato come Sound-on-Demand v4.1).
> Per l'architettura corrente, vedere `blueprint.md` e `dias-workflow-logic.md`.

# Stage B2 — The Spotter: Implementation Plan V3

> **Versione**: 3.0 — Aprile 2026
> **Status**: Approvato per implementazione
> **Dipendenze a monte**: Stage 0 (Preproduzione), Stage B (Analisi Narrativa), Stage C (Scene Director), Stage D (Master Timing Grid)
> **Produce**: Copione Artistico Integrato (`IntegratedCueSheet`) → Stage E (Mixdown)

---

## 1. Visione e Principi Fondamentali

Stage B2 è il **Sound Designer** automatizzato del sistema DIAS. La sua responsabilità non è riempire il silenzio con suoni — è decidere *quando* il silenzio va interrotto e *perché*.

Il risultato finale è un **Copione Artistico Integrato** per ogni micro-blocco di scene: un documento JSON che dice a Stage E esattamente cosa suonare, a quale volume, con quale velocità di fade e in quale momento fisico dell'audio vocale. Non è una lista di suggerimenti. È una partitura eseguibile.

### Principi Irrinunciabili

1. **Il Silenzio è il Default.** Il suono deve guadagnarsi il diritto di esistere. Ogni asset piazzato deve superare un test di merito esplicito. Se il test non è superato, la scena è silenziosa.

2. **La Musica Respira.** Non è mai "ferma" su un livello fisso. Scende quando la voce parla, risale durante le pause, cresce per anticipare i climax. Questo è il "Radio Drama Effect" — il suono che si sente nei radiodramma di Star Wars.

3. **L'Asset è un Fenomeno Fisico, non una Narrativa.** Quando manca un suono nel catalogo, lo descriviamo come un evento fisico misurabile (frequenza, durata, materiale, impatto) — non come "il rumore che fa X nel romanzo". Questo garantisce che l'asset prodotto da ARIA sia riutilizzabile per decine di scene simili in futuro.

4. **Coerenza Artistica Globale.** Le scelte musicali rispettano la Palette scelta nella Fase di Preproduzione (Stage 0). Un libro con palette "Retro-Futurismo Orchestrale" non accetta come musica un loop lo-fi indie, anche se tecnicamente descrive bene una singola scena.

---

## 2. Architettura: Due Worker Sequenziali

```
Stage 0 ──────┐
(Palette)     │
              ▼
Stage B ──► B2-MACRO ──► macro-cue.json
(Analisi)              (Palette MUS scelta)
                              │
Stage C ──────┐               │
(Scene)       │               ▼
              ├──────────► B2-MICRO ──► IntegratedCueSheet
Stage D ──────┘                        (Copione per Stage E)
(Timing Grid)
```

I due worker non sono alternativi — sono **necessariamente sequenziali**. Micro non può operare senza l'output di Macro (eredita la scelta MUS). Questa architettura garantisce coerenza verticale: ogni scena del libro ha la stessa "firma musicale" del capitolo in cui si trova.

---

## 3. B2-MACRO — Il Direttore Musicale

### 3.1 Responsabilità

B2-Macro opera a livello di **Macro-Chunk** (blocchi di circa 1500-3000 parole, corrispondenti a uno o più capitoli). Ha un unico compito: scegliere il **Tema Musicale Portante (MUS)** per quel blocco ed assicurarsi che sia coerente con lo stile del progetto.

Non si occupa di ambienti, effetti sonori o accenti drammatici. Quella è responsabilità di B2-Micro.

### 3.2 Inputs

| Fonte | File | Contenuto Usato |
| :--- | :--- | :--- |
| **Stage 0** | `preproduction.json` | `palette_choice`: la palette approvata (es. "Retro-Futurismo Orchestrale") |
| **Stage 0** | `fingerprint.json` | `sound_design.palette_proposals[]`: le 3 descrizioni delle palette proposte |
| **Stage B** | `{project_id}-chunk-{id}.json` | `block_analysis.primary_emotion`, `block_analysis.secondary_emotion`, `block_analysis.setting`, `concepts[]`, `audio_cues[]` |
| **ARIA Registry** | Redis `aria:registry:master` | `assets.pads{}`: dizionario degli asset musicali disponibili, con tags e descrizione |

### 3.3 Cosa chiediamo a Gemini

Gemini legge il contesto del chunk (emozioni, ambientazione, cues) e il catalogo dei Pads, sapendo già qual è lo **stile artistico del progetto**. La domanda che deve rispondere è:

> *"C'è nel catalogo un tema musicale che suona come [palette_choice] e che accompagna un'atmosfera di [primary_emotion] in un setting di [setting]?"*

Se la risposta è sì → assegna l'ID dell'asset.
Se la risposta è no (nessun asset soddisfa ENTRAMBI i criteri: stile + emozione) → `selected_mus_id = null` e compila la shopping list con un prompt fisico coerente con la palette.

### 3.4 La Regola del Leitmotif

Se due Macro-Chunk consecutivi condividono la stessa emozione primaria e lo stesso setting, Macro **deve** usare lo stesso `selected_mus_id`. Questo crea la continuità che l'orecchio percepisce come "tema musicale del libro".

### 3.5 Output

```json
{
  "project_id": "...",
  "chunk_label": "chunk-000",
  "selected_mus_id": "retro_futurist_01",
  "music_justification": "Il setting claustrofobico della nave e l'emozione primaria di tensione richiedono un tema oscuro e sintetico. retro_futurist_01 offre il drone orchestrale con texture analogiche anni '70 necessario per questo stilema."
}
```

Con shopping list contestuale se l'asset manca:
```json
{
  "missing_assets": [
    {
      "type": "mus",
      "canonical_id": "mus_retro_sci_fi_tension",
      "production_prompt": "Orchestral retro-futuristic score. Heavy brass, 70s analog synth strings, dissonant chord clusters, slow-moving tension. No percussion. Duration: 2-4 min loop. Dark, claustrophobic."
    }
  ]
}
```

---

## 4. B2-MICRO — Il Sound Designer di Dettaglio

### 4.1 Responsabilità

B2-Micro opera a livello di **Micro-Chunk** (circa 300-500 parole, 8-20 scene). Eredita la scelta MUS da B2-Macro e si occupa di tutto il resto: **Ambiente (AMB)**, **Effetti Sonori (SFX)**, **Accenti Drammatici (Sting)** e soprattutto la **Curva di Automazione del Volume Musicale**.

Il suo output è il **Copione Artistico Integrato**: il documento finale che Stage E esegue senza necessità di interpretazione.

### 4.2 Inputs

| Fonte | File | Contenuto Usato |
| :--- | :--- | :--- |
| **B2-Macro** | `{project_id}-chunk-{id}-macro-cue.json` | `selected_mus_id`: il tema musicale da ereditare |
| **Stage C** | `{project_id}-chunk-{id}-micro-{id}-scenes.json` | `scenes[]`: testo, speaker, tipo di scena per ogni micro-scena |
| **Stage D** | `master_timing_grid.json` | Per ogni scena: `voice_duration_s`, `pause_after_s`, `start_offset_s` in secondi fisici |
| **ARIA Registry** | Redis `aria:registry:master` | `assets.pads{}`, `assets.sfx{}`, `assets.stings{}`: tutti gli asset disponibili con `canonical_id` e tags |

### 4.3 La Finestra di Contesto

Gemini riceve per ogni scena una struttura come questa:

```json
{
  "scene_id": "chunk-000-micro-000-scene-007",
  "speaker": "NARRATOR",
  "text": "Il suolo tremò. Davis sentì le vibrazioni salire lungo i piedi mentre i vermi sfondavano la roccia.",
  "voice_duration_s": 5.2,
  "pause_after_s": 1.8,
  "scene_start_offset_s": 34.6
}
```

Questo permette a Gemini di ragionare così: *"La scena 7 inizia al secondo 34.6, la voce dura 5.2 secondi. Se voglio che il rombo sismico inizi leggermente prima del climax verbale, lo posiziono con sfx_offset_s: -0.5"*.

### 4.4 L'Albero Decisionale (Il Cuore del Sistema)

Questo è il meccanismo più importante. Queste regole vanno nel prompt come istruzioni esplicite — non come suggerimenti.

---

#### 4.4.1 AMB — Ambiente Fisico

**Quando usarlo:**
```
1. L'ambiente fisico della scena è CAMBIATO rispetto al blocco precedente?
     NO → amb_id = null (ambiente ereditato implicitamente)
     SI → procedi al test 2

2. Il nuovo ambiente è SENSORIALMENTE DISTINTO e CARATTERIZZANTE?
     (Non una stanza neutra, un corridoio generico, un ufficio anonimo)
     NO → amb_id = null
     SI → scegli dalla categoria AMB della tassonomia
```

**Regola di durata:** L'AMB non va ripetuto ogni scena. Si piazza nella prima scena del nuovo ambiente con una `amb_duration_s` che copre l'intera sequenza. Se l'ambiente persiste per tutto il blocco, `amb_duration_s` è la somma di tutte le `voice_duration_s` + `pause_after_s` delle scene successive.

---

#### 4.4.2 SFX — Effetto Fisico

**Quando usarlo:**
```
1. È avvenuto un evento fisico NEL PRESENTE della narrazione?
     (Non ricordato, non immaginato, non metaforico, non descritto dal pensiero di un personaggio)
     NO → sfx_id = null

2. L'ascoltatore PERDEREBBE qualcosa di essenziale senza sentirlo?
     (Non è già chiaro dalla voce del narratore)
     NO → sfx_id = null

3. L'evento appartiene a una categoria IMPATTO o MECCANISMO della tassonomia?
     (NON: passi, vestiti, respiri, rubinetti, tastiere, oggetti quotidiani)
     NO → sfx_id = null
     SI → scegli dalla categoria SFX della tassonomia
```

**Regola del buon senso:** Un bicchiere che cade e si rompe nella scena cruciale di un thrilling → SFX. Un bicchiere che cade in una scena di dialogo leggero → silenzio. L'impatto narrativo del rumore dipende dal contesto, non dall'evento fisico in sé.

---

#### 4.4.3 STING — Accento Drammatico

**Quando usarlo:**
```
1. Hai già usato uno Sting in questo blocco?
     SI → VIETATO. sting_id = null (regola assoluta: uno per blocco)

2. Una singola informazione ha cambiato IRREVERSIBILMENTE la comprensione del lettore?
     (Morte inattesa, tradimento scoperto, rivelazione di identità, colpo di scena radicale)
     NO → sting_id = null
     SI → scegli dalla categoria STING della tassonomia
```

**Posizionamento:** Lo Sting va sulla scena dove avviene la rivelazione, con `sting_timing: "middle"` o `"end"` — mai all'inizio. Il suo compito è sottolineare la parola o il momento in cui il lettore capisce, non anticiparlo.

---

### 4.5 La Respirazione Musicale

Questo è il meccanismo che trasforma un accompagnamento musicale piatto in una colonna sonora cinematografica.

**I tre livelli di volume:**

| Stato | `mus_volume_automation` | Livello dB |
| :--- | :--- | :--- |
| Voce attiva (dialogo/narrazione) | `ducking` | -12dB (medium) / -18dB (deep) |
| Pausa tra scene / transizioni | `neutral` | 0dB (volume pieno) |
| Anticipazione climax | `build` | +2dB progressivo |

**La profondità del ducking (`mus_duck_depth`):**

| Valore | dB | Quando usarlo |
| :--- | :--- | :--- |
| `shallow` | -6dB | Narrazione lenta, descrittiva — la musica è ancora sentita |
| `medium` | -12dB | Dialogo normale, narrazione ritmica — il default |
| `deep` | -18dB | Momento intimo, segreto, confessione — la musica quasi scompare |

**La velocità del fade (`mus_fade_speed`):**

| Valore | Durata | Quando usarlo |
| :--- | :--- | :--- |
| `snap` | 0.3s | Voce che entra improvvisamente, azione che inizia |
| `smooth` | 1.0s | Transizioni normali, la musica "cede" naturalmente |
| `slow` | 2.5s | Pausa lunga, la musica "respira" e risale con calma |

**La Regola dell'Anticipazione (fondamentale per il Radio Drama Effect):**

> *La scena del climax è già in cima alla montagna. La musica deve iniziare a salire DUE SCENE PRIMA.*

Esempio pratico su un blocco di 5 scene:
```
Scena 1 → ducking/medium/snap      (dialogo normale)
Scena 2 → ducking/medium/snap      (dialogo normale)
Scena 3 → build/slow               ← ANTICIPAZIONE (la musica inizia a salire)
Scena 4 → neutral (già alta)       ← CLIMAX: + SFX o Sting
Scena 5 → ducking/medium/smooth    (atterraggio, dissolvenza)
```

**La Regola del Silenzio nelle Pause:**

Quando `pause_after_s > 1.5s`, quella pausa è un momento aureo. La musica è al massimo, senza la voce a coprirla. B2-Micro deve sfruttarla: la scena che precede una pausa lunga riceve `neutral` o `build`, non `ducking`.

---

### 4.6 Output: Il Copione Artistico Integrato

L'output include **tutte le scene** del blocco — anche quelle silenziose. Questo perché Stage E ha bisogno di una curva di automazione continua del volume. Una scena mancante significherebbe un buco nella partitura.

```json
{
  "integrated_cue_sheet": {
    "project_id": "...",
    "block_id": "chunk-000-micro-000",
    "selected_mus_id": "retro_futurist_01",
    "scenes_automation": [
      {
        "scene_id": "chunk-000-micro-000-scene-001",
        "mus_volume_automation": "ducking",
        "mus_duck_depth": "medium",
        "mus_fade_speed": "snap",
        "amb_id": "amb_enclosed_spaceship",
        "amb_offset_s": 0.0,
        "amb_duration_s": 45.0,
        "sfx_id": null,
        "sfx_timing": null,
        "sfx_offset_s": 0.0,
        "sting_id": null,
        "sting_timing": null,
        "reasoning": "Primo ingresso nell'Intrepid: AMB che copre le prossime 5 scene. Dialogo fitto → ducking medium."
      },
      {
        "scene_id": "chunk-000-micro-000-scene-006",
        "mus_volume_automation": "build",
        "mus_duck_depth": null,
        "mus_fade_speed": "slow",
        "amb_id": null,
        "sfx_id": null,
        "sting_id": null,
        "reasoning": "Scena prima del climax: build lento per anticipare la rivelazione della scena 7."
      },
      {
        "scene_id": "chunk-000-micro-000-scene-007",
        "mus_volume_automation": "neutral",
        "mus_duck_depth": null,
        "mus_fade_speed": "smooth",
        "amb_id": null,
        "sfx_id": "sfx_impact_explosion_near",
        "sfx_timing": "middle",
        "sfx_offset_s": 2.5,
        "sting_id": "sting_reveal_shock",
        "sting_timing": "end",
        "reasoning": "Climax: esplosione fisica (SFX) + rivelazione narrativa (Sting). Musica già alta per anticipazione."
      }
    ]
  }
}
```

---

## 5. La Tassonomia Sonora Universale

### Filosofia

Ogni asset ha un `canonical_id` che descrive il **fenomeno fisico**, non la narrativa. Il formato è:
`{classe}_{sottoclasse}_{variante}`

Questo ID è il punto di incontro tra:
- **DIAS** (che lo richiede nella shopping list)
- **ARIA** (che lo produce e lo etichetta con questo nome)
- **Il Matching al secondo passaggio** (che trova l'asset per ID diretto prima ancora di fare ricerca semantica)

### Tassonomia Base (v1.0)

```yaml
AMB_ENCLOSED:
  amb_enclosed_spaceship:   "Ronzio motori, aria filtrata, risonanza metallica, bassa frequenza"
  amb_enclosed_cave:        "Eco profondo, gocce, silenzio pesante, risonanza naturale"
  amb_enclosed_bunker:      "Metallo, risonanza acuta, ventilazione meccanica, isolamento"
  amb_enclosed_lab:         "Elettronica, bip sommessi, ventilazione controllata, asettico"
  amb_enclosed_vessel:      "Legno che lavora, acqua, scricchiolii, pressione"

AMB_OPEN:
  amb_open_space_void:      "Silenzio quasi assoluto, hiss cosmico, bassofondo impercettibile"
  amb_open_forest:          "Vento tra le foglie, uccelli lontani, rumori organici"
  amb_open_city_day:        "Traffico diffuso, voci lontane, clacson sporadici"
  amb_open_city_night:      "Traffico ridotto, sirene lontane, silenzio pesante"
  amb_open_desert:          "Vento secco, silenzio caldo, nulla di organico"
  amb_open_alien:           "Suoni non terrestri, texture inusuali, atmosfera sensorialmente distinta"

SFX_IMPACT:
  sfx_impact_glass_hard:    "Vetro su superficie dura. Crack ad alta freq. + frammenti. 0.5-1s."
  sfx_impact_glass_soft:    "Vetro su superficie morbida. Impatto attutito. 0.5s."
  sfx_impact_metal_heavy:   "Metallo pesante. Colpo secco + risonanza. 1-2s."
  sfx_impact_metal_light:   "Oggetto metallico leggero. Tintinnio. 0.3s."
  sfx_impact_body_fall:     "Corpo umano che cade su superficie dura. Impatto sordo. 0.5s."
  sfx_impact_explosion_near: "Esplosione vicina. Bass impact + onda di pressione. 2-3s."
  sfx_impact_explosion_far:  "Esplosione distante. Rimbombo basso, ritardato. 3-5s."
  sfx_impact_shatter_large:  "Rottura di struttura grande. Crollo, frantumazione prolungata."

SFX_MECHANICAL:
  sfx_mechanical_door_heavy: "Portellone/porta pesante. Apertura lenta, cardini, chiusura."
  sfx_mechanical_door_light: "Porta leggera. Cigolìo, chiusura secca."
  sfx_mechanical_weapon_fire: "Sparo singolo. Impatto immediato, no coda."
  sfx_mechanical_weapon_reload: "Ricarica arma. Meccanismo metallico, click."
  sfx_mechanical_engine_start: "Avvio motore. Turbina/propulsore da spento a regime."
  sfx_mechanical_alarm:      "Allarme elettronico. Ripetitivo, urgente."
  sfx_mechanical_console:    "Pannello controlli. Click, bip, risposta tattile."

SFX_BIOLOGICAL:
  sfx_bio_creature_large:   "Creatura grande. Movimento corporeo, peso percepibile."
  sfx_bio_creature_swarm:   "Sciame/moltitudine. Ronzio collettivo, movimento di massa."
  sfx_bio_creature_vocal:   "Verso non umano. Alieno, animale, indistinto."

STING:
  sting_tension_low:        "Accumulo di tensione lenta. Corde gravi, dissonanza crescente."
  sting_tension_high:       "Tensione acuta e improvvisa. Tutta l'orchestra, impatto istantaneo."
  sting_reveal_shock:       "Rivelazione scioccante. Colpo breve, acuto, senza coda."
  sting_reveal_mystery:     "Svelamento lento. Armonia ambigua, senso di scoperta inquieta."
  sting_release:            "Risoluzione, liberazione. Tensione che si scioglie, respiro."
```

### Regola di Matching al Secondo Passaggio

Quando ARIA produce un asset con un `canonical_id` (es. `sfx_impact_glass_hard`), lo inserisce nel registro con questo ID come chiave primaria. Al secondo passaggio di B2-Micro:

1. Gemini riceve il catalogo con i `canonical_id` espliciti.
2. Prima di fare semantic search, cerca il canonical_id richiesto direttamente.
3. Se lo trova: match garantito, nessuna proliferazione.
4. Se non lo trova: semantic search sull'85% di similarità.

---

## 6. La Shopping List — Principi di Produzione

### Il `production_prompt` è Fisico, non Narrativo

| ❌ Narrativo (Sbagliato) | ✅ Fisico (Corretto) |
| :--- | :--- |
| "suono del bicchiere di Dahl che cade sul ponte metallico dell'Intrepid" | "Glass shattering on metal floor. Single impact. High-freq crack 2-4kHz + scatter. Duration 0.7s. No reverb tail." |
| "rumore dei vermi alieni che sfondano la roccia del pianeta" | "Large biological creature movement through solid material. Low rumble 80-200Hz + crack. Organic, non-mechanical. Duration 2-3s." |
| "la musica inquietante del capitolo in cui Jenkins confessa" | "Orchestral retro-futuristic tension cue. Slow dissonant strings, 70s analog synth drone, no rhythm. Duration 90s loop. Key: minor. Tempo: none." |

### Struttura della Shopping List

```json
{
  "type": "sfx",
  "canonical_id": "sfx_impact_glass_hard",
  "production_prompt": "Glass shattering on hard floor. Single impact. High-frequency crack followed by debris scatter. Duration: 0.5-1s. No reverb tail. Dry recording.",
  "scene_id": "chunk-000-micro-000-scene-007"
}
```

Il `canonical_id` deve sempre corrispondere a una voce della Tassonomia. Se Gemini sente il bisogno di un suono fuori tassonomia, deve prima verificare se una categoria esistente è "abbastanza buona" (85% di fit). Solo se nessuna categoria copre il fenomeno fisico, propone un nuovo `canonical_id` rispettando il formato `{classe}_{sottoclasse}_{variante}`.

---

## 7. Logging di Tracciabilità

Il file `stages/stage_b2/output/b2_traceability.log` è scritto da entrambi i worker e dall'orchestratore. Il formato garantisce la leggibilità per revisione umana.

```
============================================================
[2026-04-08 09:52:23] [SESSION] START PIPELINE B2 - Project: urania_n_1610...
============================================================
[2026-04-08 09:52:23] [MACRO] Inizio elaborazione chunk-000
[2026-04-08 09:52:23] [MACRO] Palette Scelta: Retro-Futurismo Orchestrale
[2026-04-08 09:52:23] [MACRO] Asset in Catalogo: 3
[2026-04-08 09:52:55] [MACRO] Decisione Finale: MUS=None
[2026-04-08 09:52:55] [MACRO] Giustificazione: <reasoning da Gemini>
[2026-04-08 09:52:55] [MACRO] ⚠️ ASSET MANCANTE: [mus] canonical_id=mus_retro_sci_fi_tension
[2026-04-08 09:52:55] [MICRO] Inizio elaborazione chunk-000-micro-000
[2026-04-08 09:52:55] [MICRO] MUS Ereditata: None
[2026-04-08 09:52:55] [MICRO] Invio 13 scene a Gemini...
[2026-04-08 09:53:34] [MICRO] Scena scene-001: AMB=amb_enclosed_spaceship, DUCK=medium/snap | Rationale: ...
[2026-04-08 09:53:34] [MICRO] Scena scene-006: BUILD slow (anticipazione climax scena-007)
[2026-04-08 09:53:34] [MICRO] Scena scene-007: SFX=sfx_impact_explosion_near(+2.5s), STG=sting_reveal_shock(end)
[2026-04-08 09:53:34] [MICRO] ⚠️ ASSET MANCANTE: [sting] canonical_id=sting_reveal_shock
============================================================
[2026-04-08 09:57:39] [SESSION] STOP PIPELINE B2 - Pending Shopping List (12 assets)
============================================================
```

---

## 8. Blocco della Pipeline e Gestione degli Asset Mancanti

### Flusso di Blocco

```
Fine Pipeline B2
       │
       ▼
Aggregazione Shopping Lists
(tutte le parziali in b2/output/)
       │
       ├── Lista Vuota → ✅ Stage E può partire
       │
       └── Lista Non Vuota → ❌ STOP
               │
               ▼
        master_shopping_list_B2.json
        (nella root del progetto)
               │
               ▼
        Intervento Manuale:
        Produzione asset su ARIA (PC139)
        con canonical_id come nome file
               │
               ▼
        Riesecuzione Stage B2 da capo
        (pipeline cleanup automatico)
               │
               ▼
        Secondo Passaggio:
        Gemini trova gli asset per canonical_id
        → Lista vuota → Stage E
```

### Importanza dell'Esaustività

La pipeline processa **tutti** i chunk prima di bloccarsi. Non si ferma al primo asset mancante. Questo garantisce che con una singola esecuzione otteniamo la **shopping list completa dell'intero libro**. Possiamo poi produrre tutti gli asset in un'unica sessione su ARIA e rieseguire B2 una sola volta.

---

## 9. Connessione con Stage E (Mixdown)

Stage E riceve per ogni micro-blocco un `IntegratedCueSheet` con le seguenti informazioni operative:

| Campo | Utilizzo in Stage E |
| :--- | :--- |
| `selected_mus_id` | Carica il file audio della MUS. Loop continuo per tutto il blocco. |
| `mus_volume_automation` | Applica ducking/build/neutral in sincronia con il timing grid |
| `mus_duck_depth` | Calcola il target dB (-6/-12/-18) per la curva di automazione |
| `mus_fade_speed` | Calcola la durata del fade (0.3s/1s/2.5s) |
| `amb_id` + `amb_offset_s` + `amb_duration_s` | Piazza l'ambiente sul timeline, con fade-in/out impliciti di 1s |
| `sfx_id` + `sfx_timing` + `sfx_offset_s` | Piazza SFX rispetto all'inizio della scena (`start_offset_s + sfx_offset_s`) |
| `sting_id` + `sting_timing` | Piazza lo Sting all'inizio/metà/fine della `voice_duration_s` della scena |

Stage E non deve interpretare nulla. Esegue la partitura.

---

## 10. File Critici e Percorsi

| File | Percorso |
| :--- | :--- |
| Tassonomia Sonora | `config/sound_taxonomy.yaml` |
| Prompt Macro | `config/prompts/stage_b2/b2_macro_v2.0.yaml` |
| Prompt Micro | `config/prompts/stage_b2/b2_micro_v3.0.yaml` |
| Worker Macro | `src/stages/stage_b2_macro.py` |
| Worker Micro | `src/stages/stage_b2_micro.py` |
| Orchestratore | `tests/stages/run_b2_pipeline.py` |
| Output Macro | `stages/stage_b2/output/{project_id}-chunk-{id}-macro-cue.json` |
| Output Micro | `stages/stage_b2/output/{project_id}-chunk-{id}-micro-{id}-micro-cue.json` |
| Shopping List | `stages/stage_b2/output/{project_id}-*-shopping-list-*.json` |
| Master Shopping | `{project_root}/master_shopping_list_B2.json` |
| Log Decisionale | `stages/stage_b2/output/b2_traceability.log` |
