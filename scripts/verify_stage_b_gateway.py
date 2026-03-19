#!/usr/bin/env python3
import sys
import os
import json
import logging
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.stages.stage_b_semantic_analyzer import StageBSemanticAnalyzer
from src.common.config import get_config

def verify_stage_b():
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger("verify_stage_b")
    
    # 1. Prepare sample message from Stage A
    input_file = "/home/Projects/NH-Mini/sviluppi/dias/data/stage_a/output/Cronache-del-Silicio-chunk-000-20260307_005036.json"
    with open(input_file, 'r', encoding='utf-8') as f:
        message = json.load(f)
    
    # Prepare clean_title and chunk_label as Stage A would usually do via Redis
    message["clean_title"] = "Cronache-del-Silicio"
    message["chunk_label"] = "chunk-000"
    message["text"] = message.get("block_text")
    
    logger.info(f"Loaded message for block: {message.get('block_id')}")
    logger.info(f"Mapped text length: {len(message.get('text', ''))}")
    
    try:
        # 2. Initialize Analyzer (will use GatewayClient)
        analyzer = StageBSemanticAnalyzer()
        
        # 3. Process task
        # We call process() directly to bypass the infinite run() loop
        result = analyzer.process(message)
        
        if result["status"] == "success":
            logger.info("✅ STAGE B SUCCESS via ARIA GATEWAY!")
            logger.info(f"Entities found: {result.get('entities_count')}")
            logger.info(f"Relations found: {result.get('relations_count')}")
            logger.info(f"Concepts found: {result.get('concepts_count')}")
            logger.info(f"Job ID: {result.get('job_id')}")
            return True
        else:
            logger.error(f"❌ STAGE B FAILED: {result.get('error')}")
            return False
            
    except Exception as e:
        logger.error(f"Verification crashed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = verify_stage_b()
    sys.exit(0 if success else 1)
