"""
OAuth 认证路由端点
"""
from fastapi import APIRouter, HTTPException, Header, Body, Response
from typing import Optional, Dict, Any
import uuid
import base64
import io

try:
    import qrcode
    QR_AVAILABLE = True
except ImportError:
    QR_AVAILABLE = False

from app.auth.github_oauth import github_oauth
from app.auth.token_store import token_store
from app.config import logger

router = APIRouter(prefix="/auth", tags=["OAuth"])


def generate_qr_code(uri: str) -> str:
    """生成二维码 Base64 图片"""
    if not QR_AVAILABLE:
        return ""
    
    try:
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(uri)
        qr.make(fit=True)
        
        img = qr.make_image(fill_color="black", back_color="white")
        
        # 转换为 Base64
        buffer = io.BytesIO()
        img.save(buffer, format='PNG')
        buffer.seek(0)
        img_base64 = base64.b64encode(buffer.read()).decode()
        
        return f"data:image/png;base64,{img_base64}"
    except Exception as e:
        logger.error(f"生成二维码失败：{e}")
        return ""


@router.get("/device-code")
async def get_device_code():
    """
    请求设备码
    
    返回:
    {
        "device_code": "xxx",
        "user_code": "ABC-123",
        "verification_uri": "https://github.com/login/device",
        "expires_in": 900,
        "interval": 5,
        "qr_code": "data:image/png;base64,..."  # 二维码
    }
    """
    device_code = await github_oauth.request_device_code()
    
    if not device_code:
        raise HTTPException(status_code=500, detail="无法请求设备码，请检查 GitHub OAuth 配置")
    
    # 生成二维码
    qr_uri = f"{device_code.verification_uri}?user_code={device_code.user_code}"
    qr_code = generate_qr_code(qr_uri)
    
    return {
        "device_code": device_code.device_code,
        "user_code": device_code.user_code,
        "verification_uri": device_code.verification_uri,
        "verification_uri_complete": qr_uri,
        "expires_in": device_code.expires_in,
        "interval": device_code.interval,
        "qr_code": qr_code
    }


@router.post("/token")
async def get_access_token(device_code: str = Body(..., embed=True)):
    """
    轮询获取访问令牌
    
    请求:
    {"device_code": "xxx"}
    
    返回:
    成功:
    {
        "access_token": "gho_xxx",
        "token_type": "bearer",
        "session_id": "xxx"
    }
    
    错误:
    HTTP 400 {"error": "authorization_pending"}
    """
    # 轮询令牌
    access_token, error = await github_oauth.poll_access_token(device_code)
    
    if error == "authorization_pending":
        # 用户尚未授权，继续轮询
        # 获取当前设备码的轮询间隔
        interval = github_oauth.device_codes.get(device_code, type('obj', (object,), {'interval': 5})()).interval
        raise HTTPException(status_code=400, detail="authorization_pending", headers={"X-Interval": str(interval)})
    
    elif error == "access_denied":
        # 用户拒绝授权
        raise HTTPException(status_code=400, detail="access_denied")
    
    elif error == "expired_token":
        # 设备码过期
        raise HTTPException(status_code=400, detail="expired_token")
    
    elif error:
        # 其他错误
        raise HTTPException(status_code=400, detail=error)
    
    if not access_token:
        raise HTTPException(status_code=500, detail="获取令牌失败")
    
    # 生成会话 ID
    session_id = str(uuid.uuid4())
    
    # 存储令牌
    token_ttl = 3600  # 1 小时
    token_store.set(session_id, {
        "access_token": access_token,
        "token_type": "bearer",
        "scope": github_oauth.scope
    }, ttl=token_ttl)
    
    logger.info(f"OAuth 会话已创建：{session_id[:8]}...")
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "session_id": session_id,
        "expires_in": token_ttl
    }


@router.get("/status")
async def get_auth_status(x_session_id: Optional[str] = Header(None)):
    """
    获取当前认证状态
    
    返回:
    {
        "authenticated": true,
        "user": {
            "login": "username",
            "avatar_url": "https://...",
            "name": "User Name"
        },
        "scopes": ["repo", "workflow"]
    }
    """
    if not x_session_id:
        return {"authenticated": False}
    
    # 获取令牌
    token_info = token_store.get(x_session_id)
    if not token_info:
        return {"authenticated": False}
    
    access_token = token_info["access_token"]
    
    # 获取用户信息
    user_info = await github_oauth.get_user_info(access_token)
    
    if not user_info:
        # 令牌可能已失效
        token_store.delete(x_session_id)
        return {"authenticated": False}
    
    return {
        "authenticated": True,
        "user": {
            "login": user_info.get("login", ""),
            "avatar_url": user_info.get("avatar_url", ""),
            "name": user_info.get("name", ""),
            "email": user_info.get("email", "")
        },
        "scopes": token_info.get("scope", "").split(","),
        "expires_at": token_info.get("expires_at")
    }


@router.post("/logout")
async def logout(x_session_id: Optional[str] = Header(None)):
    """
    登出并清除令牌
    """
    if not x_session_id:
        return {"message": "未登录"}
    
    # 获取令牌
    token_info = token_store.get(x_session_id)
    
    if token_info:
        # 尝试撤销令牌
        access_token = token_info["access_token"]
        await github_oauth.revoke_token(access_token)
        
        # 删除本地存储
        token_store.delete(x_session_id)
        logger.info(f"OAuth 会话已登出：{x_session_id[:8]}...")
    
    return {"message": "登出成功"}


@router.get("/user")
async def get_current_user(x_session_id: Optional[str] = Header(None)):
    """
    获取当前登录用户信息
    """
    if not x_session_id:
        raise HTTPException(status_code=401, detail="未登录")
    
    token_info = token_store.get(x_session_id)
    if not token_info:
        raise HTTPException(status_code=401, detail="会话已过期")
    
    access_token = token_info["access_token"]
    user_info = await github_oauth.get_user_info(access_token)
    
    if not user_info:
        raise HTTPException(status_code=401, detail="令牌无效")
    
    return user_info
