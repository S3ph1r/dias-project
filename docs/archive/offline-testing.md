# DIAS Offline Testing Guide (Zero-Cost Verification)

Questa guida spiega come testare la pipeline DIAS e l'integrazione con ARIA senza chiamare le API di Google Gemini, risparmiando costi e velocità.

## 1. Filosofia "Offline-First"
Ogni stadio della pipeline salva i risultati in `/data/stage_X/output` in formato JSON. 
Invece di far ripartire l'intera pipeline dal PDF, possiamo "iniettare" un file JSON già pronto nello stadio successivo.

## 2. Verificare il Ponte ARIA (Stage D)
Se hai già dei file in `data/stage_c/output`, puoi testare la generazione audio sul PC Gaming usando lo script dedicato:

```bash
# Sostituisci [FILE] con un file reale trovato in data/stage_c/output
python3 verify_aria_offline.py data/stage_c/output/nome_file.json
```

**Cosa fa lo script:**
1. Carica l'analisi della scena dal file JSON.
2. Invia il task alla coda Redis `dias:queue:4:voice_gen`.
3. Attende il callback dall'Orchestratore ARIA su Windows.
4. Restituisce l'URL dell'audio generato.

## 3. Gestione dei Marcatori Fish
Il modello **Fish-S1-Mini** interpreta i marcatori emotivi solo se scritti in **Inglese**. 
Lo Stage C è stato aggiornato per inserire marcatori come:
- `(laughing)`
- `(sighing)`
- `(scared)`
- `(whispering)`

Se il file JSON caricato contiene marcatori in Italiano, Fish li leggerà ad alta voce invece di interpretarli. In tal caso, dovrai rieseguire lo Stage C (con le nuove regole) o modificare manualmente il JSON.

## 4. Pulizia Dati
Per mantenere il sistema snello, conserva solo gli ultimi 32 file (un libro standard) per ogni stadio. Puoi usare lo script di pulizia:
```bash
python3 /tmp/cleanup_dias_data.py
```

## 5. Troubleshooting
- **Timeout**: Se lo script fallisce per timeout, controlla che l'icona Tray di ARIA su Windows sia verde.
- **File Not Found**: Verifica che `narratore.wav` sia presente in `C:\Users\Roberto\aria\data\voices\` sul PC Gaming.
