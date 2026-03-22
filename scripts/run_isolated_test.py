#!/usr/bin/env python3
"""
Shadow Testing Script for DIAS.
Runs Stage C and D on a specific Stage B fixture (JSON) but overrides the `book_id`.
This ensures test results go into isolated directories (e.g. data/stage_c/output/Test-Phonetics)
without breaking production data.

Usage: python scripts/run_isolated_test.py tests/fixtures/chunk-008-ambrato.json Test-Phonetics-V1
"""

import sys
import json
import logging
from pathlib import Path
import time

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.common.config import get_config
from src.common.redis_client import DiasRedis
from src.common.registry import ActiveTaskTracker
from src.stages.stage_c_scene_director import SceneDirector
from src.stages.stage_d_voice_gen import StageDVoiceGeneratorProxy
from src.common.persistence import DiasPersistence

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("IsolatedTest")

def run_isolated_test(fixture_path: str, test_book_id: str):
    config = get_config()
    redis = DiasRedis(
        host=config.redis.host,
        port=config.redis.port,
        db=config.redis.db,
        decode_responses=config.redis.decode_responses
    )
    tracker = ActiveTaskTracker(redis)
    persistence = DiasPersistence(config.storage.base_path)
    
    # Load fixture
    with open(fixture_path, 'r') as f:
        data = json.load(f)
    
    # OVERRIDE BOOK ID
    data['book_id'] = test_book_id
    data['clean_title'] = test_book_id
    
    # Save a temporary B output to memory for persistence to find
    temp_job_id = f"job_test_{int(time.time())}"
    data["job_id"] = temp_job_id
    
    chunk_label = data.get('chunk_label', 'chunk-X')
    
    # Write the mock input to Stage B output dir for Stage C to pick up
    b_out_dir = Path("data/stage_b/output")
    b_out_dir.mkdir(parents=True, exist_ok=True)
    temp_b_path = b_out_dir / f"{test_book_id}-{chunk_label}-test.json"
    
    with open(temp_b_path, "w") as f:
        json.dump(data, f, indent=2)
        
    logger.info(f"1. Created isolated Stage B input: {temp_b_path}")
    
    # 1.5 MOCK STAGE A TEXT
    # Stage C needs to load the raw text from Stage A using the new book_id
    import glob
    chunk_id = fixture_path.split("chunk-")[1].split("-")[0]
    a_files = glob.glob(f"data/stage_a/output/Cronache-del-Silicio-chunk-{chunk_id}-*.json")
    if a_files:
        with open(a_files[0], 'r') as fa:
            a_data = json.load(fa)
        
        a_data['book_id'] = test_book_id
        a_out_dir = Path("data/stage_a/output")
        a_out_dir.mkdir(parents=True, exist_ok=True)
        temp_a_path = a_out_dir / f"{test_book_id}-chunk-{chunk_id}-test.json"
        
        with open(temp_a_path, "w") as fa_out:
            json.dump(a_data, fa_out, indent=2)
        logger.info(f"1.5 Created isolated Stage A text payload: {temp_a_path}")
    else:
        logger.error(f"Could not find original Stage A file for chunk {chunk_id}")
        return
    
    # Run Stage C
    logger.info("2. Triggering Stage C...")
    # Force the new prompt via config (bypassing Pydantic strictness)
    config.__dict__["stage_c_prompt_path"] = "config/prompts/stage_c/v1.1_phonetics.yaml"
    stage_c = SceneDirector(config_path=None, logger=logger)
    
    try:
        # Pass the entire Stage B JSON data directly to bypass the queue
        c_result = stage_c.process_item(data)
        logger.info("Stage C completed. Check data/stage_c/output/")
    except Exception as e:
        logger.error(f"Stage C failed: {e}")
        return

    # Trigger Stage D
    if not c_result:
        logger.error("Stage C returned None, aborting Stage D.")
        return
        
    logger.info("3. Triggering Stage D (Voice Gen)...")
    logger.info("Ensure ARIA Node Controller is running to process the jobs!")
    try:
        stage_d = StageDVoiceGeneratorProxy(redis_client=redis, config=config)
        stage_d.process_item(c_result)
        logger.info("Stage D dispatcher completed. Audio should generate under data/stage_d/output/")
        
    except Exception as e:
        logger.error(f"Stage D failed: {e}")

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python scripts/run_isolated_test.py <path_to_stage_b_json> <test_book_id>")
        sys.exit(1)
        
    fixture = sys.argv[1]
    tid = sys.argv[2]
    run_isolated_test(fixture, tid)
