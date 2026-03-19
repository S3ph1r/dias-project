#!/usr/bin/env python3
"""
Test Stage B con blocco reale salvato da 'Cronache di Silicio'
"""

import sys
import json
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / 'src'))

from src.stages.stage_b_semantic_analyzer import StageBSemanticAnalyzer
from src.common.redis_client import DiasRedis
from src.common.persistence import DiasPersistence

def test_stage_b_with_real_block():
    """Test Stage B con un blocco reale salvato"""
    
    print("🚀 Test Stage B con blocco reale da 'Cronache di Silicio'")
    print("=" * 60)
    
    # Configurazione
    block_id = "3f85c583-2570-46af-bf59-58547cbb312b"  # Primo blocco
    book_id = "cronache_silicio_001"
    
    try:
        # Inizializza componenti
        print("📦 Inizializzazione componenti...")
        redis_client = DiasRedis()
        persistence = DiasPersistence()
        analyzer = StageBSemanticAnalyzer(redis_client)
        
        # Carica il blocco dal disco
        print(f"📖 Caricamento blocco {block_id}...")
        
        # Trova il file del blocco
        stage_a_output_dir = Path("/home/Projects/NH-Mini/sviluppi/dias/data/stage_a/output")
        block_files = list(stage_a_output_dir.glob(f"{book_id}_{block_id}_*.json"))
        
        if not block_files:
            print(f"❌ File del blocco non trovato: {book_id}_{block_id}_*.json")
            return
        
        block_file = block_files[0]
        print(f"📁 File trovato: {block_file.name}")
        
        # Carica il contenuto
        with open(block_file, 'r', encoding='utf-8') as f:
            block_data = json.load(f)
        
        print(f"✅ Blocco caricato con successo")
        print(f"   - Book ID: {block_data['book_id']}")
        print(f"   - Block ID: {block_data['block_id']}")
        print(f"   - Word count: {block_data['word_count']}")
        print(f"   - Text length: {len(block_data['block_text'])} characters")
        
        # Prepara il messaggio per Stage B
        message = {
            "block_id": block_data['block_id'],
            "book_id": block_data['book_id'],
            "text": block_data['block_text'],
            "metadata": {
                "chapter_id": block_data.get('chapter_id'),
                "chapter_number": block_data.get('chapter_number'),
                "block_index": block_data.get('block_index'),
                "total_blocks": block_data.get('total_blocks_in_chapter'),
                "source_file": str(block_file),
                "word_count": block_data['word_count']
            }
        }
        
        # Mostra anteprima del testo
        print(f"\n📝 Anteprima testo (prime 300 caratteri):")
        preview = block_data['block_text'][:300].replace('\n', ' ')
        print(f"   {preview}...")
        
        # Esegui analisi semantica
        print(f"\n🔍 Avvio analisi semantica...")
        print(f"   Modello: {analyzer.model_name}")
        
        result = analyzer.process(message)
        
        # Risultati
        print(f"\n📊 Risultati analisi:")
        if result['status'] == 'success':
            print(f"   ✅ Status: {result['status']}")
            print(f"   📋 Analysis ID: {result['analysis_id']}")
            print(f"   👥 Entities: {result['entities_count']}")
            print(f"   🔗 Relations: {result['relations_count']}")
            print(f"   💡 Concepts: {result['concepts_count']}")
            print(f"   📈 Confidence: {result['confidence_score']:.2f}")
            print(f"   🕐 Processing time: {result['processing_timestamp']}")
            print(f"   📞 API calls: {result['api_calls_count']}")
            
            # Verifica salvataggio in Redis
            print(f"\n💾 Verifica salvataggio in Redis...")
            queue_name = "dias_stage_c_queue"
            queue_size = redis_client.get_queue_size(queue_name)
            print(f"   📊 Queue '{queue_name}' size: {queue_size}")
            
            if queue_size > 0:
                # Prendi il primo elemento per verificare
                queued_item = redis_client.pop_from_queue(queue_name)
                if queued_item:
                    print(f"   ✅ Item salvato correttamente in Redis")
                    print(f"   📋 Analysis ID: {queued_item.get('analysis_id')}")
                    print(f"   📦 Entities salvate: {len(queued_item.get('entities', []))}")
                    
                    # Rimetti l'item nella coda (per Stage C)
                    redis_client.push_to_queue(queue_name, queued_item)
                else:
                    print(f"   ⚠️  Impossibile recuperare item dalla coda")
            
            # Salva l'analisi su disco con persistenza
            print(f"\n💾 Salvataggio analisi su disco...")
            analysis_data = {
                "analysis_id": result['analysis_id'],
                "block_id": result['block_id'],
                "book_id": result['book_id'],
                "entities_count": result['entities_count'],
                "relations_count": result['relations_count'],
                "concepts_count": result['concepts_count'],
                "confidence_score": result['confidence_score'],
                "processing_timestamp": result['processing_timestamp'],
                "api_calls_count": result['api_calls_count'],
                "status": result['status']
            }
            
            filepath = persistence.save_stage_output("b", analysis_data, book_id, block_id)
            print(f"   ✅ Analisi salvata su disco: {Path(filepath).name}")
            
        else:
            print(f"   ❌ Status: {result['status']}")
            print(f"   ⚠️  Error: {result.get('error', 'Unknown error')}")
        
        # Verifica rate limit status
        try:
            rate_status = analyzer.get_rate_limit_status()
            print(f"\n⏱️  Rate limit status:")
            if 'current_usage' in rate_status:
                print(f"   Current usage: {rate_status['current_usage']}/{rate_status['max_requests']}")
                print(f"   Reset time: {rate_status['reset_time']}")
                print(f"   Available slots: {rate_status['available_slots']}")
            else:
                print(f"   Status: {rate_status}")
        except Exception as e:
            print(f"\n⚠️  Impossibile recuperare rate limit status: {e}")
        
        print(f"\n🎉 Test Stage B completato!")
        
    except Exception as e:
        print(f"\n❌ Errore durante il test: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_stage_b_with_real_block()