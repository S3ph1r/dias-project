#!/usr/bin/env python3
import os
import sys
import json
import logging
import argparse
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from src.stages.stage_d_voice_gen import StageDVoiceGeneratorProxy
from src.common.config import get_config
from src.common.redis_factory import get_redis_client

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("dias_offline_verify")

def run_offline_test(scene_file: str, redis_host: str = "192.168.1.120"):
    logger.info(f"🚀 Starting Offline ARIA Bridge Verification")
    logger.info(f"📁 Input File: {scene_file}")
    
    # 0. Setup Environment
    os.environ["MOCK_SERVICES"] = "false"
    os.environ["REDIS_HOST"] = redis_host
    
    config = get_config()
    redis_client = get_redis_client()
    
    if not os.path.exists(scene_file):
        logger.error(f"❌ Scene file not found: {scene_file}")
        sys.exit(1)
        
    # 1. Load Data
    with open(scene_file, 'r', encoding='utf-8') as f:
        scene_data = json.load(f)
    
    logger.info(f"✅ Loaded scene: {scene_data.get('scene_id')} (Book: {scene_data.get('book_id')})")
    
    # Check for Fish markers in text
    annotated_text = scene_data.get('fish_annotated_text', '')
    if "(" in annotated_text and ")" in annotated_text:
        logger.info(f"🎭 Found markers: {annotated_text[:100]}...")
    else:
        logger.warning("⚠️ No markers found. Text might be raw.")
    
    # 2. Execute Stage D Proxy
    logger.info("--- Phase: ARIA Bridge Submission ---")
    proxy = StageDVoiceGeneratorProxy(redis_client=redis_client, config=config)
    
    # Send to ARIA and wait for callback
    result = proxy.process(scene_data)
    
    if not result:
        logger.error("❌ Bridge failed: Timeout or ARIA Error.")
        logger.info("💡 Check ARIA logs on Windows (192.168.1.139)")
        sys.exit(1)
        
    logger.info(f"🎉 SUCCESS! Bridge Verified.")
    logger.info(f"🔗 Audio URL: {result.get('voice_path')}")
    logger.info(f"⏱️ Generation Time: {result.get('voice_duration_seconds', 'N/A')}s")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="DIAS Offline Bridge Tester")
    parser.add_argument("file", help="Path to Stage C JSON file")
    parser.add_argument("--redis", default="192.168.1.120", help="Redis Host IP")
    
    args = parser.parse_args()
    run_offline_test(args.file, args.redis)
