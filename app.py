import datetime
import html
import os
import re
import shutil
import subprocess
import uuid
import logging
from typing import Optional

from fastapi import FastAPI, HTTPException, Depends, UploadFile, File, Form, Request
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel
import yaml

app = FastAPI(title="MarkGit Editor API", version="1.0.0")

CORS_ORIGINS = os.getenv('CORS_ORIGINS', 'http://localhost:5000,http://127.0.0.1:5000')
ALLOWED_ORIGINS = [origin.strip() for origin in CORS_ORIGINS.split(',') if origin.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="."), name="static")

PROG_PATH = os.path.dirname(__file__)
MAX_CONTENT_LENGTH = int(os.getenv('MAX_CONTENT_LENGTH', str(20 * 1024 * 1024)))
BLOG_CACHE_PATH = os.getenv('BLOG_CACHE_PATH', os.path.join(PROG_PATH, 'blog_cache'))
BLOG_GIT_SSH = os.getenv('BLOG_GIT_SSH', '')
POSTS_PATH = os.getenv('POSTS_PATH', os.path.join(BLOG_CACHE_PATH, 'content', 'posts'))
BLOG_BRANCH = os.getenv('BLOG_BRANCH', 'main')
CMD_AFTER_PUSH = os.getenv('CMD_AFTER_PUSH', '')
NEW_BLOG_TEMPLATE_PATH = os.getenv('NEW_BLOG_TEMPLATE_PATH', os.path.join(BLOG_CACHE_PATH, 'archetypes', 'posts.md'))
GIT_SSH_KEY_PATH = os.getenv('GIT_SSH_KEY_PATH', '')
GIT_CONFIG_FILE = os.path.join(PROG_PATH, 'git_config.txt')

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

SECRET_KEY = os.getenv('SECRET_KEY')
if not SECRET_KEY:
    import secrets
    SECRET_KEY = secrets.token_urlsafe(32)
    logger.warning("WARNING: Using auto-generated SECRET_KEY. For production, please set SECRET_KEY environment variable.")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    username: Optional[str] = None

class User(BaseModel):
    username: str
    disabled: Optional[bool] = None

class LoginRequest(BaseModel):
    username: str
    password: str

class UserCreate(BaseModel):
    username: str
    password: str

fake_users_db = {}

def get_user_db():
    if not fake_users_db:
        admin_password = os.getenv('ADMIN_PASSWORD', 'admin123')
        fake_users_db["admin"] = {
            "username": "admin",
            "hashed_password": pwd_context.hash(admin_password[:72])
        }
    return fake_users_db

IS_INIT_WORKSPACE = False
RULE = re.compile(r'^[a-zA-Z0-9_-]+$')

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: Optional[datetime.timedelta] = None) -> str:
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.datetime.utcnow() + expires_delta
    else:
        expire = datetime.datetime.utcnow() + datetime.timedelta(minutes=15)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def check_name(dir_name: str):
    if not dir_name or not RULE.match(dir_name):
        raise HTTPException(status_code=400, detail="Invalid directory name. Only alphanumeric characters, hyphens and underscores are allowed.")

def get_git_repo_config() -> str:
    try:
        if os.path.exists(GIT_CONFIG_FILE):
            with open(GIT_CONFIG_FILE, 'r', encoding='utf-8') as f:
                content = f.read().strip()
                if content:
                    return content
    except Exception as e:
        logger.error("读取 git 配置失败：" + str(e))
    return BLOG_GIT_SSH

def save_git_repo_config(repo_url: str) -> bool:
    try:
        with open(GIT_CONFIG_FILE, 'w', encoding='utf-8') as f:
            f.write(repo_url)
        logger.info("Git 仓库配置已保存：" + repo_url)
        return True
    except Exception as e:
        logger.error("保存 git 配置失败：" + str(e))
        return False

def get_md_yaml(file_path: str) -> dict:
    yaml_lines = []
    if not os.path.isfile(file_path):
        return {}
    try:
        with open(file_path, mode='r', encoding='utf-8') as f:
            start_flag = False
            for line in f:
                if start_flag and not line.startswith('---'):
                    yaml_lines.append(line)
                if line.startswith('---'):
                    if start_flag:
                        break
                    else:
                        start_flag = True
        return yaml.safe_load('\n'.join(yaml_lines)) or {}
    except yaml.YAMLError as e:
        logger.warning("解析 YAML 失败 " + file_path + ": " + str(e))
        return {}
    except Exception as e:
        logger.error("读取文件失败 " + file_path + ": " + str(e))
        return {}

