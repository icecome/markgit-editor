import os
import subprocess
import shutil
import logging
from typing import Optional
from urllib.parse import urlparse

from app.config import (
    BLOG_CACHE_PATH, BLOG_GIT_SSH, BLOG_BRANCH, GIT_SSH_KEY_PATH,
    CMD_AFTER_PUSH, ALLOWED_DEPLOY_SCRIPTS_DIR, logger
)

def sanitize_for_log(text: str) -> str:
    if not text:
        return ''
    if '@' in text and '.' in text:
        parts = text.split('@')
        if len(parts) == 2:
            return f"{parts[0][:3]}***@***"
    if text.startswith('git@'):
        return 'git@***:***'
    if text.startswith('https://') or text.startswith('http://'):
        try:
            parsed = urlparse(text)
            return f"{parsed.scheme}://***@{parsed.netloc.split('@')[-1] if '@' in parsed.netloc else parsed.netloc}/**"
        except:
            return '***'
    if len(text) > 20:
        return text[:10] + '***' + text[-5:]
    return '***'

def get_git_env() -> dict:
    env = os.environ.copy()
    git_repo = BLOG_GIT_SSH
    if git_repo and (git_repo.startswith('git@') or git_repo.startswith('ssh://')):
        ssh_options = '-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o BatchMode=yes -o ConnectTimeout=30'
        if GIT_SSH_KEY_PATH and os.path.exists(GIT_SSH_KEY_PATH):
            env['GIT_SSH_COMMAND'] = f'ssh -i {GIT_SSH_KEY_PATH} {ssh_options}'
        else:
            env['GIT_SSH_COMMAND'] = f'ssh {ssh_options}'
    return env

def ensure_git_remote_config(git_repo: str = None):
    if not git_repo:
        git_repo = BLOG_GIT_SSH
    if not git_repo:
        return False
    try:
        remote_result = subprocess.run(['git', 'remote', '-v'], cwd=BLOG_CACHE_PATH, capture_output=True, text=True)
        has_origin = 'origin' in remote_result.stdout
        if has_origin:
            subprocess.run(['git', 'remote', 'set-url', 'origin', git_repo], cwd=BLOG_CACHE_PATH, check=True, capture_output=True)
            logger.info("已更新远程仓库配置")
        else:
            subprocess.run(['git', 'remote', 'add', 'origin', git_repo], cwd=BLOG_CACHE_PATH, check=True, capture_output=True)
            logger.info("已添加远程仓库配置")
        return True
    except subprocess.CalledProcessError as e:
        logger.warning("更新远程配置失败：" + (e.stderr if e.stderr else str(e)))
        return False

def get_current_branch() -> str:
    result = subprocess.run(['git', 'rev-parse', '--abbrev-ref', 'HEAD'], cwd=BLOG_CACHE_PATH, capture_output=True, text=True)
    return result.stdout.strip() if result.returncode == 0 else 'main'

def get_remote_default_branch() -> str:
    from app.config import BLOG_BRANCH
    remote_head_result = subprocess.run(['git', 'symbolic-ref', 'refs/remotes/origin/HEAD'], cwd=BLOG_CACHE_PATH, capture_output=True, text=True)
    if remote_head_result.returncode == 0:
        return remote_head_result.stdout.strip().replace('refs/remotes/origin/', '')
    return BLOG_BRANCH

def configure_git_user():
    subprocess.run(['git', 'config', 'user.name', 'BlogEditor'], cwd=BLOG_CACHE_PATH, check=True, capture_output=True)
    subprocess.run(['git', 'config', 'user.email', 'editor@blog.local'], cwd=BLOG_CACHE_PATH, check=True, capture_output=True)

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
        from fastapi import HTTPException
        raise HTTPException(status_code=500, detail="Git add 操作失败")

def validate_deploy_command(cmd: str) -> list:
    if not cmd:
        return []
    cmd = cmd.strip()
    if not cmd:
        return []
    parts = cmd.split()
    script_path = parts[0]
    if not os.path.isabs(script_path):
        raise ValueError(f"部署脚本必须使用绝对路径: {script_path}")
    if not os.path.isfile(script_path):
        raise ValueError(f"部署脚本不存在: {script_path}")
    if not os.access(script_path, os.X_OK):
        raise ValueError(f"部署脚本不可执行: {script_path}")
    if ALLOWED_DEPLOY_SCRIPTS_DIR:
        allowed_dir = os.path.abspath(ALLOWED_DEPLOY_SCRIPTS_DIR)
        script_abs = os.path.abspath(script_path)
        if not script_abs.startswith(allowed_dir):
            raise ValueError(f"部署脚本必须在允许目录 {ALLOWED_DEPLOY_SCRIPTS_DIR} 内")
    for part in parts:
        if any(c in part for c in ['|', ';', '&', '$', '`', '>', '<', '\n', '\r']):
            raise ValueError(f"部署命令包含非法字符: {part}")
    return parts

