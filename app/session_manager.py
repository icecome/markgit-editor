import os
import json
import uuid
import shutil
import threading
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from pathlib import Path

from app.config import (
    BLOG_CACHE_PATH, SESSION_TIMEOUT_HOURS, 
    MAX_DISK_USAGE_GB, CLEANUP_CHECK_INTERVAL_MINUTES,
    logger
)


class SessionManager:
    """用户会话管理器，负责多用户数据隔离"""
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self.cache_base_path = os.path.normpath(BLOG_CACHE_PATH)
        self.sessions_dir = os.path.join(self.cache_base_path, '.sessions')
        self.sessions_file = os.path.join(self.sessions_dir, 'sessions.json')
        self.sessions: Dict[str, Dict[str, Any]] = {}
        self._initialized = True
        self._load_sessions()
        self._ensure_directories()
    
    def _ensure_directories(self):
        """确保必要的目录存在"""
        os.makedirs(self.sessions_dir, exist_ok=True)
        os.makedirs(self.cache_base_path, exist_ok=True)
    
    def _load_sessions(self):
        """加载会话数据"""
        try:
            if os.path.exists(self.sessions_file):
                with open(self.sessions_file, 'r', encoding='utf-8') as f:
                    self.sessions = json.load(f)
                logger.info(f"加载了 {len(self.sessions)} 个会话")
        except Exception as e:
            logger.error(f"加载会话数据失败：{e}")
            self.sessions = {}
    
    def _save_sessions(self):
        """保存会话数据"""
        try:
            with open(self.sessions_file, 'w', encoding='utf-8') as f:
                json.dump(self.sessions, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存会话数据失败：{e}")
    
    def create_session(self, user_id: Optional[str] = None, clean_old: bool = True) -> tuple:
        """创建新会话
        
        Args:
            user_id: 用户 ID，如果不提供则自动生成
            clean_old: 是否清理该用户的旧会话
            
        Returns:
            (session_id, session_path) 元组
        """
        session_id = str(uuid.uuid4())
        user_id = user_id or session_id
        session_path = os.path.normpath(os.path.join(self.cache_base_path, f"user_{user_id}"))
        
        # 如果是老用户，清理旧会话（单用户单会话策略）
        if clean_old and user_id:
            old_session_result = self.get_session_by_user_id(user_id)
            if old_session_result:
                old_session_id, old_session_data = old_session_result
                logger.info(f"清理用户 {user_id[:8]}... 的旧会话")
                self.delete_session(old_session_id)
        
        self.sessions[session_id] = {
            'user_id': user_id,
            'path': session_path,
            'created_at': datetime.now().isoformat(),
            'last_access': datetime.now().isoformat(),
            'git_repo': '',
            'initialized': False
        }
        
        os.makedirs(session_path, exist_ok=True)
        self._save_sessions()
        
        logger.info(f"创建新会话：{session_id[:8]}... 用户：{user_id[:8]}...")
        return session_id, session_path
    
    def get_session_by_user_id(self, user_id: str) -> Optional[tuple]:
        """根据 user_id 获取会话
        
        Args:
            user_id: 用户 ID
            
        Returns:
            (session_id, session_data) 元组，如果不存在则返回 None
        """
        for session_id, session_data in self.sessions.items():
            if session_data.get('user_id') == user_id:
                return (session_id, session_data)
        return None
    
    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """获取会话信息"""
        return self.sessions.get(session_id)
    
    def is_session_valid(self, session_id: str) -> bool:
        """验证会话是否有效
        
        Args:
            session_id: 会话 ID
            
        Returns:
            会话是否有效
        """
        if not session_id:
            return False
        
        session = self.sessions.get(session_id)
        if not session:
            return False
        
        # 检查会话目录是否存在
        session_path = session.get('path', '')
        if not os.path.exists(session_path):
            logger.warning(f"会话目录不存在：{session_path}")
            return False
        
        return True
    
    def get_session_path(self, session_id: str) -> Optional[str]:
        """获取会话的缓存路径
        
        Args:
            session_id: 会话 ID
            
        Returns:
            会话路径，如果会话无效则返回 None
        """
        if not self.is_session_valid(session_id):
            return None
        
        session = self.sessions[session_id]
        session['last_access'] = datetime.now().isoformat()
        self._save_sessions()
        return session['path']
    
    def update_session_git_repo(self, session_id: str, git_repo: str):
        """更新会话的 Git 仓库配置"""
        if session_id in self.sessions:
            self.sessions[session_id]['git_repo'] = git_repo
            self._save_sessions()
    
    def mark_session_initialized(self, session_id: str):
        """标记会话已初始化"""
        if session_id in self.sessions:
            self.sessions[session_id]['initialized'] = True
            self._save_sessions()
    
    def is_session_initialized(self, session_id: str) -> bool:
        """检查会话是否已初始化"""
        if session_id in self.sessions:
            return self.sessions[session_id].get('initialized', False)
        return False
    
    def get_session_git_repo(self, session_id: str) -> str:
        """获取会话的 Git 仓库配置"""
        if session_id in self.sessions:
            return self.sessions[session_id].get('git_repo', '')
        return ''
    
    def delete_session(self, session_id: str) -> bool:
        """删除会话及其数据"""
        if session_id not in self.sessions:
            return False
        
        session_path = self.sessions[session_id]['path']
        
        try:
            if os.path.exists(session_path):
                shutil.rmtree(session_path, ignore_errors=True)
                logger.info(f"已删除会话数据：{session_path}")
            
            # 获取 user_id 用于日志
            user_id = self.sessions[session_id].get('user_id', 'unknown')
            
            del self.sessions[session_id]
            self._save_sessions()
            logger.info(f"已删除会话：{session_id[:8]}... (user: {user_id[:8]}...)")
            return True
        except KeyError as e:
            logger.warning(f"会话 {session_id[:8]}... 已被删除")
            return False
        except Exception as e:
            logger.error(f"删除会话失败：{e}")
            return False
    
    def cleanup_expired_sessions(self, max_age_hours: Optional[int] = None) -> int:
        """清理过期会话
        
        Args:
            max_age_hours: 最大存活小时数，默认使用配置值
            
        Returns:
            清理的会话数量
        """
        if max_age_hours is None:
            max_age_hours = SESSION_TIMEOUT_HOURS
        
        cutoff_time = datetime.now() - timedelta(hours=max_age_hours)
        expired_sessions = []
        
        for session_id, session_data in self.sessions.items():
            try:
                last_access = datetime.fromisoformat(session_data['last_access'])
                if last_access < cutoff_time:
                    expired_sessions.append(session_id)
            except Exception as e:
                logger.error(f"解析会话时间失败 {session_id}: {e}")
        
        cleaned_count = 0
        for session_id in expired_sessions:
            if self.delete_session(session_id):
                cleaned_count += 1
        
        if cleaned_count > 0:
            logger.info(f"清理了 {cleaned_count} 个过期会话")
        
        return cleaned_count
    
    def get_total_disk_usage(self) -> int:
        """获取所有会话数据占用的磁盘空间 (字节)"""
        total_size = 0
        try:
            for session_data in self.sessions.values():
                session_path = session_data['path']
                if os.path.exists(session_path):
                    for dirpath, dirnames, filenames in os.walk(session_path):
                        for filename in filenames:
                            file_path = os.path.join(dirpath, filename)
                            if os.path.exists(file_path):
                                total_size += os.path.getsize(file_path)
        except Exception as e:
            logger.error(f"计算磁盘使用量失败：{e}")
        
        return total_size
    
    def cleanup_disk_space(self, max_gb: Optional[float] = None) -> int:
        """当磁盘使用超过限制时清理空间
        
        Args:
            max_gb: 最大磁盘使用量 (GB)，默认使用配置值
            
        Returns:
            清理的会话数量
        """
        if max_gb is None:
            max_gb = MAX_DISK_USAGE_GB
        
        max_bytes = max_gb * 1024 * 1024 * 1024
        current_usage = self.get_total_disk_usage()
        
        if current_usage <= max_bytes:
            return 0
        
        logger.info(f"磁盘使用量 {current_usage / (1024**3):.2f}GB 超过限制 {max_gb}GB，开始清理")
        
        sorted_sessions = sorted(
            self.sessions.items(),
            key=lambda x: datetime.fromisoformat(x[1]['last_access'])
        )
        
        cleaned_count = 0
        for session_id, _ in sorted_sessions:
            if self.get_total_disk_usage() <= max_bytes:
                break
            
            if self.delete_session(session_id):
                cleaned_count += 1
                logger.info(f"清理会话 {session_id[:8]}... 以释放空间")
        
        logger.info(f"清理完成，共清理 {cleaned_count} 个会话")
        return cleaned_count
    
    def get_all_sessions(self) -> Dict[str, Dict[str, Any]]:
        """获取所有会话信息"""
        return self.sessions.copy()
    
    def get_active_session_count(self) -> int:
        """获取活跃会话数量"""
        cutoff_time = datetime.now() - timedelta(hours=1)
        active_count = 0
        
        for session_data in self.sessions.values():
            try:
                last_access = datetime.fromisoformat(session_data['last_access'])
                if last_access > cutoff_time:
                    active_count += 1
            except:
                pass
        
        return active_count
    
    def cleanup_invalid_sessions(self) -> int:
        """清理无效会话（目录不存在）
        
        Returns:
            清理的会话数量
        """
        invalid_count = 0
        
        for session_id in list(self.sessions.keys()):
            session_data = self.sessions[session_id]
            session_path = session_data.get('path', '')
            
            if not os.path.exists(session_path):
                logger.info(f"清理无效会话：{session_id[:8]}... (目录不存在)")
                del self.sessions[session_id]
                invalid_count += 1
        
        if invalid_count > 0:
            self._save_sessions()
            logger.info(f"已清理 {invalid_count} 个无效会话")
        
        return invalid_count
    
    def cleanup_all_sessions(self) -> int:
        """清理所有会话数据（用于服务器重启后重置）
        
        Returns:
            清理的会话数量
        """
        logger.info("开始清理所有会话数据...")
        
        for session_id in list(self.sessions.keys()):
            self.delete_session(session_id)
        
        logger.info("已清理所有会话数据")
        return len(self.sessions)


session_manager = SessionManager()
