# 生产 SSH 与自动回滚加固实施计划

> **智能体执行要求：** 必须使用 `superpowers:executing-plans`，按任务逐项实施本计划，并使用复选框（`- [ ]`）跟踪进度。

**目标：** 让生产镜像上传和 SSH 部署严格校验预置主机公钥，并在新版本健康检查失败时自动恢复部署前的三服务镜像。

**架构：** GitHub Secret 提供离线核验的 `known_hosts`，所有 SSH/SCP 调用统一启用严格校验。deploy job 使用不取消的生产并发组。远端脚本切换前通过 Compose label 捕获 web/core-api/agent-service 镜像，验证三者版本一致且镜像存在；失败 trap 用旧 tag 重新 `compose up --wait`，但始终保留新版本部署的失败状态。

**技术栈：** GitHub Actions、OpenSSH、POSIX shell、Docker Compose v2、pytest 架构测试。

---

### Task 1: 锁定 known_hosts 与部署并发契约

**Files:**
- Modify: `tests/architecture/test_github_workflow.py`
- Modify: `tests/architecture/test_deploy_scripts.py`
- Modify: `.github/workflows/build.yml`
- Modify: `scripts/upload-docker-images.sh`

- [x] **Step 1: 写静态安全失败测试**

断言 workflow 和脚本中完全不存在 `StrictHostKeyChecking=no`，并存在：

```text
DEPLOY_SSH_KNOWN_HOSTS
SSH_KNOWN_HOSTS_FILE
StrictHostKeyChecking=yes
UserKnownHostsFile=
```

断言 deploy job 的 concurrency group 为 `production` 且 `cancel-in-progress: false`；不得再由 workflow 顶层 `cancel-in-progress: true` 取消运行中的生产部署。

- [x] **Step 2: 运行测试并确认 RED**

Run: `uv run pytest tests/architecture/test_github_workflow.py tests/architecture/test_deploy_scripts.py -q`

Expected: FAIL；当前存在禁用主机校验且生产运行可被取消。

- [x] **Step 3: 在 Prepare SSH 写入预置公钥**

workflow 从 production environment secret 写入 `~/.ssh/known_hosts`，先校验非空，再 `chmod 600`。只通过环境变量传递文件路径，不输出 Secret 内容：

```yaml
env:
  SSH_KNOWN_HOSTS_FILE: ~/.ssh/known_hosts
run: |
  test -n "$DEPLOY_SSH_KNOWN_HOSTS"
  printf '%s\n' "$DEPLOY_SSH_KNOWN_HOSTS" > "$SSH_KNOWN_HOSTS_FILE"
  chmod 600 "$SSH_KNOWN_HOSTS_FILE"
```

- [x] **Step 4: 加固上传脚本**

`upload-docker-images.sh` 在任何网络调用前要求 `SSH_KNOWN_HOSTS_FILE` 已设置、可读且非空。统一数组：

```sh
ssh_options="-o StrictHostKeyChecking=yes -o UserKnownHostsFile=$SSH_KNOWN_HOSTS_FILE"
```

所有 `ssh`/`scp` 使用同一组选项；不得调用 `ssh-keyscan` 动态信任目标。

- [x] **Step 5: 调整部署并发**

普通 CI 可保留自己的可取消组，但 deploy job 必须用独立 `production` 组排队，不能中断已开始的远端切换或回滚。

- [x] **Step 6: 验证并提交 SSH 修复**

Run: `uv run pytest tests/architecture/test_github_workflow.py tests/architecture/test_deploy_scripts.py -q`

```bash
git add .github/workflows/build.yml scripts/upload-docker-images.sh tests/architecture/test_github_workflow.py tests/architecture/test_deploy_scripts.py
git commit -m "安全：严格校验生产 SSH 主机身份"
```

### Task 2: 捕获并验证部署前镜像版本

**Files:**
- Modify: `scripts/deploy-production.sh`
- Modify: `tests/architecture/test_deploy_scripts.py`
- Create: `tests/architecture/fixtures/fake_docker.sh`

- [x] **Step 1: 写镜像捕获失败测试**

shell 夹具模拟 `docker ps --filter label=com.docker.compose.project=inkforge --filter label=com.docker.compose.service=web`（以及另外两个服务）和 `docker inspect`。覆盖：

- 三个服务都没有容器：识别为首次部署，不提供回滚；
- 只存在部分服务：部署前失败；
- 三服务镜像 tag 不一致：部署前失败；
- 三服务同 tag 且镜像存在：允许继续；
- 旧镜像任一不存在：部署前失败。

测试不得依赖真实 Docker daemon。

- [x] **Step 2: 运行测试并确认 RED**

Run: `uv run pytest tests/architecture/test_deploy_scripts.py -q -k "previous or image or first"`

- [x] **Step 3: 实现只读镜像发现函数**

脚本通过 Compose project/service label 查找容器 ID，再用 `.Config.Image` 读取完整镜像名。解析 web、core-api、agent-service 的 `${repository}:${tag}`，只接受三者都有且 tag 相同的状态。

首次部署定义为三个服务都没有容器；不能把“部分缺失”猜成首次部署。发现旧 tag 后逐一 `docker image inspect` 验证旧镜像仍存在。

- [x] **Step 4: 保持切换前无副作用**

