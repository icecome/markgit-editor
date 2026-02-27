import datetime
import html.parser
import os
import re
import shutil
import subprocess
import traceback
import uuid
import logging

from fastapi import FastAPI, HTTPException, Depends, UploadFile, File, Form, status
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
BLOG_BRANCH = os.getenv('BLOG_BRANCH', 'master')
CMD_AFTER_PUSH = os.getenv('CMD_AFTER_PUSH', 'bash /home/yyq/update_blog.sh')
NEW_BLOG_TEMPLATE_PATH = os.getenv('NEW_BLOG_TEMPLATE_PATH', os.path.join(BLOG_CACHE_PATH, 'archetypes', 'posts.md'))
GIT_SSH_KEY_PATH = os.getenv('GIT_SSH_KEY_PATH', '')

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
            commit_msg = ['-m', "online editor auto update"]
        commit_cmd.extend(commit_msg)
        env = os.environ.copy()
        if GIT_SSH_KEY_PATH:
            env['GIT_SSH_COMMAND'] = f'ssh -i {GIT_SSH_KEY_PATH} -o StrictHostKeyChecking=no'
        subprocess.run(commit_cmd, cwd=BLOG_CACHE_PATH, check=True, env=env)
        subprocess.run(['git', 'push'], cwd=BLOG_CACHE_PATH, check=True, env=env)
        deploy()
    except subprocess.CalledProcessError as e:
        logger.error(f"Git commit failed: {e}")
        raise HTTPException(status_code=500, detail="Git commit operation failed")

def deploy():
    try:
        subprocess.run(CMD_AFTER_PUSH.split(' '), check=True)
        logger.info("Deployment command executed")
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
            env['GIT_SSH_COMMAND'] = f'ssh -i {GIT_SSH_KEY_PATH} -o StrictHostKeyChecking=no'
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
            shutil.rmtree(BLOG_CACHE_PATH, ignore_errors=False)
        os.makedirs(BLOG_CACHE_PATH, exist_ok=True)
        env = os.environ.copy()
        if GIT_SSH_KEY_PATH:
            env['GIT_SSH_COMMAND'] = f'ssh -i {GIT_SSH_KEY_PATH} -o StrictHostKeyChecking=no'
        subprocess.run(['git', 'clone', BLOG_GIT_SSH, '-b', BLOG_BRANCH, BLOG_CACHE_PATH], env=env)
        logger.info(f"Git repository cloned from {BLOG_GIT_SSH}")
    except subprocess.CalledProcessError as e:
        logger.error(f"Git clone failed: {e}")
