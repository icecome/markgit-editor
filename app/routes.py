import os
import datetime
import html
import shutil
import asyncio
from fastapi import APIRouter, HTTPException, Request, Header
from fastapi.responses import PlainTextResponse
from typing import Optional

from app.config import POSTS_PATH, BLOG_GIT_SSH, BLOG_CACHE_PATH, DEFAULT_WHITELIST_EXTENSIONS, logger
from app.models import ApiResponse
from app.file_service import (
    check_name, get_md_yaml, delete_image_not_included,
    pretty_git_status, read_post_template, get_files_recursive,
    validate_file_path, should_exclude_file
)
from app.git_service import (
    git_add, git_status, git_commit, pull_updates_async,
    init_local_git_async, sync_branch_name, deploy, sanitize_for_log,
    set_current_session_path
)
from app.session_manager import session_manager
from app.models import (
    FileCreateRequest, FileSaveRequest, FileRenameRequest,
    FileMoveRequest, FolderCreateRequest, GitRepoRequest, InitRequest
)

router = APIRouter()

def get_session_path(session_id: Optional[str] = None) -> str:
    """获取会话路径，如果未提供 session_id 则返回全局缓存路径"""
    if session_id:
        path = session_manager.get_session_path(session_id)
        if path:
            return path
    return BLOG_CACHE_PATH

def setup_git_context(session_id: Optional[str] = None):
    """设置 Git 操作上下文（会话路径）"""
    base_path = get_session_path(session_id)
    set_current_session_path(base_path)

@router.get("/health", response_model=ApiResponse)
def health_check():
    return ApiResponse(data={"status": "healthy", "version": "1.1.0"})

@router.get("/files", response_model=ApiResponse)
def get_files(x_session_id: Optional[str] = Header(None), 
              x_exclude_patterns: Optional[str] = Header(None),
              x_simple_patterns: Optional[str] = Header(None),
              x_use_whitelist: Optional[str] = Header(None),
              x_whitelist_exceptions: Optional[str] = Header(None)):
    """获取文件列表，支持多用户隔离和文件排除
    
    Args:
        x_session_id: 可选的会话 ID 头，用于标识用户会话
        x_exclude_patterns: 可选的正则表达式排除规则，JSON 数组格式
        x_simple_patterns: 可选的简单模式排除规则，JSON 数组格式
        x_use_whitelist: 是否使用白名单模式，"true" 或 "false"
        x_whitelist_exceptions: 可选的白名单例外规则，JSON 数组格式
    """
    try:
        # 如果提供了会话 ID 但无效，返回空列表（前端应创建新会话）
        if x_session_id and not session_manager.is_session_valid(x_session_id):
            logger.warning(f"无效的会话 ID: {x_session_id[:8] if x_session_id else 'None'}...")
            return ApiResponse(data=[], message="会话已过期，请刷新页面")
        
        base_path = get_session_path(x_session_id)
        if not base_path or not os.path.exists(base_path):
            return ApiResponse(data=[])
        
        # 解析正则表达式排除规则
        exclude_patterns = []
        if x_exclude_patterns:
            try:
                import json
                exclude_patterns = json.loads(x_exclude_patterns)
                if not isinstance(exclude_patterns, list):
                    exclude_patterns = []
            except json.JSONDecodeError as e:
                logger.warning(f"解析正则排除规则失败：{e}")
                exclude_patterns = []
        
        # 解析简单模式排除规则
        simple_patterns = []
        if x_simple_patterns:
            try:
                import json
                simple_patterns = json.loads(x_simple_patterns)
                if not isinstance(simple_patterns, list):
                    simple_patterns = []
            except json.JSONDecodeError as e:
                logger.warning(f"解析简单排除规则失败：{e}")
                simple_patterns = []
        
        # 解析白名单设置
        use_whitelist = x_use_whitelist and x_use_whitelist.lower() == 'true'
        whitelist_extensions = DEFAULT_WHITELIST_EXTENSIONS if use_whitelist else None
        
        # 解析白名单例外规则
        whitelist_exceptions = []
        if x_whitelist_exceptions:
            try:
                import json
                whitelist_exceptions = json.loads(x_whitelist_exceptions)
                if not isinstance(whitelist_exceptions, list):
                    whitelist_exceptions = []
            except json.JSONDecodeError as e:
                logger.warning(f"解析白名单例外失败：{e}")
                whitelist_exceptions = []
        
        files = get_files_recursive(
            base_path, 
            exclude_patterns=exclude_patterns,
            simple_patterns=simple_patterns,
            use_whitelist=use_whitelist,
            whitelist_extensions=whitelist_extensions,
            whitelist_exceptions=whitelist_exceptions
        )
        return ApiResponse(data=files)
    except Exception as e:
        logger.error("获取文件列表失败：" + str(e))
        raise HTTPException(status_code=500, detail="获取文件列表失败：" + str(e))

