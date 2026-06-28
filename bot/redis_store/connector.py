import redis.asyncio as redis
from typing import Optional
import logging
from bot.config.config import REDIS_HOST, REDIS_PORT, REDIS_PASS, REDIS_USERNAME

logger = logging.getLogger(__name__)

class RedisConnector:
    """Async Redis connection manager"""
    
    _instance: Optional['RedisConnector'] = None
    _client: Optional[redis.Redis] = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    async def connect(self):
        """Initialize Redis connection on startup"""
        try:
            self._client = await redis.Redis(
                host=REDIS_HOST,
                port=REDIS_PORT,
                decode_responses=True,
                username=REDIS_USERNAME,
                password=REDIS_PASS,
            )
            await self._client.ping()
            logger.info("Redis connected successfully")
        except Exception as e:
            logger.error(f"Redis connection failed: {e}")
            raise
    
    async def disconnect(self):
        """Close Redis connection on shutdown"""
        if self._client:
            await self._client.close()
            logger.info("Redis disconnected")
    
    def get_client(self) -> redis.Redis:
        """Get Redis client instance"""
        if self._client is None:
            raise RuntimeError("Redis not connected. Call connect() first.")
        return self._client

redis_connector = RedisConnector()
