import datetime
import html.parser
import os
import re
import shutil
import subprocess
import traceback
import uuid
import logging

from fastapi import FastAPI, HTTPException, Depends, UploadFile, File, Form, status, Request
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel
import yaml

app = FastAPI(title="Blog Online Editor API", version="1.0.0")

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static files
app.mount("/static", StaticFiles(directory="."), name="static")

# Root route
@app.get("/")
def root():
    return FileResponse("index.html")

@app.get("/favicon.ico")
def favicon():
    return FileResponse("favicon.ico")

# Configuration
PROG_PATH = os.path.dirname(__file__)
MAX_CONTENT_LENGTH = int(os.getenv('MAX_CONTENT_LENGTH', str(20 * 1024 * 1024)))
BLOG_CACHE_PATH = os.getenv('BLOG_CACHE_PATH', os.path.join(PROG_PATH, 'blog_cache'))
BLOG_GIT_SSH = os.getenv('BLOG_GIT_SSH', 'git@gitee.com:RainbowYYQ/my-blog.git')
POSTS_PATH = os.getenv('POSTS_PATH', os.path.join(BLOG_CACHE_PATH, 'content', 'posts'))
BLOG_BRANCH = os.getenv('BLOG_BRANCH', 'main')
CMD_AFTER_PUSH = os.getenv('CMD_AFTER_PUSH', '')
NEW_BLOG_TEMPLATE_PATH = os.getenv('NEW_BLOG_TEMPLATE_PATH', os.path.join(BLOG_CACHE_PATH, 'archetypes', 'posts.md'))
GIT_SSH_KEY_PATH = os.getenv('GIT_SSH_KEY_PATH', '')
GIT_CONFIG_FILE = os.path.join(PROG_PATH, 'git_config.txt')

# Security
SECRET_KEY = os.getenv('SECRET_KEY')
if not SECRET_KEY:
    raise ValueError("SECRET_KEY environment variable is required for security reasons")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Models
class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    username: str | None = None

class User(BaseModel):
    username: str
    disabled: bool | None = None

class LoginRequest(BaseModel):
    username: str
    password: str

class UserCreate(BaseModel):
    username: str
    password: str

# Global variables
IS_INIT_WORKSPACE = False
RULE = re.compile(r'[a-zA-Z0-9]+')

# Helper functions
def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: datetime.timedelta | None = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.datetime.utcnow() + expires_delta
    else:
        expire = datetime.datetime.utcnow() + datetime.timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def check_name(dir_name):
    if not RULE.match(dir_name):
        raise HTTPException(status_code=400, detail="invalid dir name")

def get_git_repo_config():
    try:
        if os.path.exists(GIT_CONFIG_FILE):
            with open(GIT_CONFIG_FILE, 'r', encoding='utf-8') as f:
                return f.read().strip()
    except Exception as e:
        logger.error(f"Failed to read git config: {e}")
    return BLOG_GIT_SSH

def save_git_repo_config(repo_url):
    try:
        with open(GIT_CONFIG_FILE, 'w', encoding='utf-8') as f:
            f.write(repo_url)
        logger.info(f"Git repo config saved: {repo_url}")
        return True
    except Exception as e:
        logger.error(f"Failed to save git config: {e}")
        return False

def get_md_yaml(file_path):
    yaml_lines = []
    if not os.path.isfile(file_path):
        return {}
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
    return yaml.load('\n'.join(yaml_lines), Loader=yaml.BaseLoader)

def delete_image_not_included(specific_post=None):
    def scan_post(dir_name):
        cur_post_content = ""
        md_file = os.path.join(POSTS_PATH, dir_name, 'index.md')
        if os.path.isfile(md_file):
            with open(md_file, mode='r', encoding='utf-8') as f:
                cur_post_content = f.read()
        for file in os.listdir(os.path.join(POSTS_PATH, dir_name)):
            if file == 'index.md':
                continue
            if file not in cur_post_content:
                delete_file_path = os.path.join(POSTS_PATH, dir_name, file)
                logger.info(f'file not used {delete_file_path} delete it.')
                os.remove(delete_file_path)

    if specific_post:
        scan_post(specific_post)
    else:
        for dir_name in os.listdir(POSTS_PATH):
            scan_post(dir_name)