def delete_image_not_included(specific_post: Optional[str] = None):
    def scan_post(dir_name: str):
        post_dir = os.path.join(POSTS_PATH, dir_name)
        if not os.path.isdir(post_dir):
            return
        
        md_file = os.path.join(post_dir, 'index.md')
        cur_post_content = ""
        if os.path.isfile(md_file):
            try:
                with open(md_file, mode='r', encoding='utf-8') as f:
                    cur_post_content = f.read()
            except Exception as e:
                logger.warning("读取文件失败 " + md_file + ": " + str(e))
                return
        
        try:
            for file in os.listdir(post_dir):
                if file == 'index.md':
                    continue
                delete_file_path = os.path.join(post_dir, file)
                if os.path.isdir(delete_file_path):
                    continue
                if file not in cur_post_content:
                    logger.info("文件未使用 " + delete_file_path + ", 删除中")
                    try:
                        os.remove(delete_file_path)
                    except Exception as e:
                        logger.warning("删除文件失败 " + delete_file_path + ": " + str(e))
        except OSError as e:
            logger.error("列出目录失败 " + post_dir + ": " + str(e))

    if not os.path.isdir(POSTS_PATH):
        return
    
    if specific_post:
        scan_post(specific_post)
    else:
        try:
            for dir_name in os.listdir(POSTS_PATH):
                dir_path = os.path.join(POSTS_PATH, dir_name)
                if os.path.isdir(dir_path):
                    scan_post(dir_name)
        except OSError as e:
            logger.error("列出 posts 目录失败：" + str(e))

def get_git_env() -> dict:
    env = os.environ.copy()
    git_repo = get_git_repo_config()
    if git_repo and (git_repo.startswith('git@') or git_repo.startswith('ssh://')):
        ssh_options = '-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o BatchMode=yes -o ConnectTimeout=30'
        if GIT_SSH_KEY_PATH and os.path.exists(GIT_SSH_KEY_PATH):
            env['GIT_SSH_COMMAND'] = f'ssh -i {GIT_SSH_KEY_PATH} {ssh_options}'
        else:
            env['GIT_SSH_COMMAND'] = f'ssh {ssh_options}'
    return env

def git_status() -> list:
    try:
        output = subprocess.run(['git', 'status', '-s'], cwd=BLOG_CACHE_PATH, capture_output=True, check=True)
        return [line.strip() for line in output.stdout.decode('utf-8').splitlines()]
    except subprocess.CalledProcessError as e:
        logger.error("Git status 失败：" + str(e))
        return []

def git_add():
    try:
        subprocess.run(['git', 'add', '-A'], cwd=BLOG_CACHE_PATH, check=True)
    except subprocess.CalledProcessError as e:
        logger.error("Git add 失败：" + str(e))
        raise HTTPException(status_code=500, detail="Git add 操作失败")

def git_commit():
    try:
        commit_cmd = ['git', 'commit']
        commit_msg = []
        for line in pretty_git_status(git_status()):
            commit_msg.append('-m')
            commit_msg.append(line)
        if not commit_msg:
            logger.info("没有更改需要提交")
            return
        commit_cmd.extend(commit_msg)
        env = get_git_env()
        subprocess.run(commit_cmd, cwd=BLOG_CACHE_PATH, check=True, env=env)
        logger.info("提交成功")
        
        subprocess.run(['git', 'push', '--set-upstream', 'origin', BLOG_BRANCH], cwd=BLOG_CACHE_PATH, check=True, env=env)
        logger.info("推送成功")
        
        deploy()
    except subprocess.CalledProcessError as e:
        error_msg = e.stderr if e.stderr else str(e)
        logger.error("Git 提交失败：" + error_msg)
        if 'fatal: not a git repository' in error_msg:
            raise HTTPException(status_code=500, detail="不是 Git 仓库，请先初始化")
        elif 'fatal: Authentication failed' in error_msg:
            raise HTTPException(status_code=500, detail="认证失败，请检查访问权限")
        elif 'fatal: remote error' in error_msg:
            raise HTTPException(status_code=500, detail="远程错误：无法推送")
        raise HTTPException(status_code=500, detail="提交操作失败")

