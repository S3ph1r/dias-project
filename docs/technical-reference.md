# DIAS Technical Reference: Deployment, Security & Internals

Specifiche tecniche di basso livello per il mantenimento, il deployment e la sicurezza del sistema DIAS.

---

## 1. Sicurezza e Segreti (SOPS + Age)

DIAS utilizza il sistema NH-Mini standard basato su **SOPS** e **Age** per la gestione delle credenziali. La tendenza attuale è delegare le API key ad ARIA: DIAS non possiede API key Google dirette, ma invia task ad ARIA via Redis e ARIA gestisce le chiamate Gemini.

### Componenti Core
- `/home/Projects/NH-Mini/.sops.yaml`: Configurazione SOPS con chiave pubblica Age.
- `/home/Projects/NH-Mini/core/secure_credential_manager.py`: Manager delle credenziali.
- `secrets/*.enc.yaml`: File criptati contenenti i segreti.

### Esempio Recupero API Key
```python
from core.secure_credential_manager import get_service_credential
credential = get_service_credential("google_gemini", "main")
if credential:
    api_key = credential["api_key"]
```

---

## 2. Deployment e Monitoring (LXC 120 / PC 139)

### 2.1 Configurazione Redis Produzione
- **Maxmemory**: 2GB
- **Policy**: `allkeys-lru`
- **Persistence**: `save 60 10000` (Snapshot ogni minuto se ci sono molti cambiamenti)

### 2.2 Systemd Services
```ini
[Unit]
Description=DIAS Stage A - Text Ingester
After=network.target redis.service

[Service]
Type=simple
User=dias
ExecStart=/opt/dias/venv/bin/python src/stages/stage_a_text_ingester.py
Restart=always
```

### 2.3 Health Checks
- **Redis PING**: `redis-cli ping`
- **Queue Monitor**: `redis-cli llen dias:queue:1:ingestion`
- **Log Monitoring**: `tail -f /var/log/dias/stage_a.log`

---

## 3. Guida alla Messa in Produzione (Checklist)

- [ ] Sistema SOPS+Age configurato (chiave privata in `~/.age.key`).
- [ ] Redis Server installato e configurato su LXC 120.
- [ ] Variabili ambiente impostate (`MOCK_SERVICES=false`).
- [ ] Orchestrator e Workers registrati come servizi `systemd`.

---

## 4. Registro dei Prompt e Versioning

DIAS esternalizza ogni prompt in file YAML in `config/prompts/`. Questo permette di tracciare l'evoluzione qualitativa senza toccare il codice dei worker.

### 4.1 Stage 0: Intel
- **`stage_0/0.1_discovery_v1.2.yaml` (v1.2)**: Scansione strutturale (Capitoli/Dialoghi). Produce `fingerprint.json`.
- **`stage_0/0.2_intelligence_v1.0.yaml` (v1.0)**: DNA creativo. Produce `preproduction.json` con casting e palette sonore.

### 4.2 Stage B: Semantic Analyzer
- **`stage_b/b_semantic_v1.1.yaml` (v1.1)**: Dubbing Director. Estrae emozione macro, Subtext, `narrator_base_tone`, Mood Propagation. Mediterranean Prompting (istruzioni IT, output EN).

### 4.3 Stage B2: Sound Director
- **`stage_b2/b2_macro_v4.0.yaml` (v4.2)**: Musical Director. Produce PadRequest + PadArc con roadmap_item per ACE-Step. Regola di proporzionalità segmenti (durate proporzionali alla durata totale del capitolo). Pre-build rule (segmento `low` prima dei climax). Vocabolario Qwen3 obbligatorio.
- **`stage_b2/b2_micro_v4.0.yaml` (v4.1)**: Sound Designer monolitico. Paradigma BBC/Star Wars: AMB solo su cambio fisico (3-5s, max 1), SFX solo per momenti culminanti (0.3-2s), STING solo per rivelazioni irreversibili (2-4s, max 1).
- **`stage_b2/b2_micro_director_v1.0.yaml` (v1.0)**: Narrative Event Extractor. Output SoundEventScore in linguaggio naturale. Zero vocabolario ACE-Step. Separazione ruoli: il Director vede il testo, non la tecnica.
- **`stage_b2/b2_micro_engineer_v1.0.yaml` (v1.0)**: ACE-Step Spec Generator. Riceve SoundEventScore dal Director, produce production_tags in vocabolario Qwen3 → IntegratedCueSheet. Tabella di conversione vietato/ammesso integrata nel prompt.

