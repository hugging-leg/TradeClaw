# GitHub Actions 版本升级指南

## 📋 概述

本文档记录了 GitHub Actions 中过时版本的升级过程。由于 GitHub 定期弃用旧版本的 actions，我们需要保持工作流文件的更新。

## ⚠️ 问题描述

在运行 GitHub Actions 时遇到以下错误：

```
Error: This request has been automatically failed because it uses a deprecated version of `actions/upload-artifact: v3`.
Learn more: https://github.blog/changelog/2024-04-16-deprecation-notice-v3-of-the-artifact-actions/
```

## 🔧 解决方案

### 已升级的 Actions 版本

#### 1. 测试工作流 (`.github/workflows/tests.yml`)

| Action | 旧版本 | 新版本 | 说明 |
|--------|--------|--------|------|
| `actions/setup-python` | v4 | v5 | Python 环境设置 |
| `actions/cache` | v3 | v4 | 依赖缓存 |
| `actions/upload-artifact` | v3 | v4 | 测试结果上传 |
| `codecov/codecov-action` | v3 | v4 | 代码覆盖率报告 |

#### 2. Docker 构建工作流 (`.github/workflows/docker-build.yml`)

| Action | 旧版本 | 新版本 | 说明 |
|--------|--------|--------|------|
| `peter-evans/dockerhub-description` | v3 | v4 | DockerHub 描述更新 |
| `github/codeql-action/upload-sarif` | v2 | v3 | 安全扫描结果上传 |

#### 3. 保持最新的 Actions

以下 actions 已经使用最新版本：

- `actions/checkout@v4` ✅
- `docker/setup-buildx-action@v3` ✅
- `docker/login-action@v3` ✅
- `docker/metadata-action@v5` ✅
- `docker/build-push-action@v5` ✅
- `aquasecurity/trivy-action@master` ✅

## 📝 详细更改

### 1. 修复测试工作流

```yaml
# 修复前
- uses: actions/setup-python@v4
- uses: actions/cache@v3
- uses: actions/upload-artifact@v3
- uses: codecov/codecov-action@v3

# 修复后
- uses: actions/setup-python@v5
- uses: actions/cache@v4
- uses: actions/upload-artifact@v4
- uses: codecov/codecov-action@v4
```

### 2. 修复 Docker 构建工作流

```yaml
# 修复前
- uses: peter-evans/dockerhub-description@v3
- uses: github/codeql-action/upload-sarif@v2

# 修复后
- uses: peter-evans/dockerhub-description@v4
- uses: github/codeql-action/upload-sarif@v3
```

## 🔍 版本升级说明

### `actions/upload-artifact@v4` 主要变化

- **Node.js 20 支持**：从 Node.js 16 升级到 Node.js 20
- **更好的性能**：上传速度和可靠性提升
- **向后兼容**：API 保持兼容，无需修改参数

### `actions/cache@v4` 主要变化

- **更快的缓存操作**：缓存保存和恢复速度提升
- **更好的压缩**：减少存储空间使用
- **增强的错误处理**：更清晰的错误信息

### `actions/setup-python@v5` 主要变化

- **更多 Python 版本支持**：支持最新的 Python 版本
- **更好的缓存集成**：与 pip 缓存的集成更好
- **性能提升**：Python 环境设置更快

### `codecov/codecov-action@v4` 主要变化

- **更好的令牌处理**：增强的安全性
- **更快的上传**：报告上传速度提升
- **更好的错误报告**：更详细的失败信息

## 🎯 最佳实践

### 1. 定期检查 Actions 版本

建议每个月检查一次 GitHub Actions 的版本更新：

```bash
# 检查所有使用的 actions
grep -r "uses:" .github/workflows/
```

### 2. 使用 Dependabot 自动更新

在 `.github/dependabot.yml` 中配置：

```yaml
version: 2
updates:
  - package-ecosystem: "github-actions"
    directory: "/"
    schedule:
      interval: "monthly"
```

### 3. 监控 GitHub 公告

关注 GitHub 的变更日志：
- [GitHub Changelog](https://github.blog/changelog/)
- [GitHub Actions 文档](https://docs.github.com/en/actions)

## 🚀 验证升级

### 1. 运行测试工作流

```bash
# 推送到分支触发测试
git add .
git commit -m "fix: upgrade deprecated GitHub Actions versions"
git push origin main
```

### 2. 检查工作流状态

1. 访问 GitHub repository → Actions
2. 查看最新的工作流运行
3. 确保没有弃用警告

### 3. 验证功能

- ✅ 测试运行正常
- ✅ 覆盖率报告上传成功
- ✅ Docker 镜像构建成功
- ✅ 安全扫描正常运行

## 📊 影响评估

### 兼容性

- ✅ **向后兼容**：所有升级都保持 API 兼容性
- ✅ **配置不变**：现有配置参数无需修改
- ✅ **功能增强**：性能和稳定性提升

### 性能提升

- **构建速度**：缓存和依赖安装更快
- **上传速度**：测试结果和覆盖率报告上传更快
- **可靠性**：错误处理和重试机制更好

## 🔮 未来维护

### 1. 自动化检查

考虑添加定期检查脚本：

```bash
#!/bin/bash
# check-actions-versions.sh
echo "Checking GitHub Actions versions..."
grep -r "uses:" .github/workflows/ | grep -v "@v[4-9]" | grep -v "@master"
```

### 2. 监控新版本

设置通知来跟踪新版本发布：
- GitHub Actions 官方仓库的 releases
- 第三方 actions 的更新通知

### 3. 测试策略

建议的测试流程：
1. 在测试分支验证新版本
2. 运行完整的 CI/CD 流程
3. 确认所有功能正常工作
4. 合并到主分支

## 📚 参考资料

- [GitHub Actions 弃用通知](https://github.blog/changelog/2024-04-16-deprecation-notice-v3-of-the-artifact-actions/)
- [actions/upload-artifact 升级指南](https://github.com/actions/upload-artifact#v4-what-changed)
- [GitHub Actions 版本管理最佳实践](https://docs.github.com/en/actions/creating-actions/about-custom-actions#using-release-management-for-actions)

---

**最后更新**: 2024-07-06  
**升级状态**: ✅ 完成  
**下次检查**: 2024-08-06 