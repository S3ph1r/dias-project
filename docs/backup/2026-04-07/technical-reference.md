# 🛠️ DIAS Technical Reference: Deployment, Security & Internals

Questo documento raccoglie le specifiche tecniche di basso livello per il mantenimento, il deployment e la sicurezza del sistema DIAS.

---

## 1. Sicurezza e Segreti (SOPS + Age)

DIAS utilizza il sistema NH-Mini standard basato su **SOPS** e **Age** per la gestione delle credenziali (anche se la tendenza attuale è delegare le API ad ARIA).

### Componenti Core
- `/home/Projects/NH-Mini/.sops.yaml`: Configurazione SOPS con chiave pubblica Age.
- `/home/Projects/NH-Mini/core/secure_credential_manager.py`: Manager delle credenziali.
- `secrets/*.enc.yaml`: File criptati contenenti i segreti.

### Esempio Recupero API Key (Stage B legacy)
```python
from core.secure_credential_manager import get_service_credential
credential = get_service_credential("google_gemini", "main")
if credential:
    api_key = credential["api_key"]
```

---

## 2. Deployment e Monitoring (LXC 120 / PC 139)

### 2.1 Configurazione Redis Produzione
Per garantire le performance in produzione (non-mock):
- **Maxmemory**: 2GB
- **Policy**: `allkeys-lru`
- **Persistence**: `save 60 10000` (Snapshot ogni minuto se ci sono molti cambiamenti).

### 2.2 Systemd Services
Ogni stadio della pipeline può essere isolato come servizio Linux:
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
- [ ] API Key Google Gemini salvata nello storage sicuro.
- [ ] Redis Server installato e configurato su LXC 120.
- [ ] Variabili ambiente impostate (`MOCK_SERVICES=false`).
- [ ] Orchestrator e Workers registrati come servizi `systemd`.

---

## 4. Registro dei Prompt e Versioning (Qualità Narrativa)

DIAS esternalizza ogni prompt in file YAML in `config/prompts/`. Questo permette di tracciare l'evoluzione qualitativa senza toccare il codice dei worker.

### 4.1 Stage 0: Intelligence & Discovery
- **`stage_0/discovery.yaml` (v1.0)**: Estrazione della struttura fisica (Capitoli/Titoli). Focus su integrità della mappatura 1:1.
- **`stage_0/intelligence.yaml` (v1.0)**: Analisi letteraria profonda. Genera il "Fingerprint" con casting esaustivo e proposte di palette sonore.

### 4.2 Stage B: Semantic Analyzer
- **`stage_b/v1.0_base.yaml` (v1.0)**: Estrazione di valence/arousal/tension. Identifica gli "audio cues" e definisce lo `speaking_style` (in inglese) per i personaggi.

### 4.3 Stage C: Scene Director (Regia Audio)
- **`stage_c/v1.4_contextual.yaml` (v1.4)**: Il prompt più critico. Trasforma il testo in micro-scene atomiche.
- **Logica Self-Contained**: Ogni istruzione `qwen3_instruct` è progettata per essere auto-sufficiente (pressione acustica, timbro, ritmo), poiché Qwen3-TTS non ha memoria tra i task.
- **Phonetics**: Gestisce la normalizzazione dei numeri e il respelling fonetico.

---

## 5. Schemi JSON Dettagliati (v4.0 Spec)

### 5.1 MacroAnalysisResult (Stage B)
```json
{
  "type": "object",
  "required": ["job_id", "block_analysis"],
  "properties": {
    "job_id": {"type": "string", "format": "uuid"},
    "block_analysis": {
      "type": "object",
      "required": ["valence", "arousal", "tension", "primary_emotion"],
      "properties": {
        "valence": {"type": "number", "minimum": 0, "maximum": 1},
        "arousal": {"type": "number", "minimum": 0, "maximum": 1},
        "tension": {"type": "number", "minimum": 0, "maximum": 1},
        "primary_emotion": {"enum": ["neutral", "joy", "sadness", "anger", "fear", "suspense", "curiosity"]},
        "setting": {"type": "string"},
        "audio_cues": {"type": "array", "items": {"type": "string"}}
      }
    }
  }
}
```

### 5.2 SceneScript (Stage C Audio Script)
```json
{
  "type": "object",
  "required": ["scene_id", "text_content", "voice_direction", "audio_layers"],
  "properties": {
    "scene_id": {"type": "string", "pattern": "^scene-ch[0-9]+-[0-9]+$"},
    "text_content": {"type": "string", "minLength": 50},
    "voice_direction": {
      "type": "object",
      "required": ["emotion_description", "pace_factor"],
      "properties": {
        "emotion_description": {"type": "string"},
        "pace_factor": {"type": "number", "minimum": 0.5, "maximum": 1.5},
        "pitch_shift": {"type": "integer", "minimum": -5, "maximum": 5}
      }
    },
    "audio_layers": {
      "type": "object",
      "properties": {
        "ambient": {"type": "object"},
        "music": {"type": "object", "required": ["prompt_for_musicgen"]},
        "spot_effects": {"type": "array"}
      }
    }
  }
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

**Vantaggi**:
- Sviluppo offline garantito.
- Commutazione istantanea senza riavviare il nodo.
- Test suite eseguibile interamente in RAM (MockRedis).

---

## 7. Metriche di Successo Globali (Target)

### Performance
- **Processing Time**: < 5x realtime (un libro da 10 ore prodotto in 2 ore).
- **Throughput**: Supporto a 10+ libri/giorno in parallelo.
- **Resource Usage**: < 16GB RAM sul Brain, < 8GB VRAM sul Worker.

### Qualità e Affidabilità
- **Voice Expressivity**: MOS (Mean Opinion Score) target > 4.0.
- **Fault Tolerance**: Recovery automatico < 30s dopo crash.
- **Loudness**: Standard broadcast -16 LUFS per il master finale.

---

*Documento consolidato il 27 Marzo 2026 dal Roadmap e SOPS integration guide.*
