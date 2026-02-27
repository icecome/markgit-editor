import os
import re
import logging

PROG_PATH = os.path.dirname(os.path.dirname(__file__))

MAX_CONTENT_LENGTH = int(os.getenv('MAX_CONTENT_LENGTH', str(20 * 1024 * 1024)))
BLOG_CACHE_PATH = os.getenv('BLOG_CACHE_PATH', os.path.join(PROG_PATH, 'blog_cache'))
BLOG_GIT_SSH = os.getenv('BLOG_GIT_SSH', '')
POSTS_PATH = os.getenv('POSTS_PATH', os.path.join(BLOG_CACHE_PATH, 'content', 'posts'))
BLOG_BRANCH = os.getenv('BLOG_BRANCH', 'main')
CMD_AFTER_PUSH = os.getenv('CMD_AFTER_PUSH', '')
NEW_BLOG_TEMPLATE_PATH = os.getenv('NEW_BLOG_TEMPLATE_PATH', os.path.join(BLOG_CACHE_PATH, 'archetypes', 'posts.md'))
GIT_SSH_KEY_PATH = os.getenv('GIT_SSH_KEY_PATH', '')

CORS_ORIGINS = os.getenv('CORS_ORIGINS', 'http://localhost:5000,http://127.0.0.1:5000')
ALLOWED_ORIGINS = [origin.strip() for origin in CORS_ORIGINS.split(',') if origin.strip()]

HIDDEN_FOLDERS_DEFAULT = '.git,.github,.idea,.vscode,.vs,node_modules,.node_modules,__pycache__,.pytest_cache,.mypy_cache,.tox,.eggs,.history,.Trash,themes,public,resources,static,assets,layouts,archetypes,data,i18n'
HIDDEN_FOLDERS = set(os.getenv('HIDDEN_FOLDERS', HIDDEN_FOLDERS_DEFAULT).split(','))

ALLOWED_FILE_EXTENSIONS_DEFAULT = '.md,.markdown,.mdown,.mkd,.mkdown,.ronn,'
ALLOWED_FILE_EXTENSIONS = set(ext.strip() if ext.strip() else '' for ext in os.getenv('ALLOWED_FILE_EXTENSIONS', ALLOWED_FILE_EXTENSIONS_DEFAULT).split(','))

ALLOWED_DEPLOY_SCRIPTS_DIR = os.getenv('ALLOWED_DEPLOY_SCRIPTS_DIR', '')

RULE = re.compile(r'^[a-zA-Z0-9_-]+$')

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
