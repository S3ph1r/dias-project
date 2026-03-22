# 📋 DIAS Component Inventory

> **Documento di riferimento completo per la codebase DIAS**  
> *Aggiornare ad ogni nuovo sviluppo per mantenere traccia di tutti i componenti e funzionalità*

---

## 🎯 Panoramica Architettura

DIAS (Document Intelligence & Analysis System) è una pipeline di elaborazione documenti AI con architettura a stage.  
**Filosofia chiave**: Config-driven development con zero-code-change per switch tra ambienti mock/real.

---

## 📦 Componenti Core per Ambiente

### **🔄 Mock vs Real Switch Architecture**

| Componente | Mock Mode (`MOCK_SERVICES=true`) | Real Mode (`MOCK_SERVICES=false`) |
|------------|----------------------------------|-----------------------------------|
| Redis Client | `MockRedisClient` - In-memory | `DiasRedis` - Connessione reale |
| API Calls | Simulazioni locali | Chiamate reali esterne |
| Ambiente | Sviluppo offline | Produzione/Docker |

---

## 🗂️ Struttura Completa Codebase

### **`src/common/` - Componenti Condivisi**

#### **`base_stage.py`** - Foundation di Tutti gli Stage
- **Classe**: `BaseStage` (astratta)
- **Funzionalità**:
  - Gestione configurazione centralizzata
  - Setup logging automatico
  - Interfaccia standard `process()` → `run()`
  - Error handling e retry logic
  - Validazione input/output
- **Metodi chiave**:
  ```python
  process(data: Any) -> Any  # Da implementare nei figli
  run() -> bool              # Orchestrazione completa
- **Hardening 2026**: Implementata logica `push_to_head` (re-enqueue atomico) in caso di errore 429 per garantire zero perdite di messaggi e mantenimento della sequenzialità.
  ```

#### **`config.py`** - Gestione Configurazione
- **Funzionalità**:
  - Caricamento YAML multi-environment
  - Override da variabili ambiente
  - Validazione tipi con Pydantic
  - Supporto per `.env` files
- **Variabili chiave**:
  - `MOCK_SERVICES`: Switch mock/real
  - `REDIS_HOST`, `REDIS_PORT`: Connessione Redis
  - `ACTIVE_TTS_BACKEND`: Modello TTS predefinito (Qwen3, Fish)
  - `stage_b/c_prompt_path`: Path ai template YAML dei prompt

#### **`logging_setup.py`** - Logging Strutturato
- **Funzionalità**:
  - Log JSON strutturati per parsing automatico
  - Setup centralizzato per Orchestrator e Workers
- **Formato output**:
  ```json
  {
    "timestamp": "2024-01-01T12:00:00Z",
    "level": "INFO",
    "stage": "stage_a",
    "correlation_id": "uuid-123",
    "message": "Processo completato",
    "metrics": {"chunks_created": 32}
  }
  ```

#### **`redis_factory.py`** - Factory Pattern Chiave
- **🎯 FUNZIONALITÀ CHIAVE**: Zero-code-change mock/real switch
- **Logica selezione**:
  ```python
  def get_redis_client(logger=None):
      mock_services = os.getenv('MOCK_SERVICES', 'true').lower() == 'true'
      if mock_services:
          return MockRedisClient(logger=logger).get_client()  # Sviluppo
      else:
          return DiasRedis(logger=logger)                     # Produzione
  ```
- **Vantaggi**: Stesso codice per test e produzione

#### **`mock_redis.py`** - Redis In-Memory Completo
- **Funzionalità**:
  - Implementazione Redis completa in memoria
  - Supporto per: stringhe, liste, hash, code
  - Metodi specifici DIAS:
    ```python
    push_to_queue(queue_name, message) -> int      # Push con JSON serialize
    consume_from_queue(queue_name, count=1) -> list  # Pop con deserialize
    queue_length(queue_name) -> int
    get_stats() -> dict                            # Statistiche uso
    ```
- **Persistenza**: No (volatile) - per test e sviluppo
- **Performance**: O(1) per operazioni base

#### **`redis_client.py`** - Client Redis Produzione
- **Funzionalità**:
  - Connessione pool con retry automatico
  - Gestione errori e riconnessione
  - Supporto Redis Cluster e Sentinel
  - Configurazione via environment
- **Metodi DIAS**:
  ```python
  push_to_queue(queue_name, message) -> int
  push_to_head(queue_name, message) -> int      # Nuova 2026: rpush per retries prioritari
  queue_length(queue_name) -> int
  llen(queue_name) -> int
  ```

#### **`models.py`** - Modelli Dati Pydantic
- **Classi principali**:
  ```python
  class DocumentChunk(BaseModel):
      id: str
      content: str
      metadata: dict
      word_count: int
      char_count: int
      
  class ProcessingMetrics(BaseModel):
      stage_name: str
      start_time: datetime
      end_time: datetime
      items_processed: int
      errors: List[str]
  ```

---

### **`src/stages/` - Implementazioni Pipeline**