def git_status():
    try:
        output = subprocess.run(['git', 'status', '-s'], cwd=BLOG_CACHE_PATH, capture_output=True, check=True)
        return [line.strip() for line in output.stdout.decode('utf-8').splitlines()]
    except subprocess.CalledProcessError as e:
        logger.error(f"Git status failed: {e}")
        return []

def git_add():
    try:
        subprocess.run(['git', 'add', '-A'], cwd=BLOG_CACHE_PATH, check=True)
    except subprocess.CalledProcessError as e:
        logger.error(f"Git add failed: {e}")
        raise HTTPException(status_code=500, detail="Git add operation failed")

def git_commit():
    try:
        commit_cmd = ['git', 'commit']
        commit_msg = []
        for line in pretty_git_status(git_status()):
            commit_msg.append('-m')
            commit_msg.append(line)
        if not commit_msg:
            logger.info("No changes to commit")
            return
        commit_cmd.extend(commit_msg)
        env = os.environ.copy()
        if GIT_SSH_KEY_PATH:
            env['GIT_SSH_COMMAND'] = f'ssh -i {GIT_SSH_KEY_PATH} -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null'
        else:
            env['GIT_SSH_COMMAND'] = 'ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null'
        subprocess.run(commit_cmd, cwd=BLOG_CACHE_PATH, check=True, env=env)
        subprocess.run(['git', 'push', '--set-upstream', 'origin', BLOG_BRANCH], cwd=BLOG_CACHE_PATH, check=True, env=env)
        deploy()
    except subprocess.CalledProcessError as e:
        logger.error(f"Git commit failed: {e}")
        raise HTTPException(status_code=500, detail="Git commit operation failed")

def deploy():
    try:
        if CMD_AFTER_PUSH:
            subprocess.run(CMD_AFTER_PUSH.split(' '), check=True)
            logger.info("Deployment command executed")
        else:
            logger.info("No deployment command configured")
    except subprocess.CalledProcessError as e:
        logger.error(f"Deployment failed: {e}")
        raise HTTPException(status_code=500, detail="Deployment failed")

def pull_updates():
    global IS_INIT_WORKSPACE
    if IS_INIT_WORKSPACE:
        return
    IS_INIT_WORKSPACE = True
    try:
        git_add()
        env = os.environ.copy()
        if GIT_SSH_KEY_PATH:
            env['GIT_SSH_COMMAND'] = f'ssh -i {GIT_SSH_KEY_PATH} -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null'
        else:
            env['GIT_SSH_COMMAND'] = 'ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null'
        subprocess.run(['git', 'stash'], check=True, cwd=BLOG_CACHE_PATH, env=env)
        subprocess.run(['git', 'pull'], check=True, cwd=BLOG_CACHE_PATH, env=env)
        subprocess.run(['git', 'stash', 'pop'], check=False, cwd=BLOG_CACHE_PATH, env=env)
    finally:
        IS_INIT_WORKSPACE = False

def init_git():
    global IS_INIT_WORKSPACE
    if IS_INIT_WORKSPACE:
        return
    IS_INIT_WORKSPACE = True
    try:
        if os.path.exists(BLOG_CACHE_PATH):
            shutil.rmtree(BLOG_CACHE_PATH, ignore_errors=True)
        os.makedirs(BLOG_CACHE_PATH, exist_ok=True)
        env = os.environ.copy()
        # Configure SSH for Git
        ssh_options = '-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o BatchMode=yes -o ConnectTimeout=30'
        if GIT_SSH_KEY_PATH:
            env['GIT_SSH_COMMAND'] = f'ssh -i {GIT_SSH_KEY_PATH} {ssh_options}'
            logger.info(f"Using SSH key: {GIT_SSH_KEY_PATH}")
        else:
            env['GIT_SSH_COMMAND'] = f'ssh {ssh_options}'
            logger.info("Using default SSH configuration")
        git_repo = get_git_repo_config()
        logger.info(f"Cloning repository: {git_repo} branch: {BLOG_BRANCH}")
        result = subprocess.run(
            ['git', 'clone', git_repo, '-b', BLOG_BRANCH, BLOG_CACHE_PATH],
            env=env,
            check=True,
            capture_output=True,
            text=True,
            timeout=120
        )
        logger.info(f"Git clone output: {result.stdout}")
        logger.info(f"Git repository cloned from {git_repo}")
    except subprocess.CalledProcessError as e:
        error_msg = e.stderr if e.stderr else str(e)
        logger.error(f"Git clone failed: {error_msg}")
        raise HTTPException(status_code=500, detail=f"Failed to clone repository: {error_msg}")
    except subprocess.TimeoutExpired:
        logger.error("Git clone timed out")
        raise HTTPException(status_code=500, detail="Git clone timed out - check SSH key configuration")
    except Exception as e:
        logger.error(f"Failed to initialize git: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to initialize git: {str(e)}")
    finally:
        IS_INIT_WORKSPACE = False

