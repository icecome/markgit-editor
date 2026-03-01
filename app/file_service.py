import os
import re
import html
import shutil
import yaml
import logging
from typing import Optional
from urllib.parse import unquote

from app.config import (
    BLOG_CACHE_PATH, POSTS_PATH, NEW_BLOG_TEMPLATE_PATH,
    HIDDEN_FOLDERS, ALLOWED_FILE_EXTENSIONS, RULE, 
    FILE_EXCLUDE_PATTERNS, DEFAULT_WHITELIST_EXTENSIONS, logger
)
from app.git_service import git_add

def check_name(dir_name: str):
    from fastapi import HTTPException
    if not dir_name or not RULE.match(dir_name):
        raise HTTPException(status_code=400, detail="Invalid directory name. Only alphanumeric characters, hyphens and underscores are allowed.")

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
        yaml_content = '\n'.join(yaml_lines)
        if not yaml_content.strip():
            return {}
        return yaml.safe_load(yaml_content) or {}
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

def pretty_git_status(status_result: list) -> list:
    def _get_title(filepath: str) -> str:
        if filepath.endswith("index.md"):
            post_yaml = get_md_yaml(os.path.join(BLOG_CACHE_PATH, filepath))
            return post_yaml.get('title', '') if post_yaml else ''
        return ''

    # 需要过滤的系统目录和文件
    system_paths = {
        '.sessions', '.git', '.github', '.vscode', '.idea',
        '__pycache__', '.pytest_cache', 'node_modules',
        '.env', '.env.local', '.env.*.local'
    }
    
    # 统计删除的文件数量
    delete_count = sum(1 for s in status_result if s.strip().startswith('D '))
    
    # 如果删除文件超过 20 个，说明可能是仓库初始化，不显示删除信息
    is_initialization = delete_count > 20
    
    status_result_for_show = []
    for status in status_result:
        # 去除首尾空格
        status = status.strip()
        
        # 跳过空行
        if not status:
            continue
            
        # 跳过以 "Am" 开头的行（这是 Git 的特殊状态标记）
        if status.startswith('Am'):
            continue
        
        parts = status.split(maxsplit=1)
        if len(parts) < 2:
            status_result_for_show.append(status)
            continue
        flag, filepath = parts
        
        # 过滤掉系统目录的变更
        first_part = filepath.split('/')[0]
        if first_part in system_paths or filepath.startswith('.sessions/') or filepath.startswith('.git/'):
            continue
        
        # 如果是仓库初始化，不显示删除信息
        if is_initialization and (flag == 'D' or flag == ' D'):
            continue
        
        if flag == 'M' or flag == ' M' or flag == 'M ':
            status_result_for_show.append("Modified " + _get_title(filepath) + " " + filepath)
        elif flag == 'A' or flag == ' A' or flag == 'A ':
            status_result_for_show.append("Added " + _get_title(filepath) + " " + filepath)
        elif flag == 'D' or flag == ' D' or flag == 'D ':
            status_result_for_show.append("Deleted " + filepath)
        elif flag == '??':
            status_result_for_show.append("Untracked " + filepath)
        elif flag == 'R':
            status_result_for_show.append("Renamed " + filepath)
        else:
            status_result_for_show.append(status)
    
    # 如果过滤后没有任何变更，返回空列表
    return status_result_for_show