#### **`stage_a_text_ingester.py`** - Stage A: Ingestione Documenti
- **🎯 Scopo**: Convertire PDF → Chunk testuali intelligenti
- **Input**: Percorso file PDF
- **Output**: Chunk su Redis queue `stage_b_input`
- **Algoritmo chunking**:
  ```
  1. Estrai testo completo da PDF
  2. Tokenizza per parole
  3. Crea blocchi da ~2500 parole
  4. Applica overlap di ~500 parole
  5. Salva chunk con metadati
  ```
- **Metriche tracciate**:
  - Numero chunk creati
  - Dimensione media chunk (parole/caratteri)
  - Tempo elaborazione totale
  - Errori parsing PDF

#### **`stage_b_semantic_analyzer.py`** - Stage B: Analisi Semantica
- **🎯 Scopo**: Analisi AI dei chunk con Gemini
- **Input**: Chunk da Redis queue `dias:queue:2:semantic`
- **Output**: Analisi su disco (`stage_b/output/`) + task per Stage C.
- **Funzionalità**:
  - Analisi sentiment e topic extraction.
  - Generazione macro-analisi per la regia.
- **Rate limiting**: Gestione quota Gemini API (Pacing 60s + Daily Limit 20 RPD).
- **Prompting Esternalizzato**: Carica il template da `config/prompts/stage_b/v1.0_base.yaml`.

#### **`stage_c_scene_director.py`** - Stage C: Regia e Segmentazione
- **🎯 Scopo**: Trasformare chunk in scene recitabili per Qwen3.
- **Input**: Analisi da Redis queue `dias:queue:2:semantic`.
- **Output**: Master JSON + Task su `dias:queue:4:voice`.
- **Funzionalità**:
  - Segmentazione basata su emotional beats.
  - Generazione `qwen3_instruct` (Tone, Rhythm, Attitude).
  - **Dinamismo Cinematico (v1.4)**: Usa logic "Anchor + Variation" per stabilizzare il TTS.
  - **Prompting Esternalizzato**: Carica il template da `config/prompts/stage_c/v1.4_contextual.yaml`.
  - Normalizzazione fonetica del testo.

#### **`gemini_rate_limiter.py`** - Rate Limiter Globale su Redis
- **Pacing**: 60s (Configurabile in `dias.yaml`).
  - **Daily Monitor**: Hard stop a quota RPD raggiunta (es. 20) per evitare lockout Google.
  - **Sincronizzazione Redis**: Utilizza le chiavi `aria:rate_limit:google:*` per garantire il pacing tra Stage B e Stage C indipendenti.
  - **Lockout 429**: Auto-blocco globale di 15 minuti in caso di errore quota.
  - Sostituisce i lock in memoria RAM, rendendo l'architettura sicura in multiprocesso.

---

### **`config/prompts/` - Asset di Regia (LLM Templates)**

#### **`stage_b/v1.0_base.yaml`**
- **Scopo**: Template per analisi semantica e macro-emotiva.
- **Strategia**: Mediterranean Prompting (Istruzioni in IT, output tecnico in EN).

#### **`stage_c/v1.4_contextual.yaml`**
- **Scopo**: Regia fine e segmentazione emotional beats.
- **Logica**: **Anchor + Variation**. Utilizza context Stage B per istruzioni vocali fisiche e ritmiche.

---

### **`scripts/` - Orchestrazione e Utility**

#### **`orchestrator.py`** - Motore della Pipeline Serial-Serial
- **Scopo**: Gestione "Brain" della pipeline end-to-end.
- **Logica**: Avvia uno stadio, aspetta lo svuotamento della coda e la persistenza dei file, poi passa al successivo.
- **Resume**: Capacità nativa di ripartenza analizzando lo stato del disco.

#### **`batch_process_b_c.py`** - Vecchio motore Batch
- **Stato**: **OBSOLETO** - Sostituito da `orchestrator.py`.

#### **`scripts/archive_manager.py`** - Manutenzione
- **Scopo**: Archiviazione script obsoleti e cleanup directory `output/`.

---

| Componente | Path | Stato | Descrizione Breve |
|------------|------|-------|-------------------|
| Base Stage | `src/common/base_stage.py` | ✅ Completo | Foundation per tutti gli stage |
| Stage A | `src/stages/stage_a_text_ingester.py` | ✅ Completo | PDF → Chunk testuali |
| Stage B | `src/stages/stage_b_semantic_analyzer.py` | ✅ Completo | Analisi AI con Gemini |
| Stage C | `src/stages/stage_c_scene_director.py` | ✅ Completo | Master JSON + Regia Qwen3 |
| Rate Limiter | `src/stages/gemini_rate_limiter.py` | ✅ Completo | Gestione quota + Lockout configurabile |
| Stage D | `src/api/main.py` (Proxy) | ✅ Completo | ARIA Voice Queue Integration |

*Legenda*: ✅ Completo | 🚧 In Sviluppo | 📋 Pianificato | ❌ Non Iniziato