def check_initializing():
    if IS_INIT_WORKSPACE:
        raise HTTPException(status_code=400, detail='workspace is in initializing')

def pretty_git_status(status_result):
    def _get_title(filepath):
        if filepath.endswith("index.md"):
            post_yaml = get_md_yaml(os.path.join(BLOG_CACHE_PATH, filepath))
            return post_yaml.get('title', '') if post_yaml else ''
        return ''

    status_result_for_show = []
    for status in status_result:
        flag, filepath = status.split()
        if status.startswith("M "):
            status_result_for_show.append(f"修改 {_get_title(filepath)} {filepath}")
        elif status.startswith("A "):
            status_result_for_show.append(f"新增 {_get_title(filepath)} {filepath}")
        elif status.startswith("D "):
            status_result_for_show.append(f"删除 {filepath}")
        else:
            status_result_for_show.append(status)
    return status_result_for_show

def read_post_template():
    try:
        with open(NEW_BLOG_TEMPLATE_PATH, mode='r', encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
        logger.error(f"Template file not found: {NEW_BLOG_TEMPLATE_PATH}")
        return '---\ntitle: {{title}}\ndate: {{date}}\ncategories: {{categories}}\n---\n\n'

# Helper functions for file operations
HIDDEN_FOLDERS = {'.git', '.github', '.idea', '.vscode', '.vs', 'node_modules', '.node_modules', '__pycache__', '.pytest_cache', '.mypy_cache', '.tox', '.eggs', '*.egg-info', '.env', '.venv', 'venv', '.history', '.Trash'}

def should_hide_path(path):
    """Check if path should be hidden"""
    parts = path.replace('\\', '/').split('/')
    for part in parts:
        if part in HIDDEN_FOLDERS or part.endswith('.egg-info'):
            return True
    return False

def get_files_recursive(directory):
    """Get all files recursively from a directory"""
    files = []
    try:
        for root, dirs, filenames in os.walk(directory):
            # Filter out hidden directories from dirs to prevent walking into them
            dirs[:] = [d for d in dirs if d not in HIDDEN_FOLDERS and not d.endswith('.egg-info')]
            
            for filename in filenames:
                # Get relative path from BLOG_CACHE_PATH
                relative_path = os.path.relpath(os.path.join(root, filename), BLOG_CACHE_PATH)
                # Skip hidden paths
                if should_hide_path(relative_path):
                    continue
                files.append({
                    "path": relative_path.replace('\\', '/'),
                    "type": "file",
                    "size": os.path.getsize(os.path.join(root, filename))
                })
            for dirname in dirs:
                # Get relative path from BLOG_CACHE_PATH
                relative_path = os.path.relpath(os.path.join(root, dirname), BLOG_CACHE_PATH)
                # Skip hidden paths
                if should_hide_path(relative_path):
                    continue
                files.append({
                    "path": relative_path.replace('\\', '/'),
                    "type": "directory"
                })
    except Exception as e:
        logger.error(f"Failed to get files: {e}")
    return files

# API Routes
@app.get("/api/git-repo")
def get_git_repo():
    try:
        git_repo = get_git_repo_config()
        return JSONResponse(content={"gitRepo": git_repo})
    except Exception as e:
        logger.error(f"Failed to get git repo: {e}")
        raise HTTPException(status_code=500, detail="Failed to get git repo")

@app.get("/api/files")
def get_files():
    """Get all files in the repository"""
    try:
        files = get_files_recursive(BLOG_CACHE_PATH)
        return JSONResponse(content=files)
    except Exception as e:
        logger.error(f"Failed to get files: {e}")
        raise HTTPException(status_code=500, detail="Failed to get files")

@app.post("/api/git-repo")
async def set_git_repo(request: Request):
    try:
        data = await request.json()
        git_repo = data.get("gitRepo", "")
        if not git_repo:
            raise HTTPException(status_code=400, detail="Git repo URL is required")
        if save_git_repo_config(git_repo):
            return JSONResponse(content={"message": "Git repo config saved successfully"})
        else:
            raise HTTPException(status_code=500, detail="Failed to save git repo config")
    except Exception as e:
        logger.error(f"Failed to set git repo: {e}")
        raise HTTPException(status_code=500, detail="Failed to set git repo")

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
        logger.error(f"Failed to get categories: {e}")
        raise HTTPException(status_code=500, detail="Failed to get categories")

@app.get("/api/posts/changes")
def get_post_changes():
    try:
        delete_image_not_included()
        git_add()
        status_result_for_show = pretty_git_status(git_status())
        return JSONResponse(content=status_result_for_show)
    except Exception as e:
        logger.error(f"Failed to get post changes: {e}")
        raise HTTPException(status_code=500, detail="Failed to get post changes")

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
        logger.error(f"Failed to get posts: {e}")
        raise HTTPException(status_code=500, detail="Failed to get posts")

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
        logger.info(f"New post created: {post_dir_name}")
        return JSONResponse(content={'dirName': post_dir_name})
    except Exception as e:
        logger.error(f"Failed to create post: {e}")
        raise HTTPException(status_code=500, detail="Failed to create post")

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
    except Exception as e:
        logger.error(f"Failed to get post: {e}")
        raise HTTPException(status_code=500, detail="Failed to get post")

@app.delete("/api/post/{filename}")
def delete_post(filename: str):
    try:
        check_name(filename)
        post_path = os.path.join(POSTS_PATH, filename)
        if os.path.exists(post_path):
            shutil.rmtree(post_path, ignore_errors=True)
            git_add()
            logger.info(f"Post deleted: {filename}")
            return PlainTextResponse(status_code=200)
        raise HTTPException(status_code=404, detail="Post not found")
    except Exception as e:
        logger.error(f"Failed to delete post: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete post")

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
        logger.info(f"Post saved: {filename}")
        return PlainTextResponse(status_code=200)
    except Exception as e:
        logger.error(f"Failed to save post: {e}")
        raise HTTPException(status_code=500, detail="Failed to save post")

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
                logger.warning(f"Backup failed, continuing with reset: {backup_error}")
        init_git()
        logger.info("Workspace reset completed")
        return PlainTextResponse(status_code=200)
    except Exception as e:
        logger.error(f"Failed to reset workspace: {e}")
        raise HTTPException(status_code=500, detail="Failed to reset workspace")

@app.post("/api/soft_reset")
def soft_reset():
    try:
        check_initializing()
        pull_updates()
        logger.info("Workspace soft reset completed")
        return PlainTextResponse(status_code=200)
    except Exception as e:
        logger.error(f"Failed to soft reset workspace: {e}")
        raise HTTPException(status_code=500, detail="Failed to soft reset workspace")

@app.post("/api/commit")
def commit():
    try:
        git_commit()
        logger.info("Changes committed and pushed")
        return PlainTextResponse(status_code=200)
    except Exception as e:
        logger.error(f"Failed to commit changes: {e}")
        raise HTTPException(status_code=500, detail="Failed to commit changes")

@app.post("/api/redeploy")
def redeploy():
    try:
        deploy()
        logger.info("Redeployment triggered")
        return PlainTextResponse(status_code=200)
    except Exception as e:
        logger.error(f"Failed to redeploy: {e}")
        raise HTTPException(status_code=500, detail="Failed to redeploy")

@app.post("/upload")
async def upload_files(files: list[UploadFile] = File(...), belongDirName: str = Form(...)):
    try:
        success_files = {}
        failed_files = []
        check_name(belongDirName)
        for file in files:
            try:
                suffix = os.path.splitext(file.filename)[1]
                new_filename = f"{str(uuid.uuid4()).replace('-', '')}{suffix}"
                file_path = os.path.join(POSTS_PATH, belongDirName, new_filename)
                with open(file_path, "wb") as buffer:
                    content = await file.read()
                    buffer.write(content)
                success_files[file.filename] = new_filename
                logger.info(f"File uploaded: {file.filename} -> {new_filename}")
            except Exception as e:
                logger.error(f"Failed to upload file {file.filename}: {e}")
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
    except Exception as e:
        logger.error(f"Failed to upload files: {e}")
        raise HTTPException(status_code=500, detail="Failed to upload files")

@app.get("/{dir_name}/{file_name}")
def get_file(dir_name: str, file_name: str):
    try:
        check_name(dir_name)
        file_path = os.path.join(POSTS_PATH, dir_name, file_name)
        if os.path.exists(file_path):
            return FileResponse(file_path)
        raise HTTPException(status_code=404, detail="File not found")
    except Exception as e:
        logger.error(f"Failed to get file: {e}")
        raise HTTPException(status_code=500, detail="Failed to get file")

# File operations API
@app.get("/api/file/content")
def get_file_content(file_path: str = ""):
    """Get content of a specific file"""
    try:
        if not file_path:
            raise HTTPException(status_code=400, detail="File path is required")
        # Security check - prevent path traversal
        if ".." in file_path or file_path.startswith("/"):
            raise HTTPException(status_code=400, detail="Invalid file path")
        full_path = os.path.join(BLOG_CACHE_PATH, file_path)
        if not os.path.exists(full_path):
            raise HTTPException(status_code=404, detail="File not found")
        if os.path.isdir(full_path):
            raise HTTPException(status_code=400, detail="Path is a directory, not a file")
        with open(full_path, 'r', encoding='utf-8') as f:
            content = f.read()
        return PlainTextResponse(content=content)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get file content: {e}")
        raise HTTPException(status_code=500, detail="Failed to get file content")

@app.post("/api/file/create")
async def create_file(request: Request):
    """Create a new file"""
    try:
        data = await request.json()
        file_path = data.get("path", "")
        content = data.get("content", "")
        if not file_path:
            raise HTTPException(status_code=400, detail="File path is required")
        # Security check
        if ".." in file_path or file_path.startswith("/"):
            raise HTTPException(status_code=400, detail="Invalid file path")
        full_path = os.path.join(BLOG_CACHE_PATH, file_path)
        # Create directory if it doesn't exist
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, 'w', encoding='utf-8') as f:
            f.write(content)
        git_add()
        logger.info(f"File created: {file_path}")
        return JSONResponse(content={"message": "File created successfully", "path": file_path})
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create file: {e}")
        raise HTTPException(status_code=500, detail="Failed to create file")

