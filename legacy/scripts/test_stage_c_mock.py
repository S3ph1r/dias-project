#!/usr/bin/env python3

import os
import sys
from pathlib import Path

# Aggiungi il path del progetto
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# Forza mock mode
os.environ['MOCK_SERVICES'] = 'true'

from src.stages.stage_c_scene_director import SceneDirector
from src.common.redis_factory import DiasRedis

def test_stage_c_mock():
    """Test Stage C con mock"""
    print("🧪 Testing Stage C con MOCK_SERVICES=true")
    
    # Crea client Redis
    redis_client = DiasRedis()
    
    # Crea Stage C con mock
    stage_c = SceneDirector()
    
    # Test message simile a quello di Stage B
    test_message = {
        'block_id': 'test_block_001',
        'book_id': 'cronache_silicio_001',
        'analysis_id': 'analysis_test_block_001_20260220_120730',
        'entities_count': 2,
        'relations_count': 1,
        'concepts_count': 1
    }
    
    print(f"📨 Input message: {test_message}")
    
    # Processa
    result = stage_c.process(test_message)
    
    print(f"📤 Output result: {result}")
    
    # Controlla se ci sono errori
    if result.get('status') == 'error':
        print(f"❌ Error: {result.get('error')}")
        return False
    
    # Controlla contenuto
    scenes = result.get('scenes', [])
    print(f"🎬 Scenes generated: {len(scenes)}")
    
    if len(scenes) > 0:
        for i, scene in enumerate(scenes):
            print(f"  Scene {i+1}: {scene.get('scene_type', 'unknown')}")
            print(f"    Text length: {len(scene.get('text', ''))} chars")
            print(f"    Audio script: {len(scene.get('audio_script', ''))} chars")
            print(f"    Voice tags: {scene.get('voice_tags', [])}")
    
    return len(scenes) > 0

if __name__ == '__main__':
    success = test_stage_c_mock()
    if success:
        print("✅ Stage C mock test passed!")
    else:
        print("❌ Stage C mock test failed!")
        sys.exit(1)