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
    
    @abstractmethod
    async def update_session_page(self, key: str, page: int) -> bool:
        """Update current page in session"""
        pass


class BlueprintRedisStore(RedisInterface):
    """Concrete implementation for blueprint pagination storage"""
    
    def __init__(self, client:redis.Redis):
        self.client = client
    
    async def set_session(self, key: str, data: Dict[str, Any], ttl: int = 3600) -> bool:
        """
        Store blueprint session: bp_session:{chat_id}:{message_id}
        
        data = {
            "user_id": 123,
            "region": "Asia",
            "item_name": "xiranite",
            "current_page": 0,
            "total_pages": 5
        }
        """
        try:
            await self.client.setex(
                key,
                ttl,
                json.dumps(data)
            )
            return True
        except Exception as e:
            print(f" Error setting session: {e}")
            return False
    
    async def get_session(self, key: str) -> Optional[Dict[str, Any]]:
        """Retrieve and deserialize session data"""
        try:
            data = await self.client.get(key)
            if data:
                return json.loads(data)
            return None
        except Exception as e:
            print(f" Error getting session: {e}")
            return None
    
    async def delete_session(self, key: str) -> bool:
        """Delete session data"""
        try:
            await self.client.delete(key)
            return True
        except Exception as e:
            print(f"Error deleting session: {e}")
            return False
    
    async def exists_session(self, key: str) -> bool:
        """Check if session exists"""
        try:
            return await self.client.exists(key) > 0
        except Exception as e:
            print(f"Error checking session: {e}")
            return False
    
    async def update_session_page(self, key: str, page: int) -> bool:
        """Update current_page field in session"""
        try:
            data = await self.get_session(key)
            if data:
                data["current_page"] = page
                # Preserve TTL
                ttl = await self.client.ttl(key)
                await self.set_session(key, data, ttl if ttl > 0 else 3600)
                return True
            return False
        except Exception as e:
            print(f"Error updating page: {e}")
            return False


