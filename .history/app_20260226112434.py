import datetime
import html.parser
import os
import re
import shutil
import subprocess
import traceback
import uuid

from fastapi import FastAPI, HTTPException, Depends, UploadFile, File, Form
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
app.mount("", StaticFiles(directory=".", html=True), name="static")

# Configuration
PROG_PATH = os.path.dirname(__file__)
MAX_CONTENT_LENGTH = int(os.getenv('MAX_CONTENT_LENGTH', str(20 * 1024 * 1024)))
BLOG_CACHE_PATH = os.getenv('BLOG_CACHE_PATH', os.path.join(PROG_PATH, 'blog_cache'))
BLOG_GIT_SSH = os.getenv('BLOG_GIT_SSH', 'git@gitee.com:RainbowYYQ/my-blog.git')
POSTS_PATH = os.getenv('POSTS_PATH', os.path.join(BLOG_CACHE_PATH, 'content', 'posts'))
BLOG_BRANCH = os.getenv('BLOG_BRANCH', 'master')
CMD_AFTER_PUSH = os.getenv('CMD_AFTER_PUSH', 'bash /home/yyq/update_blog.sh')
NEW_BLOG_TEMPLATE_PATH = os.getenv('NEW_BLOG_TEMPLATE_PATH', os.path.join(BLOG_CACHE_PATH, 'archetypes', 'posts.md'))

# Security
SECRET_KEY = os.getenv('SECRET_KEY', 'your-secret-key')
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

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

# Global variables
IS_INIT_WORKSPACE = False
RULE = re.compile(r'[a-zA-Z0-9]+')

# Helper functions
def verify_password(plain_password, hashed_password