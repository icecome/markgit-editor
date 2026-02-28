# MarkGit Editor

一款基于 OAuth 2.0 的现代化 Git 博客在线编辑器

## 🌟 核心特性

- **GitHub OAuth 2.0 登录** - 使用 GitHub Device Flow，无需手动创建 PAT
- **会话隔离** - 多用户支持，每个用户独立的 Git 工作区
- **Git 集成** - 完整的 Git 工作流（克隆、拉取、提交、推送）
- **文件管理** - 创建、编辑、删除、移动文件和文件夹
- **Markdown 编辑** - 实时预览，支持图片上传和管理
- **响应式设计** - 完美适配桌面和移动设备
- **安全认证** - 基于 OAuth 2.0 的安全认证系统
- **自动清理** - 智能会话管理和过期数据清理

## 📁 项目结构

```
markgit-editor/
├── app.py                          # 后端主应用（FastAPI）
├── index.html                      # 前端主页面（Vue 3）
├── .env.example                    # 环境变量示例
├── requirements.txt                # Python 依赖
├── Dockerfile                      # Docker 镜像配置
├── docker-compose.yml              # Docker Compose 配置
├── railway.toml                    # Railway 部署配置
├── fly.toml                        # Fly.io 部署配置
├── render.yaml                     # Render 部署配置
├── 部署指南.md                      # 完整部署文档
├── static/
│   ├── main.js                     # 前端主逻辑（Vue 3）
│   ├── main.css                    # 全局样式
│   └── oauth-component.js          # OAuth 登录组件
├── deploy/
│   ├── deploy.sh                   # 一键部署脚本
│   └── nginx.conf                  # Nginx 配置
├── k8s/
│   └── deployment.yaml             # Kubernetes 部署配置
└── app/
    ├── version.py                  # 版本管理
    ├── config.py                   # 配置管理
    ├── routes.py                   # API 路由
    ├── git_service.py              # Git 操作服务
    ├── file_service.py             # 文件操作服务
    ├── session_manager.py          # 会话管理器
    ├── context_manager.py          # 上下文管理
    ├── cleanup_service.py          # 清理服务
    ├── models.py                   # 数据模型
    ├── git_credential_helper.py    # Git 凭证助手
    └── auth/
        ├── github_oauth.py         # GitHub OAuth 服务
        ├── token_store.py          # OAuth 令牌存储
        └── routes.py               # 认证路由
```

## 🚀 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置 GitHub OAuth

