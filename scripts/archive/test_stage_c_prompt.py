import os
import sys
import argparse
from pathlib import Path
import google.genai as genai

# Aggiungi src al path
sys.path.append(str(Path(__file__).parent.parent))

def test_prompt(model_id, text_file=None):
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        print("ERRORE: GOOGLE_API_KEY non trovata.")
        return

    client = genai.Client(api_key=api_key)
    
    # Testo di esempio (il primo chunk di Cronache) se non fornito un file
    if text_file:
        with open(text_file, 'r') as f:
            raw_data = f.read()
            import json
            text = json.loads(raw_data).get("block_text", "")
    else:
        text = """Cronache del Silicio 
Libro Primo: L'Architetto dei Fantasmi 
Si dice che una città non sia fatta di cemento e luce, ma di storie.
Capitolo I: Il Ronzio della Statica 
Anno Domini 2042. Distretto Superiore di Kamigyo, Neo-Kyoto."""

    # PROMPT VERSION 2.0
    prompt = f"""
    Sei un esperto regista audio specializzato in romanzi narrativi di alta qualità.
    Il tuo compito è trasformare il testo grezzo in uno SCRIPT ANNOTATO per la sintesi vocale (Fish S1-mini).
    
    REGOLE MANDATORIE DI FORMATTAZIONE (SILENZIO E RITMO):
    1. TITOLI E SOTTOTITOLI: Ogni volta che incontri un titolo (es. "Libro Primo", "Capitolo I", "Cronache...") devi:
       - Chiuderlo con un punto fermo (.) se non presente.
       - Aggiungere ESATTAMENTE due ritorni a capo (\\n\\n) dopo il punto.
       - Questo è CRITICO per permettere al narratore di respirare tra le sezioni.
    
    2. CAPITOLI E NUMERI: 
       - Converti TUTTI i numeri romani in parole ORDINALI (es. "Capitolo I" -> "Capitolo Primo", "Capitolo II" -> "Capitolo Secondo").
       - Se vedi "Capitolo I: Titolo", trasformalo in "Capitolo Primo. Titolo. \\n\\n".
    
    3. TAG EMOZIONALI (FISH S1-mini):
       - Inserisci tag emozionali tra parentesi tonde (es. (serious), (worried)) PRIMA della frase.
       - USA SOLO: (neutral), (serious), (whispering), (shouting), (sad), (happy), (excited), (angry), (fearful), (surprised), (disgusted), (worried), (joyful), (thoughtful), (indifferent), (hesitating), (sighing), (sincere), (sarcastic).
       - Non abusarne: un tag ogni 2-3 frasi o al cambio di paragrafo è sufficiente.
    
    4. PULIZIA:
       - Rimuovi caratteri speciali non necessari (es. ":").
       - Restituisci SOLO lo script annotato. Niente chiacchiere.
    
    TESTO DA TRASFORMARE:
    {text}
    """

    print(f"\n--- Testing Model: {model_id} ---")
    print(f"--- Prompt Version: 2.0 ---\n")
    
    try:
        response = client.models.generate_content(
            model=model_id,
            contents=prompt
        )
        print("RESULT:\n" + "="*40)
        print(response.text)
        print("="*40)
    except Exception as e:
        print(f"Errore durante la generazione: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="gemini-2.0-flash", help="ID del modello Gemini")
    parser.add_argument("--file", help="Path al file JSON del chunk")
    args = parser.parse_args()
    
    test_prompt(args.model, args.file)
