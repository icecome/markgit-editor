# 基础镜像 - 使用构建参数支持灵活切换
# 国内构建（默认）：docker build --build-arg BASE_IMAGE=swr.cn-north-4.myhuaweicloud.com/ddn-k8s/docker.io/python:3.11-slim .
# 国外构建：docker build --build-arg BASE_IMAGE=python:3.11-slim .
ARG BASE_IMAGE=swr.cn-north-4.myhuaweicloud.com/ddn-k8s/docker.io/python:3.11-slim
FROM ${BASE_IMAGE}

# APT 镜像源 - 根据基础镜像自动选择
# 国内镜像使用华为云/阿里云，国外使用官方源
ARG APT_MIRROR=mirrors.ustc.edu.cn

LABEL maintainer="MarkGit Editor Team"
LABEL version="1.2.0"
LABEL description="一款基于 OAuth 2.0 的现代化 Git 博客在线编辑器"

# [1/4] 安装系统依赖 - 使用国内镜像源加速
# 国内环境：使用中科大/华为云/阿里云镜像
# 国外环境：使用官方源（设置 APT_MIRROR=archive.ubuntu.com）
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    echo "📦 正在配置 APT 镜像源：${APT_MIRROR}" && \
    cat > /etc/apt/sources.list <<EOF
deb http://${APT_MIRROR}/ubuntu/ jammy main restricted universe multiverse
deb http://${APT_MIRROR}/ubuntu/ jammy-updates main restricted universe multiverse
deb http://${APT_MIRROR}/ubuntu/ jammy-backports main restricted universe multiverse
deb http://${APT_MIRROR}/ubuntu/ jammy-security main restricted universe multiverse
EOF
    && echo "🔄 正在更新软件包列表..." && \
    apt-get update && \
    echo "📥 正在安装系统依赖..." && \
    apt-get install -y --no-install-recommends \
    git \
    openssh-client \
    curl && \
    echo "🧹 正在清理缓存..." && \
    rm -rf /var/lib/apt/lists/* && \
    echo "✅ 系统依赖安装完成"

# 设置工作目录
WORKDIR /markgit-editor

# 复制依赖文件
COPY requirements.txt .

# [2/4] 安装 Python 依赖 - 使用国内镜像源
RUN --mount=type=cache,target=/root/.cache/pip \
    echo "📦 正在配置 PyPI 镜像源..." && \
    echo "📥 正在安装 Python 依赖..." && \
    pip install --no-cache-dir -r requirements.txt \
        -i https://mirrors.ustc.edu.cn/pypi/simple \
        --extra-index-url https://pypi.tuna.tsinghua.edu.cn/simple \
        --extra-index-url https://pypi.aliyun.com/simple && \
    echo "✅ Python 依赖安装完成"

# [3/4] 复制应用代码
COPY . .

# [4/4] 创建缓存目录和配置用户
RUN echo "📁 正在创建缓存目录..." && \
    mkdir -p /markgit-editor/blog_cache && \
    echo "👤 正在创建应用用户..." && \
    useradd -m -u 1000 appuser && \
    chown -R appuser:appuser /markgit-editor && \
    echo "✅ 构建准备完成"

# 切换到非 root 用户
USER appuser

# 暴露端口
EXPOSE 13131

# 设置环境变量
ENV PYTHONUNBUFFERED=1
ENV PRODUCTION=true

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:${PORT:-13131}/ || exit 1

# 启动命令
CMD ["/bin/sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-13131}"]