def deploy():
    from fastapi import HTTPException
    try:
        if CMD_AFTER_PUSH:
            try:
                cmd_parts = validate_deploy_command(CMD_AFTER_PUSH)
            except ValueError as e:
                logger.error("部署命令校验失败：" + str(e))
                raise HTTPException(status_code=400, detail=str(e))
            subprocess.run(cmd_parts, check=True)
            logger.info("部署命令已执行")
        else:
            logger.info("未配置部署命令")
    except subprocess.CalledProcessError as e:
        logger.error("部署失败：" + str(e))
        raise HTTPException(status_code=500, detail="部署失败")

def git_commit():
    from fastapi import HTTPException
    from app.file_service import pretty_git_status
    try:
        status = git_status()
        if not status:
            logger.info("没有更改需要提交")
            return
        
        commit_cmd = ['git', 'commit']
        commit_msg = []
        for line in pretty_git_status(status):
            commit_msg.append('-m')
            commit_msg.append(line)
        commit_cmd.extend(commit_msg)
        
        env = get_git_env()
        commit_result = subprocess.run(commit_cmd, cwd=BLOG_CACHE_PATH, check=True, env=env, capture_output=True, text=True)
        logger.info("提交成功：" + commit_result.stdout)
        
        git_repo = BLOG_GIT_SSH
        if not git_repo:
            raise HTTPException(status_code=500, detail="未配置远程仓库地址")
        
        ensure_git_remote_config(git_repo)
        
        current_branch = get_current_branch()
        logger.info("当前分支：" + current_branch)
        
        try:
            fetch_result = subprocess.run(['git', 'fetch', 'origin'], cwd=BLOG_CACHE_PATH, env=env, capture_output=True, text=True, timeout=60)
            logger.info("Fetch result: " + fetch_result.stdout)
        except subprocess.TimeoutExpired:
            logger.warning("Fetch 超时，继续推送")
        except subprocess.CalledProcessError as e:
            logger.warning("Fetch 失败：" + (e.stderr if e.stderr else str(e)))
        
        remote_default_branch = get_remote_default_branch()
        logger.info("远程默认分支：" + remote_default_branch)
        
        push_result = subprocess.run(['git', 'push', '-u', 'origin', current_branch + ':' + remote_default_branch], cwd=BLOG_CACHE_PATH, check=True, env=env, capture_output=True, text=True)
        logger.info("推送成功：" + push_result.stdout)
        
        deploy()
    except subprocess.CalledProcessError as e:
        error_msg = e.stderr if e.stderr else str(e)
        logger.error("Git 操作失败：" + error_msg)
        if 'fatal: not a git repository' in error_msg:
            raise HTTPException(status_code=500, detail="不是 Git 仓库，请先初始化")
        elif 'fatal: Authentication failed' in error_msg:
            raise HTTPException(status_code=500, detail="认证失败，请检查访问权限")
        elif 'fatal: remote error' in error_msg:
            raise HTTPException(status_code=500, detail="远程错误：无法推送")
        elif 'fatal: repository not found' in error_msg:
            raise HTTPException(status_code=500, detail="仓库未找到，请检查仓库地址")
        elif 'fatal: could not read Username' in error_msg:
            raise HTTPException(status_code=500, detail="认证失败，请检查访问权限")
        raise HTTPException(status_code=500, detail="提交操作失败：" + error_msg)
    except Exception as e:
        logger.error("提交失败：" + str(e))
        raise HTTPException(status_code=500, detail="提交失败：" + str(e))

