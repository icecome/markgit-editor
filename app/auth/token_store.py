"""
令牌存储模块
支持内存存储（开发环境）和 Redis 存储（生产环境）
"""
import os
from typing import Dict, Optional
from datetime import datetime, timedelta
import json

try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False

from app.config import logger


class MemoryTokenStore:
    """内存令牌存储（开发环境）"""
    
    def __init__(self, max_sessions: int = 100):
        self._tokens: Dict[str, dict] = {}
        self._max_sessions = max_sessions
    
    def set(self, session_id: str, token_info: dict, ttl: int = 3600):
        """存储令牌，设置 TTL（秒）"""
        # 清理过期令牌
        self.cleanup_expired()
        
        # 检查是否超过最大会话数
        if len(self._tokens) >= self._max_sessions:
            # 删除最旧的会话
            oldest_id = min(self._tokens.keys(), 
                          key=lambda k: self._tokens[k].get('created_at', datetime.now()))
            del self._tokens[oldest_id]
            logger.info(f"清理最旧会话：{oldest_id[:8]}...")
        
        self._tokens[session_id] = {
            **token_info,
            'created_at': datetime.now(),
            'expires_at': datetime.now() + timedelta(seconds=ttl)
        }
        logger.info(f"存储令牌：{session_id[:8]}...")
    
    def get(self, session_id: str) -> Optional[dict]:
        """获取令牌"""
        token_info = self._tokens.get(session_id)
        if not token_info:
            return None
        
        # 检查是否过期
        if token_info.get('expires_at') and datetime.now() > token_info['expires_at']:
            del self._tokens[session_id]
            logger.info(f"令牌过期：{session_id[:8]}...")
            return None
        
        return token_info
    
    def delete(self, session_id: str):
        """删除令牌"""
        if session_id in self._tokens:
            del self._tokens[session_id]
            logger.info(f"删除令牌：{session_id[:8]}...")
    
    def cleanup_expired(self):
        """清理过期令牌"""
        now = datetime.now()
        expired = [
            sid for sid, info in self._tokens.items()
            if info.get('expires_at') and now > info['expires_at']
        ]
        for sid in expired:
            del self._tokens[sid]
        
        if expired:
            logger.info(f"清理了 {len(expired)} 个过期令牌")
    
    def get_all_sessions(self) -> list:
        """获取所有会话 ID"""
        return list(self._tokens.keys())


class RedisTokenStore:
    """Redis 令牌存储（生产环境）"""
    
    def __init__(self, redis_url: str = "redis://localhost:6379/0"):
        if not REDIS_AVAILABLE:
            raise ImportError("redis 库未安装，请运行：pip install redis")
        
        try:
            self.redis = redis.from_url(redis_url)
            self.redis.ping()
            logger.info("Redis 连接成功")
        except Exception as e:
            logger.error(f"Redis 连接失败：{e}")
            raise
    
    def set(self, session_id: str, token_info: dict, ttl: int = 3600):
        """存储令牌，设置 TTL"""
        key = f"markgit:token:{session_id}"
        data = {
            **token_info,
            'created_at': datetime.now().isoformat(),
            'expires_at': (datetime.now() + timedelta(seconds=ttl)).isoformat()
        }
        self.redis.setex(key, ttl, json.dumps(data))
        logger.info(f"存储令牌到 Redis: {session_id[:8]}...")
    
    def get(self, session_id: str) -> Optional[dict]:
        """获取令牌"""
        key = f"markgit:token:{session_id}"
        data = self.redis.get(key)
        if not data:
            return None
        return json.loads(data)
    
    def delete(self, session_id: str):
        """删除令牌"""
        key = f"markgit:token:{session_id}"
        self.redis.delete(key)
        logger.info(f"从 Redis 删除令牌：{session_id[:8]}...")
    
    def cleanup_expired(self):
        """Redis 自动过期，无需手动清理"""
        pass
    
    def get_all_sessions(self) -> list:
        """获取所有会话 ID"""
        keys = self.redis.keys("markgit:token:*")
        return [k.decode().replace("markgit:token:", "") for k in keys]


# 全局令牌存储实例
def create_token_store() -> MemoryTokenStore | RedisTokenStore:
    """创建令牌存储实例"""
    from app.config import MAX_CONCURRENT_SESSIONS
    
    use_redis = os.getenv("USE_REDIS", "false").lower() == "true"
    
    if use_redis and REDIS_AVAILABLE:
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        try:
            return RedisTokenStore(redis_url)
        except Exception as e:
            logger.warning(f"Redis 不可用，使用内存存储：{e}")
    
    # 默认使用内存存储
    return MemoryTokenStore(MAX_CONCURRENT_SESSIONS)


# 全局实例
token_store = create_token_store()