@app.post("/api/file/save")
async def save_file(request: Request):
    """Save content to an existing file"""
    try:
        data = await request.json()
        file_path = data.get("path", "")
        content = data.get("content", "")
        if not file_path:
            raise HTTPException(status_code=400, detail="File path is required")
        # Security check
        if ".." in file_path or file_path.startswith("/"):
            raise HTTPException(status_code=400, detail="Invalid file path")
        full_path = os.path.join(BLOG_CACHE_PATH, file_path)
        if not os.path.exists(full_path):
            raise HTTPException(status_code=404, detail="File not found")
        with open(full_path, 'w', encoding='utf-8') as f:
            f.write(content)
        git_add()
        logger.info(f"File saved: {file_path}")
        return JSONResponse(content={"message": "File saved successfully"})
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to save file: {e}")
        raise HTTPException(status_code=500, detail="Failed to save file")

@app.post("/api/file/rename")
async def rename_file(request: Request):
    """Rename a file or directory"""
    try:
        data = await request.json()
        old_path = data.get("oldPath", "")
        new_path = data.get("newPath", "")
        if not old_path or not new_path:
            raise HTTPException(status_code=400, detail="Both old and new paths are required")
        # Security check
        if ".." in old_path or old_path.startswith("/") or ".." in new_path or new_path.startswith("/"):
            raise HTTPException(status_code=400, detail="Invalid file path")
        full_old_path = os.path.join(BLOG_CACHE_PATH, old_path)
        full_new_path = os.path.join(BLOG_CACHE_PATH, new_path)
        if not os.path.exists(full_old_path):
            raise HTTPException(status_code=404, detail="File or directory not found")
        if os.path.exists(full_new_path):
            raise HTTPException(status_code=400, detail="Target path already exists")
        os.rename(full_old_path, full_new_path)
        git_add()
        logger.info(f"Renamed: {old_path} -> {new_path}")
        return JSONResponse(content={"message": "Renamed successfully"})
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to rename: {e}")
        raise HTTPException(status_code=500, detail="Failed to rename")

