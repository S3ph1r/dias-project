#!/usr/bin/env python3
"""
Scopri quali modelli Gemini sono realmente disponibili
"""
import os
import requests
from dotenv import load_dotenv

load_dotenv()

def discover_models():
    """Scopri modelli disponibili"""
    api_key = os.getenv("GOOGLE_API_KEY")
    
    print("🔍 Scoprendo modelli Gemini disponibili...")
    
    # Lista modelli disponibili
    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
    
    try:
        response = requests.get(url)
        
        if response.status_code == 200:
            data = response.json()
            
            print("✅ Modelli trovati:")
            gemini_models = []
            
            if 'models' in data:
                for model in data['models']:
                    name = model.get('name', '')
                    if 'gemini' in name.lower():
                        gemini_models.append(name)
                        print(f"\n   📋 {name}")
                        
                        # Mostra dettagli
                        if 'description' in model:
                            print(f"      📖 {model['description']}")
                        if 'supportedGenerationMethods' in model:
                            methods = ', '.join(model['supportedGenerationMethods'])
                            print(f"      🔧 Metodi: {methods}")
                        if 'inputTokenLimit' in model:
                            print(f"      📊 Token limit: {model['inputTokenLimit']}")
                        if 'temperature' in model:
                            print(f"      🌡️  Temperature: {model['temperature']}")
            
            print(f"\n🎯 Trovati {len(gemini_models)} modelli Gemini")
            
            # Testa il primo disponibile
            if gemini_models:
                test_model = gemini_models[0]
                print(f"\n🧪 Testing {test_model}...")
                
                test_url = f"https://generativelanguage.googleapis.com/v1beta/models/{test_model}:generateContent?key={api_key}"
                
                payload = {
                    "contents": [{
                        "parts": [{
                            "text": "Test: rispondi solo con 'OK'"
                        }]
                    }]
                }
                
                test_response = requests.post(test_url, json=payload)
                
                if test_response.status_code == 200:
                    print(f"   ✅ {test_model} funziona perfettamente!")
                else:
                    print(f"   ❌ {test_model} errore: {test_response.status_code}")
                    print(f"      {test_response.text[:100]}")
            
            # Suggerisci modello per Stage B
            print(f"\n💡 Suggerimenti per Stage B:")
            if any('flash' in m for m in gemini_models):
                flash_models = [m for m in gemini_models if 'flash' in m]
                print(f"   🚀 Modelli Flash consigliati: {', '.join(flash_models)}")
            else:
                print(f"   📋 Usa uno di questi: {', '.join(gemini_models[:3])}")
                
        else:
            print(f"❌ Errore: {response.status_code}")
            print(f"📄 {response.text[:200]}")
            
    except Exception as e:
        print(f"❌ Errore: {e}")

if __name__ == "__main__":
    discover_models()