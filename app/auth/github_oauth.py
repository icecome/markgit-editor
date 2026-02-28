"""
GitHub OAuth 2.0 设备授权流服务
RFC 8628 Device Authorization Grant
"""
import os
import httpx
from typing import Dict, Optional, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass

from app.config import logger


@dataclass
class DeviceCode:
    """设备码信息"""
    device_code: str
    user_code: str
    verification_uri: str
    expires_in: int
    interval: int
    created_at: datetime
    status: str = "pending"  # pending, authorized, expired, denied


class GitHubOAuthService:
    """GitHub OAuth 服务"""
    
    def __init__(self):
        self.client_id = os.getenv("GITHUB_CLIENT_ID", "")
        self.client_secret = os.getenv("GITHUB_CLIENT_SECRET", "")
        
        # 请求的权限范围
        self.scope = os.getenv("GITHUB_SCOPE", "repo workflow")
        
        logger.info(f"GitHub Client ID: {self.client_id[:8] if self.client_id else 'None'}...")
        logger.info(f"GitHub Client Secret: {'*' * 8 if self.client_secret else 'None'}")
        logger.info(f"GitHub Scope: {self.scope}")
        
        # GitHub OAuth 端点
        self.device_code_url = "https://github.com/login/device/code"
        self.access_token_url = "https://github.com/login/oauth/access_token"
        self.user_info_url = "https://api.github.com/user"
        
        if not self.client_id or not self.client_secret:
            logger.error("GitHub OAuth 配置缺失，请在 .env 中设置 GITHUB_CLIENT_ID 和 GITHUB_CLIENT_SECRET")
        
        # 设备码存储（内存）
        self.device_codes: Dict[str, DeviceCode] = {}
    
    async def request_device_code(self) -> Optional[DeviceCode]:
        """
        向 GitHub 请求设备码
        
        Returns:
            DeviceCode 对象，如果失败返回 None
        """
        if not self.client_id:
            logger.error("GitHub Client ID 未配置")
            return None
        
        try:
            logger.info(f"正在请求新的设备码，Client ID: {self.client_id[:8]}...")
            
            async with httpx.AsyncClient(verify=False) as client:
                response = await client.post(
                    self.device_code_url,
                    data={
                        "client_id": self.client_id,
                        "scope": self.scope
                    },
                    headers={
                        "Accept": "application/json",
                        "User-Agent": "MarkGit-Editor"
                    },
                    timeout=10.0
                )
            
            if response.status_code != 200:
                logger.error(f"请求设备码失败：{response.status_code} - {response.text}")
                return None
            
            data = response.json()
            logger.info(f"GitHub 返回设备码：user_code={data.get('user_code')}, expires_in={data.get('expires_in')}秒")
            
            device_code = DeviceCode(
                device_code=data['device_code'],
                user_code=data['user_code'],
                verification_uri=data['verification_uri'],
                expires_in=data['expires_in'],
                interval=data.get('interval', 5),
                created_at=datetime.now()
            )
            
            self.device_codes[device_code.device_code] = device_code
            
            logger.info(f"新设备码已创建：{device_code.user_code}")
            return device_code
            
        except httpx.RequestError as e:
            logger.error(f"请求设备码异常：{e}")
            return None
        except KeyError as e:
            logger.error(f"GitHub 响应格式异常，缺少字段：{e}")
            return None
        except Exception as e:
            logger.error(f"请求设备码异常：{e}")
            import traceback
            logger.error(traceback.format_exc())
            return None
    
    async def poll_access_token(self, device_code: str) -> Tuple[Optional[str], str]:
        """
        轮询获取访问令牌
        
        Args:
            device_code: 设备码
            
        Returns:
            (access_token, error) 元组
            - 成功：(token, "")
            - 授权中：(None, "authorization_pending")
            - 拒绝：(None, "access_denied")
            - 过期：(None, "expired_token")
        """
        if device_code not in self.device_codes:
            return None, "invalid_device"
        
        dc = self.device_codes[device_code]
        
        # 检查是否过期
        if datetime.now() > dc.created_at + timedelta(seconds=dc.expires_in):
            dc.status = "expired"
            del self.device_codes[device_code]
            return None, "expired_token"
        
        # 检查是否已被拒绝
        if dc.status == "denied":
            return None, "access_denied"
        
        try:
            # 同样需要跳过 SSL 验证（开发环境）
            try:
                async with httpx.AsyncClient(verify=False) as client:
                    response = await client.post(
                        self.access_token_url,
                        data={
                            "client_id": self.client_id,
                            "client_secret": self.client_secret,
                            "device_code": device_code,
                            "grant_type": "urn:ietf:params:oauth:grant-type:device_code"
                        },
                        headers={
                            "Accept": "application/json",
                            "User-Agent": "MarkGit-Editor"
                        },
                        timeout=10.0
                    )
            except Exception as e:
                logger.warning(f"SSL 验证失败，使用默认配置：{e}")
                async with httpx.AsyncClient() as client:
                    response = await client.post(
                        self.access_token_url,
                        data={
                            "client_id": self.client_id,
                            "client_secret": self.client_secret,
                            "device_code": device_code,
                            "grant_type": "urn:ietf:params:oauth:grant-type:device_code"
                        },
                        headers={
                            "Accept": "application/json",
                            "User-Agent": "MarkGit-Editor"
                        },
                        timeout=10.0
                    )
            
            # 解析响应
            data = response.json()
            logger.info(f"GitHub 响应数据：{data.keys() if isinstance(data, dict) else '非字典格式'}")
            
            # 先检查是否有错误（即使状态码是 200）
            if "error" in data:
                error = data.get("error", "unknown")
                
                if error == "authorization_pending":
                    return None, "authorization_pending"
                elif error == "access_denied":
                    dc.status = "denied"
                    del self.device_codes[device_code]
                    return None, "access_denied"
                elif error == "expired_token":
                    dc.status = "expired"
                    del self.device_codes[device_code]
                    return None, "expired_token"
                elif error == "slow_down":
                    # GitHub 要求降低轮询频率
                    new_interval = data.get("interval", 15)
                    dc.interval = new_interval
                    logger.warning(f"GitHub 要求降低轮询频率，新间隔：{new_interval}秒")
                    return None, "authorization_pending"
                else:
                    logger.error(f"轮询令牌失败：{error} - {data.get('error_description', '')}")
                    return None, error
            
            # 检查访问令牌
            if "access_token" in data:
                # 授权成功
                dc.status = "authorized"
                # 隐藏 token 信息，只显示前缀
                token_prefix = data['access_token'][:10] + '...' if len(data['access_token']) > 10 else '***'
                logger.info(f"获取访问令牌成功：{data['token_type']} (token: {token_prefix})")
                return data['access_token'], ""
            else:
                logger.error(f"响应中无访问令牌：{data}")
                return None, "unknown_error"
                
        except httpx.RequestError as e:
            logger.error(f"轮询令牌异常：{e}")
            return None, "network_error"
        except Exception as e:
            logger.error(f"轮询令牌异常：{e}")
            return None, "unknown_error"
    
    async def get_user_info(self, access_token: str) -> Optional[Dict]:
        """
        使用访问令牌获取用户信息
        
        Args:
            access_token: GitHub 访问令牌
            
        Returns:
            用户信息字典，失败返回 None
        """
        try:
            # 跳过 SSL 验证（开发环境）
            try:
                async with httpx.AsyncClient(verify=False) as client:
                    response = await client.get(
                        self.user_info_url,
                        headers={
                            "Authorization": f"token {access_token}",
                            "Accept": "application/json",
                            "User-Agent": "MarkGit-Editor"
                        },
                        timeout=10.0
                    )
            except Exception as e:
                logger.warning(f"SSL 验证失败，使用默认配置：{e}")
                async with httpx.AsyncClient() as client:
                    response = await client.get(
                        self.user_info_url,
                        headers={
                            "Authorization": f"token {access_token}",
                            "Accept": "application/json",
                            "User-Agent": "MarkGit-Editor"
                        },
                        timeout=10.0
                    )
            
            if response.status_code != 200:
                logger.error(f"获取用户信息失败：{response.status_code}")
                return None
            
            return response.json()
            
        except Exception as e:
            logger.error(f"获取用户信息异常：{e}")
            return None
    
    async def revoke_token(self, access_token: str) -> bool:
        """
        撤销访问令牌
        
        Args:
            access_token: GitHub 访问令牌
            
        Returns:
            是否成功撤销
        """
        if not self.client_id or not self.client_secret:
            return False
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.delete(
                    f"https://api.github.com/applications/{self.client_id}/grant",
                    auth=(self.client_id, self.client_secret),
                    json={"access_token": access_token},
                    timeout=10.0
                )
                
                return response.status_code == 204
                
        except Exception as e:
            logger.error(f"撤销令牌异常：{e}")
            return False
    
    def cleanup_expired_codes(self):
        """清理过期的设备码"""
        now = datetime.now()
        expired = [
            dc for dc in self.device_codes.values()
            if now > dc.created_at + timedelta(seconds=dc.expires_in)
        ]
        
        for dc in expired:
            del self.device_codes[dc.device_code]
        
        if expired:
            logger.info(f"清理了 {len(expired)} 个过期设备码")


# 全局 OAuth 服务实例
github_oauth = GitHubOAuthService()
