DIAS StageB2 e Soundlibrary

Ecco il documento completo e diviso in due parti. 

La \*\*PARTE 1\*\* è scritta in linguaggio tecnico e architetturale: puoi copiarla e incollarla direttamente nel tuo Agente IDE (Cursor, Copilot, ecc.) come file di specifiche (\`specs\_stage\_b2.md\`) per fargli scrivere il codice.

La \*\*PARTE 2\*\* è un manuale operativo dedicato a te. Ti spiega come usare la tua RTX 5060 Ti su Windows 11 per creare il "magazzino" dei suoni e come automatizzarne la produzione.

\---

\# PARTE 1: Specifiche Tecniche per l'Agente IDE (DIAS v6.3)

\`\`\`markdown  
\# DIAS Specifications: Cinematic Soundscape Architecture (Stage B2 & Pipeline)  
\*\*Target:\*\* IDE Agent / Lead Developer  
\*\*Context:\*\* Integrazione del Sound Design deterministico (Paradigma "Radiofilm") nella pipeline a Chunk di DIAS.

\#\# 1\. Visione Architetturale (Il Paradigma)  
Il sistema DIAS abbandona la generazione musicale in real-time durante la pipeline. Adotta un approccio a \*\*Selezione e Iniezione Deterministica\*\*:  
\- Lo \*\*Stage B2 (Sound Director)\*\* agisce come supervisore musicale. Sceglie asset audio pre-esistenti da un catalogo JSON e inietta tag testuali (\`\<anchor\>\`) nel testo.  
\- Lo \*\*Stage C (Scene Director)\*\* reagisce ai tag, spezzando le scene e imponendo pause millimetriche.  
\- Lo \*\*Stage E/F (Audio Assembler)\*\* usa librerie tradizionali (\`pydub\`) per cucire i file vocali \`.wav\` con i file musicali \`.wav\` selezionati, usando il ducking per i volumi.

\#\# 2\. Integrazione nella Pipeline a 3 Livelli (Macro \-\> Micro \-\> Scena)

\#\#\# Stato dell'Input (Prima di Stage B2)  
Lo Stage A ha diviso il libro in \*\*Macro-Chunk\*\* (\~2500 parole).  
Per alleggerire il carico cognitivo di Stage C, Stage A ha fisicamente duplicato il testo del Macro-Chunk in \*N\* \*\*Micro-Chunk\*\* (\~500 parole) salvati come \`.txt\` separati.  
Lo Stage B ha analizzato l'intero Macro-Chunk producendo un \`macro\_context.json\` (che contiene l'umore primario) copiato per ogni Micro-Chunk.

\#\#\# 2.1 Esecuzione dello Stage B2 (Sound Director)  
\*\*Trigger:\*\* Viene eseguito DOPO lo Stage B e PRIMA dello Stage C.  
\*\*Risorse:\*\* Utilizza un LLM veloce (es. Gemini Flash-Lite).  
\*\*Input:\*\*   
1\. Il testo completo del Macro-Chunk (2500 parole).  
2\. L'umore primario dal \`macro\_context.json\`.  
3\. Il catalogo suoni \`sound\_catalog.json\` (filtrato in base alla scelta del Regista in pre-produzione).

\*\*Azione dell'LLM:\*\*  
1\. Sceglie \*\*UN SOLO Pad (Stem A)\*\* dal catalogo per fare da tappeto all'intero Macro-Chunk.  
2\. Identifica chirurgicamente da 1 a 3 frasi esatte nel Macro-Chunk in cui la voce dovrebbe pausarsi drammaticamente.  
3\. Assegna a ciascuna pausa uno \*\*Sting (Stem C)\*\* dal catalogo.

\*\*Operazione su File (Iniezione Tag):\*\*  
Lo script Python di Stage B2 apre i file \`.txt\` dei \*\*Micro-Chunk\*\* generati da Stage A. Cerca le frasi identificate dall'LLM e inietta un tag nel testo.  
\*Esempio testuale modificato:\* \`"Non siamo veri. \<anchor id="sting\_bass\_drop"\> Siamo solo comparse."\`

\*\*Output:\*\* Aggiorna il \`macro\_context.json\` salvando l'ID del Pad scelto (es. \`pad\_id: "pad\_sci\_fi\_hum"\`).

\#\#\# 2.2 Esecuzione dello Stage C (Scene Director)  
\*\*Regola di Prompt Aggiornata:\*\*  
Il prompt YAML di Stage C deve includere questa direttiva assoluta:  
\> "Se incontri il tag \`\<anchor id="X"\>\` nel testo, DEVI obbligatoriamente spezzare la scena in quel punto. Chiudi il blocco JSON corrente, imposta il valore \`"pause\_after": 5.0\` e inserisci la chiave \`"sound\_anchor": "X"\`. Il tag NON deve mai comparire nel \`clean\_text\` finale."

\#\#\# 2.3 Esecuzione dello Stage E/F (Audio Assembler)  
\*\*Tecnologia:\*\* CPU only, tramite \`pydub\` o \`ffmpeg-python\`.  
\*\*Algoritmo:\*\*  
1\. \*\*Calcolo Timeline:\*\* Concatena le durate dei \`.wav\` vocali (prodotti da Stage D) sommate ai valori di \`pause\_after\`. Calcola la durata totale esatta del Macro-Chunk.  
2\. \*\*Stesura Stem A:\*\* Prende il \`pad\_id\` da \`macro\_context.json\`, carica il file \`.wav\` dal Magazzino e lo mette in loop fino a coprire la durata totale. Applica ducking a \-20dB quando la voce parla, \-14dB durante le pause standard.  
3\. \*\*Iniezione Stem C:\*\* Legge le chiavi \`sound\_anchor\` dai JSON di Stage C. Inserisce lo Sting \`.wav\` sulla timeline al millisecondo esatto in cui inizia la pausa da 5.0s.  
4\. \*\*Export:\*\* Mixdown finale in mp3.  
\`\`\`

\---

\# PARTE 2: Guida alla Creazione della "Universal Sound Library" (Per Te)

Questa parte ti spiega come creare il "Magazzino" fisico dei suoni sul tuo PC Windows 11 con la RTX 5060 Ti, fuori dalla pipeline automatica.

\#\# 1\. Struttura del Magazzino (Data Hierarchy)

Crea questa struttura di cartelle nel tuo progetto:  
\`data/assets/sound\_library/\`  
├── \`pads/\` \*(I tappeti, file di 2-3 minuti)\*  
├── \`stings/\` \*(Le botte sonore, file di 3-8 secondi)\*  
├── \`sfx/\` \*(Rumori ambientali continui)\*  
└── \`sound\_catalog.json\` \*(Il database che l'LLM leggerà)\*

\*\*Come si presenta il \`sound\_catalog.json\`:\*\*  
\`\`\`json  
{  
  "pads":\[  
    { "id": "pad\_tension\_dark", "tags": \["suspense", "fear", "dark", "thriller"\], "description": "Un drone basso e pulsante, nessuna melodia, crea molta ansia." },  
    { "id": "pad\_sci\_fi\_hum", "tags": \["calm", "spaceship", "sci-fi"\], "description": "Rumore bianco melodico, calmo, simile a un motore a curvatura." }  
  \],  
  "stings": \[  
    { "id": "sting\_bass\_drop", "tags":\["shock", "realization", "heavy"\], "description": "Un colpo di sub-basso profondo e improvviso." },  
    { "id": "sting\_transition\_swoosh", "tags": \["time\_jump", "change\_scene"\], "description": "Un effetto vento che sale e scende per cambiare scena." }  
  \]  
}  
\`\`\`

\#\# 2\. Tecnologie e Modelli da Usare (In ambiente Conda)

Poiché hai 16GB di VRAM, useremo modelli Open Source eccellenti ma divisi in base al tipo di suono.

\#\#\# A. Per gli Stings (Stem C) e Leitmotif (Stem B): Meta AudioCraft (MusicGen)  
MusicGen è formidabile per suoni brevi e melodie precise, ma per suoni sopra i 30 secondi inizia a "degradare".  
1\. \*\*Setup:\*\* In Windows, apri Anaconda Prompt.  
   \`\`\`bash  
   conda create \-n audiocraft python=3.10  
   conda activate audiocraft  
   pip install 'torch\>=2.0' torchvision torchaudio \--index-url https://download.pytorch.org/whl/cu118  
   pip install \-U audiocraft  
   \`\`\`  
2\. \*\*Modello da usare:\*\* \`musicgen-medium\` (entra perfettamente in 16GB).  
3\. \*\*Esempio di Prompt per uno Sting:\*\* \`"Cinematic heavy bass impact, sudden shock, suspense, no melody, 5 seconds"\`  
4\. \*\*Esempio di Prompt per un Leitmotif (Generato in Stage 0):\*\* \`"Melancholic cello solo, minimalist, slow, character theme, 30 seconds"\`

\#\#\# B. Per i Pads/Drones (Stem A): Stable Audio Open (o Epidemic Sound)  
I tappeti devono essere lunghi (anche 3 minuti) e loopabili. MusicGen non riesce a farlo bene.  
1\. \*\*Opzione AI:\*\* Puoi usare \*Stable Audio Open\* (tramite interfaccia web locale come ComfyUI o HuggingFace Spaces per comodità, o installando \`stable-audio-tools\`). Prompt: \`"Dark ambient drone, continuous pad, sci-fi texture, seamless loop"\`.  
2\. \*\*Opzione Artigianale (Consigliata):\*\* Per i tappeti, le AI spesso introducono "sporcizia" nel suono. I fonici professionisti scaricano pacchetti royalty-free. Cerca su YouTube o siti come Freesound "Cinematic Ambient Drones" o "Dark Pad loops". Tagliali a 2 minuti, esportali in wav, e mettili in \`pads/\`. Ne bastano 15-20 per coprire il 90% delle emozioni di qualsiasi libro.

\#\# 3\. La "Matrice delle Emozioni" (Cosa produrre)

Per iniziare a popolare il tuo \`sound\_catalog.json\`, ecco la base che ti coprirà quasi ogni sceneggiatura:

\*\*PADS (Tappeti):\*\*  
\- \`pad\_neutral\_thought\` (Per i lunghi monologhi interiori, minimale).  
\- \`pad\_action\_pulse\` (Bassi ritmati, per scene d'azione, esiti incerti).  
\- \`pad\_dark\_tension\` (Thriller, omicidi, scoperte macabre).  
\- \`pad\_melancholy\` (Tristezza, nostalgia, accordi lunghi di synth o archi).  
\- \`pad\_wonder\` (Scoperte magiche, sci-fi epico, arioso).

\*\*STINGS (Ancore):\*\*  
\- \`sting\_bass\_drop\` (La rivelazione finale di un capitolo).  
\- \`sting\_riser\` (Il suono "che sale" prima di una frase a effetto).  
\- \`sting\_cymbal\_swell\` (Un piatto della batteria sfumato, classico e discreto).  
\- \`sting\_metal\_scrape\` (Horror/Thriller, suono metallico fastidioso).

\#\# 4\. Script per l'Automazione (Factory Mode)

Se vuoi generare 50 Sting in una notte con MusicGen senza farlo a mano, puoi creare un piccolo script Python dentro il tuo ambiente \`audiocraft\`.

Crea un file \`batch\_stings.csv\`:  
\`\`\`csv  
sting\_bass\_drop,"Cinematic heavy bass impact, sudden shock, 5 seconds"  
sting\_chime\_magic,"Ethereal magical chime, bright, 4 seconds"  
sting\_heartbeat,"Slow tense single heartbeat thump, scary, 3 seconds"  
\`\`\`

Crea uno script Python (\`generator.py\`):  
\`\`\`python  
import torchaudio  
from audiocraft.models import MusicGen  
import csv

model \= MusicGen.get\_pretrained('medium')  
model.set\_generation\_params(duration=5) \# 5 secondi

with open('batch\_stings.csv', mode='r') as file:  
    reader \= csv.reader(file)  
    for row in reader:  
        filename, prompt \= row\[0\], row\[1\]  
        print(f"Generating: {filename}...")  
        res \= model.generate(\[prompt\])  
        torchaudio.save(f"data/assets/sound\_library/stings/{filename}.wav", res\[0\].cpu(), 32000\)  
\`\`\`  
Lo lanci, vai a dormire, e la mattina hai la cartella \`stings\` piena zeppa di effetti sonori unici creati dalla tua GPU, pronti per essere indicizzati nel \`sound\_catalog.json\` e usati dallo Stage B2\!  
