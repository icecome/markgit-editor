import os
import traceback
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

from app.config import ALLOWED_ORIGINS, BLOG_CACHE_PATH, POSTS_PATH, logger, is_production
from app.routes import router
from app.cleanup_service import cleanup_service
from app.auth.routes import router as auth_router
from app.version import __version__

from app.auth.rate_limiter import check_rate_limit, check_request_body_size

class CSRFMiddleware(BaseHTTPMiddleware):
    """CSRF 保护中间件 - 简化版本，只检查敏感的 POST 请求"""
    
    # 需要严格 CSRF 检查的敏感操作
    STRICT_CSRF_PATHS = [
        '/api/git-repo', '/api/init', '/api/pull', '/api/commit', 
        '/api/reset', '/api/redeploy', '/api/auth/logout'
    ]
    
    async def dispatch(self, request: Request, call_next):
        # 只对 POST/PUT/DELETE/PATCH 请求进行 CSRF 检查
        if request.method not in ["POST", "PUT", "DELETE", "PATCH"]:
            return await call_next(request)
        
        path = request.url.path
        
        # 检查是否是需要严格 CSRF 检查的路径
        needs_strict_csrf = any(path == sp or path.startswith(sp + '/') for sp in self.STRICT_CSRF_PATHS)
        
        if not needs_strict_csrf:
            # 非敏感操作，直接通过
            return await call_next(request)
        
        # 敏感操作：检查 Origin 或 Referer
        origin = request.headers.get("origin", "")
        referer = request.headers.get("referer", "")
        host = request.headers.get("host", "")
        x_requested_with = request.headers.get("x-requested-with", "")
        
        allowed_origins = ALLOWED_ORIGINS if ALLOWED_ORIGINS else ["http://localhost:13131"]
        
        # AJAX 请求允许通过
        if x_requested_with.lower() == 'xmlhttprequest':
            return await call_next(request)
        
        # 同源请求允许通过
        if origin and host:
            origin_host = origin.replace("https://", "").replace("http://", "").split("/")[0]
            if origin_host == host:
                return await call_next(request)
        
        # 检查 Origin 是否在允许列表中
        if origin:
            if origin in allowed_origins:
                return await call_next(request)
            logger.warning(f"CSRF 保护：拒绝来自未知 Origin 的请求：{origin}")
            raise HTTPException(status_code=403, detail="CSRF validation failed: Invalid origin")
        
        # 检查 Referer 是否在允许列表中
        if referer:
            referer_valid = any(referer.startswith(allowed_origin) for allowed_origin in allowed_origins)
            if referer_valid:
                return await call_next(request)
            logger.warning(f"CSRF 保护：拒绝来自未知 Referer 的请求：{referer}")
            raise HTTPException(status_code=403, detail="CSRF validation failed: Invalid referer")
        
        # 敏感操作必须有 Origin 或 Referer
        logger.warning(f"CSRF 保护：敏感操作缺少 Origin/Referer 头，路径：{path}")
        raise HTTPException(status_code=403, detail="CSRF validation failed: Missing origin/referer")

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

API_VERSION = "v1"

# 初始化速率限制器
# 注意：设置 config_filename="" 禁用自动读取 .env 文件
# 因为我们已经通过 load_dotenv(encoding='utf-8') 加载了配置
# 这样可以避免 starlette.config.Config 使用默认编码读取 .env 文件导致的编码问题
limiter = Limiter(key_func=get_remote_address, config_filename="")
app.state.limiter = limiter
app.state.api_version = API_VERSION

# 注册速率限制异常处理器
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# 注册全局异常处理器
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """全局异常处理器 - 防止敏感信息泄露"""
    error_id = id(exc)
    
    if isinstance(exc, HTTPException):
        logger.warning(f"HTTP异常 [{error_id}]: {exc.status_code} - {exc.detail}")
        return JSONResponse(
            status_code=exc.status_code,
            content={"code": exc.status_code, "message": str(exc.detail), "data": None}
        )
    
    logger.error(f"未处理异常 [{error_id}]: {type(exc).__name__}: {str(exc)}")
    logger.debug(f"异常堆栈 [{error_id}]:\n{traceback.format_exc()}")
    
    if is_production:
        return JSONResponse(
            status_code=500,
            content={"code": 500, "message": "服务器内部错误，请稍后重试", "data": None}
        )
    else:
        return JSONResponse(
            status_code=500,
            content={"code": 500, "message": f"{type(exc).__name__}: {str(exc)}", "data": None}
        )

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

# API 路由注册（保持向后兼容）
# 新版本 API：/api/v1/xxx
# 旧版本 API：/api/xxx（保持兼容）
app.include_router(auth_router, prefix="/api")  # OAuth 认证路由（旧版兼容）
app.include_router(router, prefix="/api")  # 主路由（旧版兼容）
app.include_router(auth_router, prefix=f"/api/{API_VERSION}")  # OAuth 认证路由（新版）
app.include_router(router, prefix=f"/api/{API_VERSION}")  # 主路由（新版）

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
