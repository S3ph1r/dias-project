# 🛡️ DIAS Master Registry: Proposta di Sistema Blindato

Questo documento definisce il design del "Registro di Processo" per garantire che il sistema DIAS sia resiliente a crash, riavvii selvaggi e blackout dei nodi (Brain o ARIA).

---

## 1. Il Concetto: "Tripla Verifica"
Per essere "blindato", il sistema non deve fidarsi di un singolo segnale. La decisione di "eseguire un task" viene presa incrociando tre fonti:
1.  **Filesystem (Realtà Fisica)**: Il file `.wav` o `.json` finale esiste davvero?
2.  **Redis Registry (Stato Volatile)**: Il task è contrassegnato come "in volo" o "finito"?
3.  **Redis Queues (Trasporto)**: Il messaggio è fisicamente presente nella coda?

---

## 2. Struttura del Registro (Redis Hash)

Useremo un Hash Redis per ogni libro: `dias:registry:{book_id}`.  
Ogni campo dell'hash sarà un `task_id` (es. `scene-001`), e il valore un JSON con lo stato.

### Stati del Task:
- `PENDING`: Il task è stato creato ma non ancora inviato.
- `IN_FLIGHT`: Inviato ad ARIA, in attesa di callback.
- `COMPLETED`: Callback ricevuta con successo.
- `FAILED`: Errore definitivo o troppi tentativi falliti.

**Esempio di record nel registro:**
```json
{
  "scene_id": "scene-ch001-005",
  "status": "IN_FLIGHT",
  "updated_at": "2026-03-07T17:45:00Z",
  "attempts": 1,
  "worker": "aria-pc-01",
  "callback_key": "dias:callback:stage_d:..."
}
```

---

## 3. Logica di Decisione (Pseudo-algoritmo)

Quando uno stadio (es. Stage D) deve processare una scena:

1.  **CHECK FISICO**: Esiste `/data/stage_d/output/scene-005.json`?
    - ✅ **SÌ**: Il task è finito. Aggiorna Registro a `COMPLETED` e passa oltre.
2.  **CHECK REGISTRO**:
    - Se stato è `COMPLETED` ma il file manca (anomalia): Forza rigenerazione → Stato `PENDING`.
    - Se stato è `IN_FLIGHT`:
        - Controlla `updated_at`. Se è passato > 30 min (Zombie Task):  
          Marca come `PENDING` e riaccoda.
        - Se è recente: **NON ACCARE**. Mettiti solo in ascolto sulla `callback_key`.
3.  **INVIO E LOCK**:
    - Se stato è `PENDING`:
        - Aggiorna registro a `IN_FLIGHT` (con timestamp attuale).
        - Invia il task alla coda Redis di ARIA.
        - Entra in ascolto della callback.

---

## 4. Analisi Pro e Contro

### ✅ PRO (Il Sistema è "Blindato")
- **Zero Duplicazioni**: Anche se riavvii DIAS 10 volte, se vede che un task è `IN_FLIGHT` da poco, non sporca la coda di ARIA.
- **Auto-Pulizia (Anti-Zombie)**: Se ARIA crasha mentre processa, DIAS se ne accorge dal timestamp vecchio nel registro e riprova dopo il timeout.
- **Visibilità Totale**: La Dashboard può leggere l'Hash e disegnare una barra di progresso reale: "3 scene finite, 2 in volo, 5 in attesa".

### ❌ CONTRO (Complessità Aggiuntiva)
- **Overhead Redis**: Richiede una scrittura in più per ogni operazione (piccolo impatto in un homelab).
- **Rischio di "Stale States"**: Se il Registro dice `IN_FLIGHT` ma ARIA è esploso e non ha MAI ricevuto il task, DIAS aspetterà inutilmente fino al timeout (es. 30 min) prima di riprovare. 
  *(Soluzione: Un comando manuale "Force Retry" nella Dashboard).*

---

## 5. Caso Limite: "Stampante di inferenza spenta"
Se ARIA è spento:
1. DIAS riempie la coda Redis dei task.
2. Il Registro li segna tutti come `IN_FLIGHT`.
3. DIAS va in timeout sulla callback (15 min).
4. Poiché non c'è il file su disco, al prossimo riavvio (o al prossimo giro di loop), DIAS rileverà che sono passati 15 min, i task sono "zombie" e li rimetterà in `PENDING`.

**Con questa struttura, il sistema non perde mai la bussola, anche se i pezzi si muovono a velocità diverse.**
