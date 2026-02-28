#!/bin/bash

# MarkGit Editor 部署脚本
# 适用于 Ubuntu 20.04+

set -e

echo "========================================"
echo "  MarkGit Editor 部署脚本"
echo "========================================"

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# 配置变量
APP_DIR="/opt/markgit-editor"
APP_USER="www-data"
DOMAIN="${1:-}"
EMAIL="${2:-}"

# 检查 root 权限
if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}请使用 root 权限运行此脚本${NC}"
    exit 1
fi

# 检查参数
if [ -z "$DOMAIN" ]; then
    echo "用法: $0 <域名> [邮箱]"
    echo "示例: $0 markgit.example.com admin@example.com"
    exit 1
fi

echo -e "${GREEN}[1/8] 更新系统...${NC}"
apt update && apt upgrade -y

echo -e "${GREEN}[2/8] 安装依赖...${NC}"
apt install -y python3.11 python3.11-venv python3-pip git redis-server nginx certbot python3-certbot-nginx

echo -e "${GREEN}[3/8] 创建应用目录...${NC}"
mkdir -p $APP_DIR
mkdir -p /var/cache/markgit-editor
chown -R $APP_USER:$APP_USER /var/cache/markgit-editor

echo -e "${GREEN}[4/8] 部署应用代码...${NC}"
# 如果当前目录有代码，复制到目标目录
if [ -f "app.py" ]; then
    cp -r . $APP_DIR/
else
    echo "请确保在项目根目录运行此脚本"
    exit 1
fi

cd $APP_DIR

# 创建虚拟环境
python3.11 -m venv venv
source venv/bin/activate

# 安装依赖
pip install -r requirements.txt

# 创建环境变量文件
if [ ! -f ".env" ]; then
    echo -e "${YELLOW}请配置 .env 文件:${NC}"
    echo "GITHUB_CLIENT_ID=your_client_id"
    echo "GITHUB_CLIENT_SECRET=your_client_secret"
    echo "CORS_ORIGINS=https://$DOMAIN"
    echo "PRODUCTION=true"
    read -p "按回车继续..."
fi

echo -e "${GREEN}[5/8] 配置 Systemd 服务...${NC}"
cat > /etc/systemd/system/markgit-editor.service << EOF
[Unit]
Description=MarkGit Editor API
After=network.target redis.service

[Service]
Type=simple
User=$APP_USER
Group=$APP_USER
WorkingDirectory=$APP_DIR
Environment="PATH=$APP_DIR/venv/bin"
EnvironmentFile=$APP_DIR/.env
ExecStart=$APP_DIR/venv/bin/uvicorn main:app --host 127.0.0.1 --port 13131
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable markgit-editor
systemctl start markgit-editor

echo -e "${GREEN}[6/8] 配置 Nginx...${NC}"
# 替换域名
sed -i "s/your-domain.com/$DOMAIN/g" deploy/nginx.conf
cp deploy/nginx.conf /etc/nginx/sites-available/markgit-editor
ln -sf /etc/nginx/sites-available/markgit-editor /etc/nginx/sites-enabled/
nginx -t && systemctl reload nginx

echo -e "${GREEN}[7/8] 获取 SSL 证书...${NC}"
if [ -n "$EMAIL" ]; then
    certbot --nginx -d $DOMAIN --non-interactive --agree-tos -m $EMAIL
else
    echo -e "${YELLOW}跳过 SSL 证书获取，请手动运行:${NC}"
    echo "certbot --nginx -d $DOMAIN"
fi

echo -e "${GREEN}[8/8] 验证部署...${NC}"
sleep 3
if systemctl is-active --quiet markgit-editor; then
    echo -e "${GREEN}✓ 服务运行正常${NC}"
else
    echo -e "${RED}✗ 服务启动失败，请检查日志${NC}"
    journalctl -u markgit-editor -n 20
fi

echo ""
echo "========================================"
echo -e "${GREEN}部署完成!${NC}"
echo "========================================"
echo ""
echo "访问地址: https://$DOMAIN"
echo ""
echo "常用命令:"
echo "  查看状态: systemctl status markgit-editor"
echo "  查看日志: journalctl -u markgit-editor -f"
echo "  重启服务: systemctl restart markgit-editor"
echo ""
