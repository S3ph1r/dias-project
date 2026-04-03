#!/usr/bin/env python3
"""
Verification Script: DIAS to ARIA Bridge
Processes a real PDF (Cronache del Silicio) through Stages A, B, C, and D.
Verifies the Task Submission to Redis and waits for the Callback.
"""
import os
import sys
import json
import logging
from pathlib import Path
from datetime import datetime

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from src.stages.stage_a_text_ingester import TextIngester
from src.stages.stage_b_semantic_analyzer import StageBSemanticAnalyzer
from src.stages.stage_c_scene_director import SceneDirector
from src.stages.stage_d_voice_gen import StageDVoiceGeneratorProxy
from src.common.config import get_config
from src.common.redis_factory import get_redis_client

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("dias_aria_verify")

def verify_bridge():
    logger.info("🚀 Starting DIAS-to-ARIA Bridge Verification")
    
    # 0. Setup
    config = get_config()
    redis_client = get_redis_client()
    
    # Force real Gemini if API key is present
    if os.getenv("GOOGLE_API_KEY"):
        os.environ["MOCK_SERVICES"] = "false"
        logger.info("✅ GOOGLE_API_KEY found, using Real Gemini")
    else:
        logger.warning("⚠️ GOOGLE_API_KEY not found, falling back to Mock (if enabled)")

    # 1. Stage A: Ingestion
    logger.info("--- Stage A: Ingesting 'Cronache del Silicio' ---")
    pdf_path = "/home/Projects/NH-Mini/sviluppi/dias/tests/fixtures/cronache_silicio_real_book.pdf"
    book_id = f"verification_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    
    ingester = TextIngester(redis_client, config)
    # Use process_book_file to get blocks
    blocks = ingester.process_book_file(pdf_path, book_id, {"title": "Cronache del Silicio"})
    
    if not blocks:
        logger.error("❌ Stage A failed to produce blocks")
        return
    
    logger.info(f"✅ Stage A produced {len(blocks)} blocks. Using first block for bridge test.")
    first_block = blocks[0]
    
    # 2. Stage B: Semantic Analysis (Italian)
    logger.info("--- Stage B: Semantic Analysis (Mediterranean Style) ---")
    analyzer = StageBSemanticAnalyzer(redis_client)
    
    stage_b_input = {
        "book_id": book_id,
        "block_id": first_block.block_id,
        "text": first_block.block_text
    }
    
    b_result = analyzer.process(stage_b_input)
    if not b_result or b_result.get("status") != "success":
        logger.error(f"❌ Stage B failed: {b_result}")
        return
    
    logger.info(f"✅ Stage B completed. Job ID: {b_result.get('job_id')}")
    
    # 3. Stage C: Scene Direction (Fish Markers)
    logger.info("--- Stage C: Scene Direction (Italian Markers) ---")
    
    # SceneDirector needs a gemini_client properly initialized
    director = SceneDirector(gemini_client=analyzer.gemini_client)
    
    # We need to simulate the message passed from Stage B to Stage C
    # Stage C expects: book_id, block_id, text_content (from persistence), macro_analysis (from persistence)
    # But let's see how Stage C process() actually works.
    
    c_result = director.process(b_result)
    
    if not c_result or c_result.get("status") != "ready_for_stage_d":
        logger.error(f"❌ Stage C failed: {c_result}")
        return
        
    logger.info(f"✅ Stage C completed. {c_result.get('scenes_count')} scenes ready.")
    first_scene = c_result.get("scenes")[0]
    
    # 4. Stage D: ARIA Proxy (Redis Bridge)
    logger.info("--- Stage D: ARIA Proxy (Task Submission) ---")
    proxy = StageDVoiceGeneratorProxy(redis_client=redis_client, config=config)
    
    # Stage D expects individual scenes
    logger.info("Sending task to Redis queue for ARIA...")
    # This will BLOCK for 120s if ARIA doesn't respond
    d_result = proxy.process(first_scene)
    
    if not d_result:
        logger.error("❌ Stage D Proxy failed (Timeout or ARIA Error)")
        logger.info("💡 Tip: Verify if the ARIA Node Orchestrator is running on Windows and connected to Redis.")
        return
        
    logger.info(f"🎉 SUCCESS! Stage D reached and returned from ARIA.")
    logger.info(f"📍 Audio URL: {d_result.get('voice_path')}")
    logger.info(f"⏱️ Duration: {d_result.get('voice_duration_seconds')}s")

if __name__ == "__main__":
    verify_bridge()
