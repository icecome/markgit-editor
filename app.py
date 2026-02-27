import os
import uvicorn
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from app.config import ALLOWED_ORIGINS, BLOG_CACHE_PATH, POSTS_PATH, logger
from app.routes import router

app = FastAPI(title="MarkGit Editor API", version="1.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="static"), name="static")

app.include_router(router, prefix="/api")

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
        logger.info("应用启动完成")
    except Exception as e:
        logger.error("初始化工作区失败：" + str(e))
        from fastapi import HTTPException
        raise HTTPException(status_code=500, detail="初始化工作区失败")

if __name__ == "__main__":
    port = int(os.getenv('PORT', '13131'))
    uvicorn.run(app, host="127.0.0.1", port=port)