def deploy():
    try:
        if CMD_AFTER_PUSH:
            subprocess.run(CMD_AFTER_PUSH.split(' '), check=True)
            logger.info("部署命令已执行")
        else:
            logger.info("未配置部署命令")
    except subprocess.CalledProcessError as e:
        logger.error("部署失败：" + str(e))
        raise HTTPException(status_code=500, detail="部署失败")

def pull_updates():
    global IS_INIT_WORKSPACE
    if IS_INIT_WORKSPACE:
        return
    IS_INIT_WORKSPACE = True
    try:
        if not os.path.exists(os.path.join(BLOG_CACHE_PATH, '.git')):
            raise HTTPException(status_code=400, detail="不是 Git 仓库，请先初始化")
        
        env = get_git_env()
        
        result = subprocess.run(['git', 'fetch', 'origin'], check=True, cwd=BLOG_CACHE_PATH, env=env, capture_output=True, text=True)
        logger.info("Fetch result: " + result.stdout)
        
        status_result = subprocess.run(['git', 'status', '--porcelain'], cwd=BLOG_CACHE_PATH, env=env, capture_output=True, text=True)
        local_changes = status_result.stdout.strip() != ''
        
        if local_changes:
            subprocess.run(['git', 'stash', 'push', '-m', 'auto-stash-before-pull'], check=True, cwd=BLOG_CACHE_PATH, env=env, capture_output=True)
            logger.info("本地更改已暂存")
        
        result = subprocess.run(['git', 'merge', 'origin/' + BLOG_BRANCH], check=True, cwd=BLOG_CACHE_PATH, env=env, capture_output=True, text=True)
        logger.info("Merge result: " + result.stdout)
        
        if local_changes:
            stash_pop = subprocess.run(['git', 'stash', 'pop'], cwd=BLOG_CACHE_PATH, env=env, capture_output=True, text=True)
            if stash_pop.returncode == 0:
                logger.info("本地更改已恢复")
            else:
                logger.warning("无法恢复本地更改：" + stash_pop.stderr)
        
        logger.info("已拉取远程最新更改")
    except subprocess.CalledProcessError as e:
        error_msg = e.stderr if e.stderr else str(e)
        logger.error("Git 拉取失败：" + error_msg)
        if 'does not appear to be a git repository' in error_msg:
            raise HTTPException(status_code=500, detail="远程仓库未找到，请先初始化")
        elif 'Could not connect' in error_msg or 'Could not resolve' in error_msg:
            raise HTTPException(status_code=500, detail="网络错误：无法连接到服务器")
        elif 'CONFLICT' in error_msg:
            raise HTTPException(status_code=500, detail="合并冲突，请手动解决")
        raise HTTPException(status_code=500, detail="拉取失败：" + error_msg)
    except Exception as e:
        logger.error("拉取失败：" + str(e))
        raise HTTPException(status_code=500, detail="拉取失败：" + str(e))
    finally:
        IS_INIT_WORKSPACE = False

