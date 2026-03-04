import os
import threading
import time
from datetime import datetime
from typing import Optional
from pathlib import Path

from app.config import (
    SESSION_TIMEOUT_HOURS, MAX_DISK_USAGE_GB,
    CLEANUP_CHECK_INTERVAL_MINUTES, logger
)
from app.session_manager import session_manager


class CleanupService:
    """清理服务，负责定期清理过期会话和监控磁盘空间"""
    
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
        
        self.cleanup_interval = CLEANUP_CHECK_INTERVAL_MINUTES * 60
        self.running = False
        self.cleanup_thread: Optional[threading.Thread] = None
        self._initialized = True
        self.last_cleanup_time: Optional[datetime] = None
        self.last_disk_check_time: Optional[datetime] = None
        
        logger.info(f"清理服务已初始化，清理间隔：{self.cleanup_interval}秒")
    
    def start(self):
        """启动清理服务"""
        if self.running:
            logger.warning("清理服务已在运行")
            return
        
        self.running = True
        self.cleanup_thread = threading.Thread(target=self._cleanup_loop, daemon=True)
        self.cleanup_thread.start()
        logger.info("清理服务已启动")
    
    def stop(self):
        """停止清理服务"""
        self.running = False
        if self.cleanup_thread:
            self.cleanup_thread.join(timeout=5)
        logger.info("清理服务已停止")
    
    def _cleanup_loop(self):
        """清理循环"""
        while self.running:
            try:
                self._perform_cleanup()
                self._check_disk_space()
                self.last_cleanup_time = datetime.now()
            except Exception as e:
                logger.error(f"清理任务执行失败：{e}")
            
            for _ in range(self.cleanup_interval):
                if not self.running:
                    break
                time.sleep(1)
    
    def _perform_cleanup(self):
        """执行清理任务"""
        logger.info("开始执行定期清理任务")
        
        expired_count = session_manager.cleanup_expired_sessions()
        
        if expired_count > 0:
            logger.info(f"清理了 {expired_count} 个过期会话")
        else:
            logger.info("没有需要清理的过期会话")
    
    def _check_disk_space(self):
        """检查磁盘空间"""
        current_usage_gb = session_manager.get_total_disk_usage() / (1024 ** 3)
        
        if current_usage_gb >= MAX_DISK_USAGE_GB * 0.8:
            logger.warning(f"磁盘使用量达到 {current_usage_gb:.2f}GB，接近限制 {MAX_DISK_USAGE_GB}GB")
            
            if current_usage_gb >= MAX_DISK_USAGE_GB:
                logger.info("磁盘使用量超过限制，开始清理")
                cleaned_count = session_manager.cleanup_disk_space()
                logger.info(f"清理了 {cleaned_count} 个会话以释放磁盘空间")
    
    def manual_cleanup(self, max_age_hours: Optional[int] = None) -> int:
        """手动执行清理
        
        Args:
            max_age_hours: 最大存活小时数
            
        Returns:
            清理的会话数量
        """
        return session_manager.cleanup_expired_sessions(max_age_hours)
    
    def manual_disk_cleanup(self, max_gb: Optional[float] = None) -> int:
        """手动执行磁盘空间清理
        
        Args:
            max_gb: 最大磁盘使用量 (GB)
            
        Returns:
            清理的会话数量
        """
        return session_manager.cleanup_disk_space(max_gb)
    
    def get_status(self) -> dict:
        """获取清理服务状态"""
        return {
            'running': self.running,
            'last_cleanup': self.last_cleanup_time.isoformat() if self.last_cleanup_time else None,
            'last_disk_check': self.last_disk_check_time.isoformat() if self.last_disk_check_time else None,
            'cleanup_interval_seconds': self.cleanup_interval,
            'active_sessions': session_manager.get_active_session_count(),
            'total_disk_usage_gb': session_manager.get_total_disk_usage() / (1024 ** 3),
            'max_disk_usage_gb': MAX_DISK_USAGE_GB
        }


cleanup_service = CleanupService()

def start_cleanup_service():
    """启动清理服务的便捷函数"""
    cleanup_service.start()

def stop_cleanup_service():
    """停止清理服务的便捷函数"""
    cleanup_service.stop()
