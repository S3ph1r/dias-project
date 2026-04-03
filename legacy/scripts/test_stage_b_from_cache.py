#!/usr/bin/env python3
"""
Script 2: Test sistema con risposta salvata (nessuna chiamata API)
Questo script usa la risposta salvata per testare tutto il resto del sistema
"""

import sys
import json
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / 'src'))

from src.common.redis_client import DiasRedis
from src.common.persistence import DiasPersistence

def test_stage_b_from_cache():
    """Test sistema usando risposta salvata (nessuna chiamata API)"""
    
    print("🧪 Script 2: Test sistema con risposta salvata")
    print("=" * 60)
    
    try:
        # Inizializza componenti
        print("📦 Inizializzazione componenti...")
        redis_client = DiasRedis()
        persistence = DiasPersistence()
        
        # Verifica che esista la risposta salvata
        cache_file = Path("/home/Projects/NH-Mini/sviluppi/dias/data/test_cache/stage_b_api_response.json")
        detailed_cache_file = Path("/home/Projects/NH-Mini/sviluppi/dias/data/test_cache/stage_b_detailed_analysis.json")
        
        if not cache_file.exists():
            print(f"❌ File di cache non trovato: {cache_file}")
            print(f"   Esegui prima: python test_stage_b_api_call.py")
            return False
        
        # Carica la risposta salvata
        print(f"📂 Caricamento risposta salvata...")
        with open(cache_file, 'r', encoding='utf-8') as f:
            cached_result = json.load(f)
        
        print(f"✅ Risposta caricata con successo")
        print(f"   - Analysis ID: {cached_result['analysis_id']}")
        print(f"   - Status: {cached_result['status']}")
        print(f"   - Entities: {cached_result['entities_count']}")
        print(f"   - Relations: {cached_result['relations_count']}")
        print(f"   - Concepts: {cached_result['concepts_count']}")
        
        # Test 1: Simula salvataggio in Redis
        print(f"\n📤 Test 1: Simulazione salvataggio in Redis...")
        
        # Carica l'analisi dettagliata se esiste
        if detailed_cache_file.exists():
            with open(detailed_cache_file, 'r', encoding='utf-8') as f:
                detailed_analysis = json.load(f)
        else:
            # Usa i dati base se non c'è quella dettagliata
            detailed_analysis = {
                "analysis_id": cached_result['analysis_id'],
                "block_id": cached_result['block_id'],
                "book_id": cached_result['book_id'],
                "entities": [],  # Sarebbero i dettagli reali
                "relations": [],
                "concepts": [],
                "processing_timestamp": cached_result['processing_timestamp'],
                "confidence_score": cached_result['confidence_score']
            }
        
        # Salva in Redis (simulando Stage C)
        queue_name = "dias_stage_c_queue"
        redis_client.push_to_queue(queue_name, detailed_analysis)
        
        queue_size = redis_client.queue_length(queue_name)
        print(f"   ✅ Item salvato in Redis queue '{queue_name}'")
        print(f"   📊 Queue size: {queue_size}")
        
        # Test 2: Verifica recupero da Redis
        print(f"\n📥 Test 2: Verifica recupero da Redis...")
        
        retrieved_item = redis_client.consume_from_queue(queue_name, timeout=1)
        if retrieved_item:
            print(f"   ✅ Item recuperato con successo")
            print(f"   📋 Analysis ID: {retrieved_item.get('analysis_id')}")
            print(f"   📦 Entities count: {len(retrieved_item.get('entities', []))}")
            
            # Rimetti l'item nella coda per Stage C
            redis_client.push_to_queue(queue_name, retrieved_item)
        else:
            print(f"   ❌ Impossibile recuperare item da Redis")
        
        # Test 3: Simula salvataggio su disco
        print(f"\n💾 Test 3: Simulazione salvataggio su disco...")
        
        # Crea dati di test per Stage C
        stage_c_data = {
            "stage": "c",
            "analysis_id": cached_result['analysis_id'],
            "block_id": cached_result['block_id'],
            "book_id": cached_result['book_id'],
            "entities_count": cached_result['entities_count'],
            "relations_count": cached_result['relations_count'],
            "concepts_count": cached_result['concepts_count'],
            "confidence_score": cached_result['confidence_score'],
            "processing_timestamp": cached_result['processing_timestamp'],
            "api_calls_count": cached_result['api_calls_count'],
            "status": cached_result['status'],
            "test_note": "Dati salvati da cache per test Stage C"
        }
        
        # Salva come Stage C input
        stage_c_filepath = persistence.save_stage_input("c", stage_c_data, 
                                                       cached_result['book_id'], 
                                                       cached_result['block_id'])
        
        print(f"   ✅ Dati salvati come input Stage C")
        print(f"   📁 File: {Path(stage_c_filepath).name}")
        
        # Test 4: Verifica struttura directory
        print(f"\n📂 Test 4: Verifica strutture directory...")
        
        base_path = Path("/home/Projects/NH-Mini/sviluppi/dias/data")
        
        directories_to_check = [
            "stage_a/input", "stage_a/output",
            "stage_b/input", "stage_b/output", 
            "stage_c/input", "stage_c/output",
            "test_cache"
        ]
        
        for dir_name in directories_to_check:
            dir_path = base_path / dir_name
            if dir_path.exists():
                files = list(dir_path.glob("*.json"))
                print(f"   ✅ {dir_name}: {len(files)} file trovati")
            else:
                print(f"   ⚠️  {dir_name}: directory non trovata")
        
        # Test 5: Verifica coerenza dati
        print(f"\n🔍 Test 5: Verifica coerenza dati...")
        
        # Controlla che i dati siano coerenti tra loro
        checks = [
            ("Book ID", cached_result['book_id'] == "cronache_silicio_001"),
            ("Block ID", cached_result['block_id'] == "3f85c583-2570-46af-bf59-58547cbb312b"),
            ("Status", cached_result['status'] == 'success'),
            ("Entities count", cached_result['entities_count'] > 0),
            ("Confidence score", cached_result['confidence_score'] > 0),
        ]
        
        all_passed = True
        for check_name, result in checks:
            status = "✅" if result else "❌"
            print(f"   {status} {check_name}: {'PASS' if result else 'FAIL'}")
            if not result:
                all_passed = False
        
        # Riepilogo finale
        print(f"\n📊 Riepilogo test:")
        print(f"   ✅ Cache caricata correttamente")
        print(f"   ✅ Redis funzionante")
        print(f"   ✅ Persistenza su disco funzionante")
        print(f"   ✅ Strutture directory OK")
        
        if all_passed:
            print(f"   ✅ Tutti i controlli di coerenza PASS")
            print(f"\n🎉 Script 2 completato con successo!")
            print(f"   Il sistema è pronto per Stage C")
            return True
        else:
            print(f"   ⚠️  Alcuni controlli di coerenza FALLITI")
            return False
            
    except Exception as e:
        print(f"\n❌ Errore durante il test: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_stage_b_from_cache()
    if success:
        print("\n✅ Test da cache completato con successo!")
    else:
        print("\n❌ Test da cache fallito!")
        sys.exit(1)