@router.get("/file/content")
def get_file_content(file_path: str = "", x_session_id: Optional[str] = Header(None)):
    try:
        base_path = get_session_path(x_session_id)
        full_path = validate_file_path(file_path, base_path=base_path)
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
async def create_file(request: FileCreateRequest, x_session_id: Optional[str] = Header(None)):
    try:
        base_path = get_session_path(x_session_id)
        setup_git_context(x_session_id)
        full_path = validate_file_path(request.path, base_path=base_path)
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
async def save_file(request: FileSaveRequest, x_session_id: Optional[str] = Header(None)):
    try:
        base_path = get_session_path(x_session_id)
        setup_git_context(x_session_id)
        full_path = validate_file_path(request.path, base_path=base_path)
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
async def rename_file(request: FileRenameRequest, x_session_id: Optional[str] = Header(None)):
    try:
        if not request.oldPath or not request.newPath:
            raise HTTPException(status_code=400, detail="Both old and new paths are required")
        base_path = get_session_path(x_session_id)
        setup_git_context(x_session_id)
        full_old_path = validate_file_path(request.oldPath, base_path=base_path)
        full_new_path = validate_file_path(request.newPath, base_path=base_path)
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
async def delete_file(file_path: str = "", x_session_id: Optional[str] = Header(None)):
    try:
        base_path = get_session_path(x_session_id)
        setup_git_context(x_session_id)
        full_path = validate_file_path(file_path, base_path=base_path)
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
async def move_file(request: FileMoveRequest, x_session_id: Optional[str] = Header(None)):
    try:
        if not request.sourcePath or not request.destPath:
            raise HTTPException(status_code=400, detail="Both source and destination paths are required")
        base_path = get_session_path(x_session_id)
        setup_git_context(x_session_id)
        full_source_path = validate_file_path(request.sourcePath, base_path=base_path)
        full_dest_path = validate_file_path(request.destPath, base_path=base_path)
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
async def create_folder(request: FolderCreateRequest, x_session_id: Optional[str] = Header(None)):
    try:
        base_path = get_session_path(x_session_id)
        setup_git_context(x_session_id)
        full_path = validate_file_path(request.path, base_path=base_path)
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
def get_git_repo(x_session_id: Optional[str] = Header(None)):
    """获取 Git 仓库配置，优先返回会话级别的配置"""
    try:
        if x_session_id:
            session_git_repo = session_manager.get_session_git_repo(x_session_id)
            if session_git_repo:
                return ApiResponse(data={"gitRepo": session_git_repo})
        return ApiResponse(data={"gitRepo": BLOG_GIT_SSH})
    except Exception as e:
        logger.error("获取 git 仓库失败：" + str(e))
        raise HTTPException(status_code=500, detail="获取 git 仓库失败")

