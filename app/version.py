"""
MarkGit Editor 版本管理

此文件定义了项目的版本号和变更历史。
版本号遵循语义化版本规范 (SemVer): https://semver.org/
"""

__version__ = "1.2.0"
__author__ = "MarkGit Editor Team"
__license__ = "MIT"

VERSION_HISTORY = """
# MarkGit Editor 版本历史

## v1.2.0 (2026-02-28) - 安全增强版

### 新增功能
- 添加 CSRF 防护中间件 (Origin/Referer 验证)
- 添加 XSS 防护 (DOMPurify 净化 HTML)
- 添加 `safe_git_run` 函数封装 Git 命令
- 添加 `get_safe_git_env` 函数设置 Git 环境变量
- 添加多平台部署配置 (Railway, Fly.io, Render, Kubernetes)

### 安全修复
- 修复 Git 命令可能误操作开发项目目录的问题
- 修复会话验证不一致的问题
- 添加 `.env.example` 替代真实凭据

### 改进
- 统一会话验证逻辑
- 优化错误处理和日志记录
- 完善 README.md 和部署文档

---

## v1.1.0 (2026-02-28) - OAuth 认证版

### 新增功能
- 实现 GitHub OAuth 2.0 Device Flow 认证
- 添加 OAuth 令牌存储 (支持内存和 Redis)
- 使用 GitHub 用户信息配置 Git 身份
- 添加会话级别的 Git 仓库配置

### 改进
- 移除用户信息中的 email 字段以保护隐私
- 优化 OAuth 登录流程

---

## v1.0.0 (2026-02-28) - 多用户版

### 新增功能
- 实现多用户会话隔离
- 每个用户独立的 Git 工作区
- 智能会话管理和过期数据清理
- 会话状态 API

### 核心特性
- 会话隔离设计
- 自动清理服务
- 线程安全的上下文管理

---

## v0.5.0 (2026-02-27) - 架构重构版

### 改进
- 添加多用户隔离方案文档
- 重构 Git 服务模块
- 优化代码结构

---

## v0.4.0 (2026-02-27) - 初始化版

### 新增功能
- 初始化博客编辑器项目
- 包含核心功能模块
- 基础配置文件

---

## v0.3.0 (2026-02-27) - 优化版

### 改进
- 移除认证功能 (后续重新实现)
- 优化 Git 操作逻辑
- 改进文件管理

---

## v0.2.0 (2026-02-27) - 功能增强版

### 新增功能
- 增强 Git 操作功能
- 改进文件管理

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
