import os
import subprocess
import shutil
import logging
import time
from typing import Optional
from urllib.parse import urlparse

import app.config as config
from app.auth.token_store import token_store
from app.context_manager import get_current_cache_path, setup_git_context, get_session_path

logger = logging.getLogger(__name__)

def get_oauth_token(session_id: str) -> Optional[str]:
    """获取 OAuth 访问令牌"""
    if not session_id:
        return None
    
    token_info = token_store.get(session_id)
    if not token_info:
        return None
    
    return token_info.get("access_token")

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

def get_git_env(session_id: Optional[str] = None) -> dict:
    """获取 Git 环境变量，支持 OAuth 令牌"""
    env = os.environ.copy()
    git_repo = config.BLOG_GIT_SSH
    
    # 检查是否有 OAuth 令牌
    oauth_token = get_oauth_token(session_id) if session_id else None
    
    if oauth_token:
        # 使用 OAuth 令牌进行 HTTPS 认证
        logger.info("使用 OAuth 令牌进行 Git 认证")
        # 设置临时环境变量用于 Git 操作
        env['MARKGIT_OAUTH_TOKEN'] = oauth_token
    elif git_repo and (git_repo.startswith('git@') or git_repo.startswith('ssh://')):
        # 使用 SSH 认证
        ssh_options = '-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o BatchMode=yes -o ConnectTimeout=30'
        if config.GIT_SSH_KEY_PATH and os.path.exists(config.GIT_SSH_KEY_PATH):
            env['GIT_SSH_COMMAND'] = f'ssh -i {config.GIT_SSH_KEY_PATH} {ssh_options}'
        else:
            env['GIT_SSH_COMMAND'] = f'ssh {ssh_options}'
    
    return env

def ensure_git_remote_config(git_repo: str = None):
    if not git_repo:
        git_repo = config.BLOG_GIT_SSH
    if not git_repo:
        return False
    try:
        cache_path = get_current_cache_path()
        remote_result = subprocess.run(['git', 'remote', '-v'], cwd=cache_path, capture_output=True, text=True)
        has_origin = 'origin' in remote_result.stdout
        if has_origin:
            subprocess.run(['git', 'remote', 'set-url', 'origin', git_repo], cwd=cache_path, check=True, capture_output=True)
            logger.info("已更新远程仓库配置")
        else:
            subprocess.run(['git', 'remote', 'add', 'origin', git_repo], cwd=cache_path, check=True, capture_output=True)
            logger.info("已添加远程仓库配置")
        return True
    except subprocess.CalledProcessError as e:
        logger.warning("更新远程配置失败：" + (e.stderr if e.stderr else str(e)))
        return False

def get_current_branch() -> str:
    cache_path = get_current_cache_path()
    result = subprocess.run(['git', 'rev-parse', '--abbrev-ref', 'HEAD'], cwd=cache_path, capture_output=True, text=True)
    return result.stdout.strip() if result.returncode == 0 else 'main'

def get_remote_default_branch() -> str:
    cache_path = get_current_cache_path()
    remote_head_result = subprocess.run(['git', 'symbolic-ref', 'refs/remotes/origin/HEAD'], cwd=cache_path, capture_output=True, text=True)
    if remote_head_result.returncode == 0:
        return remote_head_result.stdout.strip().replace('refs/remotes/origin/', '')
    return config.BLOG_BRANCH

