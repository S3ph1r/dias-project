#!/usr/bin/env python3
"""
Script 1: Esegue chiamata API Gemini e salva la risposta
Questo script fa la chiamata vera e salva il risultato per test successivi
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

def execute_api_call_and_save():
    """Esegue la chiamata API e salva la risposta"""
    
    print("🚀 Script 1: Esecuzione chiamata API Gemini")
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
            return False
        
        block_file = block_files[0]
        print(f"📁 File trovato: {block_file.name}")
        
        # Carica il contenuto
        with open(block_file, 'r', encoding='utf-8') as f:
            block_data = json.load(f)
        
        print(f"✅ Blocco caricato con successo")
        print(f"   - Book ID: {block_data['book_id']}")
        print(f"   - Block ID: {block_data['block_id']}")
        print(f"   - Word count: {block_data['word_count']}")
        
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
        
        # Esegui analisi semantica (CHIAMATA API VERA)
        print(f"\n🔍 Esecuzione analisi semantica con Gemini API...")
        print(f"   Modello: {analyzer.model_name}")
        print("⚠️  ATTENZIONE: Questa è una chiamata API vera!")
        
        result = analyzer.process(message)
        
        if result['status'] == 'success':
            print(f"\n✅ Analisi completata con successo!")
            
            # Salva la risposta completa per uso futuro
            api_response_file = Path("/home/Projects/NH-Mini/sviluppi/dias/data/test_cache/stage_b_api_response.json")
            api_response_file.parent.mkdir(parents=True, exist_ok=True)
            
            # Salva l'analisi completa (con tutti i dati delle entità, relazioni, concetti)
            with open(api_response_file, 'w', encoding='utf-8') as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
            
            print(f"\n💾 Risposta API salvata in: {api_response_file}")
            print(f"📊 Riepilogo risultati:")
            print(f"   - Analysis ID: {result['analysis_id']}")
            print(f"   - Entities: {result['entities_count']}")
            print(f"   - Relations: {result['relations_count']}")
            print(f"   - Concepts: {result['concepts_count']}")
            print(f"   - Confidence: {result['confidence_score']:.2f}")
            print(f"   - File salvato: {result['file_path']}")
            
            # Salva anche l'analisi completa con tutti i dettagli
            detailed_file = Path("/home/Projects/NH-Mini/sviluppi/dias/data/test_cache/stage_b_detailed_analysis.json")
            
            # Recupera l'analisi completa da Redis o dal file salvato
            stage_b_output_dir = Path("/home/Projects/NH-Mini/sviluppi/dias/data/stage_b/output")
            analysis_files = list(stage_b_output_dir.glob(f"{book_id}_{block_id}_*.json"))
            
            if analysis_files:
                with open(analysis_files[0], 'r', encoding='utf-8') as f:
                    detailed_analysis = json.load(f)
                
                with open(detailed_file, 'w', encoding='utf-8') as f:
                    json.dump(detailed_analysis, f, ensure_ascii=False, indent=2)
                
                print(f"💾 Analisi dettagliata salvata in: {detailed_file}")
            
            print(f"\n🎉 Script 1 completato con successo!")
            print(f"   Puoi ora usare test_stage_b_from_cache.py per testare senza chiamate API")
            return True
            
        else:
            print(f"\n❌ Analisi fallita: {result.get('error', 'Unknown error')}")
            return False
            
    except Exception as e:
        print(f"\n❌ Errore durante la chiamata API: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = execute_api_call_and_save()
    if success:
        print("\n✅ Chiamata API eseguita e salvata correttamente!")
    else:
        print("\n❌ Chiamata API fallita!")
        sys.exit(1)