async def pull_updates_async():
    from fastapi import HTTPException
    if not os.path.exists(os.path.join(BLOG_CACHE_PATH, '.git')):
        raise HTTPException(status_code=400, detail="不是 Git 仓库，请先初始化")
    
    ensure_git_remote_config()
    env = get_git_env()
    
    current_branch = get_current_branch()
    logger.info("当前分支：" + current_branch)
    
    result = subprocess.run(['git', 'fetch', 'origin'], check=True, cwd=BLOG_CACHE_PATH, env=env, capture_output=True, text=True)
    logger.info("Fetch result: " + result.stdout)
    
    remote_default_branch = get_remote_default_branch()
    logger.info("远程默认分支：" + remote_default_branch)
    
    status_result = subprocess.run(['git', 'status', '--porcelain'], cwd=BLOG_CACHE_PATH, env=env, capture_output=True, text=True)
    local_changes = status_result.stdout.strip() != ''
    
    if local_changes:
        subprocess.run(['git', 'stash', 'push', '-m', 'auto-stash-before-pull'], check=True, cwd=BLOG_CACHE_PATH, env=env, capture_output=True)
        logger.info("本地更改已暂存")
    
    result = subprocess.run(['git', 'merge', 'origin/' + remote_default_branch], check=True, cwd=BLOG_CACHE_PATH, env=env, capture_output=True, text=True)
    logger.info("Merge result: " + result.stdout)
    
    if local_changes:
        stash_pop = subprocess.run(['git', 'stash', 'pop'], cwd=BLOG_CACHE_PATH, env=env, capture_output=True, text=True)
        if stash_pop.returncode == 0:
            logger.info("本地更改已恢复")
        else:
            logger.warning("无法恢复本地更改：" + stash_pop.stderr)
    
    logger.info("已拉取远程最新更改")

async def init_local_git_async():
    from fastapi import HTTPException
    git_repo = BLOG_GIT_SSH
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
                if git_repo:
                    subprocess.run(['git', 'remote', 'add', 'origin', git_repo], cwd=BLOG_CACHE_PATH, check=True, capture_output=True)
                    configure_git_user()
                    logger.info("已设置远程仓库配置")
                    return {"message": "初始化成功，远程仓库已配置", "status": "remote_configured"}
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
            configure_git_user()
            
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
        subprocess.run(['git', 'init', '-b', 'main'], cwd=BLOG_CACHE_PATH, check=True, capture_output=True)
        configure_git_user()
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
            subprocess.run(['git', 'init', '-b', 'main'], cwd=BLOG_CACHE_PATH, check=True, capture_output=True)
            subprocess.run(['git', 'remote', 'add', 'origin', git_repo], cwd=BLOG_CACHE_PATH, check=True, capture_output=True)
            configure_git_user()
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
        subprocess.run(['git', 'init', '-b', 'main'], cwd=BLOG_CACHE_PATH, check=True, capture_output=True)
        configure_git_user()
        return {"message": "初始化成功，请配置远程仓库地址", "status": "initialized"}

def sync_branch_name():
    try:
        if not os.path.exists(os.path.join(BLOG_CACHE_PATH, '.git')):
            return
        
        current_branch_result = subprocess.run(['git', 'rev-parse', '--abbrev-ref', 'HEAD'], cwd=BLOG_CACHE_PATH, capture_output=True, text=True)
        if current_branch_result.returncode != 0:
            return
        current_branch = current_branch_result.stdout.strip()
        
        remote_result = subprocess.run(['git', 'remote', '-v'], cwd=BLOG_CACHE_PATH, capture_output=True, text=True)
        if 'origin' not in remote_result.stdout:
            return
        
        env = get_git_env()
        subprocess.run(['git', 'fetch', 'origin'], cwd=BLOG_CACHE_PATH, env=env, capture_output=True, text=True, timeout=60)
        
        remote_head_result = subprocess.run(['git', 'symbolic-ref', 'refs/remotes/origin/HEAD'], cwd=BLOG_CACHE_PATH, capture_output=True, text=True)
        if remote_head_result.returncode != 0:
            return
        remote_default_branch = remote_head_result.stdout.strip().replace('refs/remotes/origin/', '')
        
        if current_branch != remote_default_branch:
            logger.info(f"本地分支 '{current_branch}' 与远程分支 '{remote_default_branch}' 不一致，正在重命名...")
            subprocess.run(['git', 'branch', '-m', current_branch, remote_default_branch], cwd=BLOG_CACHE_PATH, check=True, capture_output=True)
            subprocess.run(['git', 'branch', '--set-upstream-to=origin/' + remote_default_branch, remote_default_branch], cwd=BLOG_CACHE_PATH, capture_output=True)
            logger.info(f"已将本地分支重命名为 '{remote_default_branch}' 并设置跟踪远程分支")
    except Exception as e:
        logger.warning("同步分支名称时出错：" + str(e))
