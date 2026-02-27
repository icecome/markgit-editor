# 多用户隔离问题分析与解决方案

## 问题描述

当前MarkGit Editor存在多用户数据隔离问题：

### 当前架构缺陷
1. **共享缓存目录**：所有用户共享同一个缓存目录 `blog_cache`
2. **数据混乱风险**：多用户同时使用时，仓库会互相覆盖或混乱
3. **架构不一致**：用户验证保存在浏览器本地，但仓库数据保存在服务器本地

### 当前初始化逻辑流程
```
用户访问 → 添加远程仓库 → 初始化 → 所有数据存储在 blog_cache/
第二个用户访问 → 添加远程仓库 → 初始化 → 覆盖第一个用户的 blog_cache/
```

## 解决方案

### 方案一：单用户模式（当前架构）

**适用场景**：个人使用、内部工具、单用户部署

**实现方式**：
- 明确这是一个单用户工具
- 每次只能有一个用户使用
- 在前端添加提示："当前已有用户使用，请等待"
- 添加用户锁定机制

**优点**：
- 实现简单，无需修改现有架构
- 适合个人博客编辑场景
- 代码改动最小

**缺点**：
- 不支持多用户同时使用
- 用户体验受限

**需要修改的内容**：
1. 添加用户锁定状态管理
2. 前端显示锁定提示
3. 用户离开时自动释放锁定

---

### 方案二：多用户隔离模式

**适用场景**：多用户环境、团队协作、公共服务

**实现方式**：
- 为每个用户创建独立的缓存目录
- 基于用户ID或会话ID隔离数据
- 实现用户会话管理

**目录结构**：
```
blog_cache/
├── user_001/
│   ├── .git/
│   ├── content/
│   ├── hugo.toml
│   └── ...
├── user_002/
│   ├── .git/
│   ├── content/
│   ├── hugo.toml
│   └── ...
└── sessions.json
```

**优点**：
- 支持多用户同时使用
- 数据完全隔离，安全性高
- 符合多用户应用架构

**缺点**：
- 实现复杂度高
- 需要会话管理和清理机制
- 磁盘空间占用增加

**需要修改的内容**：

#### 1. 用户会话管理
```python
# app/session_manager.py
import uuid
import json
import os
from datetime import datetime, timedelta

class SessionManager:
    def __init__(self, cache_base_path):
        self.cache_base_path = cache_base_path
        self.sessions_file = os.path.join(cache_base_path, 'sessions.json')
        self.sessions = self.load_sessions()
    
    def create_session(self, user_id=None):
        session_id = str(uuid.uuid4())
        user_id = user_id or session_id
        session_path = os.path.join(self.cache_base_path, f"user_{user_id}")
        
        self.sessions[session_id] = {
            'user_id': user_id,
            'path': session_path,
            'created_at': datetime.now().isoformat(),
            'last_access': datetime.now().isoformat()
        }
        
        self.save_sessions()
        return session_id, session_path
    
    def get_session_path(self, session_id):
        if session_id in self.sessions:
            self.sessions[session_id]['last_access'] = datetime.now().isoformat()
            self.save_sessions()
            return self.sessions[session_id]['path']
        return None
    
    def cleanup_expired_sessions(self, max_age_hours=24):
        # 清理过期会话
        pass
```

#### 2. 修改配置管理
```python
# app/config.py
# 添加动态路径获取函数
def get_user_cache_path(session_id):
    from app.session_manager import session_manager
    return session_manager.get_session_path(session_id)
```

#### 3. 修改所有文件操作
- 所有使用 `config.BLOG_CACHE_PATH` 的地方改为动态获取用户路径
- 添加session_id参数传递

#### 4. 前端会话管理
- 登录时生成session_id
- 存储在localStorage或cookie中
- 所有API请求携带session_id

---

## 推荐方案

根据项目定位"在线编辑器，不保存任何数据到服务器"，建议：

### 短期方案：方案一（单用户模式）
- 快速实现，解决当前问题
- 适合个人使用场景
- 添加用户锁定提示

### 长期方案：方案二（多用户隔离）
- 如果需要支持多用户
- 实现完整的会话管理
- 定期清理过期会话数据

---

## 实施步骤

### 方案一实施步骤
1. 添加用户锁定状态（使用文件锁或内存锁）
2. 前端检测锁定状态并显示提示
3. 用户离开时释放锁定
4. 添加超时自动释放机制

### 方案二实施步骤
1. 创建SessionManager类
2. 修改配置管理，支持动态路径
3. 修改所有文件操作，添加session_id参数
4. 前端实现会话管理
5. 添加会话清理机制
6. 测试多用户场景

---

## 注意事项

1. **安全性**：确保用户只能访问自己的数据
2. **资源清理**：定期清理过期会话数据，避免磁盘空间耗尽
3. **并发控制**：Git操作需要加锁，避免并发冲突
4. **错误处理**：会话过期、路径不存在等异常情况处理
