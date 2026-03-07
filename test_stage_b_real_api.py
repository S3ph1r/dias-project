#!/usr/bin/env python3
"""
Test Stage B Semantic Analyzer con API Google reali
"""
import os
import sys
import json
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent / "src"))

from src.stages.stage_b_semantic_analyzer import StageBSemanticAnalyzer
from src.common.redis_client import DiasRedis

def test_stage_b_real_api():
    """Test Stage B con API Google reali"""
    print("🧪 Testing Stage B Semantic Analyzer con API Google reali")
    
    # Check API key
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key or api_key == "your-google-api-key-here":
        print("❌ GOOGLE_API_KEY non configurata nel .env")
        print("\n🔧 Per configurare:")
        print("   1. Vai su https://makersuite.google.com/app/apikey")
        print("   2. Crea una nuova API key")
        print("   3. Copia il file .env.template in .env:")
        print("      cp .env.template .env")
        print("   4. Modifica .env e inserisci la tua API key")
        print("   5. Riprova il test")
        return
    
    print(f"✅ API Key trovata: {api_key[:10]}...")
    
    # Test message simile a Stage A output
    test_message = {
        "block_id": "test_block_001",
        "book_id": "test_book_001", 
        "text": """
        Il detective Smith entrò nell'ufficio del commissario. Il caso del serial killer lo aveva tenuto sveglio per notti. 
        Maria Rossi, la nuova psicologa, lo stava aspettando. "Il profilo del killer", disse, "è quello di un uomo tra i 30 e 40 anni, 
        con problemi relazionali e un lavoro precario. Probabilmente vive nella periferia nord della città."
        
        Smith annuì. "Questo coincide con le nostre indagini. Il killer conosce bene le strade del quartiere Aurora."
        
        L'atmosfera era tesa. Il commissario Bianchi entrò nella stanza. "Abbiamo un nuovo indizio", annunciò. 
        "Un testimone ha visto un uomo sospetto vicino all'ultima scena del crimine."
        """,
        "metadata": {
            "chapter": 1,
            "position": 1,
            "word_count": 150
        }
    }
    
    print(f"📖 Testo di input: {len(test_message['text'])} caratteri")
    
    try:
        # Inizializza Stage B
        print("🚀 Inizializzando Stage B...")
        analyzer = StageBSemanticAnalyzer()
        print("✅ Stage B inizializzato")
        
        # Processa
        print("⚡ Processando con API Google...")
        result = analyzer.process(test_message)
        
        print(f"\n📊 Risultati:")
        print(f"   Status: {result['status']}")
        print(f"   Entities: {result['entities_count']}")
        print(f"   Relations: {result['relations_count']}")  
        print(f"   Concepts: {result['concepts_count']}")
        print(f"   Confidence: {result['confidence_score']}")
        print(f"   API calls: {result['api_calls_count']}")
        
        if result['status'] == 'success':
            print("\n🎉 Stage B test completato con successo!")
            print("\n💡 Per testare il flusso completo:")
            print("   1. Assicurati che Stage A abbia processato un PDF")
            print("   2. I risultati saranno in coda Redis per Stage B")
            print("   3. Stage B processerà automaticamente i blocchi")
        else:
            print(f"\n❌ Errore: {result.get('error', 'Unknown error')}")
            
    except Exception as e:
        print(f"\n❌ Errore durante test: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_stage_b_real_api()