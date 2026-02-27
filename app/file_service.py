import os
import html
import shutil
import yaml
import logging
from typing import Optional
from urllib.parse import unquote

from app.config import (
    BLOG_CACHE_PATH, POSTS_PATH, NEW_BLOG_TEMPLATE_PATH,
    HIDDEN_FOLDERS, ALLOWED_FILE_EXTENSIONS, RULE, logger
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

def is_allowed_file(filename: str) -> bool:
    _, ext = os.path.splitext(filename)
    return ext.lower() in ALLOWED_FILE_EXTENSIONS

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
                if not is_allowed_file(filename):
                    continue
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
    from fastapi import HTTPException
    if not file_path:
        raise HTTPException(status_code=400, detail="File path cannot be empty")
    decoded_path = unquote(file_path)
    for check_path in [file_path, decoded_path]:
        if ".." in check_path or check_path.startswith("/"):
            raise HTTPException(status_code=400, detail="Invalid file path")
        if "\\" in check_path and os.name != 'nt':
            raise HTTPException(status_code=400, detail="Invalid file path")
        if "%2e%2e" in check_path.lower() or "%2f" in check_path.lower():
            raise HTTPException(status_code=400, detail="Invalid file path")
    full_path = os.path.normpath(os.path.join(BLOG_CACHE_PATH, decoded_path))
    abs_cache_path = os.path.abspath(BLOG_CACHE_PATH)
    abs_full_path = os.path.abspath(full_path)
    if not abs_full_path.startswith(abs_cache_path):
        raise HTTPException(status_code=400, detail="Invalid file path")
    return abs_full_path
