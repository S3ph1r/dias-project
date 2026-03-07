#!/usr/bin/env python3
"""
Test completo del pipeline DIAS: A → B → C
Verifica che tutti gli stage funzionino insieme con dati reali
"""

import json
import logging
from pathlib import Path
from datetime import datetime

# Import degli stage
from src.stages.stage_a_text_ingester import TextIngester
from src.stages.stage_b_semantic_analyzer import StageBSemanticAnalyzer
from src.stages.stage_c_scene_director import SceneDirector

# Import Redis client and config
from src.common.redis_client import DiasRedis
from src.common.config import get_config
from src.common.redis_factory import get_redis_client

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def test_full_pipeline():
    """Test completo del pipeline DIAS"""
    
    logger.info("🚀 Avvio test pipeline completo DIAS")
    
    # Inizializza Redis client
    logger.info("Connessione a Redis...")
    redis_client = get_redis_client()
    config = get_config()
    
    # Test Stage A - PDF Processing
    logger.info("📚 Stage A - PDF Processing")
    stage_a = TextIngester(redis_client=redis_client, config=config)
    
    # Processa il PDF direttamente
    blocks = stage_a.process_book_file(
        "/home/Projects/NH-Mini/sviluppi/dias/tests/fixtures/cronache_silicio_real_book.pdf",
        "cronache_silicio_001",
        {"title": "Cronache di Silicio", "author": "Autore Sconosciuto"}
    )
    
    if not blocks:
        logger.error("❌ Stage A fallito")
        return False
        
    logger.info(f"✅ Stage A completato: {len(blocks)} blocchi generati")
    
    # Test Stage B - Semantic Analysis
    logger.info("🧠 Stage B - Semantic Analysis")
    stage_b = StageBSemanticAnalyzer(redis_client=redis_client)
    
    # Usa il primo blocco per il test
    first_block = blocks[0]
    
    stage_b_input = {
        "book_id": first_block.book_id,
        "block_id": first_block.block_id,
        "text": first_block.block_text
    }
    
    stage_b_result = stage_b.process(stage_b_input)
    
    if not stage_b_result:
        logger.error("❌ Stage B fallito")
        return False
        
    logger.info(f"✅ Stage B completato: analisi {stage_b_result['analysis_id']} generata")
    
    # Test Stage C - Scene Director
    logger.info("🎬 Stage C - Scene Director")
    stage_c = SceneDirector(logger=logger)
    
    stage_c_input = {
        "book_id": first_block.book_id,
        "block_id": first_block.block_id,
        "analysis_id": stage_b_result['analysis_id'],
        "entities_count": stage_b_result['entities_count'],
        "relations_count": stage_b_result['relations_count'],
        "concepts_count": stage_b_result['concepts_count'],
        "confidence_score": stage_b_result['confidence_score']
    }
    
    stage_c_result = stage_c.process(stage_c_input)
    
    if not stage_c_result:
        logger.error("❌ Stage C fallito")
        return False
        
    logger.info(f"✅ Stage C completato: {stage_c_result['scenes_count']} scene generate")
    
    # Verifica i file generati
    logger.info("📁 Verifica file generati")
    
    # Conta file in stage_c/output
    stage_c_output_path = Path("/home/Projects/NH-Mini/sviluppi/dias/data/stage_c/output")
    scene_files = list(stage_c_output_path.glob("cronache_silicio_001_*.json"))
    
    logger.info(f"📊 File scena trovati: {len(scene_files)}")
    
    if len(scene_files) > 0:
        # Leggi il primo file scena
        first_scene_file = scene_files[0]
        with open(first_scene_file, 'r', encoding='utf-8') as f:
            scene_data = json.load(f)
            
        logger.info(f"📝 Prima scena: {scene_data['scene_id']}")
        logger.info(f"   Word count: {scene_data['word_count']}")
        logger.info(f"   TTS Backend: {scene_data['tts_backend']}")
        
        # Conta tag Orpheus
        orpheus_tags = scene_data['orpheus_annotated_text'].count('<')
        logger.info(f"🏷️  Tag Orpheus trovati: {orpheus_tags}")
        
        logger.info("🎉 Pipeline DIAS completato con successo!")
        return True
    else:
        logger.error("❌ Nessun file scena trovato")
        return False

if __name__ == "__main__":
    success = test_full_pipeline()
    if success:
        logger.info("✅ Test pipeline completato con successo")
    else:
        logger.error("❌ Test pipeline fallito")