#!/usr/bin/env python3
"""
Test alternativo per scoprire modelli Google Gemini disponibili
"""
import os
import requests
from dotenv import load_dotenv

load_dotenv()

def test_gemini_direct():
    """Test diretto con Google AI API"""
    api_key = os.getenv("GOOGLE_API_KEY")
    
    print("🔍 Testing Google Gemini API direttamente...")
    print(f"API Key: {api_key[:15]}...")
    
    # Test con gemini-1.5-flash (più comune)
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"
    
    payload = {
        "contents": [{
            "parts": [{
                "text": "Ciao! Quali modelli Gemini sono disponibili? Rispondi brevemente."
            }]
        }]
    }
    
    headers = {
        'Content-Type': 'application/json',
    }
    
    try:
        response = requests.post(url, json=payload, headers=headers)
        
        print(f"\n📊 Status Code: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            print("✅ API Key funziona!")
            
            if 'candidates' in result and result['candidates']:
                text = result['candidates'][0]['content']['parts'][0]['text']
                print(f"🤖 Risposta: {text}")
            
            # Test con lista modelli
            print("\n🎯 Testing lista modelli...")
            models_url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
            models_response = requests.get(models_url)
            
            if models_response.status_code == 200:
                models_data = models_response.json()
                print("📋 Modelli trovati:")
                
                if 'models' in models_data:
                    for model in models_data['models']:
                        if 'gemini' in model['name'].lower():
                            print(f"   ✅ {model['name']}")
                            if 'description' in model:
                                print(f"      📖 {model['description'][:100]}...")
            else:
                print(f"❌ Errore lista modelli: {models_response.status_code}")
                print(models_response.text[:200])
                
        else:
            print(f"❌ Errore API: {response.status_code}")
            print(f"📄 Risposta: {response.text[:300]}")
            
            if response.status_code == 403:
                print("\n🔒 Possibili problemi:")
                print("   1. API Key non abilitata per Gemini")
                print("   2. Progetto Google Cloud non configurato")
                print("   3. Billing non attivato")
                print("\n🔧 Soluzioni:")
                print("   1. Verifica su Google AI Studio: https://makersuite.google.com/app/apikey")
                print("   2. Assicurati che il progetto sia abilitato per Gemini API")
                print("   3. Verifica che il billing sia attivo su Google Cloud")
                
    except Exception as e:
        print(f"❌ Errore durante test: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_gemini_direct()