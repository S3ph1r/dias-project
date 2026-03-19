"""
Mock Redis Implementation for Development/Testing

Provides Redis-compatible interface without requiring actual Redis server.
Stores data in-memory for fast, reliable testing.
"""

import json
import time
from typing import Any, Optional, List, Union, Dict
from collections import defaultdict


class MockRedis:
    """In-memory Redis mock for development and testing"""
    
    def __init__(self):
        self.data = {}  # Key-value store
        self.lists = defaultdict(list)  # List operations
        self.expiry = {}  # Key expiry times
        self.logger = None
        
    def hset(self, key: str, field: str, value: Any) -> int:
        """Set field in hash at key"""
        if key not in self.data or not isinstance(self.data[key], dict):
            self.data[key] = {}
        self.data[key][field] = value
        return 1

    def hget(self, key: str, field: str) -> Optional[Any]:
        """Get field from hash at key"""
        if key in self.data and isinstance(self.data[key], dict):
            # Redis mock returns strings in many cases, match that
            val = self.data[key].get(field)
            return str(val) if val is not None else None
        return None

    def hgetall(self, key: str) -> Dict[str, Any]:
        """Get all fields from hash at key"""
        if key in self.data and isinstance(self.data[key], dict):
            return {k: str(v) for k, v in self.data[key].items()}
        return {}

    def set(self, key: str, value: Any, ex: Optional[int] = None) -> bool:
        """Set key with optional expiry (seconds)"""
        self.data[key] = value
        if ex:
            self.expiry[key] = time.time() + ex
        return True
    
    def get(self, key: str) -> Optional[Any]:
        """Get value by key"""
        # Check expiry
        if key in self.expiry and time.time() > self.expiry[key]:
            self.delete(key)
            return None
        return self.data.get(key)
    
    def delete(self, key: str) -> int:
        """Delete key"""
        deleted = 0
        if key in self.data:
            del self.data[key]
            deleted = 1
        if key in self.expiry:
            del self.expiry[key]
        if key in self.lists:
            del self.lists[key]
        return deleted
    
    def exists(self, key: str) -> int:
        """Check if key exists"""
        return 1 if self.get(key) is not None else 0
    
    def incr(self, key: str) -> int:
        """Increment numeric key"""
        val = self.get(key)
        if val is None:
            new_val = 1
        else:
            new_val = int(val) + 1
        self.set(key, new_val)
        return new_val

    def expire(self, key: str, seconds: int) -> bool:
        """Set key expiry"""
        if key in self.data:
            self.expiry[key] = time.time() + seconds
            return True
        return False
    
    def lpush(self, name: str, *values) -> int:
        """Push values to the left of list"""
        for value in reversed(values):
            self.lists[name].insert(0, value)
        return len(self.lists[name])
    
    def rpush(self, name: str, *values) -> int:
        """Push values to the right of list"""
        self.lists[name].extend(values)
        return len(self.lists[name])
    
    def lpop(self, name: str) -> Optional[Any]:
        """Pop value from left of list"""
        if name in self.lists and self.lists[name]:
            return self.lists[name].pop(0)
        return None
    
    def rpop(self, name: str) -> Optional[Any]:
        """Pop value from right of list"""
        if name in self.lists and self.lists[name]:
            return self.lists[name].pop()
        return None
    
    def llen(self, name: str) -> int:
        """Get list length"""
        return len(self.lists.get(name, []))
    
    def lrange(self, name: str, start: int, end: int) -> List[Any]:
        """Get list range (end=-1 for all)"""
        if end == -1:
            end = None
        else:
            end = end + 1
        return self.lists.get(name, [])[start:end]
    
    def flushdb(self) -> bool:
        """Clear all data"""
        self.data.clear()
        self.lists.clear()
        self.expiry.clear()
        return True
    
    def keys(self, pattern: str = "*") -> List[str]:
        """Get keys matching pattern (simple wildcard)"""
        import fnmatch
        return [k for k in self.data.keys() if fnmatch.fnmatch(k, pattern)]
    
    def info(self) -> str:
        """Mock Redis INFO command"""
        return f"""
# MockRedis Info
db0:keys={len(self.data)},expires={len(self.expiry)},avg_ttl=0
"""
    
    def ping(self) -> bool:
        """Mock Redis PING command"""
        return True
    
    def close(self) -> None:
        """Close connection (mock)"""
        pass
    
    def eval(self, script: str, numkeys: int, *args) -> Any:
        """Mock Redis EVAL command (DUMMY - always returns 0 to allow slot acquisition)"""
        if self.logger:
            self.logger.info("MockRedis EVAL called (simulating successful slot acquisition)")
        return 0
    
    # --- Queue Operations (for DIAS compatibility) ---
    
    def push_to_queue(self, queue_name: str, message: dict) -> int:
        """Push message to queue (LPUSH) - returns queue length"""
        import json
        payload = json.dumps(message, ensure_ascii=False)
        return self.lpush(queue_name, payload)
    
    def consume_from_queue(self, queue_name: str, timeout: int = 0) -> Optional[dict]:
        """Consume message from queue (BRPOP) - returns deserialized message or None"""
        import json
        # Simulate BRPOP with RPOP (non-blocking mock)
        result = self.rpop(queue_name)
        if result is None:
            return None
        try:
            return json.loads(result)
        except json.JSONDecodeError:
            return result
    
    def queue_length(self, queue_name: str) -> int:
        """Get queue length (LLEN)"""
        return self.llen(queue_name)
    
    # Debug utilities
    def get_stats(self) -> dict:
        """Get mock statistics"""
        return {
            "keys": len(self.data),
            "lists": len(self.lists),
            "expiring_keys": len(self.expiry),
            "total_memory": sum(len(str(v)) for v in self.data.values())
        }
    
    def dump_data(self) -> dict:
        """Dump all data for debugging"""
        return {
            "data": self.data.copy(),
            "lists": {k: v.copy() for k, v in self.lists.items()},
            "expiry": self.expiry.copy()
        }


class MockRedisClient:
    """Factory for mock Redis client with logging support"""
    
    def __init__(self, logger=None):
        self.redis = MockRedis()
        self.logger = logger
        if logger:
            self.redis.logger = logger
            logger.info("MockRedis initialized for development/testing")
    
    def get_client(self):
        """Get mock Redis client"""
        if self.logger:
            self.logger.info("Using MockRedis (development mode)")
        return self.redis
    
    def __enter__(self):
        return self.get_client()
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.redis:
            self.redis.close()


# Compatibility alias for import
MockRedisConnection = MockRedis