def configure_git_user(session_id: Optional[str] = None, cache_path: Optional[str] = None):
    """
    配置 Git 用户信息
    
    Args:
        session_id: OAuth 会话 ID，用于获取 GitHub 用户信息（可选）
        cache_path: 可选的缓存路径，如果不提供则从线程局部存储获取
    
    Note:
        如果没有提供 session_id 或无法获取 GitHub 用户信息，
        将使用默认配置 "MarkGit User <markgit@example.com>"
    """
    # 获取缓存路径
    if not cache_path:
        cache_path = get_current_cache_path()
    
    # 默认 Git 用户配置
    default_name = "MarkGit User"
    default_email = "markgit@example.com"
    
    # 如果没有 session_id，使用默认配置
    if not session_id:
        logger.info(f"未提供 OAuth 会话 ID，使用默认 Git 用户配置：{default_name}")
        subprocess.run(['git', 'config', 'user.name', default_name], 
                     cwd=cache_path, check=True, capture_output=True)
        subprocess.run(['git', 'config', 'user.email', default_email], 
                     cwd=cache_path, check=True, capture_output=True)
        logger.info(f"Git 用户已配置：{default_name} <{default_email}>")
        return
    
    # 尝试从 OAuth 获取用户信息
    from app.auth.token_store import token_store
    
    token_info = token_store.get(session_id)
    if not token_info or not token_info.get('access_token'):
        logger.warning(f"OAuth 会话 {session_id[:8]}... 无效或已过期，使用默认 Git 用户配置")
        subprocess.run(['git', 'config', 'user.name', default_name], 
                     cwd=cache_path, check=True, capture_output=True)
        subprocess.run(['git', 'config', 'user.email', default_email], 
                     cwd=cache_path, check=True, capture_output=True)
        logger.info(f"Git 用户已配置：{default_name} <{default_email}>")
        return
    
    try:
        # 使用同步 HTTP 客户端获取 GitHub 用户信息
        import httpx
        with httpx.Client(verify=False) as client:
            response = client.get(
                "https://api.github.com/user",
                headers={
                    "Authorization": f"token {token_info['access_token']}",
                    "Accept": "application/json",
                    "User-Agent": "MarkGit-Editor"
                },
                timeout=10.0
            )
            
            if response.status_code == 200:
                user_info = response.json()
                # 使用 GitHub 用户名和邮箱
                git_name = user_info.get('name') or user_info.get('login')
                git_email = user_info.get('email') or f"{user_info.get('login')}@users.noreply.github.com"
                
                if not git_name:
                    git_name = default_name
                    git_email = default_email
                
                subprocess.run(['git', 'config', 'user.name', git_name], 
                             cwd=cache_path, check=True, capture_output=True)
                subprocess.run(['git', 'config', 'user.email', git_email], 
                             cwd=cache_path, check=True, capture_output=True)
                logger.info(f"Git 用户已配置：{git_name} <{git_email}>")
            else:
                logger.warning(f"获取 GitHub 用户信息失败：{response.status_code}，使用默认配置")
                subprocess.run(['git', 'config', 'user.name', default_name], 
                             cwd=cache_path, check=True, capture_output=True)
                subprocess.run(['git', 'config', 'user.email', default_email], 
                             cwd=cache_path, check=True, capture_output=True)
                logger.info(f"Git 用户已配置：{default_name} <{default_email}>")
    except httpx.RequestError as e:
        logger.warning(f"请求 GitHub API 失败：{e}，使用默认配置")
        subprocess.run(['git', 'config', 'user.name', default_name], 
                     cwd=cache_path, check=True, capture_output=True)
        subprocess.run(['git', 'config', 'user.email', default_email], 
                     cwd=cache_path, check=True, capture_output=True)
        logger.info(f"Git 用户已配置：{default_name} <{default_email}>")
    except Exception as e:
        logger.warning(f"配置 Git 用户失败：{e}，使用默认配置")
        subprocess.run(['git', 'config', 'user.name', default_name], 
                     cwd=cache_path, check=True, capture_output=True)
        subprocess.run(['git', 'config', 'user.email', default_email], 
                     cwd=cache_path, check=True, capture_output=True)
        logger.info(f"Git 用户已配置：{default_name} <{default_email}>")

def git_status() -> list:
    try:
        cache_path = get_current_cache_path()
        logger.info(f"Git status 操作目录：{cache_path}")
        output = subprocess.run(['git', 'status', '-s'], cwd=cache_path, capture_output=True, check=True)
        status_lines = [line.strip() for line in output.stdout.decode('utf-8').splitlines()]
        logger.info(f"Git status 结果：{len(status_lines)} 行变更")
        for line in status_lines[:5]:  # 只显示前 5 行
            logger.info(f"  - {line}")
        if len(status_lines) > 5:
            logger.info(f"  ... 还有 {len(status_lines) - 5} 行")
        return status_lines
    except subprocess.CalledProcessError as e:
        logger.error(f"Git status 失败：{e}, stderr: {e.stderr.decode('utf-8', errors='ignore')}")
        return []

