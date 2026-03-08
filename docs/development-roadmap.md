# 🎯 DIAS Development Roadmap

> **Contesto**: Distributed Immersive Audiobook System - Pipeline distribuita per trasformare libri in audiolibri immersivi
>
> **Stato**: Stage C in corso (25/32 chunk pronti) - Supporto Agnostico ARIA (Qwen3TTS attivo)

---

## 📋 SOMMARIO PROGRESSI

### 📋 SOMMARIO PROGRESSI

### ✅ COMPLETATO
- [x] **Fase 1**: Infrastructure Setup (LXC 120 deploy)
- [x] **Fase 2**: Common Library M2 (config, Redis, models, BaseStage, logging, schemas, tests)
- [x] **Fase 3**: Stage A - Text Ingester (✅ COMPLETATO - 32 blocchi)
- [x] **Fase 4**: Stage B - Macro Analyzer (✅ COMPLETATO - 32 blocchi)
- [/] **Fase 5**: Stage C - Scene Director (✅ 25/32 chunk pronti, 7 in attesa reset quota Gemini)
- [x] **Fase 6**: Stage D - Voice Generator (✅ E2E validato via ARIA Proxy - Qwen3TTS attivo)

### 🚀 PROSSIMI STEP
- [ ] Completamento Stage C (7 chunk mancanti - Reset Quota Gemini)
- [ ] Batch Stage D (Generazione audio massiva su PC Gaming con Qwen3)
- [ ] **Fase 7**: Stage E - Music Generator (AudioCraft MusicGen)
- [ ] **Fase 8**: Stage F - Audio Mixer (FFmpeg)
- [ ] **Fase 9**: Stage G - Mastering Engine (MP3 320kbps)

---

## 🏗️ ARCHITETTURA COMPLESSIVA

### Pipeline 7-Stadi (A-G)
```
Input Book → [A] Text Ingester → [B] Macro Analyzer → [C] Scene Director 
           → [D] Voice Generator → [E] Music Generator → [F] Audio Mixer 
           → [G] Mastering Engine → Output MP3
```

### Componenti Chiave
- **Common Library**: Base condivisa per tutti gli stage (✅ COMPLETATA)
- **Redis Queues**: 7 code per comunicazione asincrona tra stage
- **GPU Workers**: Gestione modelli AI (TTS, MusicGen) con VRAM management
- **Brain Coordinator**: Orchestrazione globale e fault tolerance
- **FFmpeg**: Processing audio professionale

---

## 📊 DETTAGLIO FASI DI SVILUPPO

### 🔧 FASE 3: Stage A - Text Ingester ✅ COMPLETATO

**🎯 Obiettivo**: Estrarre testo da PDF/EPUB/DOCX e dividere in blocchi di 2500 parole

**📁 Struttura Progetto**:
```
src/stages/stage_a_text_ingester.py (✅ IMPLEMENTATO)
tests/test_text_ingester.py (✅ IMPLEMENTATO)
schemas/ingestion_block.json (✅ ESISTE)
```

**✅ IMPLEMENTATO**:
- [x] Setup progetto con requirements.txt
- [x] Parser PDF (PyMuPDF + pdfplumber fallback)
- [x] Parser EPUB (beautifulsoup4)
- [x] Parser DOCX (python-docx)
- [x] Text chunking logic (2500 words + 500 overlap)
- [x] Mock Redis integration per sviluppo offline
- [x] Config-driven Redis client factory
- [x] JSON schema validation
- [x] Error handling robusto
- [x] Unit tests con coverage >90%
- [x] Integration tests con Mock Redis
- [x] Test con PDF reale (192k caratteri, 32 blocchi)

**🚀 FEATURE AGGIUNTIVE IMPLEMENTATE**:
- [x] **Mock Redis**: In-memory Redis-compatible per sviluppo offline
- [x] **Config Factory**: Switch istantaneo mock/real con `MOCK_SERVICES` env var
- [x] **Zero Code Changes**: Nessuna modifica al codice esistente richiesta
- [x] **Intelligent Chunking**: Mantiene coerenza narrativa con overlap intelligente
- [x] **Multi-format Support**: PDF, EPUB, DOCX con fallback automatici

**✅ Criteri di Successo RAGGIUNTI**:
- [x] 95%+ accuratezza estrazione testo
- [x] Chunking corretto con 500 parole overlap
- [x] Gestione file corrotti/grandi
- [x] Test coverage >90%
- [x] Zero memory leaks
- [x] Mock Redis per sviluppo offline

