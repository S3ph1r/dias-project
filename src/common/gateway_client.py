import json
import uuid
import time
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone

class GatewayClient:
    """
    Standardized client for DIAS to communicate with the ARIA Gateway v2.0.
    Delegates cloud tasks (Gemini) to ARIA via Redis queues.
    """

    def __init__(self, redis_client, client_id: str = "dias"):
        """
        Args:
            redis_client: Instance of DiasRedis.
            client_id: Identifier for this client (default: 'dias').
        """
        self.redis = redis_client
        self.client_id = client_id
        self.logger = logging.getLogger("gateway_client")
        
        # Load config to get default model if needed
        from src.common.config import get_config
        self.cfg = get_config()

    def generate_content(
        self, 
        contents: List[Dict[str, Any]], 
        model_id: Optional[str] = None, 
        model_type: str = "cloud", # "cloud" or "local"
        provider: str = "google",   # "google", "openai", "local"
        config: Optional[Dict[str, Any]] = None,
        job_id_meta: Optional[Dict[str, str]] = None,
        timeout: int = 1200, 
        job_id: Optional[str] = None 
    ) -> Dict[str, Any]:
        """
        Sends a generation task to the Gateway and waits for the result.
        
        Args:
            contents: List of content parts.
            model_id: Model to use.
            config: Generation parameters.
            job_id_meta: Dict containing identifiers to create a deterministic job_id.
                         e.g., {"book_id": "...", "chunk": "001", "scene": "0"}
            timeout: Max seconds to wait for result.
            job_id: Optional pre-generated job_id to use consistently.
        """
        import hashlib
        
        # 1. Job ID Generation/Selection
        if job_id:
            # Use provided ID directly
            self.logger.info(f"Using explicit job_id: {job_id}")
        elif job_id_meta:
            # Create a stable string from metadata
            keys = sorted(job_id_meta.keys())
            stable_id_str = "|".join([f"{k}:{job_id_meta[k]}" for k in keys])
            # We don't use current timestamp here to ensure crash-resilience
            job_hash = hashlib.sha256(stable_id_str.encode()).hexdigest()[:12]
            job_id = f"job-{job_hash}"
            self.logger.info(f"Generated deterministic job_id: {job_id} from meta: {job_id_meta}")
        else:
            job_id = f"job-{uuid.uuid4().hex[:8]}"
            self.logger.info(f"Generated random job_id: {job_id}")
            
        model_id = model_id or self.cfg.google.model_flash_lite
        # New Standard: aria:c:{client}:{job}
        callback_key = f"aria:c:{self.client_id}:{job_id}"
        
        # 2. Check Mailbox (Persistence)
        # Check if a result already exists in the callback queue (e.g., from a pre-crash task)
        existing_result = self.redis.client.lindex(callback_key, 0)
        if existing_result:
            self.logger.info(f"Found existing result for {job_id} in mailbox. Skipping submission.")
            return self._parse_gateway_result(existing_result, job_id)

        # 3. Prepare ARIA Gateway Payload
        payload = {
            "job_id": job_id,
            "client_id": self.client_id,
            "model_type": model_type,
            "provider": provider,
            "model_id": model_id,
            "callback_key": callback_key,
            "payload": {
                "contents": contents,
                "config": config or {}
            },
            "schema_version": "1.0"
        }
        
        # 4. Submit Task
        # New Standard: aria:q:{env}:{prov}:{model}:{client}
        queue_key = f"aria:q:{model_type}:{provider}:{model_id}:{self.client_id}"
        self.logger.info(f"Submitting task {job_id} to ARIA queue: {queue_key}")
        self.redis.client.lpush(queue_key, json.dumps(payload))
        
        # 5. Wait for Result (BRPOP)
        self.logger.info(f"Waiting for result on {callback_key} (timeout {timeout}s)...")
        result_raw = self.redis.client.brpop(callback_key, timeout=timeout)
        
        if not result_raw:
            self.logger.error(f"Timeout waiting for Gateway result for job {job_id}")
            return {
                "status": "error",
                "error": "GATEWAY_TIMEOUT",
                "error_code": "TIMEOUT"
            }
        
        _, result_json = result_raw
        return self._parse_gateway_result(result_json, job_id)

    def _parse_gateway_result(self, result_json: str, job_id: str) -> Dict[str, Any]:
        """Helper to parse ARIA result JSON"""
        result_data = json.loads(result_json)
        
        if result_data.get("status") == "done":
            return {
                "status": "success",
                "job_id": job_id,
                "output": result_data.get("output", {}),
                "processing_time": result_data.get("processing_time_seconds")
            }
        else:
            error_msg = result_data.get("error", "Unknown Gateway Error")
            error_code = result_data.get("error_code", "GATEWAY_ERROR")
            self.logger.error(f"Gateway task failed: {error_msg} (code: {error_code})")
            return {
                "status": "error",
                "error": error_msg,
                "error_code": error_code
            }