def init_local_git():
    global IS_INIT_WORKSPACE
    if IS_INIT_WORKSPACE:
        raise HTTPException(status_code=400, detail="另一个操作正在进行中")
    IS_INIT_WORKSPACE = True
    
    try:
        git_repo = get_git_repo_config()
        has_git = os.path.exists(os.path.join(BLOG_CACHE_PATH, '.git'))
        has_files = os.path.exists(BLOG_CACHE_PATH) and any(
            os.path.exists(os.path.join(BLOG_CACHE_PATH, f)) 
            for f in os.listdir(BLOG_CACHE_PATH) if f != '.git'
        ) if os.path.exists(BLOG_CACHE_PATH) else False
        
        env = get_git_env()
        
        if has_git:
            logger.info("Git 仓库已存在，检查远程配置")
            try:
                remote_result = subprocess.run(['git', 'remote', '-v'], cwd=BLOG_CACHE_PATH, capture_output=True, text=True)
                has_remote = 'origin' in remote_result.stdout
                
                if has_remote:
                    return {"message": "初始化成功，仓库已连接", "status": "connected"}
                else:
                    return {"message": "仓库已初始化，请配置远程仓库地址", "status": "no_remote"}
            except subprocess.CalledProcessError as e:
                logger.warning("检查远程配置失败：" + (e.stderr if e.stderr else str(e)))
                return {"message": "仓库已初始化，远程配置检查失败", "status": "remote_check_failed"}
        
        if has_files and git_repo:
            logger.info("本地有文件但无 Git 仓库，保留本地文件并连接远程仓库")
            temp_dir = BLOG_CACHE_PATH + "_remote_temp"
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir, ignore_errors=True)
            
            clone_success = False
            clone_error = None
            
            try:
                subprocess.run(
                    ['git', 'clone', git_repo, '-b', BLOG_BRANCH, temp_dir],
                    env=env, check=True, capture_output=True, text=True, timeout=120
                )
                clone_success = True
            except subprocess.CalledProcessError as e:
                clone_error = e.stderr if e.stderr else str(e)
                if 'Remote branch' in clone_error and 'not found' in clone_error:
                    try:
                        subprocess.run(
                            ['git', 'clone', git_repo, temp_dir],
                            env=env, check=True, capture_output=True, text=True, timeout=120
                        )
                        clone_success = True
                    except subprocess.CalledProcessError as e2:
                        clone_error = e2.stderr if e2.stderr else str(e2)
            
            if clone_success or (clone_error and 'empty repository' in clone_error.lower()):
                if os.path.exists(os.path.join(temp_dir, '.git')):
                    shutil.copytree(os.path.join(temp_dir, '.git'), os.path.join(BLOG_CACHE_PATH, '.git'))
                subprocess.run(['git', 'config', 'user.name', 'BlogEditor'], cwd=BLOG_CACHE_PATH, check=True, capture_output=True)
                subprocess.run(['git', 'config', 'user.email', 'editor@blog.local'], cwd=BLOG_CACHE_PATH, check=True, capture_output=True)
                
                if clone_success and os.path.exists(temp_dir):
                    for item in os.listdir(temp_dir):
                        if item == '.git':
                            continue
                        src = os.path.join(temp_dir, item)
                        dst = os.path.join(BLOG_CACHE_PATH, item)
                        if not os.path.exists(dst):
                            if os.path.isdir(src):
                                shutil.copytree(src, dst)
                            else:
                                shutil.copy2(src, dst)
                
                if os.path.exists(temp_dir):
                    shutil.rmtree(temp_dir, ignore_errors=True)
                
                subprocess.run(['git', 'add', '-A'], cwd=BLOG_CACHE_PATH, check=True, capture_output=True)
                logger.info("本地文件已保留，远程仓库已连接")
                return {"message": "初始化成功，本地文件已保留", "status": "preserved_local"}
            else:
                if os.path.exists(temp_dir):
                    shutil.rmtree(temp_dir, ignore_errors=True)
                error_msg = clone_error or "未知错误"
                if 'Repository not found' in error_msg or 'not found' in error_msg.lower():
                    raise HTTPException(status_code=500, detail="仓库未找到，请检查地址和访问权限")
                raise HTTPException(status_code=500, detail="连接远程仓库失败：" + error_msg)
        
        elif has_files and not git_repo:
            logger.info("本地有文件，无远程仓库配置，仅初始化 Git")
            subprocess.run(['git', 'init'], cwd=BLOG_CACHE_PATH, check=True, capture_output=True)
            subprocess.run(['git', 'config', 'user.name', 'BlogEditor'], cwd=BLOG_CACHE_PATH, check=True, capture_output=True)
            subprocess.run(['git', 'config', 'user.email', 'editor@blog.local'], cwd=BLOG_CACHE_PATH, check=True, capture_output=True)
            return {"message": "初始化成功，请配置远程仓库地址", "status": "no_remote"}
        
        elif not has_files and git_repo:
            logger.info("本地无文件，克隆远程仓库")
            os.makedirs(BLOG_CACHE_PATH, exist_ok=True)
            
            clone_success = False
            clone_error = None
            
            try:
                subprocess.run(
                    ['git', 'clone', git_repo, '-b', BLOG_BRANCH, BLOG_CACHE_PATH],
                    env=env, check=True, capture_output=True, text=True, timeout=120
                )
                clone_success = True
            except subprocess.CalledProcessError as e:
                clone_error = e.stderr if e.stderr else str(e)
                if 'Remote branch' in clone_error and 'not found' in clone_error:
                    try:
                        subprocess.run(
                            ['git', 'clone', git_repo, BLOG_CACHE_PATH],
                            env=env, check=True, capture_output=True, text=True, timeout=120
                        )
                        clone_success = True
                    except subprocess.CalledProcessError as e2:
                        clone_error = e2.stderr if e2.stderr else str(e2)
            
            if clone_success:
                logger.info("远程仓库克隆成功")
                return {"message": "初始化成功，远程仓库已克隆", "status": "cloned"}
            elif clone_error and 'empty repository' in clone_error.lower():
                subprocess.run(['git', 'init'], cwd=BLOG_CACHE_PATH, check=True, capture_output=True)
                subprocess.run(['git', 'remote', 'add', 'origin', git_repo], cwd=BLOG_CACHE_PATH, check=True, capture_output=True)
                subprocess.run(['git', 'config', 'user.name', 'BlogEditor'], cwd=BLOG_CACHE_PATH, check=True, capture_output=True)
                subprocess.run(['git', 'config', 'user.email', 'editor@blog.local'], cwd=BLOG_CACHE_PATH, check=True, capture_output=True)
                logger.info("空仓库初始化成功")
                return {"message": "初始化成功，远程仓库为空", "status": "empty_repo"}
            else:
                error_msg = clone_error or "未知错误"
                if 'Repository not found' in error_msg or 'not found' in error_msg.lower():
                    raise HTTPException(status_code=500, detail="仓库未找到，请检查地址和访问权限")
                elif 'Permission denied' in error_msg or 'password' in error_msg.lower():
                    raise HTTPException(status_code=500, detail="认证失败，请检查访问权限")
                raise HTTPException(status_code=500, detail="克隆仓库失败：" + error_msg)
        
        else:
            logger.info("本地无文件，无远程仓库配置，初始化空仓库")
            os.makedirs(BLOG_CACHE_PATH, exist_ok=True)
            subprocess.run(['git', 'init'], cwd=BLOG_CACHE_PATH, check=True, capture_output=True)
            subprocess.run(['git', 'config', 'user.name', 'BlogEditor'], cwd=BLOG_CACHE_PATH, check=True, capture_output=True)
            subprocess.run(['git', 'config', 'user.email', 'editor@blog.local'], cwd=BLOG_CACHE_PATH, check=True, capture_output=True)
            return {"message": "初始化成功，请配置远程仓库地址", "status": "initialized"}
            
    except HTTPException:
        raise
    except subprocess.TimeoutExpired:
        logger.error("Git 操作超时")
        raise HTTPException(status_code=500, detail="操作超时，请检查网络连接")
    except Exception as e:
        logger.error("初始化失败：" + str(e))
        raise HTTPException(status_code=500, detail="初始化失败：" + str(e))
    finally:
        IS_INIT_WORKSPACE = False