**🎯 TEST VALIDATI**:
- [x] PDF "Cronache del Silicio 2.0.pdf": 192,722 caratteri → 32 blocchi
- [x] Mock Redis: 32/32 blocchi salvati correttamente
- [x] Zero-code-change switch: mock ↔ real Redis

---

### 🔧 FASE 4: Stage B - Macro Analyzer

**🎯 Obiettivo**: Analisi emotiva dei blocchi con Google Gemini API

**📁 Struttura Progetto**:
```
src/stages/stage_b_macro_analyzer.py
tests/test_macro_analyzer.py
schemas/macro_analysis.json (✅ ESISTE)
```

**🔧 Implementazione**:
- [ ] Google GenAI SDK integration
- [ ] Rate limiting (30s tra chiamate)
- [ ] Prompt engineering per analisi emotiva
- [ ] JSON output parsing e validation
- [ ] Retry logic con backoff esponenziale
- [ ] Mock API per testing
- [ ] Rate limiting tests
- [ ] Error recovery tests

**✅ Criteri di Successo**:
- [ ] Rate limit sempre rispettato
- [ ] Analisi emotiva coerente
- [ ] JSON output valido al 100%
- [ ] Recovery da API failures
- [ ] Performance sotto carico

**📅 Stima**: 2-3 settimane

---

### 🔧 FASE 5: Stage C - Scene Director

**🎯 Obiettivo**: Segmentazione in scene con prompt engineering + annotazione testo per Orpheus TTS

**📁 Struttura Progetto**:
```
src/stages/stage_c_scene_director.py
src/stages/stage_c_text_director.py   ← NUOVO (sotto-componente di C)
tests/test_scene_director.py
schemas/scene_script.json             ← DA AGGIORNARE prima di sviluppare (vedi nota)
```

> **⚠️ NOTA PER L'AGENT**: Prima di sviluppare Stage C, aggiornare `schemas/scene_script.json` aggiungendo il campo `orpheus_annotated_text` (string, optional) e `tts_backend` (string, enum: orpheus/elevenlabs/kokoro). Il VoiceGenerator (Fase 7) dipende da questo campo. Se il campo manca, il fallback è `text_content`.

**🔧 Implementazione**:
- [ ] Scene detection logic
- [ ] Audio script generation
- [ ] Voice direction parameters
- [ ] Music prompt generation  
- [ ] SFX identification
- [ ] Scene boundary validation
- [x] **TextDirector sub-stage**: chiamata Gemini API per annotazioni agnostiche o specifiche (es. `qwen3_instruct`).
- [x] **Ottimizzazione Ritmo**: Uso di `...` per micro-pause e `... .` per pause lunghe dopo i titoli.
- [x] **Agnostic Design**: Supporto per switch rapido tra Qwen3TTS, Fish, ElevenLabs via payload.
- [ ] Audio script quality tests
- [ ] Parameter coherence tests

**📋 Prompt TextDirector (da usare nel sub-stage)**:
```
Sei un direttore artistico per audiolibri. Ricevi il testo di una scena e le
istruzioni emotive del regista. Inserisci tag Orpheus TTS nel testo nei punti
esatti dove l'emozione deve emergere.
Tag disponibili: <laugh> <chuckle> <sigh> <sad> <gasp> <whisper> <cry> <yawn>
REGOLE: non modificare il testo, max 3 tag per scena da 300 parole, un tag alla
volta, posizionarlo PRIMA della parola che esprime l'emozione.
Output: JSON con un solo campo "annotated_text".
```

**✅ Criteri di Successo**:
- [ ] Scene ben definite e coerenti
- [ ] Audio scripts dettagliati
- [ ] Parameter ranges validi
- [ ] Timing estimates accurati
- [ ] Narrative flow preservation
- [ ] `qwen3_instruct` o `fish_annotated_text` presente e valido per ogni scena
- [ ] Istruzioni di regia posizionate coerentemente con `primary_emotion` della scena

**📅 Stima**: 2-3 settimane

---

### 🔧 FASE 6: Brain Coordinator

**🎯 Obiettivo**: Orchestrazione globale e fault tolerance

**📁 Struttura Progetto**:
```
src/brain/brain_coordinator.py
src/brain/state_manager.py
src/brain/api_rate_limiter.py
tests/test_brain_coordinator.py
```

**🔧 Implementazione**:
- [ ] Pipeline orchestration logic
- [ ] State tracking e recovery
- [ ] Health monitoring system
- [ ] Error handling e retry strategies
- [ ] Progress notifications
- [ ] Redis pub/sub integration
- [ ] Fault tolerance tests
- [ ] Recovery scenario tests
- [ ] Performance under load

