#!/usr/bin/env python3
"""
Git 凭证辅助脚本 - 用于 OAuth 令牌认证
当 Git 需要认证时，此脚本会被调用返回 OAuth 令牌

使用方式：
1. Git 会调用此脚本并传入操作参数 (get/store/erase)
2. Git 通过 stdin 传递请求信息
3. 脚本通过 stdout 返回凭证
"""
import os
import sys
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def main():
    # 获取操作类型 (get/store/erase)
    operation = sys.argv[1] if len(sys.argv) > 1 else 'get'
    
    # 读取 Git 的请求
    lines = []
    for line in sys.stdin:
        line = line.strip()
        if not line:
            break
        lines.append(line)
    
    # 解析请求
    protocol = None
    host = None
    path = None
    
    for line in lines:
        if line.startswith('protocol='):
            protocol = line.split('=', 1)[1]
        elif line.startswith('host='):
            host = line.split('=', 1)[1]
        elif line.startswith('path='):
            path = line.split('=', 1)[1]
    
    logger.info(f"凭证助手被调用: operation={operation}, protocol={protocol}, host={host}")
    
    # 只处理 get 操作
    if operation != 'get':
        return
    
    # 检查是否有 OAuth 令牌
    oauth_token = os.environ.get('MARKGIT_OAUTH_TOKEN', '')
    
    if oauth_token and host and ('github.com' in host or 'gitlab.com' in host):
        logger.info(f"返回 OAuth 令牌用于 {host}")
        # 返回 OAuth 令牌
        print("username=oauth2")
        print(f"password={oauth_token}")
        sys.stdout.flush()
    else:
        logger.warning(f"无 OAuth 令牌或非 GitHub/GitLab 主机: host={host}, has_token={bool(oauth_token)}")

if __name__ == '__main__':
    main()