def check_initializing():
    if IS_INIT_WORKSPACE:
        raise HTTPException(status_code=400, detail='Workspace is being initialized')

def pretty_git_status(status_result: list) -> list:
    def _get_title(filepath: str) -> str:
        if filepath.endswith("index.md"):
            post_yaml = get_md_yaml(os.path.join(BLOG_CACHE_PATH, filepath))
            return post_yaml.get('title', '') if post_yaml else ''
        return ''

    status_result_for_show = []
    for status in status_result:
        parts = status.split(maxsplit=1)
        if len(parts) < 2:
            status_result_for_show.append(status)
            continue
        flag, filepath = parts
        if flag == 'M':
            status_result_for_show.append("Modified " + _get_title(filepath) + " " + filepath)
        elif flag == 'A':
            status_result_for_show.append("Added " + _get_title(filepath) + " " + filepath)
        elif flag == 'D':
            status_result_for_show.append("Deleted " + filepath)
        elif flag == '??':
            status_result_for_show.append("Untracked " + filepath)
        elif flag == 'R':
            status_result_for_show.append("Renamed " + filepath)
        else:
            status_result_for_show.append(status)
    return status_result_for_show

def read_post_template() -> str:
    try:
        with open(NEW_BLOG_TEMPLATE_PATH, mode='r', encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
        logger.error("模板文件未找到：" + NEW_BLOG_TEMPLATE_PATH)
        return '---\ntitle: {{title}}\ndate: {{date}}\ncategories: {{categories}}\n---\n\n'

HIDDEN_FOLDERS = {'.git', '.github', '.idea', '.vscode', '.vs', 'node_modules', '.node_modules', '__pycache__', '.pytest_cache', '.mypy_cache', '.tox', '.eggs', '.history', '.Trash'}

def should_hide_path(path: str) -> bool:
    parts = path.replace('\\', '/').split('/')
    for part in parts:
        if part in HIDDEN_FOLDERS or part.endswith('.egg-info'):
            return True
    return False

def get_files_recursive(directory: str) -> list:
    files = []
    try:
        for root, dirs, filenames in os.walk(directory):
            dirs[:] = [d for d in dirs if d not in HIDDEN_FOLDERS and not d.endswith('.egg-info')]
            
            for filename in filenames:
                relative_path = os.path.relpath(os.path.join(root, filename), BLOG_CACHE_PATH)
                if should_hide_path(relative_path):
                    continue
                files.append({
                    "path": relative_path.replace('\\', '/'),
                    "type": "file",
                    "size": os.path.getsize(os.path.join(root, filename))
                })
            for dirname in dirs:
                relative_path = os.path.relpath(os.path.join(root, dirname), BLOG_CACHE_PATH)
                if should_hide_path(relative_path):
                    continue
                files.append({
                    "path": relative_path.replace('\\', '/'),
                    "type": "directory"
                })
    except Exception as e:
        logger.error("获取文件列表失败：" + str(e))
    return files

def validate_file_path(file_path: str) -> str:
    if not file_path:
        raise HTTPException(status_code=400, detail="File path cannot be empty")
    if ".." in file_path or file_path.startswith("/"):
        raise HTTPException(status_code=400, detail="Invalid file path")
    return os.path.join(BLOG_CACHE_PATH, file_path)

@app.get("/")
def root():
    return FileResponse("index.html")



@app.get("/api/files")
def get_files():
    try:
        if not os.path.exists(BLOG_CACHE_PATH):
            return JSONResponse(content=[])
        files = get_files_recursive(BLOG_CACHE_PATH)
        return JSONResponse(content=files)
    except Exception as e:
        logger.error("获取文件列表失败：" + str(e))
        raise HTTPException(status_code=500, detail="获取文件列表失败：" + str(e))

@app.get("/api/file/content")
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

@app.post("/api/file/create")
async def create_file(request: Request):
    try:
        data = await request.json()
        file_path = data.get("path", "")
        content = data.get("content", "")
        full_path = validate_file_path(file_path)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, 'w', encoding='utf-8') as f:
            f.write(content)
        git_add()
        logger.info("文件已创建：" + file_path)
        return JSONResponse(content={"message": "文件创建成功", "path": file_path})
    except HTTPException:
        raise
    except Exception as e:
        logger.error("创建文件失败：" + str(e))
        raise HTTPException(status_code=500, detail="创建文件失败：" + str(e))

