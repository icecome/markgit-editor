# 基础镜像 - 支持多架构 (amd64/arm64)
# 国内构建（默认）：docker buildx build --platform linux/amd64,linux/arm64 --build-arg BASE_IMAGE=swr.cn-north-4.myhuaweicloud.com/ddn-k8s/docker.io/python:3.11-slim .
# 国外构建：docker buildx build --platform linux/amd64,linux/arm64 --build-arg BASE_IMAGE=python:3.11-slim .
ARG BASE_IMAGE=swr.cn-north-4.myhuaweicloud.com/ddn-k8s/docker.io/python:3.11-slim
FROM ${BASE_IMAGE}

# APT 镜像源 - 自动检测系统类型
ARG APT_MIRROR=mirrors.ustc.edu.cn

LABEL maintainer="MarkGit Editor Team"
LABEL version="1.2.0"
LABEL description="一款基于 OAuth 2.0 的现代化 Git 博客在线编辑器"

# [1/4] 安装系统依赖 - 自动检测系统类型
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    rm -f /etc/apt/apt.conf.d/docker-clean && \
    apt-get update && \
    apt-get install -y --no-install-recommends \
    git \
    openssh-client \
    curl && \
    rm -rf /var/lib/apt/lists/*

# 设置工作目录
WORKDIR /markgit-editor

# 复制依赖文件
COPY requirements.txt .

# [2/4] 安装 Python 依赖
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --no-cache-dir -r requirements.txt \

# [3/4] 复制应用代码
COPY . .

# [4/4] 创建缓存目录和配置用户
RUN mkdir -p /markgit-editor/blog_cache && \
    useradd -m -u 1000 appuser && \
    chown -R appuser:appuser /markgit-editor

# 切换到非 root 用户
USER appuser

EXPOSE 13131

ENV PYTHONUNBUFFERED=1
ENV PRODUCTION=true

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:${PORT:-13131}/ || exit 1

CMD ["/bin/sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-13131}"]
