#!/usr/bin/env python3
"""
Test disponibilità modelli Google Gemini API
"""
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Load environment
load_dotenv()

def test_gemini_models():
    """Test quali modelli Gemini sono disponibili"""
    print("🔍 Testing Google Gemini API e modelli disponibili...")
    
    # Get API key
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        print("❌ GOOGLE_API_KEY non trovata nel .env")
        return
    
    print(f"✅ API Key trovata: {api_key[:15]}...")
    
    try:
        from google import genai
        
        # Initialize client
        print("🚀 Inizializzando client Gemini...")
        client = genai.Client(api_key=api_key)
        
        # Test list models
        print("📋 Lista modelli disponibili:")
        models = client.models.list()
        
        gemini_models = []
        for model in models:
            if 'gemini' in model.name.lower():
                gemini_models.append(model.name)
                print(f"   ✅ {model.name}")
                if hasattr(model, 'description'):
                    print(f"      📖 {model.description}")
                if hasattr(model, 'input_token_limit'):
                    print(f"      📊 Token limit: {model.input_token_limit}")
        
        if not gemini_models:
            print("   ⚠️  Nessun modello Gemini trovato")
            return
        
        print(f"\n🎯 Trovati {len(gemini_models)} modelli Gemini")
        
        # Test specific models
        test_models = [
            "gemini-2.5-flash",
            "gemini-2.5-flash-lite", 
            "gemini-2.0-flash",
            "gemini-1.5-flash",
            "gemini-1.5-pro"
        ]
        
        print("\n🧪 Testing modelli specifici:")
        for model_name in test_models:
            try:
                # Simple test generation
                response = client.models.generate_content(
                    model=model_name,
                    contents="Ciao, rispondi solo con la parola 'test'"
                )
                
                if response.text and 'test' in response.text.lower():
                    print(f"   ✅ {model_name} - FUNZIONA")
                else:
                    print(f"   ⚠️  {model_name} - Risponde ma non come previsto")
                    
            except Exception as e:
                error_msg = str(e)
                if "quota" in error_msg.lower() or "rate" in error_msg.lower():
                    print(f"   ⚠️  {model_name} - Rate limited")
                elif "not found" in error_msg.lower():
                    print(f"   ❌ {model_name} - Modello non trovato")
                else:
                    print(f"   ❌ {model_name} - Errore: {error_msg[:50]}...")
        
        # Test our target model specifically
        print(f"\n🎯 Testing modello target per DIAS (gemini-2.5-flash-lite):")
        try:
            response = client.models.generate_content(
                model="gemini-2.5-flash-lite",
                contents="""
                Analizza questo testo e restituisci JSON:
                "Il detective Rossi indaga sul caso. Maria è la testimone principale."
                
                Restituisci: {"entities": [{"text": "Rossi", "type": "person"}]}
                """,
                generation_config={"temperature": 0.2}
            )
            
            print(f"   ✅ Modello gemini-2.5-flash-lite funziona!")
            print(f"   📄 Risposta: {response.text[:100]}...")
            
        except Exception as e:
            print(f"   ❌ Errore con gemini-2.5-flash-lite: {e}")
        
        print(f"\n✅ Test completato! Stage B può usare Gemini API.")
        
    except ImportError:
        print("❌ google-genai non installato")
        print("   Installa: pip install google-genai")
    except Exception as e:
        print(f"❌ Errore durante test: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_gemini_models()