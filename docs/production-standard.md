# DIAS Production Standard (v3.0)

Questo documento definisce lo standard qualitativo per la produzione audio di DIAS: voce, sound design e mixing. Il benchmark di riferimento è la **BBC Radio Drama degli anni '80** e **Star Wars Audio Drama (NPR, 1981)**.

---

## 1. Standard Teatrale: La "Formula Oscar" (Voce)

Target: qualità di narrazione cinematica sovrapponibile a ElevenLabs, usando Qwen3-TTS v1.7b.

| Parametro | Valore Target | Effetto |
| :--- | :--- | :--- |
| `subtalker_temperature` | **0.75** | Grana umana e sospiri naturali. |
| `temperature` | **0.7** | Bilanciamento fedeltà linguistica / variazione prosodica. |
| `top_p` / `top_k` | **0.8+ / 50** | Campionamento stabile (standard Qwen3). |
| `voice_ref_text` | **Mandatorio** | Metronomo fonetico. Deve corrispondere al `ref_padded.wav`. |

---

## 2. Regia Vocale e Punteggiatura Audio

### 2.1 Regime Monastico (Fidelità)
Nessuna alterazione del testo sorgente. La qualità si misura sulla precisione fonetica (accenti tonici inseriti da Stage C) e sulla coerenza narrativa.

### 2.2 Tag Splitting (Isolamento)
I "speech tags" (`disse lui`, `replicò Chen`) devono essere separati fisicamente dalle battute. Il clone vocale del personaggio non legge descrizioni di se stesso.

### 2.3 Istruzioni TTS (qwen3_instruct)
Descrizioni fisiche ed emotive in inglese, in prosa. Non comandi tecnici secchi.
Esempio: `"Hushed, inward voice, very slow pace. Private doubt laced with concealed tension."`

### 2.4 Punteggiatura Ottimizzata
- **Tratto lungo (` - `)**: Pause drammatiche e sospensioni pulite. Sostituisce i puntini di sospensione (`...`) che causano artefatti (clicking).
- **Virgola extra (`,`)**: Forza il respiro naturale.
- **CAPS o virgolette**: Enfasi su parole chiave.

### 2.5 Normalizzazione Fonetica
- Numeri: convertiti in lettere (`"2042"` → `"duemilaquarantadue"`).
- Accenti: solo per parole ambigue (`"pàtina"`, `"scivolò"`).
- Titoli: isolati in scene dedicate con `pause_after_ms` = 2000.

---

## 3. Standard Sound Design (Paradigma BBC/Star Wars)

Il principio fondamentale: **il silenzio è il default. Un suono deve guadagnarsi il diritto di esistere.**

La voce e i dialoghi sono i protagonisti assoluti. La musica PAD è un personaggio invisibile che respira con la narrazione. AMB, SFX e STING sono punteggiatura rara e precisa.

### 3.1 PAD (Tappeto Musicale Continuo)
- Sempre presente, gestito tramite PadArc (low/mid/high stem layers).
- Ducking depth locale per ogni scena:
  - `shallow` = -6 dB (scena intensa, voce forte)
  - `medium` = -12 dB (narrazione standard)
  - `deep` = -18 dB (momento intimo, voce sommessa)
- Fade speed:
  - `snap` = 0.3s (cambio improvviso)
  - `smooth` = 1s (transizione naturale, default)
  - `slow` = 2.5s (dissolvenza lenta, finali di scena)
- `pad_volume_automation`: `ducking` (default) | `build` (crescendo verso climax) | `neutral` (volume costante)

### 3.2 AMB (Cambio di Scena)
- **Durata**: 3-5 secondi. Non è un loop.
- **Limite**: max 1 per micro-chunk. Spesso zero.
- **Regola di attivazione**: solo se il testo descrive esplicitamente un cambio di ambientazione fisica tra scene consecutive (interno → esterno, silenzio → folla, stanza → spazio aperto).
- Si applica alla scena del cambio. Tutte le scene successive: `amb_id: null`.
- Esempi validi: uscita dall'edificio in strada, entrata in una sala rumorosa, cambio da interno a deserto.
- Esempi non validi: cambio di umore, cambio di personaggio, cambio di argomento.