def read_post_template() -> str:
    try:
        with open(NEW_BLOG_TEMPLATE_PATH, mode='r', encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
        logger.error("模板文件未找到：" + NEW_BLOG_TEMPLATE_PATH)
        return '---\ntitle: {{title}}\ndate: {{date}}\ncategories: {{categories}}\n---\n\n'

def is_allowed_file(filename: str) -> bool:
    _, ext = os.path.splitext(filename)
    return ext.lower() in ALLOWED_FILE_EXTENSIONS

def should_hide_path(path: str) -> bool:
    """判断路径是否应该隐藏"""
    parts = path.replace('\\', '/').split('/')
    for part in parts:
        if part in HIDDEN_FOLDERS or part.endswith('.egg-info'):
            return True
    return False

def should_exclude_file(path: str, 
                       additional_patterns: Optional[list] = None,
                       simple_patterns: Optional[list] = None,
                       use_whitelist: bool = False,
                       whitelist_extensions: Optional[set] = None,
                       whitelist_exceptions: Optional[list] = None) -> bool:
    """根据排除规则判断文件是否应该被排除
    
    Args:
        path: 文件路径（相对于根目录的路径，如：static/style.css）
        additional_patterns: 额外的正则表达式排除规则
        simple_patterns: 简单模式排除规则（后缀、文件名、路径）
        use_whitelist: 是否使用白名单模式
        whitelist_extensions: 白名单扩展名集合
        whitelist_exceptions: 白名单例外（允许显示的目录/文件）
        
    Returns:
        是否应该排除
    
    排除模式说明:
        1. 正则表达式模式：.*\.css$ (排除任意目录下 .css 结尾的文件)
        2. 简单模式:
           - .css : 排除 .css 后缀文件
           - test.txt : 排除名为 test.txt 的文件
           - dist/ : 排除 dist 目录
           - node_modules/ : 排除 node_modules 目录
        3. 白名单例外:
           - src/ : 显示 src 目录及其内容
           - config.json : 显示 config.json 文件
           - assets/ : 显示 assets 目录及其内容
    """
    filename = os.path.basename(path)
    path_normalized = path.replace('\\', '/')  # 统一使用正斜杠
    _, file_ext = os.path.splitext(filename)
    file_ext_lower = file_ext.lower()
    
    # 0. 白名单例外检查：如果在例外列表中，直接允许显示
    if whitelist_exceptions:
        for exception in whitelist_exceptions:
            exception = exception.strip()
            if not exception:
                continue
            # 目录例外：如果路径以该目录开头
            if exception.endswith('/'):
                dir_name = exception[:-1]
                if path_normalized.startswith(dir_name + '/') or path_normalized == dir_name:
                    return False
            # 文件例外：精确匹配文件名
            elif filename == exception:
                return False
            # 路径包含匹配
            elif exception in path_normalized:
                return False
    
    # 1. 白名单模式：如果启用，只允许白名单中的扩展名
    if use_whitelist and whitelist_extensions:
        if file_ext_lower not in whitelist_extensions:
            return True
    
    # 2. 正则表达式排除规则
    all_patterns = FILE_EXCLUDE_PATTERNS + (additional_patterns or [])
    for pattern in all_patterns:
        try:
            # 尝试匹配完整路径
            if re.search(pattern, path_normalized, re.IGNORECASE):
                return True
            # 尝试匹配文件名
            if re.search(pattern, filename, re.IGNORECASE):
                return True
        except re.error as e:
            logger.warning(f"正则表达式错误 {pattern}: {e}")
    
    # 3. 简单模式排除规则
    if simple_patterns:
        for simple_pattern in simple_patterns:
            simple_pattern = simple_pattern.strip()
            if not simple_pattern:
                continue
            
            # 后缀匹配：.css, .js 等
            if simple_pattern.startswith('.'):
                if file_ext_lower == simple_pattern.lower():
                    return True
            # 精确文件名匹配：test.txt
            elif '/' not in simple_pattern and '\\' not in simple_pattern:
                if filename == simple_pattern:
                    return True
            # 路径/目录匹配：dist/, node_modules/
            elif simple_pattern.endswith('/'):
                dir_name = simple_pattern[:-1]
                if dir_name in path_normalized:
                    return True
            # 包含匹配
            else:
                if simple_pattern in path_normalized:
                    return True
    
    return False

def get_files_recursive(directory: str, 
                       user_session_path: Optional[str] = None,
                       exclude_patterns: Optional[list] = None,
                       simple_patterns: Optional[list] = None,
                       use_whitelist: bool = False,
                       whitelist_extensions: Optional[set] = None,
                       whitelist_exceptions: Optional[list] = None) -> list:
    """递归获取文件列表
    
    Args:
        directory: 根目录
        user_session_path: 用户会话路径，如果提供则只显示该路径下的内容
        exclude_patterns: 正则表达式排除规则
        simple_patterns: 简单模式排除规则
        use_whitelist: 是否使用白名单模式
        whitelist_extensions: 白名单扩展名集合
        whitelist_exceptions: 白名单例外（允许显示的目录/文件）
        
    Returns:
        文件列表
    """
    files = []
    valid_directories = set()
    try:
        for root, dirs, filenames in os.walk(directory):
            dirs[:] = [d for d in dirs if d not in HIDDEN_FOLDERS and not d.endswith('.egg-info')]
            
            for filename in filenames:
                if not is_allowed_file(filename):
                    continue
                relative_path = os.path.relpath(os.path.join(root, filename), directory)
                if should_hide_path(relative_path):
                    continue
                if should_exclude_file(
                    relative_path, 
                    exclude_patterns, 
                    simple_patterns, 
                    use_whitelist, 
                    whitelist_extensions,
                    whitelist_exceptions
                ):
                    continue
                files.append({
                    "path": relative_path.replace('\\', '/'),
                    "type": "file",
                    "size": os.path.getsize(os.path.join(root, filename))
                })
                parts = relative_path.replace('\\', '/').split('/')
                for i in range(len(parts) - 1):
                    valid_directories.add('/'.join(parts[:i+1]))
            
            for dirname in dirs:
                relative_path = os.path.relpath(os.path.join(root, dirname), directory)
                if should_hide_path(relative_path):
                    continue
                if should_exclude_file(
                    relative_path, 
                    exclude_patterns, 
                    simple_patterns, 
                    use_whitelist, 
                    whitelist_extensions,
                    whitelist_exceptions
                ):
                    continue
                normalized_path = relative_path.replace('\\', '/')
                if normalized_path in valid_directories:
                    files.append({
                        "path": normalized_path,
                        "type": "directory"
                    })
    except Exception as e:
        logger.error("获取文件列表失败：" + str(e))
    return files

def validate_file_path(file_path: str, base_path: Optional[str] = None) -> str:
    """验证文件路径的合法性
    
    Args:
        file_path: 文件路径
        base_path: 基础路径，默认为 BLOG_CACHE_PATH
        
    Returns:
        完整的文件路径
        
    Raises:
        HTTPException: 路径不合法时抛出
    """
    from fastapi import HTTPException
    
    if not file_path:
        raise HTTPException(status_code=400, detail="File path cannot be empty")
    
    if base_path is None:
        base_path = BLOG_CACHE_PATH
    
    decoded_path = unquote(file_path)
    for check_path in [file_path, decoded_path]:
        if ".." in check_path or check_path.startswith("/"):
            raise HTTPException(status_code=400, detail="Invalid file path")
        if "\\" in check_path and os.name != 'nt':
            raise HTTPException(status_code=400, detail="Invalid file path")
        if "%2e%2e" in check_path.lower() or "%2f" in check_path.lower():
            raise HTTPException(status_code=400, detail="Invalid file path")
    
    full_path = os.path.normpath(os.path.join(base_path, decoded_path))
    abs_base_path = os.path.abspath(base_path)
    abs_full_path = os.path.abspath(full_path)
    
    if not abs_full_path.startswith(abs_base_path):
        raise HTTPException(status_code=400, detail="Invalid file path")
    
    return abs_full_path