def git_add():
    try:
        cache_path = get_current_cache_path()
        logger.info(f"Git add 操作目录：{cache_path}")
        result = subprocess.run(['git', 'add', '-A'], cwd=cache_path, capture_output=True, check=True)
        logger.info(f"Git add 成功，输出：{result.stdout.decode('utf-8', errors='ignore')[:200]}")
    except subprocess.CalledProcessError as e:
        logger.error(f"Git add 失败：{e}, stderr: {e.stderr.decode('utf-8', errors='ignore')}")
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
    # 强制要求配置允许目录（生产环境必须配置）
    allowed_dir = os.getenv('ALLOWED_DEPLOY_SCRIPTS_DIR', '')
    if not allowed_dir:
        logger.error("部署命令执行失败：未配置 ALLOWED_DEPLOY_SCRIPTS_DIR 环境变量")
        raise ValueError("必须配置 ALLOWED_DEPLOY_SCRIPTS_DIR 环境变量以指定允许的部署脚本目录")
    
    # 验证脚本在允许目录内
    abs_script = os.path.abspath(script_path)
    abs_allowed = os.path.abspath(allowed_dir)
    if not abs_script.startswith(abs_allowed + os.sep) and abs_script != abs_allowed:
        logger.error(f"部署脚本不在允许目录内：{abs_script} (允许目录：{abs_allowed})")
        raise ValueError(f"部署脚本必须在允许目录内：{allowed_dir}")
    for part in parts:
        if any(c in part for c in ['|', ';', '&', '$', '`', '>', '<', '\n', '\r']):
            raise ValueError(f"部署命令包含非法字符: {part}")
    return parts

def deploy():
    from fastapi import HTTPException
    try:
        if config.CMD_AFTER_PUSH:
            try:
                cmd_parts = validate_deploy_command(config.CMD_AFTER_PUSH)
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

def git_commit(session_id: Optional[str] = None):
    from fastapi import HTTPException
    from app.file_service import pretty_git_status
    from app.session_manager import session_manager
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
        
        env = get_git_env(session_id)
        cache_path = get_current_cache_path()
        commit_result = subprocess.run(commit_cmd, cwd=cache_path, check=True, env=env, capture_output=True, text=True)
        logger.info("提交成功：" + commit_result.stdout)
        
        # 优先使用会话级别的 Git 仓库配置
        git_repo = ''
        if session_id:
            git_repo = session_manager.get_session_git_repo(session_id)
        if not git_repo:
            git_repo = config.BLOG_GIT_SSH
        if not git_repo:
            raise HTTPException(status_code=500, detail="未配置远程仓库地址")
        
        ensure_git_remote_config(git_repo)
        
        current_branch = get_current_branch()
        logger.info("当前分支：" + current_branch)
        
        try:
            fetch_result = subprocess.run(['git', 'fetch', 'origin'], cwd=cache_path, env=env, capture_output=True, text=True, timeout=60)
            logger.info("Fetch result: " + fetch_result.stdout)
        except subprocess.TimeoutExpired:
            logger.warning("Fetch 超时，继续推送")
        except subprocess.CalledProcessError as e:
            logger.warning("Fetch 失败：" + (e.stderr if e.stderr else str(e)))
        
        remote_default_branch = get_remote_default_branch()
        logger.info("远程默认分支：" + remote_default_branch)
        
        push_result = subprocess.run(['git', 'push', '-u', 'origin', current_branch + ':' + remote_default_branch], cwd=cache_path, check=True, env=env, capture_output=True, text=True)
        logger.info("推送成功：" + push_result.stdout)
        
        deploy()
    except subprocess.CalledProcessError as e:
        error_msg = e.stderr if e.stderr else str(e)
        logger.error("Git 操作失败：" + error_msg)  # 详细错误记录到日志
        
        # 返回用户友好的错误信息，不包含敏感路径
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
        elif 'Permission denied' in error_msg or 'password' in error_msg.lower():
            logger.error("Git 认证失败")  # 只记录到日志
            raise HTTPException(status_code=403, detail="Git 认证失败")
        else:
            logger.error("Git 推送失败，详细错误已记录到日志")
            raise HTTPException(status_code=500, detail="Git 操作失败，请查看服务器日志")
    except Exception as e:
        logger.error("提交失败：" + str(e))
        raise HTTPException(status_code=500, detail="提交失败：" + str(e))

