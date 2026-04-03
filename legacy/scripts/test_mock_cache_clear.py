#!/usr/bin/env python3

import os
import sys
from pathlib import Path
import shutil

# Aggiungi il path del progetto
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# Forza mock mode
os.environ['MOCK_SERVICES'] = 'true'

from src.stages.mock_gemini_client import MockGeminiClient
import json

def test_mock_with_cache_clear():
    """Test diretto del mock client con cache pulita"""
    print("🧪 Testing MockGeminiClient con cache pulita")
    
    # Crea mock client
    mock_client = MockGeminiClient()
    
    # Pulisci cache
    if mock_client.cache_dir.exists():
        shutil.rmtree(mock_client.cache_dir)
        print("🗑️  Cache pulita")
    
    # Test prompt per Stage B
    prompt = """
    Analizza il seguente testo per estrarre:
    1. Entità (persone, luoghi, organizzazioni, concetti specifici)
    2. Relazioni tra entità
    3. Concetti chiave e loro definizioni
    
    Testo da analizzare:
    Kaelen vive a Neo-Kyoto, una grande città cyberpunk.
    
    Rispondi in formato JSON con questa struttura:
    """
    
    print(f"📨 Prompt: {prompt[:100]}...")
    
    # Genera risposta mock
    response = mock_client.generate_content(prompt, model="gemini-2.5-flash")
    
    print(f"📤 Response: {response[:500]}...")
    
    # Prova a parsare la risposta
    try:
        # Estrai JSON
        json_start = response.find('{')
        json_end = response.rfind('}') + 1
        
        if json_start >= 0 and json_end > json_start:
            json_str = response[json_start:json_end]
            result = json.loads(json_str)
            print(f"📊 Parsed result:")
            print(f"  - Entities: {len(result.get('entities', []))}")
            print(f"  - Relations: {len(result.get('relations', []))}")
            print(f"  - Concepts: {len(result.get('concepts', []))}")
            
            # Controlla struttura concetti
            for i, concept in enumerate(result.get('concepts', [])):
                print(f"  - Concept {i}: {concept}")
                if 'definition' not in concept:
                    print(f"    ⚠️  Missing 'definition' field!")
                if 'confidence' not in concept:
                    print(f"    ⚠️  Missing 'confidence' field!")
            
            return True
        else:
            print("❌ No JSON found in response")
            return False
            
    except Exception as e:
        print(f"❌ Error parsing: {e}")
        return False

if __name__ == '__main__':
    success = test_mock_with_cache_clear()
    if success:
        print("✅ Mock client test passed!")
    else:
        print("❌ Mock client test failed!")
        sys.exit(1)