### 3.3 SFX (Effetto Puntuale)
- **Durata**: 0.3-2 secondi.
- **Limite**: max 1 per scena. Zero è spesso la risposta corretta.
- **Regola di attivazione**: solo per il momento culminante in cui l'azione fisica accade. Non per la preparazione, non per l'aftermath.
- Esempi validi: colpo di pistola nel momento in cui viene sparato, porta che sbatte nell'istante della chiusura, oggetto che cade.
- Esempi non validi: tensione prima di uno sparo, eco dopo una porta, passi di un personaggio che cammina normalmente.
- `sfx_timing`: `start` | `middle` | `end`.

### 3.4 STING (Accento Orchestrale)
- **Durata**: 2-4 secondi.
- **Limite**: max 1 per micro-chunk. Mai all'inizio di una scena (`sting_timing`: `middle` o `end`).
- **Regola di attivazione**: solo per rivelazioni narrative irreversibili. La soglia è: "questa informazione cambia tutto quello che verrà dopo."
- Esempi validi: morte confermata di un personaggio principale, tradimento rivelato, svolta narrativa definitiva e irreversibile.
- Esempi non validi: momento di tensione, paura passeggera, suspense generica, sorpresa non narrativamente definitiva.

---

## 4. Standard Vocali (Asset)

Ogni voce in `/data/assets/voices/{voice_id}/` deve contenere:
- `ref.txt`: Testo esatto pronunciato nel campione audio.
- `ref_padded.wav`: Campione audio di riferimento (min 10-15s).

> **Il Bug della Collisione**: Se il testo da recitare è identico al testo in `ref.txt`, il modello può andare in loop o troncare l'audio. Non usare sample che contengano le parole della scena target.

---

## 5. Benchmarking Qualità (KPIs)

| Metrica | Target | Strumento |
| :--- | :--- | :--- |
| **Pitch Correlation (F0)** | > 0.60 | Similitudine melodica con reference umano (librosa). |
| **Energy Correlation (RMS)** | > 0.85 | Enfasi e sospiri coesi con intento narrativo (scipy). |
| **Speech Rate** | ~150 wpm | Cadenza narrativa naturale. |
| **Loudness finale** | -16 LUFS | Standard broadcast (normalizzazione Stage E). |

---

## 6. Vocabolario Qwen3 (Sound Design)

Per i campi `production_tags` in `SoundShoppingItem` e `PadRequest`.

Non usare gergo da studio di registrazione o nomi di synth hardware specifici. Qwen3 è addestrato su metadata di canzoni, non su manuali di sound engineering.

Vedi tabella completa in `technical-reference.md` § 7.

---

## 7. Standard Audiobook Master (Stage F)

Il file finale `.m4b` deve rispettare i seguenti parametri per garantire compatibilità universale e alta fedeltà.

| Parametro | Valore | Note |
| :--- | :--- | :--- |
| **Container** | **.m4b** | Supporto nativo per metadati capitoli e segnalibri. |
| **Codec** | **AAC (LC)** | Bilanciamento ottimale compressione/qualità. |
| **Bitrate** | **128 kbps** | Trasparente per la sola voce e AMB leggera. |
| **Sample Rate**| **44100 Hz** | Standard CD Quality. |
| **MIME Type** | **audio/mp4** | Mapping obbligatorio per player web/dashboard. |
| **Chapters** | **FUB (Fixed)** | Marcatori capitoli basati sulla Scene Grid (Stage C). |

### 7.1 Gestione delle Pause nel Master
A differenza del mix cinematico (Stage E), nel Master Audiobook le pause tra scene sono inserite forzatamente in fase di concatenazione basandosi sul valore `pause_after_ms` dello Stage C. Questo garantisce il ritmo della lettura "ad alta voce".

---

*Ultimo aggiornamento: 21 Aprile 2026 — v4.0: Integrato sistema Audiobook-Only, Stage F Mastering, standard M4B e Chaptering automatico.*
