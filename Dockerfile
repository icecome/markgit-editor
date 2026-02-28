FROM python:3.11-slim

LABEL maintainer="MarkGit Editor Team"
LABEL version="1.2.0"
LABEL description="一款基于 OAuth 2.0 的现代化 Git 博客在线编辑器"

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    git \
    openssh-client \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 设置工作目录
WORKDIR /app

# 复制依赖文件
COPY requirements.txt .

# 安装 Python 依赖
RUN pip install --no-cache-dir -r requirements.txt

# 复制应用代码
COPY . .

# 创建缓存目录
RUN mkdir -p /app/blog_cache

# 创建非 root 用户
RUN useradd -m -u 1000 appuser && \
    chown -R appuser:appuser /app

# 切换到非 root 用户
USER appuser

# 暴露端口
EXPOSE 13131

# 设置环境变量
ENV PYTHONUNBUFFERED=1
ENV PRODUCTION=true
ENV PORT=13131

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:13131/ || exit 1

# 启动命令
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "13131"]