@app.post("/api/file/save")
async def save_file(request: Request):
    try:
        data = await request.json()
        file_path = data.get("path", "")
        content = data.get("content", "")
        full_path = validate_file_path(file_path)
        if not os.path.exists(full_path):
            raise HTTPException(status_code=404, detail="文件未找到")
        with open(full_path, 'w', encoding='utf-8') as f:
            f.write(content)
        git_add()
        logger.info("文件已保存：" + file_path)
        return JSONResponse(content={"message": "文件保存成功"})
    except HTTPException:
        raise
    except Exception as e:
        logger.error("保存文件失败：" + str(e))
        raise HTTPException(status_code=500, detail="保存文件失败：" + str(e))

@app.post("/api/file/rename")
async def rename_file(request: Request):
    try:
        data = await request.json()
        old_path = data.get("oldPath", "")
        new_path = data.get("newPath", "")
        if not old_path or not new_path:
            raise HTTPException(status_code=400, detail="Both old and new paths are required")
        full_old_path = validate_file_path(old_path)
        full_new_path = validate_file_path(new_path)
        if not os.path.exists(full_old_path):
            raise HTTPException(status_code=404, detail="File or directory not found")
        if os.path.exists(full_new_path):
            raise HTTPException(status_code=400, detail="Target path already exists")
        os.rename(full_old_path, full_new_path)
        git_add()
        logger.info("已重命名：" + old_path + " -> " + new_path)
        return JSONResponse(content={"message": "重命名成功"})
    except HTTPException:
        raise
    except Exception as e:
        logger.error("重命名失败：" + str(e))
        raise HTTPException(status_code=500, detail="重命名失败：" + str(e))

@app.delete("/api/file/delete")
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
        return JSONResponse(content={"message": "删除成功"})
    except HTTPException:
        raise
    except Exception as e:
        logger.error("删除失败：" + str(e))
        raise HTTPException(status_code=500, detail="删除失败：" + str(e))