async def pull_updates_async(session_id: Optional[str] = None):
    from fastapi import HTTPException
    from app.session_manager import session_manager
    
    cache_path = get_current_cache_path()
    
    if not os.path.exists(os.path.join(cache_path, '.git')):
        raise HTTPException(status_code=400, detail="不是 Git 仓库，请先初始化")
    
    # 优先使用会话级别的 Git 仓库配置
    git_repo = ''
    if session_id:
        git_repo = session_manager.get_session_git_repo(session_id)
    if not git_repo:
        git_repo = config.BLOG_GIT_SSH
    
    ensure_git_remote_config(git_repo)
    env = get_git_env(session_id)
    
    current_branch = get_current_branch()
    logger.info("当前分支：" + current_branch)
    
    # 检查是否有初始提交
    has_initial_commit = False
    try:
        commit_result = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=cache_path, env=env, capture_output=True, text=True)
        has_initial_commit = commit_result.returncode == 0
    except Exception as e:
        logger.warning("检查初始提交失败：" + str(e))
    
    # 执行 fetch 操作
    try:
        result = subprocess.run(['git', 'fetch', 'origin'], check=True, cwd=cache_path, env=env, capture_output=True, text=True)
        logger.info("Fetch result: " + result.stdout)
    except subprocess.CalledProcessError as e:
        logger.error("Fetch 失败：" + e.stderr)
        raise HTTPException(status_code=500, detail="拉取失败：" + e.stderr)
    
    remote_default_branch = get_remote_default_branch()
    logger.info("远程默认分支：" + remote_default_branch)
    
    status_result = subprocess.run(['git', 'status', '--porcelain'], cwd=cache_path, env=env, capture_output=True, text=True)
    local_changes = status_result.stdout.strip() != ''
    
    if local_changes and has_initial_commit:
        try:
            stash_result = subprocess.run(
                ['git', 'stash', 'push', '-m', 'auto-stash-before-pull'], 
                check=True, 
                cwd=cache_path, 
                env=env, 
                capture_output=True,
                text=True
            )
            logger.info("本地更改已暂存：" + stash_result.stdout)
        except subprocess.CalledProcessError as e:
            logger.error("Stash 失败：" + e.stderr)
            # 即使 stash 失败，也继续尝试拉取
            logger.warning("Stash 失败，跳过暂存，直接拉取")
    
    try:
        result = subprocess.run(
            ['git', 'merge', 'origin/' + remote_default_branch], 
            check=True, 
            cwd=cache_path, 
            env=env, 
            capture_output=True, 
            text=True
        )
        logger.info("Merge result: " + result.stdout)
    except subprocess.CalledProcessError as e:
        logger.error("Merge 失败：" + e.stderr)
        raise HTTPException(status_code=500, detail="拉取失败：" + e.stderr)
    
    if local_changes:
        try:
            stash_pop = subprocess.run(
                ['git', 'stash', 'pop'], 
                cwd=cache_path, 
                env=env, 
                capture_output=True, 
                text=True
            )
            if stash_pop.returncode == 0:
                logger.info("本地更改已恢复")
            else:
                logger.warning("无法恢复本地更改：" + stash_pop.stderr)
        except Exception as e:
            logger.warning("恢复本地更改失败：" + str(e))
    
    logger.info("已拉取远程最新更改")

