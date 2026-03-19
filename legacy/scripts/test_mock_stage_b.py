#!/usr/bin/env python3

import os
import sys
from pathlib import Path

# Aggiungi il path del progetto
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# Forza mock mode
os.environ['MOCK_SERVICES'] = 'true'

from src.stages.stage_b_semantic_analyzer import StageBSemanticAnalyzer
from src.common.redis_factory import DiasRedis

def test_stage_b_mock():
    """Test Stage B con mock"""
    print("🧪 Testing Stage B con MOCK_SERVICES=true")
    
    # Crea client Redis
    redis_client = DiasRedis()
    
    # Crea Stage B con mock
    stage_b = StageBSemanticAnalyzer(redis_client)
    
    # Test message simile a quello di Stage A
    test_message = {
        'block_id': 'test_block_001',
        'book_id': 'cronache_silicio_001',
        'text': 'Kaelen vive a Neo-Kyoto, una grande città cyberpunk.',
        'metadata': {'chapter': 1, 'position': 1}
    }
    
    print(f"📨 Input message: {test_message}")
    
    # Processa
    result = stage_b.process(test_message)
    
    print(f"📤 Output result: {result}")
    
    # Controlla se ci sono errori
    if result.get('status') == 'error':
        print(f"❌ Error: {result.get('error')}")
        return False
    
    # Controlla contenuto
    print(f"📊 Entities: {len(result.get('entities', []))}")
    print(f"🔗 Relations: {len(result.get('relations', []))}")
    print(f"💡 Concepts: {len(result.get('concepts', []))}")
    
    # Verifica che ci siano effettivamente dati
    if len(result.get('entities', [])) == 0 and len(result.get('relations', [])) == 0 and len(result.get('concepts', [])) == 0:
        print("⚠️  Attenzione: Nessun dato trovato nel risultato!")
        return False
    
    return True

if __name__ == '__main__':
    success = test_stage_b_mock()
    if success:
        print("✅ Stage B mock test passed!")
    else:
        print("❌ Stage B mock test failed!")
        sys.exit(1)