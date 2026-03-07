#!/usr/bin/env python3
"""
Test Stage C - Scene Director
Valida segmentazione scene e annotazioni Orpheus
"""

import json
import logging
import sys
from pathlib import Path

# Aggiungi il path src al Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.stages.stage_c_scene_director import SceneDirector


def test_scene_director():
    """Test completo Stage C"""
    logger = logging.getLogger("test_stage_c")
    logger.setLevel(logging.INFO)
    handler = logging.StreamHandler()
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    
    logger.info("🎬 Testing Stage C - Scene Director")
    
    try:
        # Crea istanza Stage C
        director = SceneDirector(logger=logger)
        
        # Mock input da Stage B
        test_input = {
            "book_id": "cronache_silicio_001",
            "block_id": "8958e5f8-a959-4960-9c00-5da0ce5a7d56",
            "analysis_id": "analysis_8958e5f8-a959-4960-9c00-5da0ce5a7d56_20260220_094944",
            "entities_count": 18,
            "relations_count": 13,
            "concepts_count": 4,
            "confidence_score": 0.94,
            "job_id": "test_job_c_001"
        }
        
        logger.info(f"Input test: book_id={test_input['book_id']}, block_id={test_input['block_id']}")
        
        # Processa
        result = director.process_item(test_input)
        
        if result:
            logger.info("✅ Stage C completato con successo")
            logger.info(f"Scenes generate: {result['scenes_count']}")
            
            # Verifica output
            output_path = Path("data/stage_c/output")
            scene_files = list(output_path.glob(f"{test_input['book_id']}_{test_input['block_id']}_*.json"))
            
            if scene_files:
                logger.info(f"📁 Trovati {len(scene_files)} file scena")
                
                # Analizza prima scena
                with open(scene_files[0], 'r', encoding='utf-8') as f:
                    first_scene = json.load(f)
                
                logger.info(f"📝 Prima scena: {first_scene['scene_id']}")
                logger.info(f"   Word count: {first_scene['word_count']}")
                logger.info(f"   Emotion: {first_scene['voice_direction']['emotion_description']}")
                logger.info(f"   TTS Backend: {first_scene['tts_backend']}")
                
                # Verifica Orpheus annotations
                if 'orpheus_annotated_text' in first_scene:
                    annotated = first_scene['orpheus_annotated_text']
                    original = first_scene['text_content']
                    
                    # Conta tag Orpheus
                    orpheus_tags = ['<laugh>', '<chuckle>', '<sigh>', '<sad>', '<gasp>', '<whisper>', '<cry>', '<yawn>']
                    tag_count = sum(1 for tag in orpheus_tags if tag in annotated)
                    
                    logger.info(f"🏷️  Tag Orpheus trovati: {tag_count}")
                    logger.info(f"   Testo originale: {len(original)} caratteri")
                    logger.info(f"   Testo annotato: {len(annotated)} caratteri")
                    
                    if tag_count > 0:
                        logger.info("✅ Annotazioni Orpheus presenti")
                    else:
                        logger.warning("⚠️  Nessuna annotazione Orpheus trovata")
                
                # Verifica struttura completa
                required_fields = ['scene_id', 'text_content', 'orpheus_annotated_text', 'tts_backend', 
                                 'voice_direction', 'audio_layers', 'timing_estimate']
                missing_fields = [f for f in required_fields if f not in first_scene]
                
                if not missing_fields:
                    logger.info("✅ Struttura scena completa")
                else:
                    logger.error(f"❌ Campi mancanti: {missing_fields}")
                    return False
                
                # Verifica audio layers
                audio_layers = first_scene.get('audio_layers', {})
                if 'music' in audio_layers and 'prompt_for_musicgen' in audio_layers['music']:
                    logger.info(f"🎵 Music prompt: {audio_layers['music']['prompt_for_musicgen'][:50]}...")
                else:
                    logger.warning("⚠️  Audio layers incompleti")
                
                return True
            else:
                logger.error("❌ Nessun file scena trovato")
                return False
        else:
            logger.error("❌ Stage C fallito")
            return False
            
    except Exception as e:
        logger.error(f"💥 Test fallito: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = test_scene_director()
    sys.exit(0 if success else 1)