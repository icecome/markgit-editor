"""
异常处理工具模块
提供统一的异常处理装饰器和错误响应格式
"""
import functools
import logging
from typing import Callable, Optional
from fastapi import HTTPException

logger = logging.getLogger(__name__)


class APIError(Exception):
    """API 错误基类"""
    def __init__(self, message: str, code: int = 500, detail: Optional[str] = None):
        self.message = message
        self.code = code
        self.detail = detail
        super().__init__(self.message)


class NotFoundError(APIError):
    """资源未找到错误"""
    def __init__(self, message: str = "资源未找到"):
        super().__init__(message, code=404)


class ValidationError(APIError):
    """验证错误"""
    def __init__(self, message: str = "参数验证失败"):
        super().__init__(message, code=400)


class AuthError(APIError):
    """认证错误"""
    def __init__(self, message: str = "认证失败"):
        super().__init__(message, code=401)


class ForbiddenError(APIError):
    """权限错误"""
    def __init__(self, message: str = "权限不足"):
        super().__init__(message, code=403)


def handle_api_errors(func: Callable) -> Callable:
    """
    API 错误处理装饰器
    统一处理异常，记录日志，返回标准错误响应
    """
    @functools.wraps(func)
    async def async_wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except HTTPException:
            raise
        except APIError as e:
            logger.warning(f"API 错误 [{func.__name__}]: {e.message}")
            raise HTTPException(status_code=e.code, detail=e.message)
        except ValueError as e:
            logger.warning(f"参数错误 [{func.__name__}]: {str(e)}")
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            logger.error(f"未处理异常 [{func.__name__}]: {type(e).__name__}: {str(e)}")
            raise HTTPException(status_code=500, detail="服务器内部错误，请稍后重试")
    
    @functools.wraps(func)
    def sync_wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except HTTPException:
            raise
        except APIError as e:
            logger.warning(f"API 错误 [{func.__name__}]: {e.message}")
            raise HTTPException(status_code=e.code, detail=e.message)
        except ValueError as e:
            logger.warning(f"参数错误 [{func.__name__}]: {str(e)}")
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            logger.error(f"未处理异常 [{func.__name__}]: {type(e).__name__}: {str(e)}")
            raise HTTPException(status_code=500, detail="服务器内部错误，请稍后重试")
    
    if asyncio.iscoroutinefunction(func):
        return async_wrapper
    return sync_wrapper


import asyncio