@app.delete("/api/file/delete")
async def delete_file(file_path: str = ""):
    """Delete a file or directory"""
    try:
        if not file_path:
            raise HTTPException(status_code=400, detail="File path is required")
        # Security check
        if ".." in file_path or file_path.startswith("/"):
            raise HTTPException(status_code=400, detail="Invalid file path")
        full_path = os.path.join(BLOG_CACHE_PATH, file_path)
        if not os.path.exists(full_path):
            raise HTTPException(status_code=404, detail="File or directory not found")
        if os.path.isdir(full_path):
            shutil.rmtree(full_path)
        else:
            os.remove(full_path)
        git_add()
        logger.info(f"Deleted: {file_path}")
        return JSONResponse(content={"message": "Deleted successfully"})
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete")

@app.post("/api/file/move")
async def move_file(request: Request):
    """Move a file or directory to a new location"""
    try:
        data = await request.json()
        source_path = data.get("sourcePath", "")
        dest_path = data.get("destPath", "")
        if not source_path or not dest_path:
            raise HTTPException(status_code=400, detail="Both source and destination paths are required")
        # Security check
        if ".." in source_path or source_path.startswith("/") or ".." in dest_path or dest_path.startswith("/"):
            raise HTTPException(status_code=400, detail="Invalid file path")
        full_source_path = os.path.join(BLOG_CACHE_PATH, source_path)
        full_dest_path = os.path.join(BLOG_CACHE_PATH, dest_path)
        if not os.path.exists(full_source_path):
            raise HTTPException(status_code=404, detail="Source file or directory not found")
        if os.path.exists(full_dest_path):
            raise HTTPException(status_code=400, detail="Destination path already exists")
        # Create destination directory if it doesn't exist
        os.makedirs(os.path.dirname(full_dest_path), exist_ok=True)
        shutil.move(full_source_path, full_dest_path)
        git_add()
        logger.info(f"Moved: {source_path} -> {dest_path}")
        return JSONResponse(content={"message": "Moved successfully"})
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to move: {e}")
        raise HTTPException(status_code=500, detail="Failed to move")