### 4.4 Stage C: Scene Director
- **`stage_c/c_monastic_v2.3.yaml` (v2.3)**: Regia Fine. Segmentazione Emotional Beat, Tag Splitting, fidelità monastica al testo. Istruzioni TTS Qwen3 in prosa fisica.

---

## 5. Schemi JSON Dettagliati

### 5.1 MacroAnalysisResult (Stage B v1.1)
```json
{
  "analysis_it": "Sintesi narrativa in italiano",
  "primary_emotion": "joy|anger|sorrow|suspense|...",
  "secondary_emotion": "string",
  "subtext": "Intento nascosto o non detto nella scena",
  "narrative_arc": "Andamento della tensione nel blocco",
  "narrator_base_tone": "vocal description in english",
  "entities_speaking_styles": {
    "CHARACTER_NAME": "detailed vocal profile in english"
  }
}
```

### 5.2 SceneScript (Stage C v4.1)
```json
{
  "project_id": "TITOLO_UNIFICATO",
  "chunk_label": "chunk-001-micro-001",
  "scene_id": "chunk-001-micro-001-scene-001",
  "scene_label": "Narratore — cornice",
  "text_content": "Testo pulito, normalizzato e monastico.",
  "qwen3_instruct": "Acting instructions in natural english PROSE.",
  "speaker": "NomePersonaggio|Narratore",
  "pause_after_ms": 200,
  "has_dialogue": true,
  "tts_backend": "qwen3-tts-1.7b",
  "primary_emotion": "joy|suspense|...",
  "voice_direction": {
    "pace_factor": 1.1,
    "pitch_shift": 0,
    "energy": 0.6
  }
}
```

### 5.3 VoiceScene (Stage D Output v1.0)
```json
{
  "project_id": "TITOLO_UNIFICATO",
  "scene_id": "chunk-001-micro-001-scene-001",
  "voice_path": ".../stages/stage_d/output/scene-wav-name.wav",
  "voice_duration_seconds": 4.12,
  "voice_status": "completed",
  "pause_after_ms": 200,
  "speaker": "NomePersonaggio"
}
```

> Il campo `voice_duration_seconds` è il valore di verità per Stage E (Mixer). Le pause in `pause_after_ms` non sono incluse nel WAV, vanno "cucite" da Stage E.

### 5.4 MacroCue (Stage B2-Macro Output v4)
```json
{
  "project_id": "TITOLO_UNIFICATO",
  "chunk_label": "chunk-000",
  "music_justification": "Spiegazione scelta: palette, emozione, ritmo narrativo.",
  "pad": {
    "canonical_id": "pad_suspense_dark_orchestral_01",
    "production_prompt": "Descrizione leggibile del PAD",
    "production_tags": "dark orchestral, low strings, analog warmth, minor key",
    "negative_prompt": "epic, cinematic, generic ai, polished pop",
    "guidance_scale": 4.5,
    "inference_steps": 60,
    "is_leitmotif": false,
    "estimated_duration_s": 900.0,
    "pad_arc": [
      {
        "start_s": 0,
        "end_s": 120,
        "intensity": "low",
        "note": "apertura silenziosa",
        "roadmap_item": "[00:00 - [intro]. Sparse strings, low energy]"
      },
      {
        "start_s": 120,
        "end_s": 480,
        "intensity": "mid",
        "note": "narrazione centrale",
        "roadmap_item": "[02:00 - [verse]. Melody enters, moderate tension]"
      }
    ]
  }
}
```

### 5.5 SoundEventScore (Stage B2-Micro-Director Output v1.0)
```json
{
  "project_id": "TITOLO_UNIFICATO",
  "block_id": "chunk-000-micro-001",
  "pad_canonical_id": "pad_suspense_dark_orchestral_01",
  "asset_summary": ["AMB: urban street 4s", "SFX: door slam 0.5s"],
  "scenes": [
    {
      "scene_id": "chunk-000-micro-001-scene-001",
      "pad_behavior": "ducking",
      "pad_duck_depth": "medium",
      "ambient_event": {
        "trigger_description": "Il personaggio esce dall'edificio nella strada",
        "physical_description": "Strada urbana notturna con traffico lontano",
        "estimated_duration_s": 4.0,
        "target_scene_id": "chunk-000-micro-001-scene-001"
      },
      "sfx_event": null,
      "sting_event": null
    }
  ]
}
```

