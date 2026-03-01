#!/bin/bash
# Docker Compose 构建脚本 (Linux) - 支持进度条显示

set -e

# 默认参数
TAG="markgit-editor:latest"
PROGRESS="plain"
REBUILD=false
MIRROR="domestic"

# 显示帮助
show_help() {
    cat << EOF
Docker Compose 构建脚本 - 带进度条显示

使用方法:
  $0                          # 使用默认参数构建
  $0 -t myimage:1.0           # 自定义镜像标签
  $0 -p tty                   # 美化进度条
  $0 --rebuild                # 无缓存重新构建
  $0 -m overseas              # 使用国外镜像源
  $0 -h                       # 显示帮助

参数:
  -t, --tag <tag>             镜像标签（默认：markgit-editor:latest）
  -p, --progress <mode>       进度模式：auto/plain/tty（默认：plain）
  -m, --mirror <source>       镜像源：domestic/overseas（默认：domestic）
  --rebuild                   无缓存重新构建（--no-cache）
  -h, --help                  显示帮助

进度模式:
  auto   - 自动检测终端能力
  plain  - 显示详细进度和日志（推荐用于 CI/CD）
  tty    - 美化进度条（推荐用于本地开发）

EOF
}

# 解析参数
while [[ $# -gt 0 ]]; do
    case $1 in
        -t|--tag)
            TAG="$2"
            shift 2
            ;;
        -p|--progress)
            PROGRESS="$2"
            shift 2
            ;;
        -m|--mirror)
            MIRROR="$2"
            shift 2
            ;;
        --rebuild)
            REBUILD=true
            shift
            ;;
        -h|--help)
            show_help
            exit 0
            ;;
        *)
            echo "未知参数：$1"
            show_help
            exit 1
            ;;
    esac
done

# 设置构建参数
if [ "$MIRROR" = "domestic" ]; then
    export BASE_IMAGE="swr.cn-north-4.myhuaweicloud.com/ddn-k8s/docker.io/python:3.11-slim"
    export APT_MIRROR="mirrors.ustc.edu.cn"
    echo "🇨🇳 使用国内镜像源加速构建"
    echo "   基础镜像：$BASE_IMAGE"
    echo "   APT 镜像：$APT_MIRROR"
else
    export BASE_IMAGE="python:3.11-slim"
    export APT_MIRROR="archive.ubuntu.com"
    echo "🌍 使用国外官方镜像源构建"
    echo "   基础镜像：$BASE_IMAGE"
    echo "   APT 镜像：$APT_MIRROR"
fi

echo ""
echo "🐳 开始构建 Docker 镜像..."
echo "   镜像标签：$TAG"
echo "   进度模式：$PROGRESS"
if [ "$REBUILD" = true ]; then
    echo "   构建模式：无缓存重新构建"
fi
echo ""

# 检查 Docker 是否运行
if ! docker info > /dev/null 2>&1; then
    echo "❌ Docker 未运行或不可用"
    exit 1
fi

# 构建命令
BUILD_CMD="docker-compose build --progress=$PROGRESS"
if [ "$REBUILD" = true ]; then
    BUILD_CMD="$BUILD_CMD --no-cache"
fi

echo "📦 执行命令：$BUILD_CMD"
echo ""

# 执行构建
eval "$BUILD_CMD"

echo ""
if [ $? -eq 0 ]; then
    echo "✅ 构建成功！"
    echo "   镜像：$TAG"
    echo ""
    echo "运行容器："
    echo "   docker-compose up -d"
else
    echo "❌ 构建失败"
    exit 1
fi
