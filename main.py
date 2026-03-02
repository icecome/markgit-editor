import os
import uvicorn
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from app.config import ALLOWED_ORIGINS, BLOG_CACHE_PATH, POSTS_PATH, logger
from app.routes import router
from app.cleanup_service import cleanup_service
from app.auth.routes import router as auth_router
from app.version import __version__

from app.auth.rate_limiter import check_rate_limit, check_request_body_size

class CSRFMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # OAuth 相关路径跳过 CSRF 检查
        if request.url.path.startswith('/api/auth/'):
            return await call_next(request)
        
        if request.method in ["POST", "PUT", "DELETE", "PATCH"]:
            origin = request.headers.get("origin", "")
            referer = request.headers.get("referer", "")
            host = request.headers.get("host", "")
            
            allowed_origins = ALLOWED_ORIGINS if ALLOWED_ORIGINS else ["http://localhost:13131"]
            
            # 自动允许同源请求（Origin 或 Referer 与 Host 相同）
            if origin and host:
                origin_host = origin.replace("https://", "").replace("http://", "").split("/")[0]
                if origin_host == host:
                    return await call_next(request)
            
            # 如果没有 origin 和 referer，允许请求通过（可能是直接 API 调用）
            if not origin and not referer:
                return await call_next(request)
            
            if origin:
                if origin not in allowed_origins:
                    logger.warning(f"CSRF 保护：拒绝来自未知 Origin 的请求：{origin}")
                    raise HTTPException(status_code=403, detail="CSRF validation failed: Invalid origin")
            elif referer:
                referer_valid = any(referer.startswith(origin) for origin in allowed_origins)
                if not referer_valid:
                    logger.warning(f"CSRF 保护：拒绝来自未知 Referer 的请求：{referer}")
                    raise HTTPException(status_code=403, detail="CSRF validation failed: Invalid referer")
        
        return await call_next(request)

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """添加安全响应头"""
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['X-XSS-Protection'] = '1; mode=block'
        response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        response.headers['Permissions-Policy'] = 'geolocation=(), microphone=(), camera=()'
        
        if request.url.scheme == 'https':
            response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
        
        if request.url.path.startswith('/api/'):
            response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate'
            response.headers['Pragma'] = 'no-cache'
            response.headers['Expires'] = '0'
        
        return response

class RequestBodySizeLimitMiddleware(BaseHTTPMiddleware):
    """请求体大小限制中间件"""
    async def dispatch(self, request: Request, call_next):
        if request.method in ["POST", "PUT", "PATCH"]:
            content_length = request.headers.get("content-length")
            if content_length:
                try:
                    length = int(content_length)
                    is_valid, error_msg = check_request_body_size(length)
                    if not is_valid:
                        raise HTTPException(status_code=413, detail=error_msg)
                except ValueError:
                    pass
        
        return await call_next(request)

app = FastAPI(
    title="MarkGit Editor API", 
    version=__version__,
    description="一款基于 OAuth 2.0 的现代化 Git 博客在线编辑器"
)

# 初始化速率限制器
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter

# 注册速率限制异常处理器
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

app.add_middleware(CSRFMiddleware)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RequestBodySizeLimitMiddleware)

app.mount("/static", StaticFiles(directory="static"), name="static")

# 先注册 OAuth 路由（优先级更高，避免被通配符路由拦截）
app.include_router(auth_router, prefix="/api")  # OAuth 认证路由
app.include_router(router, prefix="/api")  # 主路由（包含通配符）

@app.get("/")
def root():
    return FileResponse("index.html")

@app.on_event("startup")
def startup_event():
    try:
        if not os.path.exists(BLOG_CACHE_PATH):
            os.makedirs(BLOG_CACHE_PATH, exist_ok=True)
            os.makedirs(os.path.join(BLOG_CACHE_PATH, 'content', 'posts'), exist_ok=True)
            os.makedirs(os.path.join(BLOG_CACHE_PATH, 'archetypes'), exist_ok=True)
            with open(os.path.join(BLOG_CACHE_PATH, 'archetypes', 'posts.md'), 'w', encoding='utf-8') as f:
                f.write('---\ntitle: {{title}}\ndate: {{date}}\ncategories: {{categories}}\n---\n\n')
        
        # 服务器重启时清理所有会话（激进策略）
        from app.session_manager import session_manager
        logger.info("服务器重启，清理所有会话数据...")
        session_manager.cleanup_all_sessions()
        
        cleanup_service.start()
        logger.info("应用启动完成，清理服务已启动")
    except Exception as e:
        logger.error("初始化工作区失败：" + str(e))
        from fastapi import HTTPException
        raise HTTPException(status_code=500, detail="初始化工作区失败")

@app.on_event("shutdown")
def shutdown_event():
    try:
        cleanup_service.stop()
        logger.info("清理服务已停止")
    except Exception as e:
        logger.error("停止清理服务失败：" + str(e))

if __name__ == "__main__":
    port = int(os.getenv('PORT', '13131'))
    uvicorn.run(app, host="127.0.0.1", port=port)
