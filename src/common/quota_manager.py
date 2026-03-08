"""
DIAS Gemini API Quota Manager
Tracks and enforces daily API limits using Redis.
"""

import datetime
import os
from typing import Dict, Any, Optional

from src.common.redis_factory import get_redis_client

class QuotaManager:
    """
    Manages daily API quotas for Gemini.
    Default limit is 20 calls per day.
    """
    
    def __init__(self, limit: Optional[int] = None, redis_client = None):
        # Use env var or default to 20
        self.limit = limit or int(os.getenv("DIAS_GEMINI_DAILY_LIMIT", "20"))
        self._redis = redis_client or get_redis_client()
        self.base_key = "dias:quota:google"

    def _get_current_key(self) -> str:
        """Returns the Redis key for today's quota."""
        today = datetime.date.today().isoformat()
        return f"{self.base_key}:{today}"

    def get_usage(self) -> int:
        """Returns the number of API calls made today."""
        val = self._redis.get(self._get_current_key())
        return int(val) if val else 0

    def is_available(self) -> bool:
        """Checks if there is still quota available for today."""
        return self.get_usage() < self.limit

    def increment(self) -> int:
        """
        Increments the today's quota counter.
        Returns the new value.
        """
        key = self._get_current_key()
        # Direct access to underlying redis client for atomic incr
        new_val = self._redis.client.incr(key)
        
        # Set a 48-hour expiration if this is the first call of the day
        if new_val == 1:
            self._redis.client.expire(key, 172800) # 48 hours in seconds
            
        return new_val

    def get_quota_info(self) -> Dict[str, Any]:
        """Returns a summary of the current quota status."""
        usage = self.get_usage()
        
        # Calculate time until next reset (midnight)
        now = datetime.datetime.now()
        tomorrow = (now + datetime.timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        seconds_until_reset = int((tomorrow - now).total_seconds())
        
        return {
            "usage": usage,
            "limit": self.limit,
            "available": max(0, self.limit - usage),
            "reset_at": tomorrow.isoformat(),
            "seconds_until_reset": seconds_until_reset
        }

# Singleton helper
_quota_instance: Optional[QuotaManager] = None

def get_quota_manager() -> QuotaManager:
    """Returns the QuotaManager singleton."""
    global _quota_instance
    if _quota_instance is None:
        _quota_instance = QuotaManager()
    return _quota_instance
