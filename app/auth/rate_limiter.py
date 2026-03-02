"""
简单的内存速率限制器
用于防止暴力破解和滥用
"""
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Dict, Tuple
import threading
from app.config import logger


class InMemoryRateLimiter:
    """线程安全的内存速率限制器"""
    
    def __init__(self):
        self._requests: Dict[str, list] = defaultdict(list)
        self._lock = threading.Lock()
    
    def is_allowed(self, key: str, max_requests: int, window_seconds: int) -> Tuple[bool, int]:
        """
        检查是否允许请求
        
        Args:
            key: 限制键（通常是 IP 地址）
            max_requests: 时间窗口内允许的最大请求数
            window_seconds: 时间窗口（秒）
        
        Returns:
            (is_allowed, retry_after): 是否允许，重试等待时间（秒）
        """
        now = datetime.now()
        window_start = now - timedelta(seconds=window_seconds)
        
        with self._lock:
            # 清理过期的请求记录
            self._requests[key] = [
                req_time for req_time in self._requests[key]
                if req_time > window_start
            ]
            
            # 检查是否超过限制
            if len(self._requests[key]) >= max_requests:
                # 计算需要等待的时间
                oldest_request = min(self._requests[key])
                retry_after = int((oldest_request + timedelta(seconds=window_seconds) - now).total_seconds())
                return False, max(1, retry_after)
            
            # 记录本次请求
            self._requests[key].append(now)
            return True, 0
    
    def cleanup_expired(self):
        """清理所有过期的请求记录"""
        with self._lock:
            self._requests.clear()


# 全局速率限制器实例
rate_limiter = InMemoryRateLimiter()


def check_rate_limit(key: str, max_requests: int = 10, window_seconds: int = 60) -> Tuple[bool, int]:
    """
    检查速率限制的便捷函数
    
    Args:
        key: 限制键（通常是 IP 地址或用户 ID）
        max_requests: 时间窗口内允许的最大请求数（默认 10 次）
        window_seconds: 时间窗口（默认 60 秒）
    
    Returns:
        (is_allowed, retry_after): 是否允许，重试等待时间（秒）
    """
    return rate_limiter.is_allowed(key, max_requests, window_seconds)


MAX_REQUEST_BODY_SIZE = 10 * 1024 * 1024  # 10MB

def check_request_body_size(content_length: int) -> Tuple[bool, str]:
    """
    检查请求体大小是否超过限制
    
    Args:
        content_length: 请求体大小（字节）
    
    Returns:
        (is_valid, error_message): 是否有效，错误消息
    """
    if content_length > MAX_REQUEST_BODY_SIZE:
        size_mb = content_length / (1024 * 1024)
        max_mb = MAX_REQUEST_BODY_SIZE / (1024 * 1024)
        return False, f"请求体过大（{size_mb:.1f}MB），最大支持 {max_mb:.0f}MB"
    
    return True, ""