async def init_local_git_async(session_path: str = None, session_id: Optional[str] = None, oauth_session_id: Optional[str] = None):
    """初始化本地 Git 仓库
    
    Args:
        session_path: 会话路径（必须提供）
        session_id: 会话 ID，用于获取 Git 仓库配置
        oauth_session_id: OAuth 会话 ID，用于获取访问令牌和用户信息
    
    Raises:
        ValueError: 当未提供 session_path 时抛出
    """
    from fastapi import HTTPException
    from app.session_manager import session_manager
    
    # 必须提供会话路径，不允许使用全局配置
    if not session_path:
        raise ValueError("必须提供会话路径，不允许使用全局配置")
    cache_path = session_path
    
    # 记录操作路径，确保不会误操作上级目录
    logger.info(f"init_local_git_async 操作路径: {cache_path}")
    
    # 安全检查：确保 cache_path 不在当前项目目录内（防止误操作开发目录）
    current_project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if os.path.abspath(cache_path).startswith(current_project_dir):
        logger.warning(f"警告：会话路径 {cache_path} 在项目目录 {current_project_dir} 内，可能存在安全风险")
    
    # 优先使用会话级别的 Git 仓库配置
    git_repo = ''
    if session_id:
        git_repo = session_manager.get_session_git_repo(session_id)
    if not git_repo:
        git_repo = config.BLOG_GIT_SSH
    
    has_git = os.path.exists(os.path.join(cache_path, '.git'))
    has_files = os.path.exists(cache_path) and any(
        os.path.exists(os.path.join(cache_path, f)) 
        for f in os.listdir(cache_path) if f != '.git'
    ) if os.path.exists(cache_path) else False
    
    env = get_git_env(oauth_session_id)
    
    if has_git:
        logger.info("Git 仓库已存在，检查远程配置")
        try:
            remote_result = subprocess.run(['git', 'remote', '-v'], cwd=cache_path, capture_output=True, text=True)
            has_remote = 'origin' in remote_result.stdout
            
            if has_remote:
                # 检查是否有文件（除了 .git 目录）
                has_content = any(
                    os.path.exists(os.path.join(cache_path, f)) 
                    for f in os.listdir(cache_path) if f != '.git'
                ) if os.path.exists(cache_path) else False
                
                if not has_content:
                    # 仓库存在但没有文件，尝试拉取远程内容
                    logger.info("仓库存在但没有文件，尝试拉取远程内容")
                    try:
                        # 先 fetch 远程内容
                        fetch_result = subprocess.run(['git', 'fetch', 'origin'], cwd=cache_path, env=env, capture_output=True, text=True, timeout=60)
                        logger.info(f"Fetch 结果: {fetch_result.stdout[:200] if fetch_result.stdout else '无输出'}")
                        
                        # 获取默认分支
                        remote_head_result = subprocess.run(['git', 'symbolic-ref', 'refs/remotes/origin/HEAD'], cwd=cache_path, capture_output=True, text=True)
                        if remote_head_result.returncode == 0:
                            default_branch = remote_head_result.stdout.strip().replace('refs/remotes/origin/', '')
                            logger.info(f"远程默认分支: {default_branch}")
                            
                            # 检出分支
                            checkout_result = subprocess.run(['git', 'checkout', default_branch], cwd=cache_path, capture_output=True, text=True)
                            logger.info(f"Checkout 结果: {checkout_result.stdout[:200] if checkout_result.stdout else checkout_result.stderr[:200]}")
                            
                            # 重置到远程分支
                            reset_result = subprocess.run(['git', 'reset', '--hard', f'origin/{default_branch}'], cwd=cache_path, capture_output=True, text=True)
                            logger.info(f"Reset 结果: {reset_result.stdout[:200] if reset_result.stdout else reset_result.stderr[:200]}")
                            
                            # 检查是否有文件
                            files_after = [f for f in os.listdir(cache_path) if f != '.git']
                            logger.info(f"拉取后目录文件数: {len(files_after)}")
                        else:
                            # 如果无法获取默认分支，尝试直接 checkout
                            logger.warning("无法获取远程默认分支，尝试直接检出")
                            subprocess.run(['git', 'checkout', 'main'], cwd=cache_path, capture_output=True, text=True)
                            subprocess.run(['git', 'reset', '--hard', 'origin/main'], cwd=cache_path, capture_output=True, text=True)
                    except Exception as e:
                        logger.warning(f"拉取远程内容失败：{e}")
                
                try:
                    configure_git_user(oauth_session_id, cache_path=cache_path)
                except Exception as e:
                    logger.error(f"配置 Git 用户失败：{e}")
                
                return {"message": "初始化成功，仓库已连接", "status": "connected"}
            else:
                if git_repo:
                    subprocess.run(['git', 'remote', 'add', 'origin', git_repo], cwd=cache_path, check=True, capture_output=True)
                    try:
                        configure_git_user(oauth_session_id, cache_path=cache_path)
                    except Exception as e:
                        logger.error(f"配置 Git 用户失败：{e}")
                    logger.info("已设置远程仓库配置")
                    return {"message": "初始化成功，远程仓库已配置", "status": "remote_configured"}
                else:
                    return {"message": "仓库已初始化，请配置远程仓库地址", "status": "no_remote"}
        except subprocess.CalledProcessError as e:
            logger.warning("检查远程配置失败：" + (e.stderr if e.stderr else str(e)))
            return {"message": "仓库已初始化，远程配置检查失败", "status": "remote_check_failed"}
    
    if has_files and git_repo:
        logger.info("本地有文件但无 Git 仓库，保留本地文件并连接远程仓库")
        temp_dir = cache_path + "_remote_temp"
        
        # 彻底清理临时目录，带重试机制
        if os.path.exists(temp_dir):
            logger.info("清理已存在的临时目录：" + temp_dir)
            for retry in range(3):
                try:
                    shutil.rmtree(temp_dir, ignore_errors=True)
                    if not os.path.exists(temp_dir):
                        break
                except Exception as e:
                    logger.warning(f"清理临时目录失败 (尝试 {retry+1}/3): {e}")
                    import time
                    time.sleep(0.5)
            
            # 如果仍然存在，尝试强制删除
            if os.path.exists(temp_dir):
                logger.warning("无法完全清理临时目录，尝试使用系统命令")
                try:
                    if os.name == 'nt':  # Windows
                        subprocess.run(['cmd', '/c', 'rmdir', '/s', '/q', temp_dir], 
                                     cwd=cache_path, capture_output=True, timeout=5)
                    else:  # Linux/Mac
                        subprocess.run(['rm', '-rf', temp_dir], 
                                     cwd=cache_path, capture_output=True, timeout=5)
                except Exception as e:
                    logger.error("强制清理临时目录失败：" + str(e))
        
        clone_success = False
        clone_error = None
        
        try:
            subprocess.run(
                ['git', 'clone', git_repo, '-b', config.BLOG_BRANCH, temp_dir],
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
                shutil.copytree(os.path.join(temp_dir, '.git'), os.path.join(cache_path, '.git'))
            configure_git_user(oauth_session_id, cache_path=cache_path)
            
            if clone_success and os.path.exists(temp_dir):
                for item in os.listdir(temp_dir):
                    if item == '.git':
                        continue
                    src = os.path.join(temp_dir, item)
                    dst = os.path.join(cache_path, item)
                    if not os.path.exists(dst):
                        if os.path.isdir(src):
                            shutil.copytree(src, dst)
                        else:
                            shutil.copy2(src, dst)
            
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir, ignore_errors=True)
            
            subprocess.run(['git', 'add', '-A'], cwd=cache_path, check=True, capture_output=True)
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
        subprocess.run(['git', 'init', '-b', 'main'], cwd=cache_path, check=True, capture_output=True)
        configure_git_user(oauth_session_id, cache_path=cache_path)
        return {"message": "初始化成功，请配置远程仓库地址", "status": "no_remote"}
    
    elif not has_files and git_repo:
        logger.info("本地无文件，克隆远程仓库")
        
        # 如果目录已存在，先备份并清空
        if os.path.exists(cache_path) and os.listdir(cache_path):
            backup_path = cache_path + "_backup_" + str(int(time.time()))
            logger.info("目录已存在，备份到：" + backup_path)
            try:
                shutil.move(cache_path, backup_path)
            except Exception as e:
                logger.warning("备份目录失败：" + str(e))
        
        os.makedirs(cache_path, exist_ok=True)
        
        clone_success = False
        clone_error = None
        
        try:
            subprocess.run(
                ['git', 'clone', git_repo, '-b', config.BLOG_BRANCH, cache_path],
                env=env, check=True, capture_output=True, text=True, timeout=120
            )
            clone_success = True
        except subprocess.CalledProcessError as e:
            clone_error = e.stderr if e.stderr else str(e)
            if 'Remote branch' in clone_error and 'not found' in clone_error:
                try:
                    subprocess.run(
                        ['git', 'clone', git_repo, cache_path],
                        env=env, check=True, capture_output=True, text=True, timeout=120
                    )
                    clone_success = True
                except subprocess.CalledProcessError as e2:
                    clone_error = e2.stderr if e2.stderr else str(e2)
        
        if clone_success:
            logger.info("远程仓库克隆成功")
            try:
                configure_git_user(oauth_session_id, cache_path=cache_path)
            except Exception as e:
                logger.error(f"配置 Git 用户失败：{e}")
            return {"message": "初始化成功，远程仓库已克隆", "status": "cloned"}
        elif clone_error and 'empty repository' in clone_error.lower():
            subprocess.run(['git', 'init', '-b', 'main'], cwd=cache_path, check=True, capture_output=True)
            subprocess.run(['git', 'remote', 'add', 'origin', git_repo], cwd=cache_path, check=True, capture_output=True)
            configure_git_user(oauth_session_id, cache_path=cache_path)
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
        os.makedirs(cache_path, exist_ok=True)
        subprocess.run(['git', 'init', '-b', 'main'], cwd=cache_path, check=True, capture_output=True)
        configure_git_user(oauth_session_id, cache_path=cache_path)
        return {"message": "初始化成功，请配置远程仓库地址", "status": "initialized"}

