from abc import ABC, abstractmethod
import json
from typing import Optional, Dict, Any
import redis.asyncio as redis


class RedisInterface(ABC):
    """Abstract interface for Redis operations"""
    
    @abstractmethod
    async def set_session(self, key: str, data: Dict[str, Any], ttl: int = 3600) -> bool:
        """Store blueprint session data"""
        pass
    
    @abstractmethod
    async def get_session(self, key: str) -> Optional[Dict[str, Any]]:
        """Retrieve blueprint session data"""
        pass
    
    @abstractmethod
    async def delete_session(self, key: str) -> bool:
        """Delete session data"""
        pass
    
    @abstractmethod
    async def exists_session(self, key: str) -> bool:
        """Check if session exists"""
        pass
    
