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
  - `GEMINI_API_KEY`: Chiave API Google

#### **`logging_setup.py`** - Logging Strutturato
- **Funzionalità**:
  - Log JSON strutturati per parsing automatico
  - Livelli configurabili per componente
  - Rotazione files e gestione dimensione
  - Correlation ID per tracciamento richieste
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
  consume_from_queue(queue_name, count=1) -> list
  queue_length(queue_name) -> int
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
- **Input**: Chunk da Redis queue `stage_b_input`
- **Output**: Analisi su Redis queue `stage_c_input`
- **Funzionalità**:
  - Analisi sentiment e topic extraction
  - Entity recognition e linking
  - Riepilogo automatico per chunk
  - Punteggio rilevanza contenuto
- **Rate limiting**: Gestione quota Gemini API

#### **`gemini_rate_limiter.py`** - Rate Limiter Globale e Lockout
- **Funzionalità**:
  - Gestione quota Gemini (30s cooldown).
  - **Lockout 429**: Auto-blocco di 10 minuti in caso di errore quota.
  - Singleton pattern condiviso tra tutti gli stage.
  - Persistenza stato lockout (opzionale via Redis).

---

### **`scripts/` - Orchestrazione e Utility**

#### **`batch_process_b_c.py`** - Motore del Batch Processing
- **Scopo**: Esecuzione sequenziale di Stage B e C su tutti i chunk.
- **Logica**: Gestisce lo skipping e il rate limiting garantendo la produzione dei Master JSON.

#### **`scripts/archive_manager.py`** - Manutenzione
- **Scopo**: Archiviazione script obsoleti e cleanup directory `output/`.

---

| Componente | Path | Stato | Descrizione Breve |
|------------|------|-------|-------------------|
| Base Stage | `src/common/base_stage.py` | ✅ Completo | Foundation per tutti gli stage |
| Stage A | `src/stages/stage_a_text_ingester.py` | ✅ Completo | PDF → Chunk testuali |
| Stage B | `src/stages/stage_b_semantic_analyzer.py` | ✅ Completo | Analisi AI con Gemini |
| Stage C | `src/stages/stage_c_scene_director.py` | ✅ Progress | Master JSON + Regia Qwen3 |
| Rate Limiter | `src/stages/gemini_rate_limiter.py` | ✅ Completo | Gestione quota + Lockout 10m |
| Stage D | `src/stages/stage_d_voice_gen.py` | ✅ Completo | ARIA Proxy Integration |

*Legenda*: ✅ Completo | 🚧 In Sviluppo | 📋 Pianificato | ❌ Non Iniziato