@app.post("/api/file/move")
async def move_file(request: Request):
    try:
        data = await request.json()
        source_path = data.get("sourcePath", "")
        dest_path = data.get("destPath", "")
        if not source_path or not dest_path:
            raise HTTPException(status_code=400, detail="Both source and destination paths are required")
        full_source_path = validate_file_path(source_path)
        full_dest_path = validate_file_path(dest_path)
        if not os.path.exists(full_source_path):
            raise HTTPException(status_code=404, detail="Source file or directory not found")
        if os.path.exists(full_dest_path):
            raise HTTPException(status_code=400, detail="Destination path already exists")
        os.makedirs(os.path.dirname(full_dest_path), exist_ok=True)
        shutil.move(full_source_path, full_dest_path)
        git_add()
        logger.info("已移动：" + source_path + " -> " + dest_path)
        return JSONResponse(content={"message": "移动成功"})
    except HTTPException:
        raise
    except Exception as e:
        logger.error("移动失败：" + str(e))
        raise HTTPException(status_code=500, detail="移动失败：" + str(e))

@app.post("/api/folder/create")
async def create_folder(request: Request):
    try:
        data = await request.json()
        folder_path = data.get("path", "")
        full_path = validate_file_path(folder_path)
        os.makedirs(full_path, exist_ok=True)
        git_add()
        logger.info("文件夹已创建：" + folder_path)
        return JSONResponse(content={"message": "文件夹创建成功", "path": folder_path})
    except HTTPException:
        raise
    except Exception as e:
        logger.error("创建文件夹失败：" + str(e))
        raise HTTPException(status_code=500, detail="创建文件夹失败：" + str(e))

@app.get("/api/git-repo")
def get_git_repo():
    try:
        git_repo = get_git_repo_config()
        return JSONResponse(content={"gitRepo": git_repo})
    except Exception as e:
        logger.error("获取 git 仓库失败：" + str(e))
        raise HTTPException(status_code=500, detail="获取 git 仓库失败")

@app.post("/api/git-repo")
async def set_git_repo(request: Request):
    try:
        data = await request.json()
        git_repo = data.get("gitRepo", "")
        if not git_repo:
            raise HTTPException(status_code=400, detail="Git repo URL is required")
        if save_git_repo_config(git_repo):
            return JSONResponse(content={"message": "Git 仓库配置保存成功"})
        else:
            raise HTTPException(status_code=500, detail="保存 git 仓库配置失败")
    except HTTPException:
        raise
    except Exception as e:
        logger.error("设置 git 仓库失败：" + str(e))
        raise HTTPException(status_code=500, detail="设置 git 仓库失败")

@app.get("/api/categories")
def get_categories():
    try:
        categories = set()
        if not os.path.exists(POSTS_PATH):
            return JSONResponse(content=list(categories))
        for i in os.listdir(POSTS_PATH):
            post_yaml = get_md_yaml(os.path.join(POSTS_PATH, i, 'index.md'))
            if post_yaml:
                for item in post_yaml.get('categories', []):
                    categories.add(item)
        return JSONResponse(content=list(categories))
    except Exception as e:
        logger.error("获取分类失败：" + str(e))
        raise HTTPException(status_code=500, detail="获取分类失败")

@app.get("/api/posts/changes")
def get_post_changes():
    try:
        delete_image_not_included()
        git_add()
        status_result_for_show = pretty_git_status(git_status())
        return JSONResponse(content=status_result_for_show)
    except Exception as e:
        logger.error("获取帖子更改失败：" + str(e))
        raise HTTPException(status_code=500, detail="获取帖子更改失败")

@app.get("/api/posts")
def get_posts():
    try:
        posts = {}
        if not os.path.exists(POSTS_PATH):
            return JSONResponse(content=posts)
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
        return JSONResponse(content=posts)
    except Exception as e:
        logger.error("获取帖子失败：" + str(e))
        raise HTTPException(status_code=500, detail="获取帖子失败")

@app.post("/api/post/create")
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
        return JSONResponse(content={'dirName': post_dir_name})
    except Exception as e:
        logger.error("创建帖子失败：" + str(e))
        raise HTTPException(status_code=500, detail="创建帖子失败")

@app.get("/api/post/{filename}")
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

