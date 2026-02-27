import os
import datetime
import html
import shutil
import asyncio
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import PlainTextResponse

from app.config import POSTS_PATH, BLOG_GIT_SSH, logger
from app.models import ApiResponse
from app.file_service import (
    check_name, get_md_yaml, delete_image_not_included,
    pretty_git_status, read_post_template, get_files_recursive,
    validate_file_path
)
from app.git_service import (
    git_add, git_status, git_commit, pull_updates_async,
    init_local_git_async, sync_branch_name, deploy, sanitize_for_log
)
from app.models import (
    FileCreateRequest, FileSaveRequest, FileRenameRequest,
    FileMoveRequest, FolderCreateRequest, GitRepoRequest, InitRequest
)

router = APIRouter()

@router.get("/health", response_model=ApiResponse)
def health_check():
    return ApiResponse(data={"status": "healthy", "version": "1.1.0"})

@router.get("/files", response_model=ApiResponse)
def get_files():
    from app.config import BLOG_CACHE_PATH
    try:
        if not os.path.exists(BLOG_CACHE_PATH):
            return ApiResponse(data=[])
        files = get_files_recursive(BLOG_CACHE_PATH)
        return ApiResponse(data=files)
    except Exception as e:
        logger.error("获取文件列表失败：" + str(e))
        raise HTTPException(status_code=500, detail="获取文件列表失败：" + str(e))

@router.get("/file/content")
def get_file_content(file_path: str = ""):
    try:
        full_path = validate_file_path(file_path)
        if not os.path.exists(full_path):
            raise HTTPException(status_code=404, detail="文件未找到")
        if os.path.isdir(full_path):
            raise HTTPException(status_code=400, detail="Path is a directory, not a file")
        with open(full_path, 'r', encoding='utf-8') as f:
            content = f.read()
        return PlainTextResponse(content=content)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("获取文件内容失败：" + str(e))
        raise HTTPException(status_code=500, detail="获取文件内容失败：" + str(e))

@router.post("/file/create", response_model=ApiResponse)
async def create_file(request: FileCreateRequest):
    try:
        full_path = validate_file_path(request.path)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, 'w', encoding='utf-8') as f:
            f.write(request.content)
        git_add()
        logger.info("文件已创建：" + request.path)
        return ApiResponse(message="文件创建成功", data={"path": request.path})
    except HTTPException:
        raise
    except Exception as e:
        logger.error("创建文件失败：" + str(e))
        raise HTTPException(status_code=500, detail="创建文件失败：" + str(e))

@router.post("/file/save", response_model=ApiResponse)
async def save_file(request: FileSaveRequest):
    try:
        full_path = validate_file_path(request.path)
        if not os.path.exists(full_path):
            raise HTTPException(status_code=404, detail="文件未找到")
        with open(full_path, 'w', encoding='utf-8') as f:
            f.write(request.content)
        git_add()
        logger.info("文件已保存：" + request.path)
        return ApiResponse(message="文件保存成功")
    except HTTPException:
        raise
    except Exception as e:
        logger.error("保存文件失败：" + str(e))
        raise HTTPException(status_code=500, detail="保存文件失败：" + str(e))

@router.post("/file/rename", response_model=ApiResponse)
async def rename_file(request: FileRenameRequest):
    try:
        if not request.oldPath or not request.newPath:
            raise HTTPException(status_code=400, detail="Both old and new paths are required")
        full_old_path = validate_file_path(request.oldPath)
        full_new_path = validate_file_path(request.newPath)
        if not os.path.exists(full_old_path):
            raise HTTPException(status_code=404, detail="File or directory not found")
        if os.path.exists(full_new_path):
            raise HTTPException(status_code=400, detail="Target path already exists")
        os.rename(full_old_path, full_new_path)
        git_add()
        logger.info("已重命名：" + request.oldPath + " -> " + request.newPath)
        return ApiResponse(message="重命名成功")
    except HTTPException:
        raise
    except Exception as e:
        logger.error("重命名失败：" + str(e))
        raise HTTPException(status_code=500, detail="重命名失败：" + str(e))