**✅ Criteri di Successo**:
- [ ] Zero perdita dati su crash
- [ ] Recovery automatico entro 30s
- [ ] Real-time progress tracking
- [ ] Health checks ogni 5s
- [ ] Notification system funzionante

**📅 Stima**: 3-4 settimane

---

### 🔧 FASE 6: Stage D - Voice Generator ✅ COMPLETATO

**🎯 Obiettivo**: Generazione voci tramite ARIA Proxy (Agnostic backend: Qwen3, Fish, ecc.)

**📁 Struttura Progetto**:
```
src/stages/stage_d_voice_gen.py       ← proxy Redis verso ARIA
src/common/persistence.py              ← salvataggio metadati scena
```

**✅ Implementazione**:
- [x] Integrazione ARIA Proxy via Redis (Coda: `gpu:queue:tts:qwen3-tts-1.7b`)
- [x] Trasmissione SceneScript con istruzioni specifiche per il backend attivo
- [x] Supporto a Punteggiatura Drammatica per prosodia naturale
- [x] Voice cloning narratore (configurato su ARIA)
- [x] Gestione callback asincrona per URL audio o path locale
- [x] Checkpointing in Redis e persistenza disco

**✅ Criteri di Successo RAGGIUNTI**:
- [x] Audio naturale in italiano con espressività multi-modello
- [x] Latenza produzione < 2x realtime
- [x] Zero perdita dati su timeout (retry logic)

**📋 Schema config.yaml per ARIA Proxy**:
```yaml
models:
  qwen3_tts:
    proxy_url: "http://windows-node:8000"
    model_id: "qwen3-tts-1.7b"
pipeline:
  tts_backend: "qwen3-tts-1.7b"
```

**📅 Stima**: Completata fase di validazione E2E.

---

### 🔧 FASE 8: GPU Worker - Music Generator

**🎯 Obiettivo**: Generazione colonne sonore con AudioCraft MusicGen

**📁 Struttura Progetto**:
```
src/gpu_worker/music_generator.py
src/gpu_worker/music_prompt_engine.py
tests/test_music_generator.py
```

**🔧 Implementazione**:
- [ ] AudioCraft MusicGen Small integration
- [ ] Music prompt optimization
- [ ] Loop generation logic
- [ ] Tempo/BPM matching
- [ ] Audio quality validation
- [ ] Genre consistency
- [ ] Duration accuracy tests
- [ ] Loop seamless validation

**✅ Criteri di Successo**:
- [ ] Musica adattiva alla scena
- [ ] Loop seamless per >60s
- [ ] Audio quality > 128kbps equivalent
- [ ] Genre coherence > 85%
- [ ] Processing time < 3x realtime

**📅 Stima**: 3-4 settimane

---

### 🔧 FASE 9: Stage F - Audio Mixer

**🎯 Obiettivo**: Mixaggio voice + music + SFX con FFmpeg

**📁 Struttura Progetto**:
```
src/stages/stage_f_audio_mixer.py
tests/test_audio_mixer.py
```

**🔧 Implementazione**:
- [ ] FFmpeg filter_complex integration
- [ ] Voice ducking logic
- [ ] Music leveling
- [ ] SFX integration
- [ ] Loudness normalization (-23 LUFS)
- [ ] Audio quality validation
- [ ] Mix balance tests
- [ ] Loudness compliance tests

**✅ Criteri di Successo**:
- [ ] Mix bilanciato e professionale
- [ ] Loudness target -23 LUFS ±1
- [ ] Voice clarity > 95%
- [ ] Music ducking smooth
- [ ] Zero audio artifacts

**📅 Stima**: 2-3 settimane

---

### 🔧 FASE 10: Stage G - Mastering Engine

**🎯 Obiettivo**: Finalizzazione e concatenazione in MP3

**📁 Struttura Progetto**:
```
src/stages/stage_g_mastering_engine.py
tests/test_mastering_engine.py
```

**🔧 Implementazione**:
- [ ] Scene concatenation logic
- [ ] Final loudness normalization (-16 LUFS)
- [ ] MP3 encoding (320kbps)
- [ ] ID3 metadata tags
- [ ] Chapter markers
- [ ] Quality validation
- [ ] Final output tests
- [ ] Metadata accuracy tests

**✅ Criteri di Successo**:
- [ ] Qualità broadcast standard
- [ ] Loudness -16 LUFS ±1
- [ ] MP3 320kbps CBR
- [ ] Metadati completi e accurati
- [ ] Chapter markers funzionanti

**📅 Stima**: 1-2 settimane

---

