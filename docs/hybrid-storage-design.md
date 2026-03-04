# MarkGit Editor 混合方案设计文档

## 文档信息

| 项目 | 内容 |
|------|------|
| **项目名称** | MarkGit Editor 混合存储方案 |
| **版本** | v1.0 |
| **创建日期** | 2026-03-04 |
| **状态** | 设计阶段 |
| **目标分支** | feature/hybrid-local-storage |

---

## 目录

1. [概述](#1-概述)
2. [整体架构设计](#2-整体架构设计)
3. [本地存储层设计](#3-本地存储层设计)
4. [服务端精简方案](#4-服务端精简方案)
5. [数据同步策略](#5-数据同步策略)
6. [性能与代码量评估](#6-性能与代码量评估)
7. [实施路线图](#7-实施路线图)
8. [风险与缓解措施](#8-风险与缓解措施)
9. [总结与建议](#9-总结与建议)

---

## 1. 概述

### 1.1 项目背景

MarkGit Editor 是一款基于 OAuth 2.0 的现代化 Git 博客在线编辑器，当前采用全服务端架构。所有文件操作都需要通过网络请求到后端，导致响应延迟、无离线能力、服务器成本较高。

### 1.2 方案目标

| 目标 | 当前状态 | 目标状态 | 收益 |
|------|----------|----------|--------|
| **文件操作响应时间** | 100-300ms | 1-10ms | ↓ 95% |
| **离线编辑能力** | ❌ 无 | ✅ 完全支持 | 新增功能 |
| **服务器内存占用** | 100-200MB | 30-50MB | ↓ 70% |
| **网络带宽消耗** | 高 | 低 | ↓ 80% |
| **数据隐私** | 服务器暂存 | 完全本地 | 更安全 |

### 1.3 设计原则

| 原则 | 说明 |
|------|------|
| **渐进增强** | 本地存储失败时自动回退到服务端模式 |
| **数据一致性** | 本地变更与远程仓库保持同步 |
| **最小权限** | 前端只读 GitHub API，写操作通过后端 |
| **安全优先** | 敏感操作（push）必须经过后端验证 |

---

## 2. 整体架构设计

### 2.1 架构对比

#### 现有架构（全服务端）

```
┌─────────────────────────────────────────────────────────────┐
│                    现有架构（全服务端）                    │
├─────────────────────────────────────────────────────────────┤
│                                                         │
│   ┌─────────────┐     HTTP API      ┌───────────────┐  │
│   │   浏览器     │ ◄──────────────► │ Python 后端   │  │
│   │  (Vue.js)   │                   │              │  │
│   │             │                   │ 文件操作     │  │
│   │  - 显示UI   │                   │ Git 操作     │  │
│   │  - 编辑器   │                   │ 会话管理     │  │
│   └─────────────┘                   └──────┬───────┘  │
│                                          │           │
│                                          ▼           │
│                                   ┌───────────────┐  │
│                                   │  blog_cache/  │  │
│                                   │  (服务端存储)  │  │
│                                   └───────────────┘  │
│                                                         │
│   问题：每次文件操作都需要网络请求，响应慢，无离线能力  │
└─────────────────────────────────────────────────────────────┘
```

#### 混合架构（本地+服务端）

```
┌─────────────────────────────────────────────────────────────┐
│                  混合架构（本地+服务端）                  │
├─────────────────────────────────────────────────────────────┤
│                                                         │
│   ┌───────────────────────────────────────┐            │
│   │              浏览器层                   │            │
│   │  ┌─────────────┐  ┌─────────────────┐ │         │
│   │  │   Vue.js    │  │  IndexedDB/OPFS │ │         │
│   │  │   应用层    │◄─┤   本地存储层    │ │         │
│   │  │             │  │                 │ │         │
│   │  │ - 文件缓存  │  │ - 文件内容      │ │         │
│   │  │ - 快速响应  │  │ - 元数据        │ │         │
│   │  │ - 离线编辑  │  │ - 变更追踪      │ │         │
│   │  └──────┬──────┘  └────────┬────────┘ │         │
│   │         │                  │          │         │
│   │         │   GitHub API     │          │         │
│   │         └──────────────────┼──────────┘         │
│   │                            │                   │
│   │                            ▼                   │
│   │                   ┌──────────────────┐       │
│   │                   │ GitHub API 集成 │       │
│   │                   │ (前端直接调用)    │       │
│   │                   └──────────────────┘       │
│   └───────────────────────────────────────────────┘         │
│                                                         │
│   ┌─────────────────────────────────────────────┐          │
│   │     Python 后端（精简版）                │          │
│   │  ┌─────────────────┐  ┌─────────────┐ │         │
│   │  │ Git 操作        │  │ OAuth 认证  │ │         │
│   │  │ - clone/push   │  │ - 设备授权流 │ │         │
│   │  │ - pull/fetch   │  │ - 令牌管理  │ │         │
│   │  │ - 复杂合并      │  │             │ │         │
│   │  └─────────────────┘  └─────────────┘ │         │
│   └─────────────────────────────────────────────┘          │
│                                                         │
│   优势：文件操作本地化（毫秒级响应），支持离线编辑    │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 数据流设计

#### 文件读取流程

```
用户打开文件
    │
    ▼
检查本地存储 (IndexedDB)
    │
    ├──► 存在 ──► 直接返回 (1-10ms)
    │
    └──► 不存在
           │
           ▼
      调用 GitHub API
           │
           ▼
      缓存到本地
           │
           ▼
      返回给用户
```

#### 文件保存流程

```
用户保存文件
    │
    ▼
写入本地存储 (OPFS) ──► 即时完成 (1-5ms)
    │
    ▼
更新元数据 (IndexedDB)
    │
    ▼
记录变更 (changes 表)
    │
    ▼
触发同步调度
    │
    ▼
网络检测
    │
    ├──► 在线 ──► 立即同步
    │
    └──► 离线 ──► 加入队列，等待联网
```

---

## 3. 本地存储层设计

### 3.1 存储技术选型

| 技术 | 容量 | 性能 | 适用场景 | 推荐度 |
|------|------|------|----------|--------|
| **IndexedDB** | ~50MB-1GB | 中等 | 结构化数据、元数据 | ⭐⭐⭐⭐⭐ |
| **OPFS** | 动态 | 高 | 大文件、二进制数据 | ⭐⭐⭐⭐⭐ |
| **Cache API** | 动态 | 高 | 静态资源缓存 | ⭐⭐⭐ |
| **localStorage** | ~5MB | 高 | 少量配置数据 | ⭐⭐⭐⭐ |

**推荐方案**：IndexedDB + OPFS 混合存储

### 3.2 数据库 Schema

```javascript
const DB_SCHEMA = {
  name: 'MarkGitDB',
  version: 1,
  stores: {
    // 文件元数据
    metadata: {
      keyPath: 'path',
      indexes: [
        { name: 'by_sha', keyPath: 'sha', unique: false },
        { name: 'by_modified', keyPath: 'modified', unique: false },
        { name: 'by_type', keyPath: 'type', unique: false }
      ]
    },
    // 本地变更记录
    changes: {
      keyPath: 'id',
      autoIncrement: true,
      indexes: [
        { name: 'by_path', keyPath: 'path', unique: false },
        { name: 'by_timestamp', keyPath: 'timestamp', unique: false }
      ]
    },
    // 同步状态
    sync_state: {
      keyPath: 'repo_url',
      indexes: []
    }
  }
};
```

### 3.3 数据结构定义

#### 文件元数据

```typescript
interface FileMetadata {
  path: string;           // 文件路径: "posts/my-article/index.md"
  sha: string;            // GitHub SHA (用于检测远程变更)
  size: number;           // 文件大小
  type: 'file' | 'directory';
  modified: number;       // 本地修改时间戳
  remote_modified: string; // 远程修改时间 (ISO string)
  local_changes: boolean; // 是否有本地未同步的变更
  content_hash: string;   // 内容哈希 (用于快速比较)
}
```

#### 变更记录

```typescript
interface ChangeRecord {
  id?: number;
  path: string;
  operation: 'create' | 'modify' | 'delete' | 'rename';
  old_path?: string;      // 重命名时的旧路径
  timestamp: number;
  synced: boolean;        // 是否已同步到远程
  content_hash?: string;  // 变更时的内容哈希
}
```

#### 同步状态

```typescript
interface SyncState {
  repo_url: string;
  branch: string;
  last_sync: number;      // 最后同步时间戳
  last_commit_sha: string;
  pending_changes: number;
  sync_status: 'synced' | 'pending' | 'conflict' | 'offline';
}
```

### 3.4 OPFS 目录结构

```
/user_{userId}/
├── posts/                    # 博客文章
│   ├── article-1/
│   │   ├── index.md
│   │   └── images/
│   │       └── cover.jpg
│   └── article-2/
│       └── index.md
├── _config.yml                # 配置文件
└── .sync/                     # 同步元数据
    └── sync_state.json
```

### 3.5 本地存储服务接口

```javascript
class LocalStorageService {
  // === 初始化 ===
  async init(): Promise<void>

  // === 文件操作 ===
  async readFile(path: string): Promise<string>
  async writeFile(path: string, content: string): Promise<void>
  async deleteFile(path: string): Promise<void>
  async renameFile(oldPath: string, newPath: string): Promise<void>

  // === 元数据操作 ===
  async getMetadata(path: string): Promise<FileMetadata>
  async updateMetadata(path: string, data: Partial<FileMetadata>): Promise<void>
  async getAllMetadata(): Promise<FileMetadata[]>
  async deleteMetadata(path: string): Promise<void>

  // === 变更追踪 ===
  async recordChange(path: string, operation: string): Promise<void>
  async getUnsyncedChanges(): Promise<ChangeRecord[]>
  async markChangeSynced(id: number): Promise<void>

  // === 同步状态 ===
  async getSyncState(repoUrl: string): Promise<SyncState>
  async updateSyncState(repoUrl: string, data: Partial<SyncState>): Promise<void>

  // === 工具方法 ===
  async hashContent(content: string): Promise<string>
  async clearCache(): Promise<void>
}
```

---

## 4. 服务端精简方案

### 4.1 模块职责变化

| 模块 | 现有职责 | 混合方案职责 | 变化 |
|------|---------|-------------|------|
| routes.py | 文件CRUD、Git操作、会话管理 | Git操作、同步协调 | **精简 70%** |
| git_service.py | Git命令封装 | 保留，增强 | **保留** |
| file_service.py | 文件操作、过滤 | 删除/精简 | **删除大部分** |
| session_manager.py | 会话管理、磁盘存储 | 精简，仅保留元数据 | **精简 60%** |
| auth/ | OAuth认证 | 保留 | **保留** |

### 4.2 精简后的 API 设计

#### 保留的 API（核心 Git 操作）

| 端点 | 方法 | 功能 |
|------|------|------|
| `/api/git/clone` | POST | 克隆仓库（首次初始化） |
| `/api/git/pull` | POST | 拉取远程更新 |
| `/api/git/push` | POST | 推送本地变更 |
| `/api/git/sync` | POST | 同步操作（pull + push） |
| `/api/git/status` | GET | 获取 Git 状态 |
| `/api/git/changes` | GET | 获取变更列表 |
| `/api/git/resolve` | POST | 解决冲突 |

#### 保留的 API（认证相关）

| 端点 | 方法 | 功能 |
|------|------|------|
| `/api/auth/device-code` | GET | 获取设备码 |
| `/api/auth/token` | POST | 获取访问令牌 |
| `/api/auth/status` | GET | 认证状态 |
| `/api/auth/logout` | POST | 登出 |
| `/api/auth/user` | GET | 获取用户信息 |

#### 新增的 API（同步协调）

| 端点 | 方法 | 功能 |
|------|------|------|
| `/api/sync/prepare` | POST | 准备同步（返回远程变更） |
| `/api/sync/commit` | POST | 提交同步（创建 commit 并 push） |
| `/api/sync/conflicts` | GET | 获取冲突列表 |
| `/api/sync/resolve` | POST | 解决冲突 |

#### 删除的 API（移至前端本地处理）

| 端点 | 原因 |
|------|------|
| ❌ `GET /api/files` | 前端从 IndexedDB/OPFS 读取 |
| ❌ `GET /api/file/content` | 前端从 IndexedDB/OPFS 读取 |
| ❌ `POST /api/file/create` | 前端写入 IndexedDB/OPFS |
| ❌ `POST /api/file/save` | 前端写入 IndexedDB/OPFS |
| ❌ `POST /api/file/rename` | 前端操作 IndexedDB/OPFS |
| ❌ `DELETE /api/file/delete` | 前端操作 IndexedDB/OPFS |
| ❌ `POST /api/file/upload` | 前端处理 + 后端验证 |
| ❌ `POST /api/folder/create` | 前端操作 IndexedDB/OPFS |

### 4.3 新增同步服务模块

```python
# app/sync_service.py

class SyncService:
    """同步协调服务 - 处理本地与远程的同步"""

    async def get_remote_changes(self) -> Dict[str, Any]:
        """获取远程变更"""

    async def commit_and_push(
        self,
        files: List[Dict[str, Any]],
        commit_message: str,
        oauth_session_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """提交文件并推送"""

    async def detect_conflicts(self, local_changes, remote_changes) -> List[Dict]:
        """检测冲突"""

    async def resolve_conflict(self, path: str, resolution: str) -> bool:
        """解决冲突"""
```

---

## 5. 数据同步策略

### 5.1 同步流程

```
用户编辑文件
    │
    ▼
写入本地存储 (OPFS) ◄── 即时完成
    │
    ▼
更新元数据 (IndexedDB)
    │
    ▼
记录变更 (changes 表)
    │
    ▼
自动保存触发 (3秒防抖)
    │
    ▼
网络检测
    │
    ├──► 在线 ──► 立即同步
    │            │
    │            ▼
    │       获取远程变更
    │            │
    │            ▼
    │       冲突检测
    │            │
    │       ┌────┴────┐
    │       │         │
    │       ▼         ▼
    │    无冲突    有冲突
    │       │         │
    │       ▼         ▼
    │   直接同步   提示用户
    │       │         │
    │       ▼         ▼
    │   Git Push  冲突解决
    │       │         │
    │       ▼         ▼
    │   更新状态   用户选择
    │                 │
    │                 ▼
    │             执行操作
    │
    └──► 离线 ──► 加入队列
```

### 5.2 自动同步策略

| 策略 | 配置 | 说明 |
|------|------|------|
| **自动保存** | 3秒防抖 | 用户停止编辑3秒后自动保存到本地 |
| **自动同步** | 30秒间隔 | 每30秒检查一次未同步变更 |
| **页面可见性** | 切回时同步 | 用户切换回页面时立即同步 |
| **网络状态** | 在线时同步 | 检测到网络恢复时立即同步 |

### 5.3 冲突检测与解决

#### 冲突检测算法

```
场景：用户A 和 用户B 同时编辑同一文件

T0: 文件状态 SHA=abc123
    │
    ├──► 用户A 本地编辑
    │    本地 SHA: def456 (未推送)
    │
    └──► 用户B 编辑并推送
         远程 SHA: ghi789

T1: 用户A 尝试同步
    │
    ▼
┌─────────────────────────────────────────┐
│            冲突检测流程              │
├─────────────────────────────────────────┤
│                                   │
│ 1. 获取本地文件 SHA: def456       │
│ 2. 获取远程文件 SHA: ghi789       │
│ 3. 获取基准 SHA: abc123          │
│                                   │
│ 比较：                             │
│ - 本地 SHA ≠ 基准 SHA  → 本地有修改 │
│ - 远程 SHA ≠ 基准 SHA  → 远程有修改 │
│ - 本地 SHA ≠ 远程 SHA  → 冲突！   │
│                                   │
└─────────────────────────────────────────┘
```

#### 冲突解决选项

| 选项 | 说明 | 适用场景 |
|------|------|----------|
| **保留本地** | 强制推送本地版本 | 确认本地修改正确 |
| **使用远程** | 放弃本地，使用远程 | 本地修改不重要 |
| **手动合并** | 打开合并编辑器 | 需要保留双方修改 |

### 5.4 GitHub API 集成

```javascript
class GitHubAPI {
  // === 仓库操作 ===
  async getRepoContents(owner, repo, path, ref): Promise<any>
  async getFileContent(owner, repo, path, ref): Promise<string>
  async getFileSHA(owner, repo, path, ref): Promise<string>
  async getCommitHistory(owner, repo, path, limit): Promise<any[]>
  async compareCommits(owner, repo, base, head): Promise<any>

  // === 分支操作 ===
  async getBranches(owner, repo): Promise<any[]>
  async getDefaultBranch(owner, repo): Promise<string>
}
```

---

## 6. 性能与代码量评估

### 6.1 性能对比

#### 文件操作性能

| 操作 | 现有架构 | 混合方案 | 提升幅度 |
|------|---------|---------|---------|
| 打开文件 | 100-300ms | 1-10ms | ↓ 95% |
| 保存文件 | 150-400ms | 1-5ms | ↓ 98% |
| 文件列表 | 200-500ms | 5-20ms | ↓ 96% |
| 创建文件 | 100-250ms | 1-5ms | ↓ 98% |
| 删除文件 | 100-250ms | 1-5ms | ↓ 98% |
| 重命名 | 150-300ms | 2-10ms | ↓ 97% |

#### Git 操作性能

| 操作 | 现有架构 | 混合方案 | 变化 |
|------|---------|---------|------|
| Clone | 2-10s | 2-10s | 无变化 |
| Pull | 1-5s | 1-5s | 无变化 |
| Push | 2-8s | 2-8s | 无变化 |
| Status | 100-300ms | 50-100ms | ↓ 50% |

#### 用户体验指标

| 指标 | 现有架构 | 混合方案 | 改善 |
|------|---------|---------|------|
| 首次加载 | 2-5s | 3-8s | 略慢 |
| 后续加载 | 2-5s | 0.5-1s | ↓ 80% |
| 离线能力 | ❌ 无 | ✅ 完全支持 | 新增 |
| 编辑响应 | 即时 | 即时 | 相同 |
| 保存反馈 | 等待网络 | 即时确认 | 显著改善 |

### 6.2 代码量变化

#### 后端代码变化

| 模块 | 现有行数 | 混合方案行数 | 变化 |
|------|---------|-------------|------|
| routes.py | 1,082 | 300-400 | ↓ 65% |
| git_service.py | 957 | 800-900 | ↓ 10% |
| file_service.py | 409 | 50-100 | ↓ 80% |
| session_manager.py | 357 | 150-200 | ↓ 50% |
| sync_service.py (新增) | 0 | 200-300 | 新增 |
| auth/* | 802 | 802 | 无变化 |
| main.py | 224 | 150-180 | ↓ 30% |
| 其他模块 | 384 | 200-250 | ↓ 35% |
| **后端总计** | **~4,215** | **~2,600-3,100** | **↓ 30-35%** |

#### 前端代码变化

| 模块 | 现有行数 | 混合方案行数 | 变化 |
|------|---------|-------------|------|
| main.js | 1,147 | 1,200-1,400 | ↑ 15% |
| local-storage-service.js (新增) | 0 | 400-500 | 新增 |
| sync-manager.js (新增) | 0 | 300-400 | 新增 |
| github-api.js (新增) | 0 | 200-300 | 新增 |
| oauth-component.js | ~200 | ~200 | 无变化 |
| index.html | 773 | 800-900 | ↑ 10% |
| main.css | 1,657 | 1,700-1,800 | ↑ 5% |
| **前端总计** | **~3,777** | **~4,800-5,500** | **↑ 30-45%** |

#### 总体代码量

| 类别 | 现有 | 混合方案 | 变化 |
|------|------|---------|------|
| 后端 | ~4,215 | ~2,800 | ↓ 35% |
| 前端 | ~3,777 | ~5,100 | ↑ 35% |
| **总计** | **~8,000** | **~7,900** | **基本持平** |

### 6.3 资源消耗对比

| 资源 | 现有架构 | 混合方案 | 变化 |
|------|---------|---------|------|
| 服务器内存 | 100-200MB/实例 | 30-50MB/实例 | ↓ 70% |
| 服务器磁盘 | 按用户数增长 | 最小化 | ↓ 90% |
| 服务器 CPU | 中等 | 低 | ↓ 60% |
| 网络带宽 | 高 | 低 | ↓ 80% |
| 客户端存储 | 0 | 50-500MB | 新增 |

### 6.4 安全性评估

| 安全方面 | 现有架构 | 混合方案 | 评估 |
|----------|---------|---------|------|
| 令牌存储 | 服务端 Redis | 浏览器 + 服务端 | 需加强 |
| 文件隔离 | 服务端会话隔离 | 浏览器同源策略 | 相当 |
| XSS 防护 | DOMPurify | DOMPurify | 相同 |
| CSRF 防护 | 需要防护 | 大部分操作本地 | 更安全 |
| 数据隐私 | 服务器暂存 | 完全本地 | 更安全 |
| Git 操作 | 服务端验证 | 服务端验证 | 相同 |

**安全建议**：
1. OAuth 令牌存储在 `sessionStorage` 而非 `localStorage`
2. 敏感操作（push）仍需经过后端验证
3. 实现令牌自动刷新机制

---

## 7. 实施路线图

### 7.1 分阶段实施计划

#### 阶段一：基础设施（第 1 周）

| 任务 | 预估时间 | 优先级 | 依赖 |
|------|---------|--------|------|
| 设计 IndexedDB Schema | 2h | P0 | 无 |
| 实现 IndexedDB 初始化 | 4h | P0 | Schema |
| 实现 OPFS 访问层 | 4h | P0 | 无 |
| 浏览器兼容性检测 | 2h | P1 | 无 |
| 降级机制设计 | 3h | P1 | 兼容性检测 |

**交付物**：
- `static/local-storage-service.js`（基础框架）
- IndexedDB 数据库初始化代码
- OPFS 访问封装

#### 阶段二：本地存储层（第 2 周）

| 任务 | 预估时间 | 优先级 | 依赖 |
|------|---------|--------|------|
| 文件读取操作 | 4h | P0 | 阶段一 |
| 文件写入操作 | 4h | P0 | 阶段一 |
| 文件删除操作 | 2h | P0 | 阶段一 |
| 元数据管理 | 4h | P0 | 阶段一 |
| 变更追踪 | 4h | P0 | 元数据管理 |
| GitHub API 集成 | 6h | P0 | 无 |
| 内容哈希计算 | 2h | P1 | 无 |

**交付物**：
- 完整的 `LocalStorageService` 类
- `static/github-api.js` 模块
- 单元测试

#### 阶段三：同步机制（第 3 周）

| 任务 | 预估时间 | 优先级 | 依赖 |
|------|---------|--------|------|
| 同步调度器 | 4h | P0 | 阶段二 |
| 自动保存机制 | 3h | P0 | 同步调度器 |
| 冲突检测算法 | 6h | P0 | 变更追踪 |
| 冲突解决 UI | 8h | P0 | 冲突检测 |
| 离线模式支持 | 4h | P1 | 同步调度器 |
| 网络状态监听 | 2h | P1 | 无 |

**交付物**：
- `static/sync-manager.js` 模块
- 冲突解决对话框组件
- 离线/在线状态指示器

#### 阶段四：后端精简（第 4 周）

| 任务 | 预估时间 | 优先级 | 依赖 |
|------|---------|--------|------|
| 创建 sync_service.py | 4h | P0 | 无 |
| 精简 routes.py | 6h | P0 | sync_service |
| 精简 session_manager.py | 3h | P1 | 无 |
| 增强 git_service.py | 4h | P0 | 无 |
| API 文档更新 | 2h | P1 | 所有后端改动 |

**交付物**：
- 精简后的 `app/routes.py`
- 新增 `app/sync_service.py`
- 更新的 API 文档

#### 阶段五：集成测试（第 5 周）

| 任务 | 预估时间 | 优先级 | 依赖 |
|------|---------|--------|------|
| 端到端测试 | 8h | P0 | 所有阶段 |
| 冲突场景测试 | 6h | P0 | 同步机制 |
| 离线/在线切换测试 | 4h | P0 | 同步机制 |
| 性能基准测试 | 4h | P1 | 所有阶段 |
| 浏览器兼容性测试 | 6h | P1 | 所有阶段 |

**交付物**：
- 测试报告
- 性能基准数据
- 兼容性矩阵

#### 阶段六：优化上线（第 6 周）

| 任务 | 预估时间 | 优先级 | 依赖 |
|------|---------|--------|------|
| 性能优化 | 8h | P0 | 测试报告 |
| 错误处理完善 | 4h | P0 | 测试报告 |
| 用户文档更新 | 4h | P1 | 所有阶段 |
| 灰度发布 | 4h | P0 | 所有阶段 |
| 监控告警配置 | 2h | P1 | 所有阶段 |

**交付物**：
- 优化后的代码
- 用户使用文档
- 监控配置

### 7.2 总体时间线

```
Week 1: ████████████████████████████████████████ 基础设施
Week 2:                          ████████████████████████████████████ 本地存储层
Week 3:                                                   ████████████████████████████████████ 同步机制
Week 4:                                                                             ████████████████████████████████████ 后端精简
Week 5:                                                                                                    ████████████████████████████████████ 集成测试
Week 6:                                                                                                                   ████████████████████████████████████ 优化上线
```

---

## 8. 风险与缓解措施

### 8.1 风险评估矩阵

| 风险 | 影响 | 概率 | 风险等级 | 缓解措施 |
|------|------|------|----------|----------|
| 浏览器兼容性问题 | 高 | 中 | 🔴 高 | 实现降级机制 |
| IndexedDB 存储限制 | 中 | 低 | 🟡 中 | 存储配额检测 |
| 同步冲突复杂 | 高 | 中 | 🔴 高 | 完善冲突解决 UI |
| 离线数据丢失 | 高 | 低 | 🟡 中 | 定期备份 |
| 性能不达预期 | 中 | 低 | 🟢 低 | 分阶段性能测试 |

### 8.2 回滚策略

#### 场景 1：用户浏览器不支持

```
检测条件：!window.indexedDB || !navigator.storage
回滚操作：自动使用服务端模式，显示提示
```

#### 场景 2：本地存储损坏

```
检测条件：IndexedDB 操作异常
回滚操作：清除本地数据，从服务端重新拉取
```

#### 场景 3：同步失败累积

```
检测条件：未同步变更 > 50 个
回滚操作：提示用户手动处理，提供批量操作选项
```

#### 场景 4：严重 Bug

```
检测条件：用户报告或监控告警
回滚操作：通过配置开关禁用本地存储，全局回退服务端模式
```

---

## 9. 总结与建议

### 9.1 核心收益

| 维度 | 改善幅度 | 说明 |
|------|---------|------|
| **用户体验** | ⭐⭐⭐⭐⭐ | 文件操作毫秒级响应，支持离线编辑 |
| **服务器成本** | ⭐⭐⭐⭐⭐ | 内存/磁盘/CPU 消耗降低 60-90% |
| **网络带宽** | ⭐⭐⭐⭐ | 减少 80% 的网络请求 |
| **数据隐私** | ⭐⭐⭐⭐ | 文件内容仅存于用户本地 |
| **代码维护** | ⭐⭐⭐ | 总代码量持平，但职责更清晰 |

### 9.2 最终建议

✅ **推荐实施混合方案**

**理由**：
1. 性能提升显著（文件操作响应时间降低 95%+）
2. 新增离线能力，用户体验大幅改善
3. 服务器成本显著降低
4. 总代码量基本持平，维护成本可控
5. 数据隐私更好，符合现代 Web 应用趋势

**实施建议**：
- 采用渐进式实施，每个阶段独立可测试
- 保留服务端模式作为降级方案
- 优先实现核心功能（文件读写、同步），后续迭代优化
- 关注浏览器兼容性，做好降级处理

**不推荐**：
- ❌ 完全迁移到 Rust/Go（ROI 不高）
- ❌ 完全本地化（会失去 Git 操作能力）

### 9.3 下一步行动

1. **立即可做**：创建 `local-storage-service.js` 和 IndexedDB Schema
2. **第一周**：完成基础设施搭建，实现基本的本地文件读写
3. **第二周**：实现同步机制和冲突检测
4. **第三周**：精简后端，完成集成测试

---

## 附录

### A. 相关文件清单

#### 新增文件

```
static/
├── local-storage-service.js      # 本地存储服务（400-500 行）
├── sync-manager.js              # 同步管理器（300-400 行）
├── github-api.js              # GitHub API 集成（200-300 行）
└── conflict-resolver.js        # 冲突解决 UI（150-200 行）

app/
└── sync_service.py            # 同步协调服务（200-300 行）
```

#### 修改文件

```
static/
├── main.js                   # 集成本地存储服务（+50-100 行）
└── index.html               # 添加冲突解决 UI（+50-100 行）

app/
├── routes.py                 # 精简 API（-700-800 行）
├── session_manager.py         # 精简会话管理（-150-200 行）
└── git_service.py            # 增强同步功能（+50-100 行）
```

### B. 技术栈

| 层级 | 技术 | 版本 | 说明 |
|------|------|------|------|
| **前端框架** | Vue.js | 3.4.21 |
| **本地存储** | IndexedDB + OPFS | - |
| **同步机制** | 自定义 | - |
| **后端框架** | FastAPI | 0.104.1 |
| **Git 操作** | Git 命令行 | - |
| **认证** | OAuth 2.0 | 设备授权流 |

### C. 参考资料

- [IndexedDB API - MDN](https://developer.mozilla.org/en-US/docs/Web/API/IndexedDB_API)
- [Origin Private File System - MDN](https://developer.mozilla.org/en-US/docs/Web/API/File_System_Access_API)
- [GitHub REST API](https://docs.github.com/en/rest)
- [OAuth 2.0 Device Authorization Grant](https://datatracker.ietf.org/doc/html/rfc8628)

---

**文档版本**: v1.0
**最后更新**: 2026-03-04
**维护者**: MarkGit Editor Team
