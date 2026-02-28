#!/usr/bin/env python3
"""
Git 凭证辅助脚本 - 用于 OAuth 令牌认证
当 Git 需要认证时，此脚本会被调用返回 OAuth 令牌
"""
import os
import sys

def main():
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
    
    for line in lines:
        if line.startswith('protocol='):
            protocol = line.split('=', 1)[1]
        elif line.startswith('host='):
            host = line.split('=', 1)[1]
    
    # 检查是否有 OAuth 令牌
    oauth_token = os.environ.get('MARKGIT_OAUTH_TOKEN', '')
    
    if oauth_token and host and ('github.com' in host or 'gitlab.com' in host):
        # 返回 OAuth 令牌
        print("username=oauth2")
        print(f"password={oauth_token}")
    else:
        # 无 OAuth 令牌，使用其他方式
        pass

if __name__ == '__main__':
    main()
