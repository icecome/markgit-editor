#!/bin/bash
# ARM 机器构建脚本（简单快速）

set -e

echo "🔧 检测当前架构..."
ARCH=$(uname -m)
if [ "$ARCH" = "aarch64" ] || [ "$ARCH" = "arm64" ]; then
    echo "✅ 检测到 ARM64 架构"
    PLATFORM="linux/arm64"
elif [ "$ARCH" = "x86_64" ]; then
    echo "✅ 检测到 AMD64 架构"
    PLATFORM="linux/amd64"
else
    echo "❌ 不支持的架构：$ARCH"
    exit 1
fi

echo ""
echo "🚀 启用 BuildKit..."
export DOCKER_BUILDKIT=1
export BUILDKIT_PROGRESS=plain

echo ""
echo "📦 开始构建（平台：$PLATFORM）..."

# 使用 buildx 构建
docker buildx build \
    --platform $PLATFORM \
    --build-arg BASE_IMAGE=swr.cn-north-4.myhuaweicloud.com/ddn-k8s/docker.io/python:3.11-slim \
    --build-arg APT_MIRROR=mirrors.ustc.edu.cn \
    --load \
    -t markgit-editor:latest \
    .

if [ $? -eq 0 ]; then
    echo ""
    echo "✅ 构建成功！"
    echo ""
    echo "运行容器："
    echo "  docker-compose up -d"
else
    echo ""
    echo "❌ 构建失败"
    exit 1
fi
