# Docker 构建 DNS 解析问题解决方案

## 🔍 问题诊断

错误信息：
```
Could not resolve 'repo.myhuaweicloud.com'
```

**根本原因**：Docker 容器内 DNS 解析失败，不是镜像源本身的问题。

---

## ✅ 解决方案（按优先级）

### 方案 1：在 docker-compose.yml 中配置 DNS（最简单，推荐）

已经在 `docker-compose.yml` 中添加了 DNS 配置：

```yaml
services:
  markgit-editor:
    dns:
      - 8.8.8.8
      - 114.114.114.114
      - 223.5.5.5
```

**直接重新构建即可**：
```bash
docker-compose build --no-cache
```

---

### 方案 2：配置 Docker 守护进程 DNS（永久解决）

#### 步骤 1：创建/编辑 Docker 配置文件

```bash
sudo vim /etc/docker/daemon.json
```

添加以下内容：
```json
{
  "dns": ["8.8.8.8", "114.114.114.114", "223.5.5.5"]
}
```

#### 步骤 2：重启 Docker 服务

```bash
sudo systemctl restart docker
```

#### 步骤 3：验证配置

```bash
docker inspect --format='{{.HostConfig.Dns}}' $(docker run -d alpine sleep 3600)
```

---

### 方案 3：使用自动修复脚本

```bash
# 赋予执行权限
chmod +x fix-docker-dns.sh

# 以 root 权限运行
sudo ./fix-docker-dns.sh
```

---

### 方案 4：手动测试 DNS 连通性

```bash
# 运行诊断脚本
chmod +x diagnose-network.sh
./diagnose-network.sh
```

---

## 🚀 快速开始

### 方式 1：使用构建脚本（推荐）

```bash
# 赋予执行权限
chmod +x build.sh

# 国内网络构建（带进度条）
./build.sh

# 无缓存重新构建
./build.sh --rebuild

# 使用国外镜像源
./build.sh -m overseas
```

### 方式 2：直接使用 docker-compose

```bash
# 国内网络（默认配置）
docker-compose build --no-cache

# 或者指定镜像源
export APT_MIRROR=mirrors.aliyun.com
docker-compose build --no-cache
```

### 方式 3：使用 docker build 命令

```bash
# 国内网络
docker build \
  --build-arg BASE_IMAGE=swr.cn-north-4.myhuaweicloud.com/ddn-k8s/docker.io/python:3.11-slim \
  --build-arg APT_MIRROR=mirrors.ustc.edu.cn \
  --progress=plain \
  -t markgit-editor .

# 如果 DNS 仍有问题，添加 DNS 参数
docker build \
  --dns 8.8.8.8 \
  --dns 114.114.114.114 \
  --build-arg BASE_IMAGE=swr.cn-north-4.myhuaweicloud.com/ddn-k8s/docker.io/python:3.11-slim \
  --build-arg APT_MIRROR=mirrors.ustc.edu.cn \
  --progress=plain \
  -t markgit-editor .
```

---

## 📦 可用镜像源

### 国内镜像源（推荐）

| 镜像源 | APT_MIRROR | 适用网络 |
|--------|-----------|---------|
| **中科大** | `mirrors.ustc.edu.cn` | 通用，最稳定 |
| **阿里云** | `mirrors.aliyun.com` | 移动网络推荐 |
| **清华大学** | `mirrors.tuna.tsinghua.edu.cn` | 教育网推荐 |
| **华为云** | `repo.myhuaweicloud.com` | 部分地区可能 DNS 解析失败 |

### 切换镜像源

```bash
# 切换到阿里云
export APT_MIRROR=mirrors.aliyun.com
docker-compose build --no-cache

# 切换到清华大学
export APT_MIRROR=mirrors.tuna.tsinghua.edu.cn
docker-compose build --no-cache
```

---

## 🔧 故障排查

### 问题 1：仍然卡在 apt-get update

**解决方案**：
```bash
# 1. 测试 DNS 解析
ping -c 4 mirrors.ustc.edu.cn

# 2. 如果 ping 不通，切换 DNS
sudo vim /etc/resolv.conf
# 添加：nameserver 8.8.8.8

# 3. 使用 IP 地址直接访问（临时方案）
# 获取阿里云镜像源 IP
nslookup mirrors.aliyun.com

# 4. 在 docker-compose.yml 中添加更多 DNS
dns:
  - 8.8.8.8
  - 114.114.114.114
  - 223.5.5.5
  - 1.1.1.1
```

### 问题 2：基础镜像拉取失败

```bash
# 1. 手动拉取镜像
docker pull swr.cn-north-4.myhuaweicloud.com/ddn-k8s/docker.io/python:3.11-slim

# 2. 或者使用阿里云镜像
export BASE_IMAGE=registry.cn-hangzhou.aliyuncs.com/library/python:3.11-slim
docker-compose build --no-cache
```

### 问题 3：Docker 版本过低

```bash
# 检查 Docker 版本
docker --version
docker-compose --version

# 需要 Docker 20.10+ 和 docker-compose 1.29+
# 升级 Docker（Ubuntu/Debian）
curl -fsSL https://get.docker.com | sh
```

---

## 📝 完整示例

```bash
# 1. 诊断网络
./diagnose-network.sh

# 2. 如果 DNS 有问题，修复它
sudo ./fix-docker-dns.sh

# 3. 重新构建
./build.sh --rebuild

# 4. 启动服务
docker-compose up -d

# 5. 查看日志
docker-compose logs -f
```

---

## 💡 最佳实践

1. **国内用户**：优先使用中科大或阿里云镜像源
2. **移动网络**：推荐使用阿里云镜像源
3. **永久解决**：配置 `/etc/docker/daemon.json` 的 DNS 设置
4. **临时解决**：在 `docker-compose.yml` 中配置 dns 字段
5. **CI/CD**：使用 `--progress=plain` 便于日志记录

---

## 📞 需要帮助？

如果以上方案都无法解决问题，请提供：

1. 运行 `./diagnose-network.sh` 的输出
2. Docker 版本：`docker --version`
3. 操作系统版本：`cat /etc/os-release`
4. 具体的错误日志