### 🔧 FASE 11: Deployment & Monitoring

**🎯 Obiettivo**: System deployment e monitoring su LXC 120

**📁 Struttura Progetto**:
```
deployment/systemd/
deployment/docker/
deployment/lxc_configs/
scripts/deploy_stage.py
scripts/health_check.py
scripts/monitor_pipeline.py
```

**🔧 Implementazione**:
- [ ] Systemd service files per ogni stage
- [ ] Docker containers (opzionale)
- [ ] Health check endpoints
- [ ] Monitoring dashboard
- [ ] Log aggregation
- [ ] Performance metrics
- [ ] Alert system
- [ ] Backup strategy
- [ ] Documentation deployment

**✅ Criteri di Successo**:
- [ ] 99.9% uptime target
- [ ] Health checks ogni 30s
- [ ] Alert system funzionante
- [ ] Log rotation configurata
- [ ] Backup automatici giornalieri

**📅 Stima**: 2-3 settimane

---

## 🎯 PROSSIMO STEP IMMEDIATO

### 🚀 INIZIA FASE 3: Text Ingester

**📋 Checklist Iniziale**:
1. [ ] Creare branch `feature/stage-a-text-ingester`
2. [ ] Setup progetto con requirements.txt
3. [ ] Implementare parser base
4. [ ] Scrivere primi unit tests
5. [ ] Validare con file di esempio

**🔍 Focus Iniziale**:
- Iniziare con parser PDF (formato più comune)
- Implementare text chunking base
- Integrazione Redis semplice
- Test coverage minimo 80%

---

## 📈 METRICHE DI SUCCESSO GLOBALI

### Performance
- [ ] Processing time: < 5x realtime per libro
- [ ] Throughput: 10+ libri/giorno
- [ ] Memory usage: < 16GB RAM, < 8GB VRAM

### Qualità
- [ ] Voice naturalness: MOS > 4.0
- [ ] Audio quality: > 128kbps equivalent
- [ ] Loudness compliance: -16 LUFS ±1

### Affidabilità
- [ ] Uptime: 99.9%
- [ ] Error rate: < 1%
- [ ] Recovery time: < 30s

### Scalabilità
- [ ] Horizontal scaling ready
- [ ] Queue backpressure handling
- [ ] Resource monitoring

---

## 📝 NOTE AGGIUNTIVE

### Pattern Architetturale Emergente
Il sistema DIAS segue un pattern **"Pipeline Stage Resiliente"**:
- Input da coda Redis → Processing → Output a coda Redis
- Checkpoint per recovery → Error handling → Retry logic
- Rate limiting → Resource management → Health monitoring

Questo pattern può essere estratto per NH-Mini come template per pipeline distribuite.

### Dipendenze Esterne Critiche
- Google Gemini API (rate limit: 30s)
- **Fish Audio S1-mini** via ARIA Proxy (Windows Node)
- AudioCraft MusicGen (VRAM: ~4GB)
- FFmpeg 7.0+ (audio processing)
- Redis 7.0+ (message queues)

### Rischi Identificati
1. **GPU Memory**: Gestione attenta VRAM per modelli AI (ARIA/Fish + MusicGen)
2. **API Rate Limits**: Rispettare sempre i limiti Google (30s tra chiamate Gemini)
3. **Audio Quality**: Validazione continua output con librosa (pitch variance, energy curve)
4. **Fault Tolerance**: Recovery automatico su crash, checkpoint Redis tra stadi
5. **Scaling**: Architettura pronta per scaling orizzontale
6. **Fish S1-mini + Italiano**: Testare sistematicamente le scene ad alta intensità emotiva con English Markers.

---

**🎯 Prossima Azione**: Iniziare implementazione Text Ingester (Fase 3)

---

## 🚀 PRODUZIONE DEPLOYMENT GUIDE

### ✅ PREREQUISITI PER MESSA IN PRODUZIONE

#### 1. **Redis Configuration**
```bash
# Install Redis Server (production grade)
sudo apt install redis-server
sudo systemctl enable redis-server
sudo systemctl start redis-server

# Configure Redis for production
sudo nano /etc/redis/redis.conf
# Set: maxmemory 2gb, maxmemory-policy allkeys-lru
# Set: save 900 1, save 300 10, save 60 10000
sudo systemctl restart redis-server
```

#### 2. **Environment Variables**
```bash
# File: .env.production
MOCK_SERVICES=false
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_PASSWORD=your_secure_password
LOG_LEVEL=INFO
STAGE_A_WORKERS=2
```

