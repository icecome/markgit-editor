"""Git 上下文管理模块

提供 Git 操作所需的上下文环境，包括会话路径管理、线程安全等。
"""

import os
import threading
from typing import Optional

import app.config as config
from app.session_manager import session_manager

_current_session_path = threading.local()

def set_current_session_path(path: str):
    """
    设置当前会话的路径
    
    Args:
        path: 会话路径
    """
    _current_session_path.value = path

def validate_session_path(path: str, session_id: str) -> bool:
    """
    验证路径是否在会话目录内
    
    Args:
        path: 要验证的路径
        session_id: 会话 ID
    
    Returns:
        路径是否有效
    
    Raises:
        RuntimeError: 当路径不在会话目录内时抛出
    """
    session_data = session_manager.get_session(session_id)
    if not session_data or 'path' not in session_data:
        raise RuntimeError(f"会话 {session_id[:8] if session_id else 'unknown'}... 不存在或无效")
    
    session_path = session_data['path']
    abs_path = os.path.abspath(path)
    abs_session_path = os.path.abspath(session_path)
    
    if not abs_path.startswith(abs_session_path):
        raise RuntimeError(f"路径 {path} 不在会话目录 {session_path} 内，可能存在安全风险")
    
    return True

def get_current_cache_path() -> str:
    """
    获取当前缓存路径，必须有会话路径
    
    Returns:
        当前缓存路径
    
    Raises:
        RuntimeError: 当没有设置会话路径时抛出
    """
    if hasattr(_current_session_path, 'value') and _current_session_path.value:
        return _current_session_path.value
    raise RuntimeError("未设置会话路径，Git 操作必须在有效的会话上下文中进行")

def setup_git_context(session_id: Optional[str] = None):
    """
    设置 Git 操作上下文（会话路径），必须提供有效的 session_id
    
    Args:
        session_id: 会话 ID
    
    Raises:
        RuntimeError: 当没有提供 session_id 或会话不存在时抛出
    """
    if not session_id:
        raise RuntimeError("必须提供会话 ID 才能设置 Git 上下文")
    
    session_data = session_manager.get_session(session_id)
    if not session_data or 'path' not in session_data:
        raise RuntimeError(f"会话 {session_id[:8] if session_id else 'unknown'}... 不存在或无效")
    
    set_current_session_path(session_data['path'])

def get_session_path(session_id: Optional[str] = None) -> str:
    """
    获取会话路径，必须提供有效的 session_id
    
    Args:
        session_id: 会话 ID
        
    Returns:
        会话路径
    
    Raises:
        RuntimeError: 当没有提供 session_id 或会话不存在时抛出
    """
    if not session_id:
        raise RuntimeError("必须提供会话 ID")
    
    session_data = session_manager.get_session(session_id)
    if not session_data or 'path' not in session_data:
        raise RuntimeError(f"会话 {session_id[:8] if session_id else 'unknown'}... 不存在或无效")
    
    return session_data['path']
