# DIAS vs ElevenLabs: Comparison and Optimization Plan 🕵️⚖️🔊

Questo documento riassume lo stato del progetto al **24 Marzo 2026** e definisce i passi per il confronto qualitativo tra ElevenLabs e Qwen3-TTS.

## 1. Contesto del Sistema
Il sistema è diviso in due macro-progetti indipendenti:
- **DIAS (LXC 190)**: Orchestratore, Ingestione, Regia (Stage A, B, C) e Stitching (Stage E).
- **ARIA (PC 139 - Windows GPU)**: Backend AI. Gestisce il server Qwen3-TTS che riceve i task da DIAS.

## 2. Obiettivi Raggiunti (Oggi)
- ✅ **Completamento Chunk 00**: Tutte le 38 scene generate con successo (WAV in `data/stage_d/output/Cronache-del-Silicio/`).
- ✅ **Stitching Capitolo 1**: Generato il file unico `data/milestone_outputs/Cronache-del-Silicio-chapter_001.wav` (25MB) con pause di regia inserite.
- ✅ **Manutenzione**: Creati backup datati e pulite le cartelle temporanee.
- ✅ **Accessibilità**: Permessi `777` e `root:root` su tutta la cartella `dias` per accesso tramite RaiDrive.

## 3. Il Test di Confronto (EL vs Qwen3)
Abbiamo creato un'area di analisi dedicata in: `/home/Projects/NH-Mini/sviluppi/dias/analysis/el_vs_qwen3/`.

### Asset Pronti per l'Analisi:
- `EL_reference.wav`: Audio originale scaricato da ElevenLabs (testo: *"Si dice che una città..."*).
- `DIAS_comparison.wav`: Audio generato da DIAS per le scene 002, 003, 004 dello stesso testo.
- `Si_dice_che_una_citt__non_sia_.txt`: Testo sorgente completo.

### Il Piano "Eleven" (Voice Cloning):
Per un confronto "puro", vogliamo clonare la voce di EL su Qwen3.
- **Stato**: Abbiamo creato la cartella voce su LXC: `/home/Projects/NH-Mini/sviluppi/ARIA/data/voices/eleven/`.
- **File Pronti**: 
    - `ref.wav` (Taglio a 14.5s di EL).
    - `ref_padded.wav` (Con padding di 0.5s per Qwen3).
- **Mancante**: Scrittura definitiva di `ref.txt` e sincronizzazione su PC 139.

## 4. Prossimi Passi (Nuova Sessione)
1. **Finalizzare la Voce**:
   - Scrivere `ref.txt` con il testo: *"Si dice che una città non sia fatta di cemento e luce, ma di storie. Se così fosse, Neo-Kyoto era un'antologia infinita scritta in una lingua che nessuno poteva più leggere per intero. Era una città costruita su strati di altre città"*.
   - Eseguire il push della cartella `eleven` su PC 139 (`C:\Users\Roberto\aria\data\voices\eleven`).
2. **Generazione Comparativa**:
   - Chiedere a DIAS di rigenerare le scene 002-004 usando `speaker: eleven`.
3. **Analisi e Tuning**:
   - Confrontare la "recitazione" di EL con quella di Qwen3.
   - Modificare il campo `instruct` (es: aggiungere *"with emotional pauses"*, *"somber tone"*) per vedere come Qwen3 risponde e quanto si avvicina alla qualità EL.

---
*Documento generato da Antigravity per la continuità operativa del progetto DIAS.*
