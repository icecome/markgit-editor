#!/bin/bash
# 修复 Docker DNS 配置脚本 (Linux)

echo "🔧 修复 Docker DNS 配置"
echo "=================================================="
echo ""

# 检查 root 权限
if [ "$EUID" -ne 0 ]; then 
    echo "❌ 此脚本需要 root 权限运行"
    echo "   请使用：sudo ./fix-docker-dns.sh"
    exit 1
fi

DAEMON_CONFIG="/etc/docker/daemon.json"
DNS_SERVERS='["8.8.8.8", "114.114.114.114", "223.5.5.5"]'

echo "📋 将配置以下 DNS 服务器:"
echo "   - 8.8.8.8 (Google DNS)"
echo "   - 114.114.114.114 (114 DNS)"
echo "   - 223.5.5.5 (阿里 DNS)"
echo ""

# 备份现有配置
if [ -f "$DAEMON_CONFIG" ]; then
    echo "📦 备份现有配置..."
    BACKUP_PATH="$DAEMON_CONFIG.backup.$(date +%Y%m%d-%H%M%S)"
    cp "$DAEMON_CONFIG" "$BACKUP_PATH"
    echo "   备份文件：$BACKUP_PATH"
    
    # 读取现有配置（保留其他配置）
    if command -v jq > /dev/null 2>&1; then
        echo "✏️  更新 DNS 配置..."
        jq '.dns = ["8.8.8.8", "114.114.114.114", "223.5.5.5"]' "$DAEMON_CONFIG" > "${DAEMON_CONFIG}.tmp"
        mv "${DAEMON_CONFIG}.tmp" "$DAEMON_CONFIG"
    else
        echo "⚠️  未找到 jq，将创建新配置"
        echo '{"dns": ["8.8.8.8", "114.114.114.114", "223.5.5.5"]}' > "$DAEMON_CONFIG"
    fi
else
    echo "ℹ️  daemon.json 不存在，将创建新文件"
    mkdir -p /etc/docker
    echo '{"dns": ["8.8.8.8", "114.114.114.114", "223.5.5.5"]}' > "$DAEMON_CONFIG"
fi

echo ""
echo "📄 配置内容:"
cat "$DAEMON_CONFIG"
echo ""

# 重启 Docker 服务
echo "🔄 重启 Docker 服务..."
if systemctl restart docker; then
    echo "✅ Docker 服务已重启"
else
    echo "⚠️  无法自动重启 Docker 服务"
    echo "   请手动执行：sudo systemctl restart docker"
fi

echo ""
echo "=================================================="
echo "✅ DNS 配置完成！"
echo ""
echo "下一步操作:"
echo "1. 等待 Docker 服务完全重启（约 5-10 秒）"
echo "2. 运行诊断脚本：./diagnose-network.sh"
echo "3. 重新构建 Docker: docker-compose build --no-cache"
echo ""
