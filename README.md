# MarkGit Editor
一款极其轻量化的博客在线编辑器

## 功能列表
- 支持在线创建、修改、删除博客文章
- 支持在线上传图片，自动重命名为 UUID 格式
- 支持删除已上传但未引用到的图片
- 支持查看文章变更并提交
- 支持多窗口编辑不同文章
- 支持文件和文件夹的管理（创建、重命名、移动、删除）
- 集成 Git 功能（克隆、拉取、提交、推送）
- 支持响应式设计，适配移动端
- 内置简单的认证系统（基于 JWT）

## 注意事项
- 支持 Markdown 文件在形如`content/posts/XXX/index.md`下，并且图片与 md 文件同级的场景
- 所有图片文件上传后均会自动更名为 UUID 存放在文章目录下
- 系统默认使用 admin:admin123 作为登录凭据，可通过环境变量 ADMIN_PASSWORD 修改

## 快速使用
1. 安装依赖
```shell
pip3 install fastapi uvicorn pyyaml python-jose passlib[bcrypt] python-multipart python-dotenv
```

2. 配置环境变量并启动
```shell
export BLOG_GIT_SSH="Hugo博客站点的代码仓，需要提前配置git ssh免密"
export CMD_AFTER_PUSH="在进行git push后自动执行的脚本路径，通常用于串联自动部署流程"
export ADMIN_PASSWORD="自定义管理员密码"
python3 app.py
```

3. 访问应用
   打开浏览器访问 `http://localhost:5000`

## 环境变量配置
| 环境变量 | 描述 | 默认值 |
|---------|------|--------|
| BLOG_GIT_SSH | Git 仓库 SSH 地址 | 空 |
| CMD_AFTER_PUSH | 推送后执行的命令 | 空 |
| BLOG_CACHE_PATH | 本地缓存目录 | ./blog_cache |
| BLOG_BRANCH | Git 分支 | main |
| ADMIN_PASSWORD | 管理员密码 | admin123 |
| SECRET_KEY | JWT 密钥 | 自动生成 |
| CORS_ORIGINS | 允许的 CORS 来源 | http://localhost:13131,http://127.0.0.1:13131 |
| MAX_CONTENT_LENGTH | 最大上传文件大小 | 20MB |
| PORT | 服务端口 | 8080 |
| HIDDEN_FOLDERS | 隐藏的文件夹（逗号分隔） | .git,.github,.idea,.vscode,.vs,node_modules,... |
| ALLOWED_FILE_EXTENSIONS | 允许的文件扩展名（逗号分隔） | .md,.markdown,.mdown,.mkd,.mkdown,.ronn, |

### 隐藏文件夹配置
默认隐藏以下文件夹，避免用户误操作破坏博客系统：
- `.git`, `.github` - Git 相关
- `themes`, `public`, `resources`, `static`, `assets` - 博客系统目录
- `layouts`, `archetypes`, `data`, `i18n` - Hugo 配置目录

### 允许的文件类型
默认只显示以下文件类型：
- Markdown 文件：`.md`, `.markdown`, `.mdown`, `.mkd`, `.mkdown`, `.ronn`
- 无后缀文件

### 不同博客系统的配置示例

**Hugo 博客**：
```shell
export HIDDEN_FOLDERS=".git,.github,themes,public,resources,static,assets,layouts,archetypes,data,i18n"
export ALLOWED_FILE_EXTENSIONS=".md,.markdown,"
```

**Hexo 博客**：
```shell
export HIDDEN_FOLDERS=".git,.github,node_modules,themes,public,source,scaffolds,scripts"
export ALLOWED_FILE_EXTENSIONS=".md,.markdown,"
```

**Jekyll 博客**：
```shell
export HIDDEN_FOLDERS=".git,.github,_site,_includes,_layouts,_sass,_plugins,assets"
export ALLOWED_FILE_EXTENSIONS=".md,.markdown,.html,"
```

**通用博客**（显示所有文件）：
```shell
export HIDDEN_FOLDERS=".git,.github"
export ALLOWED_FILE_EXTENSIONS=""  # 空字符串表示允许所有文件
```

## 实现原理
1. Git clone 拉下远端博客文章库
2. 在线创建、修改、删除博客文章
3. Git commit && git push 将文章改动推送到远端
4. 调用自定义脚本拉取远端库重新生成静态站点部署

## 技术栈清单
- **后端**: Python3, FastAPI, Uvicorn, Git, JWT, Bcrypt
- **前端**: Vue3, Vditor (Markdown 编辑器), Tailwind CSS, Axios, Lucide Icons
- **其他**: YAML 解析

## 项目结构
```
markgit-editor/
├── app.py                 # 后端主文件
├── index.html             # 前端主文件
├── git_config.txt         # Git仓库配置
├── markgit-editor.service  # 系统服务配置
├── start.sh               # 启动脚本
├── stop.sh                # 停止脚本
├── requirements.txt       # 依赖文件
└── favicon.ico            # 网站图标
```

## 核心功能说明
1. **文件管理**: 支持浏览、创建、编辑、重命名、移动、删除文件和文件夹
2. **文章编辑**: 使用 Vditor 编辑器，支持 Markdown 实时预览
3. **图片上传**: 支持拖拽上传，自动处理图片命名和存储
4. **Git 集成**: 支持初始化仓库、拉取更新、提交变更、推送更改
5. **认证系统**: 基于 JWT 的简单认证，保护编辑器访问

## 免责声明
- 本项目完全使用 AI 编写构建，旨在提供一个轻量化的 Hugo 博客在线编辑工具
- 项目作者不对使用本软件导致的任何直接或间接损失承担责任
- 所有代码均为开源，任何人都可以自由修改、分发和使用
- 本软件按"原样"提供，不附带任何形式的保证或担保
- 使用本软件即表示您同意上述免责声明

本项目源码结构清晰，可以随意修改源码进行二次开发直至满足你的诉求。