1. 访问 [GitHub Developer Settings](https://github.com/settings/developers)
2. 创建新的 OAuth App：
   - **Application name**: MarkGit Editor
   - **Homepage URL**: http://localhost:13131
   - **Authorization callback URL**: http://localhost:13131
   - ✅ 勾选 **Enable Device Flow**
3. 复制 Client ID 和生成 Client Secret

### 3. 配置环境变量

```bash
cp .env.example .env
```

编辑 `.env` 文件：

```env
GITHUB_CLIENT_ID=你的 Client ID
GITHUB_CLIENT_SECRET=你的 Client Secret
GITHUB_SCOPE=repo,workflow
```

### 4. 启动服务器

```bash
python app.py
```

### 5. 访问应用

打开浏览器访问：http://localhost:13131

## 🐳 Docker 部署

```bash
# 使用 Docker Compose
docker-compose up -d

# 或直接运行
docker build -t markgit-editor .
docker run -d -p 13131:13131 --env-file .env markgit-editor
```

## ☁️ 云平台部署

| 平台 | 难度 | 成本 | 推荐度 |
|------|------|------|--------|
| Railway | ⭐ | 低 | ⭐⭐⭐⭐⭐ |
| Fly.io | ⭐⭐ | 低 | ⭐⭐⭐⭐ |
| Render | ⭐ | 低 | ⭐⭐⭐⭐ |
| Zeabur | ⭐ | 低 | ⭐⭐⭐⭐ |

详细部署步骤请参考 [部署指南.md](部署指南.md)

## ⚙️ 环境变量配置

### 必需配置

| 变量名 | 描述 | 示例 |
|--------|------|------|
| `GITHUB_CLIENT_ID` | GitHub OAuth Client ID | `Ov23li...` |
| `GITHUB_CLIENT_SECRET` | GitHub OAuth Client Secret | `abc123...` |

### 可选配置

| 变量名 | 描述 | 默认值 |
|--------|------|--------|
| `PRODUCTION` | 生产环境标志 | `false` |
| `PORT` | 服务端口 | `13131` |
| `CORS_ORIGINS` | 允许的来源 | `http://localhost:13131` |
| `REDIS_URL` | Redis 连接地址 | - |
| `BLOG_CACHE_PATH` | 本地缓存目录 | `./blog_cache` |
| `SESSION_TIMEOUT_HOURS` | 会话超时时间 | `1` |
| `MAX_CONCURRENT_SESSIONS` | 最大并发会话数 | `100` |

## 🔐 安全特性

- **Git 命令隔离** - 使用 `GIT_DIR` 和 `GIT_WORK_TREE` 环境变量防止误操作
- **会话验证** - 所有操作需要有效的 Session ID
- **XSS 防护** - 使用 DOMPurify 净化 HTML 内容
- **CSRF 保护** - Origin/Referer 验证
- **CORS 配置** - 限制允许的来源
- **敏感信息保护** - `.env` 不在版本控制中

## 📝 使用指南

### 1. 登录

- 点击右上角"登录"按钮
- 使用手机或浏览器访问显示的 URL
- 输入用户码并授权

### 2. 配置仓库

- 点击设置按钮 ⚙️
- 输入 Git 仓库 HTTPS 地址
- 点击"保存配置"

### 3. 初始化工作区

- 点击"初始化"按钮
- 系统自动克隆远程仓库

### 4. 编辑文件

- 浏览文件树
- 点击文件进行编辑
- 支持 Markdown 实时预览

### 5. 提交更改

- 查看文件变更列表
- 点击"提交并推送"

## 🛠️ 技术栈

### 后端
- **Python 3.11** - 主编程语言
- **FastAPI** - 现代 Web 框架
- **Uvicorn** - ASGI 服务器
- **Git** - 版本控制

### 前端
- **Vue 3** - 渐进式框架
- **Axios** - HTTP 客户端
- **Lucide Icons** - 图标库
- **Tailwind CSS** - CSS 框架
- **DOMPurify** - XSS 防护

### 认证
- **OAuth 2.0 Device Flow** - GitHub 设备流认证

## 📋 API 文档

### 认证相关
- `GET /api/auth/device-code` - 获取设备码
- `POST /api/auth/token` - 轮询访问令牌
- `GET /api/auth/status` - 获取认证状态

### 文件操作
- `GET /api/files` - 获取文件列表
- `GET /api/file/content` - 获取文件内容
- `POST /api/file/create` - 创建文件
- `POST /api/file/save` - 保存文件
- `DELETE /api/file/delete` - 删除文件

### Git 操作
- `POST /api/init` - 初始化工作区
- `POST /api/pull` - 拉取远程更新
- `POST /api/commit` - 提交并推送

### 会话管理
- `GET /api/session/status` - 获取会话状态
- `GET /api/session/create` - 创建新会话

## 📄 许可证

本项目采用 MIT 许可证，详见 [LICENSE](LICENSE)。

## ⚠️ 免责声明

- 本项目完全使用 AI 编写构建，旨在提供一个轻量化的博客在线编辑工具
- 项目作者不对使用本软件导致的任何直接或间接损失承担责任
- 所有代码均为开源，任何人都可以自由修改、分发和使用
- 本软件按"原样"提供，不附带任何形式的保证或担保

---

**版本**: v1.2.0  
**更新日期**: 2026-02-28

详细版本历史请参考 [app/version.py](app/version.py)
