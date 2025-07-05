# GitHub CI & DockerHub 集成指南

本指南介绍如何设置 GitHub Actions 来自动构建和推送 Docker 镜像到 DockerHub。

## 🏗️ 架构概述

我们的 CI/CD 流程包括：
- **Python 3.12** 基础镜像
- **多平台构建** (linux/amd64, linux/arm64)
- **自动版本标记** (基于 Git tags)
- **安全扫描** (Trivy 漏洞扫描)
- **自动推送** 到 DockerHub

## 📋 前置条件

### 1. DockerHub 账户设置

1. 注册或登录 [DockerHub](https://hub.docker.com/)
2. 创建一个新的 repository（如：`username/trading-agent`）
3. 生成访问令牌：
   - 进入 Account Settings → Security
   - 点击 "New Access Token"
   - 名称：`github-actions`
   - 权限：`Read, Write, Delete`
   - 保存生成的令牌

### 2. GitHub Secrets 配置

在你的 GitHub repository 中设置以下 secrets：

1. 进入 GitHub repository → Settings → Secrets and variables → Actions
2. 点击 "New repository secret" 添加以下 secrets：

```
DOCKERHUB_USERNAME: your-dockerhub-username
DOCKERHUB_TOKEN: your-dockerhub-access-token
```

## 🚀 CI/CD 流程

### 触发条件

CI/CD 流程会在以下情况下触发：

1. **代码推送** 到 `main` 或 `master` 分支
2. **创建 Git tag** (如 `v1.0.0`)
3. **Pull Request** 创建或更新（仅构建，不推送）

### 构建过程

1. **代码检出**：获取最新代码
2. **Docker Buildx 设置**：支持多平台构建
3. **DockerHub 登录**：使用配置的 secrets
4. **元数据提取**：自动生成标签和标签
5. **镜像构建**：
   - 平台：`linux/amd64`, `linux/arm64`
   - 使用 GitHub Actions 缓存优化构建速度
6. **镜像推送**：推送到 DockerHub
7. **README 同步**：自动更新 DockerHub repository 的 README
8. **安全扫描**：使用 Trivy 进行漏洞扫描

### 自动标签策略

镜像会自动获得以下标签：

- `latest` - 最新的 main/master 分支构建
- `main` - main 分支构建
- `v1.0.0` - 对应的 Git tag
- `v1.0` - 主要版本.次要版本
- `v1` - 主要版本
- `pr-123` - Pull Request 构建（仅用于测试）

## 📝 使用示例

### 发布新版本

1. **创建并推送 tag**：
```bash
git tag v1.0.0
git push origin v1.0.0
```

2. **GitHub Actions 会自动**：
   - 构建镜像
   - 推送到 DockerHub
   - 应用版本标签

### 拉取镜像

```bash
# 拉取最新版本
docker pull username/trading-agent:latest

# 拉取特定版本
docker pull username/trading-agent:v1.0.0

# 拉取特定架构
docker pull username/trading-agent:latest --platform linux/amd64
```

### 运行镜像

```bash
# 基本运行
docker run -d \
  --name trading-agent \
  -p 8000:8000 \
  -e ALPACA_API_KEY=your_key \
  -e TIINGO_API_KEY=your_key \
  username/trading-agent:latest

# 使用 docker-compose
docker-compose up -d
```

## 🔧 配置说明

### Dockerfile 特性

我们的 Dockerfile 包含以下特性：

- **Python 3.12** 基础镜像
- **非 root 用户** 运行（安全性）
- **健康检查** 内置
- **缓存优化** 的层级结构
- **多阶段构建** 支持

### 环境变量

构建过程中的关键环境变量：

```yaml
env:
  REGISTRY: docker.io
  IMAGE_NAME: trading-agent
```

你可以在 `.github/workflows/docker-build.yml` 中修改这些值。

## 🛡️ 安全功能

### 漏洞扫描

每次构建都会运行 Trivy 安全扫描：

- 扫描操作系统漏洞
- 检查 Python 包安全性
- 结果上传到 GitHub Security 标签页
- 不会阻止构建，但会提供安全报告

### 访问控制

- 使用 DockerHub 访问令牌而非密码
- GitHub Secrets 加密存储凭证
- 仅在非 PR 时推送镜像

## 📊 监控和故障排除

### 查看构建状态

1. 进入 GitHub repository → Actions
2. 查看 "Build and Push Docker Image" workflow
3. 点击具体的运行查看详细日志

### 常见问题

**1. 认证失败**
```
Error: buildx failed with: ERROR: failed to solve: failed to authorize
```
解决方案：检查 `DOCKERHUB_USERNAME` 和 `DOCKERHUB_TOKEN` secrets

**2. 推送失败**
```
Error: failed to push: denied: requested access to the resource is denied
```
解决方案：确保 DockerHub repository 存在且令牌有写权限

**3. 多平台构建失败**
```
Error: docker exporter does not currently support exporting manifest lists
```
解决方案：这通常是临时问题，重新运行 workflow

### 日志查看

构建日志包含详细信息：
- 每个构建步骤的详细输出
- 推送进度和结果
- 安全扫描结果

## 🔄 自定义配置

### 修改镜像名称

编辑 `.github/workflows/docker-build.yml`：

```yaml
env:
  REGISTRY: docker.io
  IMAGE_NAME: your-custom-name  # 修改这里
```

### 添加构建参数

在 workflow 中添加构建参数：

```yaml
- name: Build and push Docker image
  uses: docker/build-push-action@v5
  with:
    context: .
    platforms: linux/amd64,linux/arm64
    push: ${{ github.event_name != 'pull_request' }}
    tags: ${{ steps.meta.outputs.tags }}
    labels: ${{ steps.meta.outputs.labels }}
    build-args: |
      BUILD_VERSION=${{ github.sha }}
      BUILD_DATE=$(date -u +'%Y-%m-%dT%H:%M:%SZ')
```

### 更改触发条件

修改 `on` 部分以自定义触发条件：

```yaml
on:
  push:
    branches: [ main, develop ]  # 添加更多分支
    tags: [ 'v*', 'release-*' ]  # 自定义标签模式
```

## 📈 性能优化

### 构建缓存

我们使用 GitHub Actions 缓存来加速构建：

```yaml
cache-from: type=gha
cache-to: type=gha,mode=max
```

### 并行构建

多平台构建是并行进行的，大大减少了总构建时间。

## 🆘 支持

如果遇到问题：

1. 查看 GitHub Actions 日志
2. 检查 DockerHub repository 权限
3. 验证 secrets 配置
4. 参考 [GitHub Actions 文档](https://docs.github.com/en/actions)
5. 查看 [Docker 官方文档](https://docs.docker.com/)

---

**注意**：首次设置后，建议先在测试分支验证整个流程，然后再在生产环境中使用。 