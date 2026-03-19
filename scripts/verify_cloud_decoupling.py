import sys
import os
import logging
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent))

from src.common.redis_client import DiasRedis
from src.common.gateway_client import GatewayClient
from src.common.config import get_config

def test_cloud_decoupling():
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger("test_cloud")
    
    cfg = get_config()
    redis_client = DiasRedis(cfg.redis.host, cfg.redis.port)
    client = GatewayClient(redis_client)
    
    contents = [
        {
            "role": "user",
            "parts": [{"text": "Hello ARIA Gateway! This is a test of cloud decoupling. Are you there? Answer with a very short funny greeting."}]
        }
    ]
    
    logger.info("Starting cloud test with RED semaphore (GPU reserved)...")
    result = client.generate_content(
        contents=contents,
        model_id="gemini-flash-lite-latest",
        timeout=120
    )
    
    if result["status"] == "success":
        logger.info("✅ SUCCESS! Cloud task bypassed GPU semaphore.")
        logger.info(f"Gateway Response: {result['output'].get('text')}")
    else:
        logger.error(f"❌ FAILED! Cloud task error: {result.get('error')}")

if __name__ == "__main__":
    test_cloud_decoupling()