@router.post("/git-repo", response_model=ApiResponse)
async def set_git_repo(request: GitRepoRequest, x_session_id: Optional[str] = Header(None)):
    """设置 Git 仓库配置，支持会话级别配置"""
    try:
        if not request.gitRepo:
            raise HTTPException(status_code=400, detail="Git repo URL is required")
        
        if x_session_id:
            session_manager.update_session_git_repo(x_session_id, request.gitRepo)
            logger.info(f"会话 {x_session_id[:8]}... Git 仓库配置已设置：" + sanitize_for_log(request.gitRepo))
        else:
            global BLOG_GIT_SSH
            import app.config as config
            config.BLOG_GIT_SSH = request.gitRepo
            BLOG_GIT_SSH = request.gitRepo
            logger.info("全局 Git 仓库配置已设置：" + sanitize_for_log(request.gitRepo))
        
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
def get_post_changes(x_session_id: Optional[str] = Header(None)):
    try:
        # 设置会话上下文
        setup_git_context(x_session_id)
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

@router.get("/session/create", response_model=ApiResponse)
def create_session(x_user_id: Optional[str] = Header(None)):
    """创建新的用户会话
    
    Args:
        x_user_id: 可选的用户 ID 头，用于标识用户（单用户单会话策略）
    """
    try:
        # 如果有 user_id，清理该用户的旧会话
        clean_old = x_user_id is not None
        session_id, session_path = session_manager.create_session(
            user_id=x_user_id, 
            clean_old=clean_old
        )
        logger.info(f"创建新会话：{session_id[:8]}... 用户：{x_user_id[:8] if x_user_id else 'anonymous'}...")
        return ApiResponse(
            message="会话创建成功",
            data={
                "sessionId": session_id,
                "sessionPath": session_path,
                "userId": x_user_id or session_id
            }
        )
    except Exception as e:
        logger.error("创建会话失败：" + str(e))
        raise HTTPException(status_code=500, detail="创建会话失败：" + str(e))

@router.get("/session/status", response_model=ApiResponse)
def get_session_status(x_session_id: Optional[str] = Header(None)):
    """获取会话状态"""
    try:
        if not x_session_id:
            return ApiResponse(data={"initialized": False, "hasRemote": False})
        
        session = session_manager.get_session(x_session_id)
        if not session:
            return ApiResponse(data={"initialized": False, "hasRemote": False})
        
        session_path = session['path']
        has_git = os.path.exists(os.path.join(session_path, '.git'))
        has_remote = False
        
        if has_git:
            try:
                import subprocess
                remote_result = subprocess.run(
                    ['git', 'remote', '-v'],
                    cwd=session_path,
                    capture_output=True,
                    text=True
                )
                has_remote = 'origin' in remote_result.stdout
            except:
                pass
        
        return ApiResponse(data={
            "initialized": has_git,
            "hasRemote": has_remote,
            "sessionPath": session_path,
            "userId": session.get('user_id', '')
        })
    except Exception as e:
        logger.error("获取会话状态失败：" + str(e))
        raise HTTPException(status_code=500, detail="获取会话状态失败：" + str(e))

@router.get("/session/user-id", response_model=ApiResponse)
def get_user_id():
    """生成或获取用户 ID（用于浏览器指纹识别）"""
    try:
        import uuid
        user_id = str(uuid.uuid4())
        # 这里只是生成一个新的 user_id，实际使用时会保存到 cookie
        return ApiResponse(data={"userId": user_id})
    except Exception as e:
        logger.error("生成用户 ID 失败：" + str(e))
        raise HTTPException(status_code=500, detail="生成用户 ID 失败：" + str(e))

