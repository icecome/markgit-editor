# 基础镜像 - 使用构建参数支持灵活切换
# 国内构建（默认）：docker build --build-arg BASE_IMAGE=swr.cn-north-4.myhuaweicloud.com/ddn-k8s/docker.io/python:3.11-slim .
# 国外构建：docker build --build-arg BASE_IMAGE=python:3.11-slim .
ARG BASE_IMAGE=swr.cn-north-4.myhuaweicloud.com/ddn-k8s/docker.io/python:3.11-slim
FROM ${BASE_IMAGE}

LABEL maintainer="MarkGit Editor Team"
LABEL version="1.2.0"
LABEL description="一款基于 OAuth 2.0 的现代化 Git 博客在线编辑器"

# 安装系统依赖 - 智能选择镜像源（国内自动切换中科大源）
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    # 智能检测网络环境，选择最优镜像源
    if curl -s --connect-timeout 3 -o /dev/null https://mirrors.ustc.edu.cn; then \
        echo "检测到国内网络，使用中科大镜像源..." && \
        sed -i 's|http://deb.debian.org/debian|https://mirrors.ustc.edu.cn/debian|g' /etc/apt/sources.list && \
        sed -i 's|http://security.debian.org/debian-security|https://mirrors.ustc.edu.cn/debian-security|g' /etc/apt/sources.list; \
    else \
        echo "使用官方 Debian 镜像源..." && \
        sed -i 's|http://security.debian.org/debian-security|http://security.debian.org/debian-security|g' /etc/apt/sources.list; \
    fi && \
    # 清理 apt 配置
    rm -f /etc/apt/apt.conf.d/docker-clean && \
    # 更新并安装
    apt-get update && apt-get install -y --no-install-recommends \
    git \
    openssh-client \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 设置工作目录 - 使用 /markgit-editor 避免与 app 模块冲突
WORKDIR /markgit-editor

# 复制依赖文件
COPY requirements.txt .

# 安装 Python 依赖 - 智能选择镜像源（国内自动切换中科大源）
RUN --mount=type=cache,target=/root/.cache/pip \
    # 智能检测网络环境，选择最优 pip 镜像源
    if curl -s --connect-timeout 3 -o /dev/null https://mirrors.ustc.edu.cn; then \
        echo "检测到国内网络，使用中科大 pip 镜像源..." && \
        pip install --no-cache-dir -r requirements.txt -i https://mirrors.ustc.edu.cn/pypi/simple \
            --extra-index-url https://pypi.tuna.tsinghua.edu.cn/simple \
            --extra-index-url https://pypi.aliyun.com/simple; \
    else \
        echo "使用官方 PyPI 镜像源..." && \
        pip install --no-cache-dir -r requirements.txt; \
    fi

# 复制应用代码
COPY . .

# 创建缓存目录
RUN mkdir -p /markgit-editor/blog_cache

# 创建非 root 用户
RUN useradd -m -u 1000 appuser && \
    chown -R appuser:appuser /markgit-editor

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

# 启动命令 - 使用 exec 格式包装 shell 命令
CMD ["/bin/sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-13131}"]