@router.delete("/file/delete", response_model=ApiResponse)
async def delete_file(file_path: str = ""):
    try:
        full_path = validate_file_path(file_path)
        if not os.path.exists(full_path):
            raise HTTPException(status_code=404, detail="File or directory not found")
        if os.path.isdir(full_path):
            shutil.rmtree(full_path)
        else:
            os.remove(full_path)
        git_add()
        logger.info("已删除：" + file_path)
        return ApiResponse(message="删除成功")
    except HTTPException:
        raise
    except Exception as e:
        logger.error("删除失败：" + str(e))
        raise HTTPException(status_code=500, detail="删除失败：" + str(e))

@router.post("/file/move", response_model=ApiResponse)
async def move_file(request: FileMoveRequest):
    try:
        if not request.sourcePath or not request.destPath:
            raise HTTPException(status_code=400, detail="Both source and destination paths are required")
        full_source_path = validate_file_path(request.sourcePath)
        full_dest_path = validate_file_path(request.destPath)
        if not os.path.exists(full_source_path):
            raise HTTPException(status_code=404, detail="Source file or directory not found")
        if os.path.exists(full_dest_path):
            raise HTTPException(status_code=400, detail="Destination path already exists")
        os.makedirs(os.path.dirname(full_dest_path), exist_ok=True)
        shutil.move(full_source_path, full_dest_path)
        git_add()
        logger.info("已移动：" + request.sourcePath + " -> " + request.destPath)
        return ApiResponse(message="移动成功")
    except HTTPException:
        raise
    except Exception as e:
        logger.error("移动失败：" + str(e))
        raise HTTPException(status_code=500, detail="移动失败：" + str(e))

@router.post("/folder/create", response_model=ApiResponse)
async def create_folder(request: FolderCreateRequest):
    try:
        full_path = validate_file_path(request.path)
        os.makedirs(full_path, exist_ok=True)
        git_add()
        logger.info("文件夹已创建：" + request.path)
        return ApiResponse(message="文件夹创建成功", data={"path": request.path})
    except HTTPException:
        raise
    except Exception as e:
        logger.error("创建文件夹失败：" + str(e))
        raise HTTPException(status_code=500, detail="创建文件夹失败：" + str(e))

@router.get("/git-repo", response_model=ApiResponse)
def get_git_repo():
    try:
        return ApiResponse(data={"gitRepo": BLOG_GIT_SSH})
    except Exception as e:
        logger.error("获取 git 仓库失败：" + str(e))
        raise HTTPException(status_code=500, detail="获取 git 仓库失败")

@router.post("/git-repo", response_model=ApiResponse)
async def set_git_repo(request: GitRepoRequest):
    try:
        if not request.gitRepo:
            raise HTTPException(status_code=400, detail="Git repo URL is required")
        global BLOG_GIT_SSH
        import app.config as config
        config.BLOG_GIT_SSH = request.gitRepo
        BLOG_GIT_SSH = request.gitRepo
        logger.info("Git 仓库配置已设置：" + sanitize_for_log(request.gitRepo))
        return ApiResponse(message="Git 仓库配置已设置")
    except HTTPException:
        raise
    except Exception as e:
        logger.error("设置 git 仓库失败：" + str(e))
        raise HTTPException(status_code=500, detail="设置 git 仓库失败")

@router.get("/categories", response_model=ApiResponse)
def get_categories():
    try:
        categories = set()
        if not os.path.exists(POSTS_PATH):
            return ApiResponse(data=list(categories))
        for i in os.listdir(POSTS_PATH):
            post_yaml = get_md_yaml(os.path.join(POSTS_PATH, i, 'index.md'))
            if post_yaml:
                for item in post_yaml.get('categories', []):
                    categories.add(item)
        return ApiResponse(data=list(categories))
    except Exception as e:
        logger.error("获取分类失败：" + str(e))
        raise HTTPException(status_code=500, detail="获取分类失败")

