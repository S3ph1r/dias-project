#!/usr/bin/env python3
"""
Processa tutti i 32 blocchi di Stage A con Stage B
Salva tutti gli output per "Cronache di Silicio"
Rate limiting: max 1 chiamata ogni 30 secondi
Salva cache risposte API per riutilizzo e resilienza
"""

import sys
import json
import time
import hashlib
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / 'src'))

from src.stages.stage_b_semantic_analyzer import StageBSemanticAnalyzer
from src.common.redis_client import DiasRedis
from src.common.persistence import DiasPersistence
from src.common.models import IngestionBlock

def get_cache_key(block_text, model="gemini-2.5-flash"):
    """Genera cache key univoca per blocco testo"""
    content = f"{block_text[:100]}_{model}"
    return hashlib.md5(content.encode()).hexdigest()

def check_existing_cache(block_id, book_id):
    """Verifica se esiste già un output Stage B per questo blocco"""
    stage_b_dir = Path("/home/Projects/NH-Mini/sviluppi/dias/data/stage_b/output")
    existing_files = list(stage_b_dir.glob(f"{book_id}_{block_id}_*.json"))
    return len(existing_files) > 0

def process_all_stage_b_blocks():
    """Processa tutti i blocchi Stage A con Stage B - con rate limiting e cache"""
    
    print("🚀 Processamento completo Stage B - Tutti i blocchi")
    print("⏱️  Rate limiting: max 1 chiamata ogni 30 secondi")
    print("💾 Cache: risposte salvate per riutilizzo")
    print("=" * 60)
    
    book_id = "cronache_silicio_001"
    stage_a_dir = Path("/home/Projects/NH-Mini/sviluppi/dias/data/stage_a/output")
    RATE_LIMIT_SECONDS = 30
    
    try:
        # Inizializza componenti
        print("📦 Inizializzazione componenti...")
        redis_client = DiasRedis()
        persistence = DiasPersistence()
        analyzer = StageBSemanticAnalyzer(redis_client)
        
        # Trova tutti i file Stage A per cronache_silicio_001
        print(f"📁 Ricerca blocchi Stage A per {book_id}...")
        block_files = list(stage_a_dir.glob(f"{book_id}_*.json"))
        
        print(f"📊 Trovati {len(block_files)} blocchi Stage A")
        
        if not block_files:
            print("❌ Nessun blocco trovato!")
            return
        
        # Processa ogni blocco
        success_count = 0
        error_count = 0
        skipped_count = 0
        api_calls_made = 0
        
        for i, block_file in enumerate(block_files, 1):
            print(f"\n[{i:2d}/{len(block_files)}] Processando: {block_file.name}")
            
            try:
                # Carica blocco
                with open(block_file, 'r', encoding='utf-8') as f:
                    block_data = json.load(f)
                
                block_id = block_data['block_id']
                
                # Verifica se esiste già output
                if check_existing_cache(block_id, book_id):
                    print(f"   ⏭️  Skipped - Output già esistente")
                    skipped_count += 1
                    continue
                
                # Rate limiting prima di chiamata API
                if api_calls_made > 0:
                    print(f"   ⏱️  Rate limiting: attesa {RATE_LIMIT_SECONDS}s...")
                    time.sleep(RATE_LIMIT_SECONDS)
                
                # Crea messaggio per Stage B
                message = {
                    'book_id': block_data['book_id'],
                    'block_id': block_data['block_id'],
                    'text': block_data['block_text'],  # Fix: Stage B expects 'text' not 'block_text'
                    'chapter_id': block_data.get('chapter_id', 'unknown'),
                    'word_count': block_data.get('word_count', 0)
                }
                
                # Processa con Stage B
                print(f"   🔄 Chiamata API in corso...")
                result = analyzer.process(message)
                api_calls_made += 1
                
                if result['status'] == 'success':
                    print(f"   ✅ Successo - Entities: {result['entities_count']} | Relations: {result['relations_count']} | Concepts: {result['concepts_count']}")
                    success_count += 1
                else:
                    print(f"   ❌ Errore: {result.get('error', 'Unknown error')}")
                    error_count += 1
                
            except Exception as e:
                print(f"   ❌ Eccezione: {str(e)}")
                error_count += 1
        
        # Riepilogo finale
        print("\n" + "=" * 60)
        print(f"📊 RISULTATI FINALI:")
        print(f"   ✅ Successi: {success_count}")
        print(f"   ❌ Errori: {error_count}")
        print(f"   ⏭️  Skipped (già processati): {skipped_count}")
        print(f"   📞 API calls effettuate: {api_calls_made}")
        print(f"   📈 Totali blocchi: {len(block_files)}")
        print(f"   📊 Percentuale successo: {(success_count/len(block_files)*100):.1f}%")
        
        # Verifica output salvati
        stage_b_dir = Path("/home/Projects/NH-Mini/sviluppi/dias/data/stage_b/output")
        output_files = list(stage_b_dir.glob(f"{book_id}_*.json"))
        print(f"\n📁 File Stage B salvati: {len(output_files)}")
        
        # Stima tempo rimanente se ci sono blocchi mancanti
        remaining = len(block_files) - success_count - skipped_count
        if remaining > 0 and api_calls_made > 0:
            estimated_time = remaining * RATE_LIMIT_SECONDS / 60  # minuti
            print(f"⏰ Tempo stimato per completare: {estimated_time:.1f} minuti")
        
    except Exception as e:
        print(f"❌ Errore generale: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    process_all_stage_b_blocks()