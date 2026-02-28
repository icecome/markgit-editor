import os
import uvicorn
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from app.config import ALLOWED_ORIGINS, BLOG_CACHE_PATH, POSTS_PATH, logger
from app.routes import router
from app.cleanup_service import cleanup_service
from app.auth.routes import router as auth_router

app = FastAPI(title="MarkGit Editor API", version="1.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

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