### 5.6 IntegratedCueSheet (Stage B2-Micro Output v4)
```json
{
  "project_id": "TITOLO_UNIFICATO",
  "block_id": "chunk-000-micro-001",
  "pad_canonical_id": "pad_suspense_dark_orchestral_01",
  "scenes_automation": [
    {
      "scene_id": "chunk-000-micro-001-scene-001",
      "pad_volume_automation": "ducking",
      "pad_duck_depth": "medium",
      "pad_fade_speed": "smooth",
      "amb_id": "amb_urban_street_night_01",
      "amb_offset_s": 0.0,
      "amb_duration_s": 4.0,
      "sfx_id": null,
      "sfx_timing": null,
      "sfx_offset_s": 0.0,
      "sting_id": null,
      "sting_timing": null,
      "reasoning": "Cambio ambientazione: interno → strada"
    }
  ],
  "sound_shopping_list": [
    {
      "type": "amb",
      "canonical_id": "amb_urban_street_night_01",
      "production_prompt": "Urban street at night, distant traffic",
      "production_tags": "urban environment, street noise, distant cars, night ambience",
      "negative_prompt": "music, melody, vocals, rhythm",
      "guidance_scale": 7.0,
      "duration_s": 4.0,
      "scene_id": "chunk-000-micro-001-scene-001"
    }
  ]
}
```

---

## 6. Architettura Mock/Real Switch

Il sistema implementa un pattern **zero-code-change** gestito dalla variabile `MOCK_SERVICES`:

```python
# src/common/redis_factory.py
def get_redis_client(logger: logging.Logger = None):
    mock_services = os.getenv('MOCK_SERVICES', 'true').lower() == 'true'
    if mock_services:
        return MockRedisClient(logger=logger).get_client()
    else:
        return DiasRedis(logger=logger)
```

---

## 7. Vocabolario Qwen3: Tabella Vietato/Ammesso

Per i campi `production_tags` di PAD, AMB, SFX, STING.

| VIETATO | USA QUESTO |
| :--- | :--- |
| spring reverb | analog reverb, vintage reverb |
| tape saturation | analog warmth, vintage recording |
| tape delay | vintage echo, analog delay |
| sub-bass drone | deep bass drone, low frequency bass |
| metallic percussive hits | metallic percussion, industrial hits |
| sidechain compression | (omettere) |
| wide stereo image | wide stereo, spacious |
| high-pass filter | (descrivere il risultato sonoro) |
| ARP 2600 | vintage analog synthesizer |
| Moog / Roland 808 / etc. | vintage synthesizer, analog synth |
| convolution reverb | room reverb, hall reverb |
| granular synthesis | textured, granular, ethereal |

---

## 8. PAD Arc Rules

La partitura emotiva (PadArc) deve rispettare queste regole:

1. **Copertura totale**: i segmenti devono coprire l'intera durata del capitolo senza gap né overlap.
2. **Proporzionalità**: la durata di ogni segmento è proporzionale alla lunghezza narrativa corrispondente. Non creare segmenti di 5 secondi in capitoli da 15 minuti.
3. **Pre-build rule**: inserire un segmento `low` immediatamente prima di ogni segmento `high` per creare tensione preparatoria. Non passare da `low` a `high` direttamente.
4. **roadmap_item**: ogni segmento deve avere un `roadmap_item` in EN nel formato `[MM:SS - [section_tag]. Description]`. Questo viene inviato ad ACE-Step come structural roadmap.

---

## 9. Metriche di Successo (Target)

| Area | Metrica | Target |
| :--- | :--- | :--- |
| **Voce** | MOS (Mean Opinion Score) | > 4.0 |
| **Voce** | Pitch Correlation (F0) vs reference | > 0.60 |
| **Voce** | Energy Correlation (RMS) vs reference | > 0.85 |
| **Voce** | Speech Rate | ~150 wpm |
| **Audio** | Loudness master finale | -16 LUFS |
| **Resilienza** | Recovery automatico dopo crash | < 30s |
| **Performance** | Processing time vs realtime | < 5x |

---

*Documento consolidato: 17 Aprile 2026 — aggiornato Stage B2 (Director/Engineer, modelli Pydantic), vocabolario Qwen3, PadArc rules, nuovi schemi JSON.*
