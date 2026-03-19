#!/usr/bin/env python3
"""
Script per processare in batch tutti i chunk di un libro attraverso gli Stage B e C.
Sfrutta la logica di skipping per non richiamare Gemini se i file esistono già.
"""
import os
import json
import logging
import sys
from pathlib import Path

# Aggiungi src al path
sys.path.append(str(Path(__file__).parent.parent))

from src.stages.stage_b_semantic_analyzer import StageBSemanticAnalyzer
from src.stages.stage_c_scene_director import SceneDirector
from src.common.redis_client import DiasRedis

def batch_process(book_title_clean="Cronache-del-Silicio"):
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    logger = logging.getLogger("BatchProcess")
    
    logger.info(f"🚀 Inizio batch process per: {book_title_clean}")
    
    # Inizializza Stages
    redis_client = DiasRedis(host="192.168.1.120")
    stage_b = StageBSemanticAnalyzer(redis_client=redis_client)
    stage_c = SceneDirector(logger=logger)
    
    # 1. Trova tutti i chunk dello Stage A
    stage_a_dir = Path("/home/Projects/NH-Mini/sviluppi/dias/data/stage_a/output")
    chunk_files = sorted(list(stage_a_dir.glob(f"{book_title_clean}-chunk-*.json")))
    
    if not chunk_files:
        logger.error(f"❌ Nessun chunk trovato per {book_title_clean} in {stage_a_dir}")
        return

    logger.info(f"📁 Trovati {len(chunk_files)} chunk da processare.")
    
    success_b = 0
    success_c = 0
    
    for i, chunk_path in enumerate(chunk_files):
        logger.info(f"\n--- Processando Chunk {i+1}/{len(chunk_files)}: {chunk_path.name} ---")
        
        try:
            with open(chunk_path, 'r', encoding='utf-8') as f:
                chunk_data = json.load(f)
            
            # Preparazione messaggio per Stage B (deve contenere i metadati che Stage B si aspetta)
            # Analizziamo cosa estrae il TextIngester
            # block_index, book_metadata, clean_title, chunk_label
            
            # Ricostruiamo i metadati minimi se mancano (lo script E2E li passa)
            block_index = int(chunk_path.stem.split('-')[-2]) if 'chunk' in chunk_path.stem else i
            
            msg_b = {
                "book_id": chunk_data.get("book_id", "unknown"),
                "block_id": chunk_data.get("block_id", "unknown"),
                "text": chunk_data.get("block_text", ""),
                "block_index": block_index,
                "clean_title": book_title_clean,
                "chunk_label": f"chunk-{block_index:03d}",
                "book_metadata": {
                    "title": book_title_clean.replace('-', ' '),
                    "book_id": chunk_data.get("book_id", "unknown")
                }
            }
            
            # Run Stage B
            res_b = stage_b.process(msg_b)
            if res_b.get("status") == "success":
                success_b += 1
                
                # Run Stage C (process_item accetta il risultato di Stage B arricchito)
                # Assicuriamoci che abbia i campi necessari
                res_b["clean_title"] = msg_b["clean_title"]
                res_b["chunk_label"] = msg_b["chunk_label"]
                res_b["block_index"] = msg_b["block_index"]
                
                res_c = stage_c.process_item(res_b)
                if res_c:
                    success_c += 1
                    logger.info(f"✅ Chunk {block_index} completato (B e C).")
                else:
                    logger.error(f"❌ Fallimento Stage C per chunk {block_index}")
            else:
                logger.error(f"❌ Fallimento Stage B per chunk {block_index}: {res_b.get('error')}")
                
        except Exception as e:
            logger.error(f"💥 Errore imprevisto sul chunk {chunk_path.name}: {e}")
            continue

    logger.info(f"\n=== BATCH COMPLETO ===")
    logger.info(f"Stage B: {success_b}/{len(chunk_files)} successi")
    logger.info(f"Stage C: {success_c}/{len(chunk_files)} successi")

if __name__ == "__main__":
    batch_process()
