import os
import re
import logging
from pathlib import Path
from dotenv import load_dotenv

# 加载 .env 文件
load_dotenv()

# 基础路径配置
BASE_DIR = Path(__file__).resolve().parent.parent
BLOG_CACHE_PATH = os.path.normpath(os.getenv('BLOG_CACHE_PATH', str(BASE_DIR / 'blog_cache')))
POSTS_PATH = os.path.join(BLOG_CACHE_PATH, 'content', 'posts')
NEW_BLOG_TEMPLATE_PATH = os.path.join(BLOG_CACHE_PATH, 'archetypes', 'posts.md')

# 自动从 Git 缓存中移除 .sessions 目录（如果存在）
try:
    import subprocess
    sessions_path = os.path.join(BLOG_CACHE_PATH, '.sessions')
    if os.path.exists(sessions_path):
        subprocess.run(['git', 'rm', '-r', '--cached', sessions_path], 
                      cwd=BASE_DIR, capture_output=True)
except Exception:
    pass

# Git 配置
BLOG_GIT_SSH = os.getenv('BLOG_GIT_SSH', '')
BLOG_BRANCH = os.getenv('BLOG_BRANCH', 'main')
GIT_SSH_KEY_PATH = os.getenv('GIT_SSH_KEY_PATH', '')

# 部署配置
CMD_AFTER_PUSH = os.getenv('CMD_AFTER_PUSH', '')
ALLOWED_DEPLOY_SCRIPTS_DIR = os.getenv('ALLOWED_DEPLOY_SCRIPTS_DIR', '')

# 文件过滤配置
HIDDEN_FOLDERS = {'.git', '.github', '.vscode', 'node_modules', '__pycache__', '.pytest_cache', '.sessions'}
ALLOWED_FILE_EXTENSIONS = {'.md', '.txt', '.html', '.css', '.js', '.json', '.yaml', '.yml', '.toml', '.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp'}

# 默认白名单扩展名（只显示这些类型的文件）
DEFAULT_WHITELIST_EXTENSIONS = {'.md', '.txt', '.toml', '.yaml', '.yml', '.json', '.xml', '.ini', '.cfg', '.conf'}

# 白名单例外（在白名单模式下允许显示的额外目录/文件）
DEFAULT_WHITELIST_EXCEPTIONS = []

# 文件排除规则 (支持正则表达式)
FILE_EXCLUDE_PATTERNS = [
    r'^\..*',  # 隐藏文件
    r'^node_modules$',
    r'^__pycache__$',
    r'\.egg-info$',
    r'\.git$',
]

# 日志配置
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# CORS 配置 - 根据环境动态配置
is_production = os.getenv('PRODUCTION', 'false').lower() == 'true'

if is_production:
    # 生产环境：严格限制来源
    CORS_ORIGINS_STR = os.getenv('CORS_ORIGINS', 'https://your-domain.com')
    logger.info(f"生产环境 CORS 配置：{CORS_ORIGINS_STR}")
else:
    # 开发环境：允许 localhost
    CORS_ORIGINS_STR = os.getenv('CORS_ORIGINS', 'http://localhost:13131,http://127.0.0.1:13131')
    logger.info(f"开发环境 CORS 配置：{CORS_ORIGINS_STR}")

# 解析 CORS 来源
ALLOWED_ORIGINS = [origin.strip() for origin in CORS_ORIGINS_STR.split(',') if origin.strip()]

# 用户会话配置
SESSION_TIMEOUT_HOURS = int(os.getenv('SESSION_TIMEOUT_HOURS', '1'))  # 1 小时无操作超时
MAX_DISK_USAGE_GB = int(os.getenv('MAX_DISK_USAGE_GB', '1'))
CLEANUP_CHECK_INTERVAL_MINUTES = int(os.getenv('CLEANUP_CHECK_INTERVAL_MINUTES', '60'))

# OAuth 配置
GITHUB_CLIENT_ID = os.getenv('GITHUB_CLIENT_ID', '')
GITHUB_CLIENT_SECRET = os.getenv('GITHUB_CLIENT_SECRET', '')
GITHUB_SCOPE = os.getenv('GITHUB_SCOPE', 'repo workflow')
MAX_CONCURRENT_SESSIONS = int(os.getenv('MAX_CONCURRENT_SESSIONS', '100'))

# 文件名验证规则
RULE = re.compile(r'^[a-zA-Z0-9_\u4e00-\u9fa5-]+$')
