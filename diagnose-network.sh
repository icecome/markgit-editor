#!/bin/bash
# Docker 网络诊断脚本 (Linux)

echo "🔍 Docker 网络诊断工具"
echo "=================================================="
echo ""

# 1. 检查 Docker 是否运行
echo "1️⃣  检查 Docker 服务状态..."
if docker info > /dev/null 2>&1; then
    echo "✅ Docker 运行正常"
else
    echo "❌ Docker 未运行或不可用"
    exit 1
fi
echo ""

# 2. 检查 Docker DNS 配置
echo "2️⃣  检查 Docker DNS 配置..."
DAEMON_CONFIG="/etc/docker/daemon.json"
if [ -f "$DAEMON_CONFIG" ]; then
    echo "📋 当前 DNS 配置:"
    grep -o '"dns"[^]]*]' "$DAEMON_CONFIG" 2>/dev/null || cat "$DAEMON_CONFIG"
else
    echo "⚠️  未找到 daemon.json，Docker 使用系统默认 DNS"
    echo "   路径：$DAEMON_CONFIG"
fi
echo ""

# 3. 测试基础网络连接
echo "3️⃣  测试基础网络连接..."
declare -A test_hosts=(
    ["中科大镜像"]="mirrors.ustc.edu.cn"
    ["阿里云镜像"]="mirrors.aliyun.com"
    ["清华大学镜像"]="mirrors.tuna.tsinghua.edu.cn"
    ["华为云镜像"]="repo.myhuaweicloud.com"
    ["Google DNS"]="8.8.8.8"
    ["114 DNS"]="114.114.114.114"
)

for name in "${!test_hosts[@]}"; do
    host="${test_hosts[$name]}"
    echo -n "   测试 $name ($host)... "
    if ping -c 1 -W 2 "$host" > /dev/null 2>&1; then
        echo "✅ 可达"
    else
        echo "❌ 不可达"
    fi
done
echo ""

# 4. 查看系统 DNS 配置
echo "4️⃣  系统 DNS 配置..."
echo "   /etc/resolv.conf 内容:"
grep -v "^#" /etc/resolv.conf | grep -v "^$" | sed 's/^/   /'
echo ""

# 5. 查看 Docker 网络配置
echo "5️⃣  Docker 网络配置..."
docker network ls | head -10
echo ""

# 6. 提供修复建议
echo "=================================================="
echo "💡 修复建议"
echo ""

echo "方案 1: 配置 Docker DNS（推荐）"
echo "   创建或编辑文件：/etc/docker/daemon.json"
echo "   添加以下内容:"
echo '   {'
echo '     "dns": ["8.8.8.8", "114.114.114.114", "223.5.5.5"]'
echo '   }'
echo "   然后重启 Docker: sudo systemctl restart docker"
echo ""

echo "方案 2: 切换到其他镜像源"
echo "   当前 APT_MIRROR=repo.myhuaweicloud.com 解析失败"
echo "   建议切换到:"
echo "   - 中科大：mirrors.ustc.edu.cn"
echo "   - 阿里云：mirrors.aliyun.com"
echo "   - 清华大学：mirrors.tuna.tsinghua.edu.cn"
echo ""

echo "方案 3: 临时测试（在构建时指定 DNS）"
echo "   创建 ~/.docker/daemon.json 或在 docker-compose.yml 中添加:"
echo '   dns:'
echo '     - 8.8.8.8'
echo '     - 114.114.114.114'
echo ""

echo "方案 4: 检查系统 DNS"
echo "   sudo vim /etc/resolv.conf"
echo "   添加或修改：nameserver 8.8.8.8"
echo ""