@router.post("/init", response_model=ApiResponse)
async def init_workspace(request: InitRequest, x_session_id: Optional[str] = Header(None),
                         x_oauth_session_id: Optional[str] = Header(None)):
    """初始化工作区，支持多用户隔离
    
    初始化策略:
    1. 如果已有 Git 仓库且有远程配置，返回 connected 状态
    2. 如果已有 Git 仓库但无远程配置，允许重新初始化或连接
    3. 如果本地有文件但无 Git 仓库，保留文件并连接远程仓库
    4. 如果本地无文件，克隆远程仓库或创建空仓库
    """
    async with git_operation_lock:
        try:
            base_path = get_session_path(x_session_id)
            
            if request.gitRepo:
                import app.config as config
                config.BLOG_GIT_SSH = request.gitRepo
                global BLOG_GIT_SSH
                BLOG_GIT_SSH = request.gitRepo
                
                if x_session_id:
                    session_manager.update_session_git_repo(x_session_id, request.gitRepo)
            
            # 传递会话路径和 OAuth session_id 给初始化函数
            result = await init_local_git_async(session_path=base_path, session_id=x_oauth_session_id)
            
            if x_session_id and result.get('status') in ['connected', 'remote_configured', 'cloned']:
                session_manager.mark_session_initialized(x_session_id)
            
            logger.info("工作区初始化成功")
            return ApiResponse(message=result.get("message", "初始化成功"), data=result)
        except HTTPException:
            raise
        except Exception as e:
            logger.error("初始化工作区失败：" + str(e))
            raise HTTPException(status_code=500, detail="初始化失败：" + str(e))
        finally:
            try:
                sync_branch_name(cache_path=base_path)
            except Exception as e:
                logger.warning("同步分支名称失败：" + str(e))

@router.post("/pull", response_model=ApiResponse)
async def pull_repo(x_session_id: Optional[str] = Header(None),
                    x_oauth_session_id: Optional[str] = Header(None)):
    """拉取远程更新，支持会话隔离"""
    async with git_operation_lock:
        try:
            setup_git_context(x_session_id)
            # 传递 OAuth session_id 用于获取访问令牌
            await pull_updates_async(session_id=x_oauth_session_id)
            logger.info("已成功拉取最新更改")
            return ApiResponse(message="拉取成功")
        except HTTPException:
            raise
        except Exception as e:
            logger.error("拉取更新失败：" + str(e))
            raise HTTPException(status_code=500, detail="拉取失败：" + str(e))

@router.post("/reset", response_model=ApiResponse)
async def reset(x_session_id: Optional[str] = Header(None)):
    async with git_operation_lock:
        try:
            base_path = get_session_path(x_session_id)
            if os.path.exists(base_path):
                backup_path = base_path + "_backup"
                shutil.rmtree(backup_path, ignore_errors=True)
                try:
                    shutil.copytree(base_path, backup_path, dirs_exist_ok=True)
                except Exception as backup_error:
                    logger.warning("备份失败，继续重置：" + str(backup_error))
            setup_git_context(x_session_id)
            await init_local_git_async(session_path=base_path)
            logger.info("工作区重置完成")
            return ApiResponse(message="工作区重置完成")
        except HTTPException:
            raise
        except Exception as e:
            logger.error("重置工作区失败：" + str(e))
            raise HTTPException(status_code=500, detail="重置工作区失败")

@router.post("/soft_reset", response_model=ApiResponse)
async def soft_reset(x_session_id: Optional[str] = Header(None)):
    async with git_operation_lock:
        try:
            setup_git_context(x_session_id)
            await pull_updates_async()
            logger.info("工作区软重置完成")
            return ApiResponse(message="工作区软重置完成")
        except HTTPException:
            raise
        except Exception as e:
            logger.error("软重置工作区失败：" + str(e))
            raise HTTPException(status_code=500, detail="软重置工作区失败")

@router.post("/commit", response_model=ApiResponse)
async def commit(x_session_id: Optional[str] = Header(None), 
                 x_oauth_session_id: Optional[str] = Header(None)):
    async with git_operation_lock:
        try:
            setup_git_context(x_session_id)
            # 传递 OAuth session_id 用于获取访问令牌
            git_commit(session_id=x_oauth_session_id)
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
