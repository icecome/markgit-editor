"""Git 上下文管理模块

提供 Git 操作所需的上下文环境，包括会话路径管理、线程安全等。
"""

import threading
from typing import Optional

import app.config as config
from app.session_manager import session_manager

# 当前会话路径（线程局部存储）
_current_session_path = threading.local()

def set_current_session_path(path: str):
    """
    设置当前会话的路径
    
    Args:
        path: 会话路径
    """
    _current_session_path.value = path

def get_current_cache_path() -> str:
    """
    获取当前缓存路径，优先返回会话路径
    
    Returns:
        当前缓存路径
    """
    if hasattr(_current_session_path, 'value') and _current_session_path.value:
        return _current_session_path.value
    return config.BLOG_CACHE_PATH

def setup_git_context(session_id: Optional[str] = None):
    """
    设置 Git 操作上下文（会话路径）
    
    Args:
        session_id: 会话 ID，如果为 None 则使用默认路径
    """
    if session_id:
        session_data = session_manager.get_session(session_id)
        if session_data and 'path' in session_data:
            set_current_session_path(session_data['path'])
    # 如果没有 session_id，使用默认路径
    else:
        set_current_session_path(config.BLOG_CACHE_PATH)

def get_session_path(session_id: Optional[str] = None) -> str:
    """
    获取会话路径，如果未提供 session_id 则返回全局缓存路径
    
    Args:
        session_id: 会话 ID
        
    Returns:
        会话路径或全局缓存路径
    """
    if session_id:
        session_data = session_manager.get_session(session_id)
        if session_data and 'path' in session_data:
            return session_data['path']
    return config.BLOG_CACHE_PATH
