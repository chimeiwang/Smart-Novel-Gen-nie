# 生产 SSH 与自动回滚加固规格

## 状态

- 日期：2026-07-14
- 状态：已批准，待实现
- 范围：GitHub Actions SSH 主机校验、上传脚本、部署并发和失败自动回滚

## 背景

当前 GitHub Actions 和镜像上传脚本使用 `StrictHostKeyChecking=no`，无法确认连接的是目标服务器。生产部署使用新镜像执行 `docker compose up --wait`，但失败后不会自动恢复部署前正在运行的三个镜像。生产 workflow 还允许同一分支的新运行取消正在部署的运行，可能把服务器停留在中间状态。

## 目标

- 所有生产 SSH 和镜像传输都严格校验预置主机公钥。
- 部署前记录三个生产服务当前运行的镜像标签。
- 新版本健康检查失败时自动恢复部署前镜像，并验证恢复结果。
- 生产部署一旦开始不能被同分支后续提交中途取消。

## 非目标

- 不在 workflow 中通过 `ssh-keyscan` 动态信任未知主机。
- 不在服务器现场构建镜像。
- 不修改数据库、不自动执行迁移，也不删除卷。
- 不改变 Nginx 唯一公网入口。

## 设计

### 1. 固定主机身份

生产环境新增 GitHub Secret：

```text
DEPLOY_SSH_KNOWN_HOSTS
```

Secret 保存经过管理员线下核对的 OpenSSH `known_hosts` 行。Prepare SSH 步骤把内容写入 `~/.ssh/known_hosts` 并设置权限 600。所有 `ssh` 调用统一使用：

```text
StrictHostKeyChecking=yes
UserKnownHostsFile=<明确路径>
```

`upload-docker-images.sh` 强制要求 `SSH_KNOWN_HOSTS_FILE`，文件不存在、不可读或为空时在任何网络连接前失败。脚本和 workflow 中禁止保留 `StrictHostKeyChecking=no`。

### 2. 部署并发

CI 和生产部署使用不同并发语义：普通 CI 可以取消旧运行；生产 deploy job 不允许 `cancel-in-progress`。同一生产环境同一时间只执行一个部署，后续版本排队等待，不能打断远端 `compose up` 或回滚。

### 3. 捕获上一版本

远端部署脚本在切换前通过 Compose service label 读取 `web`、`core-api` 和 `agent-service` 当前容器的 `.Config.Image`：

- 没有任何现存容器时视为首次部署，不提供自动回滚；
- 部分服务缺失或三个服务标签不一致时停止部署，要求人工检查，不能猜测回滚标签；
- 三个服务标签一致时提取上一提交标签，并确认三张上一版本镜像仍存在。

### 4. 自动回滚

在执行新版本 `docker compose up --no-build -d --wait` 前注册错误 trap。新版本启动或健康检查失败时：

1. 把 `INKFORGE_IMAGE_TAG` 恢复为上一标签；
2. 使用同一 Compose 文件执行 `up --no-build -d --wait`；
3. 输出恢复后的 `docker compose ps`；
4. 运行现有只读 schema 指纹检查和生产 smoke 检查中不改变数据的部分；
5. 回滚成功仍让原部署命令返回失败，使 CI 明确记录“新版本失败、旧版本已恢复”；
6. 回滚失败时同时输出新版本错误和回滚错误，返回非零，等待人工处理。

部署成功后解除 trap。自动回滚不得调用 `down -v`、删除镜像、修改 `.env`、修改密钥或重置数据库。

## 错误处理

- known_hosts 缺失时在上传镜像前失败。
- 无法可靠识别上一标签时不开始版本切换。
- 回滚过程保留原始失败退出码和中文诊断摘要。
- 日志不能输出 SSH 私钥、`.env`、JWT 或服务私钥内容。

## 测试与验收

- 架构测试断言 workflow 和脚本不存在 `StrictHostKeyChecking=no`。
- 测试断言 `DEPLOY_SSH_KNOWN_HOSTS` 和 `SSH_KNOWN_HOSTS_FILE` 是强制配置。
- shell 夹具模拟新部署失败，证明脚本用上一标签重新执行 Compose 并最终返回非零。
- 模拟回滚也失败，证明两个错误都可见且不会报告部署成功。
- 测试断言部署脚本不存在 `down -v`、现场 build 或数据库迁移命令。
- GitHub workflow 架构测试、回滚测试和 Compose 安全测试通过。