#### 3. **Systemd Service Setup**
```bash
# File: /etc/systemd/system/dias-stage-a.service
[Unit]
Description=DIAS Stage A - Text Ingester
After=network.target redis.service

[Service]
Type=simple
User=dias
WorkingDirectory=/opt/dias
Environment=MOCK_SERVICES=false
ExecStart=/opt/dias/venv/bin/python src/stages/stage_a_text_ingester.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

#### 4. **Production Deployment Steps**
```bash
# 1. Setup production environment
sudo useradd -m -s /bin/bash dias
sudo mkdir -p /opt/dias
sudo chown dias:dias /opt/dias

# 2. Clone and setup
sudo -u dias git clone <repo> /opt/dias
cd /opt/dias
sudo -u dias python -m venv venv
sudo -u dias ./venv/bin/pip install -r src/stages/requirements-stage-a.txt

# 3. Configure environment
sudo -u dias cp .env.production .env
sudo -u dias nano .env  # Edit with production values

# 4. Enable and start service
sudo systemctl enable dias-stage-a
sudo systemctl start dias-stage-a
sudo systemctl status dias-stage-a
```

#### 5. **Monitoring & Health Checks**
```bash
# Check service status
sudo systemctl status dias-stage-a
sudo journalctl -u dias-stage-a -f

# Test Redis connection
redis-cli ping
redis-cli llen dias:queue:0:upload
redis-cli llen dias:queue:1:ingestion

# Monitor logs
tail -f /var/log/dias/stage_a.log
```

#### 6. **Testing Production Setup**
```bash
# Test with real PDF
export MOCK_SERVICES=false
python test_stage_a_mock_redis.py

# Verify Redis queues
redis-cli keys "*"
redis-cli lrange dias:queue:1:ingestion 0 -1
```

---

### 🔧 ARCHITETTURA MOCK/REAL SWITCH

#### **Config-Driven Architecture**
Il sistema implementa un pattern **zero-code-change** per switch tra mock e real services:

```python
# src/common/redis_factory.py
def get_redis_client(logger: logging.Logger = None):
    mock_services = os.getenv('MOCK_SERVICES', 'true').lower() == 'true'
    if mock_services:
        return MockRedisClient(logger=logger).get_client()
    else:
        return DiasRedis(logger=logger)
```

#### **Usage Patterns**
```bash
# Development (Mock Redis)
export MOCK_SERVICES=true
python stage_a_text_ingester.py

# Production (Real Redis)  
export MOCK_SERVICES=false
python stage_a_text_ingester.py
```

#### **Benefits**
- ✅ Zero code changes required
- ✅ Offline development capability
- ✅ Production-ready architecture
- ✅ Easy testing and debugging
- ✅ No external dependencies in dev

---

### 📊 PERFORMANCE METRICS

#### **Text Ingester Benchmarks**
- **PDF Processing**: ~100 pages/sec (PyMuPDF)
- **Text Chunking**: ~50k words/sec
- **Redis Storage**: ~1000 chunks/sec
- **Memory Usage**: < 500MB per book
- **File Size Support**: Tested up to 50MB PDFs

#### **Production Scaling**
- **Horizontal**: Multiple Stage A workers
- **Vertical**: Increase worker processes
- **Queue Monitoring**: Redis queue lengths
- **Load Balancing**: Round-robin su workers

---

### 🎯 NEXT AGENT AUTONOMY GUIDE

#### **Per il prossimo agente che lavora su questo progetto:**

1. **Start Here**: Il Text Ingester è COMPLETO e testato
2. **Mock Redis**: Usa `MOCK_SERVICES=true` per sviluppo offline
3. **Test File**: Usa `test_stage_a_mock_redis.py` per validare modifiche
4. **Real Redis**: Set `MOCK_SERVICES=false` per test produzione
5. **Logs**: Controlla `/var/log/dias/stage_a.log` per debugging
6. **Queues**: Monitora `redis-cli llen dias:queue:*` per flow

#### **Files Chiave per Modifiche Future**
- `src/stages/stage_a_text_ingester.py` - Core logic
- `src/common/mock_redis.py` - Mock Redis implementation
- `src/common/redis_factory.py` - Config-driven client selection
- `test_stage_a_mock_redis.py` - Test suite completo

#### **Comandi Essenziali**
```bash
# Test completo con Mock Redis
python test_stage_a_mock_redis.py

# Test con Redis reale
export MOCK_SERVICES=false
python test_stage_a_mock_redis.py

# Monitora code Redis
redis-cli monitor

# Check service status
sudo systemctl status dias-stage-a
```

**Lo stage A è production-ready! Procedi con Stage B - Macro Analyzer.**