@router.get("/posts/changes", response_model=ApiResponse)
def get_post_changes():
    try:
        delete_image_not_included()
        git_add()
        status_result_for_show = pretty_git_status(git_status())
        return ApiResponse(data=status_result_for_show)
    except Exception as e:
        logger.error("获取帖子更改失败：" + str(e))
        raise HTTPException(status_code=500, detail="获取帖子更改失败")

@router.get("/posts", response_model=ApiResponse)
def get_posts():
    try:
        posts = {}
        if not os.path.exists(POSTS_PATH):
            return ApiResponse(data=posts)
        for i in os.listdir(POSTS_PATH):
            post_yaml = get_md_yaml(os.path.join(POSTS_PATH, i, 'index.md'))
            if post_yaml:
                posts[i] = {
                    'dirName': i,
                    'title': post_yaml.get('title', i)
                }
            else:
                posts[i] = {
                    'dirName': i,
                    'title': i
                }
        return ApiResponse(data=posts)
    except Exception as e:
        logger.error("获取帖子失败：" + str(e))
        raise HTTPException(status_code=500, detail="获取帖子失败")

@router.post("/post/create", response_model=ApiResponse)
def create_post():
    try:
        now = datetime.datetime.now(tz=datetime.timezone(datetime.timedelta(hours=8)))
        post_dir_name = now.strftime('%Y%m%d%H%M%S')
        os.makedirs(os.path.join(POSTS_PATH, post_dir_name), exist_ok=True)
        template = read_post_template()
        template = template.replace('{{title}}', post_dir_name)
        template = template.replace('{{date}}', now.isoformat())
        template = template.replace('{{categories}}', '[]')
        with open(os.path.join(POSTS_PATH, post_dir_name, 'index.md'), mode='w', encoding='utf-8') as f:
            f.write(template)
        git_add()
        logger.info("新帖子已创建：" + post_dir_name)
        return ApiResponse(data={'dirName': post_dir_name})
    except Exception as e:
        logger.error("创建帖子失败：" + str(e))
        raise HTTPException(status_code=500, detail="创建帖子失败")

@router.get("/post/{filename}")
def get_post(filename: str):
    try:
        check_name(filename)
        md_path = os.path.join(POSTS_PATH, filename, 'index.md')
        if os.path.isfile(md_path):
            with open(md_path, 'r', encoding='utf-8') as f:
                content = f.read()
            return PlainTextResponse(content=content)
        raise HTTPException(status_code=404, detail="Post not found")
    except HTTPException:
        raise
    except Exception as e:
        logger.error("获取帖子失败：" + str(e))
        raise HTTPException(status_code=500, detail="获取帖子失败")

@router.delete("/post/{filename}", response_model=ApiResponse)
def delete_post(filename: str):
    try:
        check_name(filename)
        post_path = os.path.join(POSTS_PATH, filename)
        if os.path.exists(post_path):
            shutil.rmtree(post_path, ignore_errors=True)
            git_add()
            logger.info("帖子已删除：" + filename)
            return ApiResponse(message="帖子已删除")
        raise HTTPException(status_code=404, detail="帖子未找到")
    except HTTPException:
        raise
    except Exception as e:
        logger.error("删除帖子失败：" + str(e))
        raise HTTPException(status_code=500, detail="删除帖子失败")

@router.post("/post/{filename}", response_model=ApiResponse)
async def save_post(filename: str, request: Request):
    try:
        check_name(filename)
        post_path = os.path.join(POSTS_PATH, filename)
        if not os.path.exists(post_path):
            raise HTTPException(status_code=404, detail="Post not found")
        content = await request.body()
        content_str = content.decode('utf-8')
        md_path = os.path.join(post_path, 'index.md')
        with open(md_path, mode='w', encoding='utf-8') as f:
            f.write(html.unescape(content_str))
        logger.info("帖子已保存：" + filename)
        return ApiResponse(message="帖子已保存")
    except HTTPException:
        raise
    except Exception as e:
        logger.error("保存帖子失败：" + str(e))
        raise HTTPException(status_code=500, detail="保存帖子失败")

