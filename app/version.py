"""
MarkGit Editor 版本管理

此文件定义了项目的版本号和变更历史。
版本号遵循语义化版本规范 (SemVer): https://semver.org/
"""

__version__ = "1.0.3"
__author__ = "MarkGit Editor Team"
__license__ = "MIT"

VERSION_HISTORY = """
# MarkGit Editor 版本历史

## v1.0.3 (2026-03-30) - 安全加固与修复版

### 安全修复
- 修复 OAuth CSRF State 验证逻辑错误，防止 CSRF 攻击
- 修复 SVG 文件上传安全验证，防止 XSS 和 SSRF 攻击
- 修复会话 ID 可预测性风险，使用 SHA256 哈希生成不可预测目录名
- 前端 XSS 防护增强，集成 DOMPurify 进行 HTML 净化
- CORS 配置加固，生产环境禁止 localhost 配置

### 代码质量提升
- 重构 Git 操作函数，将 280 行长函数拆分为 8 个小函数
- 完善速率限制覆盖，为敏感接口添加速率保护
- 重构重复的错误处理代码，添加统一装饰器
- 修复日志敏感信息泄露风险

### UI/UX 修复
- 修复设置侧边栏关闭按钮点击图标无法关闭的问题
- 修复提交变更后侧边栏无法关闭的问题
- 为提交变更面板添加加载状态和遮罩层

### 性能优化
- 前端文件树性能优化，实现增量更新机制
- 修复 rate_limiter 装饰器 asyncio 导入位置问题

---

## v1.0.2 (2026-03-03) - 用户体验优化版

### 修复
- 修复按钮图标点击无响应的问题（添加 pointer-events: none）
- 修复 Git 仓库输入框 placeholder 溢出问题
- 添加 Git 仓库地址格式验证功能

---

## v1.0.1 (2026-03-03) - 紧急修复版

### 修复
- 修复 SRI hash 占位符导致 CDN 脚本无法加载的问题
- 修复 CSRF 中间件过于严格导致请求被阻止的问题
- 修复 .env 文件中文注释编码问题
- 修复 slowapi Limiter 读取 .env 文件的编码问题
- 添加静态资源缓存破坏机制

---

## v1.0.0 (2026-03-03) - 正式发布版

### 核心特性
- GitHub OAuth 2.0 Device Flow 认证
- 多用户会话隔离，每个用户独立 Git 工作区
- 完整的 Git 工作流（克隆、拉取、提交、推送）
- Markdown 实时预览编辑器
- 文件管理（创建、编辑、删除、移动）
- 图片上传和管理

### 安全特性
- SSL 证书验证（可配置）
- CSRF 防护中间件
- XSS 防护（DOMPurify）
- Git 命令白名单验证
- 文件路径遍历防护
- 文件上传安全验证
- 会话 ID 独立生成，防止可预测性攻击
- 全局异常处理，防止敏感信息泄露

### 性能优化
- Git 操作超时配置
- Redis 连接池优化
- 前端图标增量渲染
- 文件内容大小限制

### API 版本控制
- 支持 /api/v1/xxx 版本化 API
- 保持 /api/xxx 向后兼容

### 部署支持
- Docker / Docker Compose
- Railway / Fly.io / Render / Zeabur

---

## v0.5.0 (2026-02-27) - 架构重构版

### 改进
- 添加多用户隔离方案
- 重构 Git 服务模块
- 优化代码结构

---

## v0.1.0 (2026-02-27) - 初始版

### 新增功能
- 项目初始化
- 基础框架搭建
- 核心功能原型
"""

def get_version():
    """获取当前版本号"""
    return __version__

def get_version_info():
    """获取版本信息字典"""
    return {
        "version": __version__,
        "author": __author__,
        "license": __license__
    }
