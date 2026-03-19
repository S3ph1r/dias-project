#!/usr/bin/env python3
import sys
import logging
import os
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.common.redis_client import DiasRedis
from src.common.gateway_client import GatewayClient
from src.common.config import get_config

def test_gateway_connectivity():
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger("test_gateway")
    
    logger.info("Starting GatewayClient connectivity test...")
    
    # 1. Setup Redis
    try:
        redis_client = DiasRedis()
        if not redis_client.health_check():
            logger.error("Redis health check failed. Is Redis running on 192.168.1.120?")
            return False
        logger.info("✅ Redis connection established.")
    except Exception as e:
        logger.error(f"Failed to connect to Redis: {e}")
        return False
        
    # 2. Setup GatewayClient
    gateway = GatewayClient(redis_client=redis_client, client_id="dias_test")
    
    # 3. Send Test Task
    prompt = "Rispondi in una riga: Sei pronto per il refactor di DIAS?"
    contents = [{"role": "user", "parts": [{"text": prompt}]}]
    
    logger.info(f"Sending test task with prompt: '{prompt}'")
    try:
        result = gateway.generate_content(
            contents=contents,
            model_id="gemini-flash-lite-latest",
            timeout=30
        )
        
        if result["status"] == "success":
            logger.info("✅ GATEWAY SUCCESS!")
            logger.info(f"Response: {result['output'].get('text')}")
            logger.info(f"Processing time: {result.get('processing_time')}s")
            return True
        else:
            logger.error(f"❌ GATEWAY FAILED: {result.get('error')}")
            return False
            
    except Exception as e:
        logger.error(f"Test crashed with error: {e}")
        return False

if __name__ == "__main__":
    success = test_gateway_connectivity()
    sys.exit(0 if success else 1)