git_operation_lock = asyncio.Lock()

@router.post("/init", response_model=ApiResponse)
async def init_workspace(request: InitRequest):
    async with git_operation_lock:
        try:
            if request.gitRepo:
                import app.config as config
                config.BLOG_GIT_SSH = request.gitRepo
                global BLOG_GIT_SSH
                BLOG_GIT_SSH = request.gitRepo
            result = await init_local_git_async()
            logger.info("工作区初始化成功")
            return ApiResponse(message=result.get("message", "初始化成功"), data=result)
        except HTTPException:
            raise
        except Exception as e:
            logger.error("初始化工作区失败：" + str(e))
            raise HTTPException(status_code=500, detail="初始化失败：" + str(e))
        finally:
            try:
                sync_branch_name()
            except Exception as e:
                logger.warning("同步分支名称失败：" + str(e))

@router.post("/pull", response_model=ApiResponse)
async def pull_repo():
    async with git_operation_lock:
        try:
            await pull_updates_async()
            logger.info("已成功拉取最新更改")
            return ApiResponse(message="拉取成功")
        except HTTPException:
            raise
        except Exception as e:
            logger.error("拉取更新失败：" + str(e))
            raise HTTPException(status_code=500, detail="拉取失败：" + str(e))

@router.post("/reset", response_model=ApiResponse)
async def reset():
    from app.config import BLOG_CACHE_PATH
    async with git_operation_lock:
        try:
            if os.path.exists(BLOG_CACHE_PATH):
                backup_path = BLOG_CACHE_PATH + "_backup"
                shutil.rmtree(backup_path, ignore_errors=True)
                try:
                    shutil.copytree(BLOG_CACHE_PATH, backup_path, dirs_exist_ok=True)
                except Exception as backup_error:
                    logger.warning("备份失败，继续重置：" + str(backup_error))
            await init_local_git_async()
            logger.info("工作区重置完成")
            return ApiResponse(message="工作区重置完成")
        except HTTPException:
            raise
        except Exception as e:
            logger.error("重置工作区失败：" + str(e))
            raise HTTPException(status_code=500, detail="重置工作区失败")

@router.post("/soft_reset", response_model=ApiResponse)
async def soft_reset():
    async with git_operation_lock:
        try:
            await pull_updates_async()
            logger.info("工作区软重置完成")
            return ApiResponse(message="工作区软重置完成")
        except HTTPException:
            raise
        except Exception as e:
            logger.error("软重置工作区失败：" + str(e))
            raise HTTPException(status_code=500, detail="软重置工作区失败")

@router.post("/commit", response_model=ApiResponse)
async def commit():
    async with git_operation_lock:
        try:
            git_commit()
            logger.info("更改已提交并推送")
            return ApiResponse(message="更改已提交并推送")
        except HTTPException:
            raise
        except Exception as e:
            logger.error("提交更改失败：" + str(e))
            raise HTTPException(status_code=500, detail="提交更改失败")

@router.post("/redeploy", response_model=ApiResponse)
def redeploy():
    try:
        deploy()
        logger.info("重新部署已触发")
        return ApiResponse(message="重新部署已触发")
    except HTTPException:
        raise
    except Exception as e:
        logger.error("重新部署失败：" + str(e))
        raise HTTPException(status_code=500, detail="重新部署失败")

@router.get("/{dir_name}/{file_name}")
def get_file(dir_name: str, file_name: str):
    from fastapi.responses import FileResponse
    try:
        check_name(dir_name)
        file_path = os.path.join(POSTS_PATH, dir_name, file_name)
        if os.path.exists(file_path):
            return FileResponse(file_path)
        raise HTTPException(status_code=404, detail="文件未找到")
    except HTTPException:
        raise
    except Exception as e:
        logger.error("获取文件失败：" + str(e))
        raise HTTPException(status_code=500, detail="获取文件失败")