@app.post("/api/folder/create")
async def create_folder(request: Request):
    """Create a new folder"""
    try:
        data = await request.json()
        folder_path = data.get("path", "")
        if not folder_path:
            raise HTTPException(status_code=400, detail="Folder path is required")
        # Security check
        if ".." in folder_path or folder_path.startswith("/"):
            raise HTTPException(status_code=400, detail="Invalid folder path")
        full_path = os.path.join(BLOG_CACHE_PATH, folder_path)
        os.makedirs(full_path, exist_ok=True)
        git_add()
        logger.info(f"Folder created: {folder_path}")
        return JSONResponse(content={"message": "Folder created successfully", "path": folder_path})
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create folder: {e}")
        raise HTTPException(status_code=500, detail="Failed to create folder")

# Startup event
@app.on_event("startup")
def startup_event():
    try:
        if not os.path.exists(BLOG_CACHE_PATH):
            os.makedirs(BLOG_CACHE_PATH, exist_ok=True)
            os.makedirs(os.path.join(BLOG_CACHE_PATH, 'content', 'posts'), exist_ok=True)
            os.makedirs(os.path.join(BLOG_CACHE_PATH, 'archetypes'), exist_ok=True)
            with open(os.path.join(BLOG_CACHE_PATH, 'archetypes', 'posts.md'), 'w', encoding='utf-8') as f:
                f.write('---\ntitle: {{title}}\ndate: {{date}}\ncategories: {{categories}}\n---\n\n')
        logger.info("Application startup completed")
    except Exception as e:
        logger.error(f"Failed to initialize workspace: {e}")
        raise HTTPException(status_code=500, detail="Failed to initialize workspace")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=5000)