在旧状态验证完成前，不得修改 `.env`、启动/停止容器、删除镜像或调用 compose。输出只包含服务名/tag/错误码，不输出环境文件内容。

### Task 3: 新版本失败后自动恢复旧版本

**Files:**
- Modify: `scripts/deploy-production.sh`
- Modify: `tests/architecture/test_deploy_scripts.py`
- Modify: `tests/architecture/fixtures/fake_docker.sh`

- [x] **Step 1: 写成功回滚故障注入测试**

Fake docker 让新 tag 的第一次 `docker compose up --no-build -d --wait` 返回非零，旧 tag 的第二次调用成功。断言：

- 调用顺序为 `new -> previous`；
- 回滚后执行 `compose ps`、只读 schema 指纹检查和不变更数据的 smoke 检查；
- 脚本最终仍返回非零；
- 日志包含“新版本失败、旧版本已恢复”，不报告部署成功。

- [x] **Step 2: 写回滚也失败的测试**

让两次 compose up 都失败，断言新部署错误和回滚错误都可见、最终非零，并且没有 `down -v`、现场 build、数据库迁移、卷删除或 `.env` 重写。

- [x] **Step 3: 运行测试并确认 RED**

Run: `uv run pytest tests/architecture/test_deploy_scripts.py -q -k rollback`

- [x] **Step 4: 实现保留原错误的 trap**

在新版本 `compose up` 前注册失败 trap。由于部署脚本承诺兼容 POSIX `/bin/sh`，而 `ERR` 不是 POSIX 信号，实际使用仅覆盖版本切换区间的 `EXIT` trap，并在成功后解除。rollback 立即保存原退出码并临时关闭递归 trap：

```sh
rollback() {
  original_status="$1"
  trap - EXIT
  set +e
  export INKFORGE_IMAGE_TAG="$previous_tag"
  docker compose -f "$COMPOSE_FILE" up --no-build -d --wait
  rollback_status="$?"
  # 输出 ps，并在成功时运行只读检查
  if [ "$rollback_status" -eq 0 ]; then
    echo "新版本部署失败，旧版本已恢复"
  else
    echo "新版本部署失败，自动回滚也失败" >&2
  fi
  exit "$original_status"
}
```

回滚成功也必须以原失败码退出。首次部署没有 previous tag 时只报告新版本失败，不伪造回滚。

- [x] **Step 5: 成功路径解除 trap**

新版本 compose health、只读 schema 指纹和 smoke 全部成功后才 `trap - EXIT` 并报告完成。smoke 中任何失败都触发同一回滚。

- [x] **Step 6: 验证并提交自动回滚**

Run: `uv run pytest tests/architecture/test_deploy_scripts.py -q`

Run: `sh -n scripts/deploy-production.sh scripts/upload-docker-images.sh`

```bash
git add scripts/deploy-production.sh tests/architecture/test_deploy_scripts.py tests/architecture/fixtures/fake_docker.sh
git commit -m "修复：生产部署失败时自动回滚"
```

### Task 4: 同步部署运维文档和完整架构门禁

**Files:**
- Modify: `docs/requirements/05-auth-billing-and-ops.md`
- Modify: `DOCS.md`
- Modify: `.env.example`
- Modify: `tests/architecture/test_compose_security.py`

- [x] **Step 1: 文档化操作契约**

记录 `DEPLOY_SSH_KNOWN_HOSTS` 必须由管理员在线下比对公钥后配置；说明生产并发排队、上一 tag 捕获条件、首次部署不自动回滚、成功/失败回滚的报警含义。不得建议 `ssh-keyscan` 直接信任远端。

`.env.example` 只说明变量用途，不放真实主机键或 Secret。

- [x] **Step 2: 增加危险命令禁用断言**

架构测试断言生产部署脚本不包含：

```text
down -v
docker compose build
alembic upgrade
prisma migrate
docker volume rm
StrictHostKeyChecking=no
```

- [x] **Step 3: 运行部署完整验证**

Run: `uv run pytest tests/architecture/test_github_workflow.py tests/architecture/test_deploy_scripts.py tests/architecture/test_compose_security.py -q`

Run: `uv run ruff check tests/architecture`

Expected: PASS。

- [x] **Step 4: 提交文档**

```bash
git add docs/requirements/05-auth-billing-and-ops.md DOCS.md .env.example tests/architecture/test_compose_security.py
git commit -m "文档：补充生产 SSH 与回滚运维规则"
```

### Task 5: 部署加固最终验证

**Files:**
- Verify only

- [x] **Step 1: 静态与夹具测试**

Run: `uv run pytest tests/architecture -q`

Run: `sh -n scripts/deploy-production.sh scripts/upload-docker-images.sh`

- [x] **Step 2: Compose 安全验证**

Run: `uv run pytest tests/architecture/test_compose_security.py -q`

若当前环境有 Docker，再运行：

Run: `docker compose -f infra/compose.yaml config --quiet`

Expected: 所有可用检查 PASS；生产路径没有动态信任主机、自动迁移、卷删除或取消运行中的部署。

验证记录：`tests/architecture` 共 60 项通过，两个部署 shell 通过语法检查；当前 Windows 环境未安装 Docker，因此按计划跳过 `docker compose config --quiet` 实机解析。
