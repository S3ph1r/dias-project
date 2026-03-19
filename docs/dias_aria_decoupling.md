# 🌐 Architettura "Linked-but-Independent": DIAS & ARIA

Questo documento chiarisce la separazione netta tra il **Cervello (DIAS)** e il **Cuore Esecutivo (ARIA)**, garantendo che possano vivere indipendentemente pur collaborando via Redis.

---

## 1. La Separazione delle Responsabilità

### DIAS (The Narrative Director) - LXC Brain
- **Focus**: Il Progetto (Audiolibro).
- **Registry**: `dias:registry:{book_id}`.
- **Scopo**: Sapere a che punto è l'audiolibro (Stadi A-G). Non gli importa *come* ARIA faccia il calcolo, gli importa solo che il file WAV sia pronto.
- **Indipendenza**: DIAS può fare Stage A, B e C (analisi) anche se ARIA è spento.

### ARIA (The Inference Engine) - Windows GPU
- **Focus**: Il Task di Inferenza (TTS, Musica, SFX).
- **Registry**: `aria:global:registry` (Hash dei task attivi).
- **Scopo**: Gestire le code GPU per **qualsiasi client** (DIAS, App mobile, Automazioni casa). Deve sapere se la GPU è carica, quali modelli sono in VRAM e qual è lo stato di salute dei backend.
- **Indipendenza**: ARIA vive a prescindere da DIAS. Serve chiunque pubblichi sulle sue code standard.

---

## 2. Il Flusso di Comunicazione "Universal Bus"

Quando DIAS (Stage B/C/D) ha bisogno di un'inferenza (Cloud o Locale):

1.  **DIAS PUSH**: DIAS invia il task tramite il `GatewayClient` alla coda Redis standard.
    - Per **TTS**: `gpu:queue:tts:qwen3-tts-1.7b`
    - Per **Cloud (Gemini)**: `global:queue:cloud:google:gemini-flash-lite-latest:dias`
2.  **ARIA RECEIVE**: L'Orchestratore (o il `CloudManager`) pesca il task.
3.  **ARIA WORK**: ARIA esegue l'inferenza (locale su GPU o remota via SDK Google).
4.  **ARIA CALLBACK**: ARIA invia la conferma a DIAS sulla `callback_key` specifica (`global:callback:dias:{job_id}`).
5.  **DIAS MONITOR**: DIAS riceve il risultato e prosegue.

---

## 3. Le Due Dashboard (La tua visione)

### A. DIAS Dashboard (Vista Narrativa)
- **Progress Bar**: "Il Manoscritto di Avila: 65%".
- **Stage View**: 
  - Stage B: ✅ Completato
  - Stage C: ✅ Completato
  - Stage D (Voce): ⏳ 12/20 scene pronte.
- **Focus**: L'opera letteraria.

### B. ARIA Dashboard (Vista Infrastrutturale)
- **GPU Status**: "RTX 5060 Ti: 75% Load, 12GB VRAM used".
- **Backend Status**:
  - Qwen3TTS: 🟢 Online
  - MusicGen: 🔴 Offline (Loading...)
- **Active Tasks**: "Processing TTS for user *dias_pipeline* (Scena 13)".
- **Focus**: La potenza di calcolo e l'efficienza dei modelli.

---

## 4. Conclusione: Perché è "Blindato"?

- Se **DIAS crasha**: ARIA continua a generare l'audio e lo scrive su disco. Al riavvio di DIAS, la Skipping Logic troverà il file.
- Se **ARIA crasha**: DIAS va in timeout sulla callback, ma il Registro DIAS ti dirà "Scena 6: IN_FLIGHT (Timeout)". Potrai decidere dalla Dashboard DIAS di riprovare.
- Se aggiungi una **nuova App**: ARIA non deve essere modificata. La nuova app invia un task, ARIA lo esegue, la nuova app riceve la risposta.

**Ti senti più "ordinato" con questa divisione? DIAS è la gestione del Libro, ARIA è la gestione della GPU. Redis è il ponte neutro.**

---
*Architettura validata e implementata con successo (Marzo 2026)*