def sync_branch_name(cache_path: str = None):
    """同步本地分支名称与远程仓库的默认分支
    
    Args:
        cache_path: 缓存路径（必须提供）
    
    Raises:
        ValueError: 当未提供 cache_path 时抛出
    """
    try:
        # 必须提供缓存路径
        if not cache_path:
            raise ValueError("必须提供缓存路径，不允许使用全局配置")
        path = cache_path
        
        if not os.path.exists(os.path.join(path, '.git')):
            return
        
        current_branch_result = subprocess.run(['git', 'rev-parse', '--abbrev-ref', 'HEAD'], cwd=path, capture_output=True, text=True)
        if current_branch_result.returncode != 0:
            return
        current_branch = current_branch_result.stdout.strip()
        
        remote_result = subprocess.run(['git', 'remote', '-v'], cwd=path, capture_output=True, text=True)
        if 'origin' not in remote_result.stdout:
            return
        
        env = get_git_env()
        subprocess.run(['git', 'fetch', 'origin'], cwd=path, env=env, capture_output=True, text=True, timeout=60)
        
        remote_head_result = subprocess.run(['git', 'symbolic-ref', 'refs/remotes/origin/HEAD'], cwd=path, capture_output=True, text=True)
        if remote_head_result.returncode != 0:
            return
        remote_default_branch = remote_head_result.stdout.strip().replace('refs/remotes/origin/', '')
        
        if current_branch != remote_default_branch:
            logger.info(f"本地分支 '{current_branch}' 与远程分支 '{remote_default_branch}' 不一致，正在重命名...")
            subprocess.run(['git', 'branch', '-m', current_branch, remote_default_branch], cwd=path, check=True, capture_output=True)
            subprocess.run(['git', 'branch', '--set-upstream-to=origin/' + remote_default_branch, remote_default_branch], cwd=path, capture_output=True)
            logger.info(f"已将本地分支重命名为 '{remote_default_branch}' 并设置跟踪远程分支")
    except Exception as e:
        logger.warning("同步分支名称时出错：" + str(e))