@app.delete("/api/post/{filename}")
def delete_post(filename: str):
    try:
        check_name(filename)
        post_path = os.path.join(POSTS_PATH, filename)
        if os.path.exists(post_path):
            shutil.rmtree(post_path, ignore_errors=True)
            git_add()
            logger.info("帖子已删除：" + filename)
            return PlainTextResponse(status_code=200)
        raise HTTPException(status_code=404, detail="帖子未找到")
    except HTTPException:
        raise
    except Exception as e:
        logger.error("删除帖子失败：" + str(e))
        raise HTTPException(status_code=500, detail="删除帖子失败")

@app.post("/api/post/{filename}")
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
        return PlainTextResponse(status_code=200)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("保存帖子失败：" + str(e))
        raise HTTPException(status_code=500, detail="保存帖子失败")

@app.post("/api/init")
def init_workspace():
    try:
        check_initializing()
        result = init_local_git()
        logger.info("工作区初始化成功")
        return JSONResponse(content=result if result else {"message": "初始化成功"})
    except HTTPException:
        raise
    except Exception as e:
        logger.error("初始化工作区失败：" + str(e))
        raise HTTPException(status_code=500, detail="初始化失败：" + str(e))

@app.post("/api/pull")
def pull_repo():
    try:
        check_initializing()
        pull_updates()
        logger.info("已成功拉取最新更改")
        return JSONResponse(content={"message": "拉取成功"})
    except HTTPException:
        raise
    except Exception as e:
        logger.error("拉取更新失败：" + str(e))
        raise HTTPException(status_code=500, detail="拉取失败：" + str(e))

@app.post("/api/reset")
def reset():
    try:
        check_initializing()
        if os.path.exists(BLOG_CACHE_PATH):
            backup_path = BLOG_CACHE_PATH + "_backup"
            shutil.rmtree(backup_path, ignore_errors=True)
            try:
                shutil.copytree(BLOG_CACHE_PATH, backup_path, dirs_exist_ok=True)
            except Exception as backup_error:
                logger.warning("备份失败，继续重置：" + str(backup_error))
        init_local_git()
        logger.info("工作区重置完成")
        return PlainTextResponse(status_code=200)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("重置工作区失败：" + str(e))
        raise HTTPException(status_code=500, detail="重置工作区失败：" + str(e))

@app.post("/api/soft_reset")
def soft_reset():
    try:
        check_initializing()
        pull_updates()
        logger.info("工作区软重置完成")
        return PlainTextResponse(status_code=200)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("软重置工作区失败：" + str(e))
        raise HTTPException(status_code=500, detail="软重置工作区失败")

@app.post("/api/commit")
def commit():
    try:
        git_commit()
        logger.info("更改已提交并推送")
        return PlainTextResponse(status_code=200)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("提交更改失败：" + str(e))
        raise HTTPException(status_code=500, detail="提交更改失败")

@app.post("/api/redeploy")
def redeploy():
    try:
        deploy()
        logger.info("重新部署已触发")
        return PlainTextResponse(status_code=200)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("重新部署失败：" + str(e))
        raise HTTPException(status_code=500, detail="重新部署失败")

@app.post("/upload")
async def upload_files(files: list[UploadFile] = File(...), belongDirName: str = Form(...)):
    try:
        success_files = {}
        failed_files = []
        check_name(belongDirName)
        for file in files:
            try:
                suffix = os.path.splitext(file.filename)[1]
                new_filename = str(uuid.uuid4()).replace('-', '') + suffix
                file_path = os.path.join(POSTS_PATH, belongDirName, new_filename)
                with open(file_path, "wb") as buffer:
                    content = await file.read()
                    buffer.write(content)
                success_files[file.filename] = new_filename
                logger.info("文件已上传：" + file.filename + " -> " + new_filename)
            except Exception as e:
                logger.error("上传文件失败 " + file.filename + ": " + str(e))
                failed_files.append(file.filename)
        git_add()
        ret_dict = {
            "msg": "",
            "code": 0,
            "data": {
                "errFiles": failed_files,
                "succMap": success_files
            }
        }
        return JSONResponse(content=ret_dict)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("上传文件失败：" + str(e))
        raise HTTPException(status_code=500, detail="上传文件失败")

@app.get("/{dir_name}/{file_name}")
def get_file(dir_name: str, file_name: str):
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
        raise HTTPException(status_code=500, detail="初始化工作区失败")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=5000)
