> **[ARCHIVIATO — Aprile 2026]**
> Questo documento descrive l'architettura "Warehouse-First" con Redis catalog (`aria:registry:master`),
> sound library persistente e matching semantico all'85%. Tale sistema è stato **completamente sostituito**
> dal paradigma **Sound-on-Demand v4.1**: ogni asset viene prodotto ex-novo da ACE-Step su richiesta
> di Stage D2, senza alcun catalogo Redis o sound library pre-esistente.
> Per l'architettura corrente, vedere `blueprint.md` e `dias-aria-integration-master.md`.

# ARIA — Universal Sound Library & Sound Factory
## Master Blueprint v1.1 — Aprile 2026

> **Filosofia**: Warehouse-First (Produzione Una Tantum di Alta Qualità)
> **Hardware**: RTX 5060 Ti (16GB VRAM, Architettura Blackwell sm_120)
> **Obiettivo**: Coprire il 90% delle esigenze narrative di DIAS e app future.

---

## 1. Visione Architetturale

A differenza dei servizi TTS (che generano audio on-the-fly), la **Sound Library** adotta un approccio a "Magazzino":
- **Produzione**: Gli asset vengono creati in batch con la massima qualità possibile (modelli `large`).
- **Pubblicazione**: ARIA espone l'inventario tramite il registro Redis (`aria:registry:master`).
- **Consumo**: Le app (DIAS) leggono il catalogo, effettuano il "casting sonoro" e scaricano l'asset via HTTP (porta 8082).

---

## 2. Specifiche dell'Ambiente: `audiocraft-env` (Blackwell Edition)

L'ambiente Conda JIT deve seguire un **Ordine di Installazione Inverso** per evitare conflitti di DLL su Windows 11 e RTX 50-series:

| Componente | Versione | Canale / Metodo | Note |
| :--- | :--- | :--- | :--- |
| **Python** | 3.10 | Conda | Base dell'ambiente |
| **FFmpeg** | latest | `conda-forge` | **CRITICO**: Installare PRIMA di Torch |
| **PyAV (av)** | 16.0.1 | `conda-forge` | **CRITICO**: Verifica `import av` subito |
| **PyTorch** | 2.7.0+cu128 | Pip (`--index-url`) | Motore nativo Blackwell sm_120 |
| **xformers** | 0.0.35 | Pip (`--no-deps`) | **OBBLIGATORIO**: Per caricamento MusicGen |

### ⚠️ Regole d'oro per la Ricostruzione:
1.  **Conda-First**: Installare Python, FFmpeg e av insieme via Conda-Forge. Se installati via Pip, le DLL falliranno il caricamento.
2.  **Blackwell Native**: Usare sempre la rotella `cu128` per PyTorch (anche se Audiocraft chiede la 2.1.0).
3.  **No Downgrade**: Installare `audiocraft` e `xformers` con il flag `--no-deps` per proteggere il motore Torch.
4.  **Cache Warehouse**: Configurare sempre `HF_HOME` e `AUDIOCRAFT_CACHE_DIR` verso `aria/data/assets/models/`.

---

## 3. Strumenti AI Inclusi:
1.  **MusicGen (AudioCraft)**: Per Stings (accenti) e Leitmotif (temi melodici). Utilizzare sempre il modello **`large`** (3.3B) per sfruttare la RTX 5060 Ti.
2.  **Stable Audio Open**: Per Pads (tappeti atmosferici) e texture lunghe.
3.  **AudioLDM 2**: Per SFX realistici (pioggia, passi, ambiente).

---

## 4. Struttura del Magazzino (Assets)

Gli asset sono archiviati in modo autodescrittivo in `C:\Users\Roberto\aria\data\assets\`:

```text
data/assets/
├── pads/            # Tappeti lunghi (> 2 min)
├── stings/          # Accenti brevi (3-10 sec)
└── sfx/             # Effetti ambientali
```

### Anatomia di un Asset:
Ogni sottocartella (es. `pads/tension_dark/`) deve contenere:
- **Audio File**: Nome parlante (es. `pad_tension_dark_synth_drone.wav`).
- **profile.json**: Metadati completi (ID, tag emotivi, descrizione, durata). **Obbligatorio** per la Discovery automatica.
- **ref.wav**: Copia del file audio principale. Necessaria per la generazione automatica della `sample_url` nel registro.

---

## 5. Discovery & Registro Pubblico

L'Orchestratore di ARIA (`AriaRegistryManager`) scansiona le cartelle e pubblica su Redis:
- **Key**: `aria:registry:master` (JSON consolidato)
- **Asset Access**: Ogni suono è raggiungibile via URL:
  `http://{ARIA_NODE_IP}:8082/assets/{type}/{id}/ref.wav` (Attualmente `{ARIA_NODE_IP} = 192.168.1.139`)

---

## 🏁 Roadmap Operativa: Workflow Produzione Suoni

1. **Intercettazione (B2)**: Lo Stage B2 di DIAS (su LXC 190) legge il registro Redis e identifica cosa manca, scrivendo la `shopping_list.json`.
2. **Batch Factory (ARIA)**: Su PC 139, convertiamo la lista in `production_order.csv` e lanciamo `sound_factory.py`.
3. **Blackwell Inference**: MusicGen-Large genera i file audio usando la VRAM della RTX 5060 Ti.
4. **Publish**: Il `RegistryManager` aggiorna Redis e i nuovi suoni diventano immediatamente disponibili per il rendering finale di DIAS.

---

## 6. Risoluzione Problemi (Troubleshooting)

### Errore: `Dependency Missing (torchcodec)`
- **Causa**: `torchaudio.save` su Windows richiede `torchcodec`.
- **Soluzione**: Usare `soundfile` per il salvataggio: `sf.write(path, audio_data, sr)`. Lo script `sound_factory.py` è già patchato.

---
*Documento aggiornato con la Roadmap Produttiva — 05/04/2026*
