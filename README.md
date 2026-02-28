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
├── .env                            # 环境变量配置（需手动创建）
├── .env.example                    # 环境变量示例
├── requirements.txt                # Python 依赖
├── static/
│   ├── main.js                     # 前端主逻辑（Vue 3）
│   ├── main.css                    # 全局样式
│   └── oauth-component.js          # OAuth 登录组件
└── app/
    ├── config.py                   # 配置管理
    ├── routes.py                   # API 路由
    ├── git_service.py              # Git 操作服务
    ├── file_service.py             # 文件操作服务
    ├── session_manager.py          # 会话管理器
    ├── cleanup_service.py          # 清理服务
    ├── models.py                   # 数据模型
    ├── git_credential_helper.py    # Git 凭证助手
    ├── auth/
    │   ├── github_oauth.py         # GitHub OAuth 服务
    │   ├── token_store.py          # OAuth 令牌存储
    │   └── routes.py               # 认证路由
    └── file_service.py             # 文件服务
```

## 🚀 快速开始

### 1. 安装依赖

```bash
pip3 install -r requirements.txt
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
# 复制示例配置
cp .env.example .env

# 编辑 .env 文件，填入：
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

## ⚙️ 环境变量配置

### 必需配置

| 变量名 | 描述 | 示例 |
|--------|------|------|
| `GITHUB_CLIENT_ID` | GitHub OAuth Client ID | `Ov23li...` |
| `GITHUB_CLIENT_SECRET` | GitHub OAuth Client Secret | `abc123...` |
| `GITHUB_SCOPE` | OAuth 权限范围 | `repo,workflow` |

### 可选配置

| 变量名 | 描述 | 默认值 |
|--------|------|--------|
| `CMD_AFTER_PUSH` | 推送后执行的命令 | 空 |
| `ALLOWED_DEPLOY_SCRIPTS_DIR` | 部署脚本允许目录 | 空 |
| `BLOG_CACHE_PATH` | 本地缓存目录 | `./blog_cache` |
| `BLOG_BRANCH` | Git 分支 | `main` |
| `PORT` | 服务端口 | `13131` |
| `MAX_CONTENT_LENGTH` | 最大上传文件大小 | `20MB` |
| `HIDDEN_FOLDERS` | 隐藏的文件夹 | `.git,.github,.sessions,...` |
| `ALLOWED_FILE_EXTENSIONS` | 允许的文件扩展名 | `.md,.markdown,...` |

### 博客系统配置示例

**Hugo 博客**：
```bash
export HIDDEN_FOLDERS=".git,.github,themes,public,resources,static,assets,layouts,archetypes,data,i18n"
export ALLOWED_FILE_EXTENSIONS=".md,.markdown,"
```

**Hexo 博客**：
```bash
export HIDDEN_FOLDERS=".git,.github,node_modules,themes,public,source,scaffolds,scripts"
export ALLOWED_FILE_EXTENSIONS=".md,.markdown,"
```

**Jekyll 博客**：
```bash
export HIDDEN_FOLDERS=".git,.github,_site,_includes,_layouts,_sass,_plugins,assets"
export ALLOWED_FILE_EXTENSIONS=".md,.markdown,.html,"
```

**通用模式**（显示所有文件）：
```bash
export HIDDEN_FOLDERS=".git,.github"
export ALLOWED_FILE_EXTENSIONS=""
```

## 🔐 OAuth 2.0 Device Flow

### 登录流程

1. **点击登录** - 用户点击 OAuth 登录按钮
2. **获取设备码** - 服务器向 GitHub 请求设备码和用户码
3. **显示授权信息** - 前端显示二维码和授权 URL
4. **用户授权** - 用户使用手机/浏览器访问 URL 并输入用户码
5. **轮询令牌** - 服务器轮询 GitHub 获取访问令牌
6. **登录成功** - 创建会话，显示用户信息

### 安全特性

- ✅ 令牌存储在服务器端，不暴露给前端
- ✅ 会话隔离，每个用户独立的工作区
- ✅ 自动过期和清理机制
- ✅ 支持随时撤销授权

## 📝 使用指南

### 1. 登录

- 点击右上角"登录"按钮
- 使用手机或浏览器访问显示的 URL
- 输入用户码并授权
- 授权成功后自动登录

### 2. 配置仓库

- 点击设置按钮 ⚙️
- 输入 Git 仓库 HTTPS 地址
- 点击"保存配置"

### 3. 初始化工作区

- 点击"初始化"按钮
- 系统自动克隆远程仓库
- 等待初始化完成

### 4. 编辑文件

- 浏览文件树
- 点击文件进行编辑
- 支持 Markdown 实时预览
- 支持图片拖拽上传

### 5. 提交更改

- 查看文件变更列表
- 输入提交信息
- 点击"提交并推送"
- 自动执行部署命令（如果配置）

## 🛠️ 技术栈

### 后端
- **Python 3** - 主编程语言
- **FastAPI** - 现代 Web 框架
- **Uvicorn** - ASGI 服务器
- **Git** - 版本控制
- **python-dotenv** - 环境变量管理
- **httpx** - HTTP 客户端

### 前端
- **Vue 3** - 渐进式框架
- **Axios** - HTTP 客户端
- **Lucide Icons** - 图标库
- **Tailwind CSS** - 实用优先 CSS 框架

### 认证
- **OAuth 2.0 Device Flow** - GitHub 设备流认证
- **Session-based** - 基于会话的用户状态管理

## 🔧 高级功能

### 自动部署

配置 `CMD_AFTER_PUSH` 环境变量，在 Git 推送后自动执行：

```bash
# 执行部署脚本
CMD_AFTER_PUSH=/path/to/deploy.sh

# Hugo 构建
CMD_AFTER_PUSH=hugo --source blog_cache

# 触发 CI/CD
CMD_AFTER_PUSH=curl -X POST https://your-server.com/deploy
```

### 会话管理

系统自动管理用户会话：
- 每个用户独立的 Git 工作区
- 会话过期自动清理（默认 1 小时）
- 支持并发用户配置

### 文件过滤

通过 `HIDDEN_FOLDERS` 和 `ALLOWED_FILE_EXTENSIONS` 控制：
- 隐藏系统目录，避免误操作
- 只显示特定类型的文件
- 支持自定义过滤规则

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
- `POST /api/file/move` - 移动文件

### Git 操作
- `POST /api/init` - 初始化工作区
- `POST /api/pull` - 拉取远程更新
- `POST /api/commit` - 提交并推送
- `GET /api/posts/changes` - 获取变更列表

### 会话管理
- `GET /api/session/status` - 获取会话状态
- `GET /api/session/create` - 创建新会话
- `POST /api/git-repo` - 配置仓库地址

## ⚠️ 免责声明

- 本项目完全使用 AI 编写构建，旨在提供一个轻量化的博客在线编辑工具
- 项目作者不对使用本软件导致的任何直接或间接损失承担责任
- 所有代码均为开源，任何人都可以自由修改、分发和使用
- 本软件按"原样"提供，不附带任何形式的保证或担保
- 使用本软件即表示您同意上述免责声明

## 📄 许可证

本项目采用开源许可证，任何人都可以自由修改、分发和使用。

---

**注意**：本项目仍在积极开发中，部分功能可能还在完善。
