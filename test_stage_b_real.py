#!/usr/bin/env python3
"""
Test Stage B con dati reali da Stage A
"""

import sys
import os
from pathlib import Path
import json
import logging

# Aggiungi src al path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from src.stages.stage_b_semantic_analyzer import StageBSemanticAnalyzer
from src.common.redis_factory import get_redis_client
from src.common.config import get_config

def test_stage_b_real():
    """Test Stage B con blocco reale"""
    
    # Configurazione logging
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    logger = logging.getLogger("test_stage_b_real")
    
    logger.info("🧠 Testing Stage B - Semantic Analyzer con dati reali")
    
    try:
        # Carica configurazione
        config = get_config()
        redis_client = get_redis_client()
        
        # Inizializza Stage B
        analyzer = StageBSemanticAnalyzer(redis_client=redis_client)
        
        # Carica un blocco reale da Stage A
        stage_a_dir = Path("/home/Projects/NH-Mini/sviluppi/dias/data/stage_a/output")
        if not stage_a_dir.exists():
            logger.error("❌ Directory Stage A non trovata")
            return
            
        # Trova il primo file di cronache_silicio_001
        files = list(stage_a_dir.glob("cronache_silicio_001_*.json"))
        if not files:
            logger.error("❌ Nessun file Stage A trovato")
            return
            
        # Carica il primo blocco
        first_file = files[0]
        logger.info(f"📄 Caricando blocco: {first_file.name}")
        
        with open(first_file, 'r', encoding='utf-8') as f:
            block_data = json.load(f)
            
        logger.info(f"📊 Info blocco:")
        logger.info(f"   - Block ID: {block_data['block_id']}")
        logger.info(f"   - Book ID: {block_data['book_id']}")
        logger.info(f"   - Word count: {block_data['word_count']}")
        logger.info(f"   - Text preview: {block_data['block_text'][:100]}...")
        
        # Prepara messaggio per Stage B
        message = {
            "block_id": block_data['block_id'],
            "book_id": block_data['book_id'],
            "text": block_data['block_text'],
            "metadata": block_data.get('metadata', {})
        }
        
        logger.info("🔄 Avvio analisi semantica...")
        
        # Processa con Stage B
        result = analyzer.process(message)
        
        if result['status'] == 'success':
            logger.info("✅ Stage B completato con successo!")
            logger.info(f"📊 Risultati:")
            logger.info(f"   - Analysis ID: {result['analysis_id']}")
            logger.info(f"   - Entities: {result['entities_count']}")
            logger.info(f"   - Relations: {result['relations_count']}")
            logger.info(f"   - Concepts: {result['concepts_count']}")
            logger.info(f"   - Confidence: {result['confidence_score']:.2f}")
            logger.info(f"   - API calls: {result['api_calls_count']}")
            
            # Salva risultato per Stage C
            output_file = f"/home/Projects/NH-Mini/sviluppi/dias/data/stage_b/output/{result['analysis_id']}.json"
            Path("/home/Projects/NH-Mini/sviluppi/dias/data/stage_b/output").mkdir(parents=True, exist_ok=True)
            
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(result, f, indent=2, ensure_ascii=False)
                
            logger.info(f"💾 Risultato salvato: {output_file}")
            
            # Mostra dettagli entities (prime 3)
            if result.get('entities'):
                logger.info(f"\n👥 Prime 3 entità trovate:")
                for i, entity in enumerate(result['entities'][:3]):
                    logger.info(f"   {i+1}. {entity['text']} ({entity['entity_type']}) - confidence: {entity['confidence']:.2f}")
                    
            # Mostra dettagli concepts (prime 3)
            if result.get('concepts'):
                logger.info(f"\n💡 Prime 3 concetti trovati:")
                for i, concept in enumerate(result['concepts'][:3]):
                    logger.info(f"   {i+1}. {concept['concept']} - confidence: {concept['confidence']:.2f}")
                    
        else:
            logger.error(f"❌ Stage B fallito: {result.get('error', 'Errore sconosciuto')}")
            
    except Exception as e:
        logger.error(f"❌ Errore durante Stage B: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_stage_b_real()