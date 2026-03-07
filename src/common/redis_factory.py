"""
Configuration-driven Redis Client Factory

Provides Redis client based on environment configuration.
Supports both real Redis and Mock Redis for development/testing.
"""

import os
import logging
from typing import Union

# Import both real and mock Redis clients
try:
    from src.common.redis_client import DiasRedis
    REAL_REDIS_AVAILABLE = True
except ImportError:
    REAL_REDIS_AVAILABLE = False
    DiasRedis = None

try:
    from src.common.mock_redis import MockRedisClient, MockRedis
    MOCK_REDIS_AVAILABLE = True
except ImportError:
    MOCK_REDIS_AVAILABLE = False
    MockRedisClient = None


def get_redis_client(logger: logging.Logger = None) -> Union['DiasRedis', 'MockRedis']:
    """
    Get Redis client based on environment configuration.
    
    Priority:
    1. MOCK_SERVICES=true → MockRedis (development)
    2. MOCK_SERVICES=false → Real DiasRedis (production)
    3. No config → MockRedis (safe default for development)
    
    Args:
        logger: Optional logger for debugging
        
    Returns:
        Redis client (real or mock)
        
    Raises:
        RuntimeError: If no Redis client can be created
    """
    
    # Check environment configuration
    mock_services = os.getenv('MOCK_SERVICES', 'true').lower() == 'true'
    
    if logger:
        logger.info(f"Redis factory: MOCK_SERVICES={mock_services}")
    
    # Case 1: Mock Redis requested or no config
    if mock_services or not REAL_REDIS_AVAILABLE:
        if not MOCK_REDIS_AVAILABLE:
            raise RuntimeError("MockRedis requested but not available")
        
        if logger:
            logger.info("Using MockRedis for development/testing")
        
        mock_client = MockRedisClient(logger=logger)
        return mock_client.get_client()
    
    # Case 2: Real Redis requested
    else:
        if not REAL_REDIS_AVAILABLE:
            raise RuntimeError("Real Redis requested but DiasRedis not available")
        
        if logger:
            logger.info("Using real DiasRedis for production")
        
        try:
            from src.common.config import get_config
            cfg = get_config()
            real_client = DiasRedis(
                host=cfg.redis.host,
                port=cfg.redis.port,
                db=cfg.redis.db,
                decode_responses=cfg.redis.decode_responses,
                retry_attempts=cfg.redis.retry_attempts,
                retry_backoff_base=cfg.redis.retry_backoff_base,
                logger=logger
            )
            return real_client
        except Exception as e:
            if logger:
                logger.error(f"Failed to create real Redis client: {e}")
            raise


def create_redis_factory(config_dict: dict = None, logger: logging.Logger = None):
    """
    Create a Redis client factory with custom configuration.
    
    Args:
        config_dict: Optional configuration override
        logger: Optional logger
        
    Returns:
        Function that creates Redis clients
    """
    
    def factory() -> Union['DiasRedis', 'MockRedis']:
        # Apply config override if provided
        if config_dict:
            for key, value in config_dict.items():
                os.environ[key] = str(value)
        
        return get_redis_client(logger=logger)
    
    return factory


# Environment detection helpers
def is_development() -> bool:
    """Check if running in development mode"""
    return os.getenv('MOCK_SERVICES', 'true').lower() == 'true'


def is_production() -> bool:
    """Check if running in production mode"""
    return os.getenv('MOCK_SERVICES', 'false').lower() == 'false'


def get_environment_info() -> dict:
    """Get current environment information"""
    return {
        'mock_services': os.getenv('MOCK_SERVICES', 'true'),
        'development': is_development(),
        'production': is_production(),
        'real_redis_available': REAL_REDIS_AVAILABLE,
        'mock_redis_available': MOCK_REDIS_AVAILABLE
    }