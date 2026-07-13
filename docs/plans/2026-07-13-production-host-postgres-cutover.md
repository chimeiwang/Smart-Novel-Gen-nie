# 生产环境复用宿主机 PostgreSQL 切换实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在不迁移、不改写现有 PostgreSQL 业务数据的前提下，把生产环境从旧 Next.js 单体安全切换到 Next.js、Core API、Agent Service 三服务。

**Architecture:** 生产 Compose 不再管理 PostgreSQL，而由 Core API 通过 Docker host gateway 连接服务器现有 PostgreSQL 14。测试 Compose 独立定义 PostgreSQL 容器和测试数据卷。切换前对生产库做可恢复备份，切换失败时停止新编排并重启旧单体容器。

**Tech Stack:** Docker Compose、PostgreSQL 14、FastAPI、Next.js 16、Redis、GitHub Actions、pytest、Shell。

---

### Task 1: 用架构测试固定生产与测试数据库边界

**Files:**
- Modify: `tests/architecture/test_compose_security.py`
- Modify: `tests/architecture/test_github_workflow.py`

- [ ] **Step 1: 写生产 Compose 不包含 PostgreSQL 的失败测试**

将生产服务集合改为 `nginx`、`web`、`core-api`、`agent-service` 和 `redis`，并加入：

```python
def test_production_compose_uses_existing_host_postgres() -> None:
    source = COMPOSE.read_text(encoding="utf-8")
    core = _service_block(source, "core-api")

    assert "host.docker.internal:host-gateway" in core
    assert "DATABASE_URL" in core
    assert not re.search(r"(?m)^  postgres:$", source)
    assert "POSTGRES_DATA_VOLUME" not in source
    assert "postgres_data:" not in source
```

同时从只发布端口和资源限制测试的服务列表中删除 `postgres`，把 Redis 检查独立为 `test_redis_is_bounded()`。

- [ ] **Step 2: 写测试 Compose 独立拥有 PostgreSQL 的失败测试**

```python
def test_test_compose_owns_isolated_postgres() -> None:
    source = (ROOT / "infra" / "compose.test.yaml").read_text(encoding="utf-8")

    assert re.search(r"(?m)^  postgres:$", source)
    assert "TEST_POSTGRES_DATA_VOLUME" in source
    assert "pgvector/pgvector:pg16" in source
    assert "condition: service_healthy" in source
```

- [ ] **Step 3: 写工作流不再伪造生产数据库卷配置的失败测试**

```python
for obsolete in (
    "POSTGRES_DATA_VOLUME",
    "POSTGRES_USER: inkforge",
    "POSTGRES_PASSWORD: ci-placeholder",
    "POSTGRES_DB: inkforge",
):
    assert obsolete not in source
```

- [ ] **Step 4: 运行测试并确认按预期失败**

Run: `uv run pytest tests/architecture/test_compose_security.py tests/architecture/test_github_workflow.py -q`

Expected: 新增的生产 Compose、测试 PostgreSQL 和工作流断言失败。

### Task 2: 重构生产与测试 Compose

**Files:**
- Modify: `infra/compose.yaml`
- Modify: `infra/compose.test.yaml`
- Modify: `.github/workflows/build.yml`

- [ ] **Step 1: 让生产 Core API 连接宿主机数据库**

在 `core-api` 中保留 `DATABASE_URL`，增加：

```yaml
    extra_hosts:
      - "host.docker.internal:host-gateway"
```

从 `core-api.depends_on` 删除 `postgres`，保留 Redis 和 Agent Service 健康依赖。

- [ ] **Step 2: 从生产 Compose 删除 PostgreSQL**

完整删除 `postgres` 服务和 `postgres_data` 外部卷声明。保留 `data_net`，让 Core API 和 Redis 继续处于隔离数据网络中。

- [ ] **Step 3: 在测试 Compose 定义完整测试 PostgreSQL**

```yaml
  core-api:
    depends_on:
      postgres:
        condition: service_healthy

  postgres:
    image: pgvector/pgvector:pg16
    user: "999:999"
    restart: unless-stopped
    read_only: true
    security_opt:
      - no-new-privileges:true
    environment:
      POSTGRES_USER: ${TEST_POSTGRES_USER:?必须配置测试数据库用户}
      POSTGRES_PASSWORD: ${TEST_POSTGRES_PASSWORD:?必须配置测试数据库密码}
      POSTGRES_DB: ${TEST_POSTGRES_DB:?必须配置测试数据库名}
      PGDATA: /var/lib/postgresql/data/pgdata
    volumes:
      - postgres_test_data:/var/lib/postgresql/data
    tmpfs:
      - /tmp:size=16m,mode=1777
      - /var/run/postgresql:size=8m,uid=999,gid=999
    networks:
      - data_net
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U $$POSTGRES_USER -d $$POSTGRES_DB"]
      interval: 10s
      timeout: 5s
      retries: 10
    cpus: "0.35"
    mem_limit: 384m
```

- [ ] **Step 4: 删除 GitHub Deploy 的 PostgreSQL 占位变量**

Deploy job 只保留 `INKFORGE_IMAGE_TAG`。镜像构建不需要生产数据库地址、数据库用户、密码、库名或数据卷。

- [ ] **Step 5: 运行架构测试并确认通过**

Run: `uv run pytest tests/architecture/test_compose_security.py tests/architecture/test_github_workflow.py -q`

Expected: PASS。

- [ ] **Step 6: 提交 Compose 重构**

```bash
git add infra/compose.yaml infra/compose.test.yaml .github/workflows/build.yml tests/architecture/test_compose_security.py tests/architecture/test_github_workflow.py
git commit -m "运维：生产编排复用宿主机数据库"
```

### Task 3: 更新生产切换契约和文档

**Files:**
- Modify: `tests/architecture/test_github_workflow.py`
- Modify: `scripts/deploy-production.sh`
- Modify: `docs/PYTHON_BACKEND_CUTOVER.md`
- Modify: `docs/requirements/05-auth-billing-and-ops.md`

- [ ] **Step 1: 写部署脚本必须验证 host gateway 配置的失败测试**

在远程部署契约测试中加入：

```python
for contract in ("host.docker.internal", "docker compose", "config"):
    assert contract in source
```

- [ ] **Step 2: 在部署脚本增加无泄密配置检查**

`scripts/deploy-production.sh` 在启动前验证生产 Compose 已包含 `host.docker.internal`，然后执行 `docker compose --env-file .env -f "$compose_file" config >/dev/null`。失败时只输出中文错误类型，不输出 `.env` 内容或 `DATABASE_URL`。

- [ ] **Step 3: 更新切换手册**

把“现有 PostgreSQL 数据卷”改为“现有宿主机 PostgreSQL 14”，明确预备备份恢复验证、停止旧容器后的最终备份、生产不运行 Playwright、JWT 轮换和无数据库覆盖回滚。

- [ ] **Step 4: 更新运维需求**

把生产 PostgreSQL 容器和数据卷要求改为宿主机 PostgreSQL 要求，同时保留 Agent 无数据库凭据、Core 独占数据库连接和 schema 零变更约束。

- [ ] **Step 5: 运行部署契约测试**

Run: `uv run pytest tests/architecture/test_github_workflow.py tests/architecture/test_compose_security.py -q`

Expected: PASS。

- [ ] **Step 6: 提交部署契约和文档**

```bash
git add scripts/deploy-production.sh docs/PYTHON_BACKEND_CUTOVER.md docs/requirements/05-auth-billing-and-ops.md tests/architecture/test_github_workflow.py
git commit -m "运维：补齐宿主机数据库切换守卫"
```

### Task 4: 运行仓库级验证并推送

**Files:**
- Verify only

- [ ] **Step 1: 运行架构测试**

Run: `uv run pytest tests/architecture -q`

Expected: PASS。

- [ ] **Step 2: 运行 Python、格式和类型门禁**

```bash
uv run pytest -q
uv run ruff check .
uv run mypy apps/core-api/src apps/agent-service/src packages/service-contracts/src packages/service-auth/src
```

Expected: 全部退出码为 0。

- [ ] **Step 3: 运行 Node 门禁**

```bash
npm run api:check
npm run test:web
npm run typecheck
npm run lint
npm run build
```

Expected: 全部退出码为 0。

- [ ] **Step 4: 检查提交范围并推送 main**

```bash
git status --short
git log -3 --oneline
git push origin main
```

Expected: 工作树干净，推送成功。

### Task 5: 在服务器完成可恢复备份和生产配置

**Files:**
- Server only: `/srv/smart-novel-gen/.env`
- Server only: `/srv/smart-novel-gen/infra/secrets/*`
- Server only: `/srv/backups/inkforge/*`

- [ ] **Step 1: 记录只读基线**

记录 PostgreSQL 版本、数据库大小、公共表数量、估算行数、schema 指纹、旧容器 ID 和旧镜像 ID。输出不得包含连接字符串或密钥。

- [ ] **Step 2: 执行在线预备备份**

使用生产 `DATABASE_URL` 和 `/srv/backups/inkforge` 运行 `scripts/backup.sh`，随后执行 `sha256sum --check SHA256SUMS`。

- [ ] **Step 3: 恢复到独立验证库**

在宿主机 PostgreSQL 创建仅用于恢复验证的数据库，设置 `ALLOW_RESTORE_VERIFY=yes`，使用 `scripts/restore_verify.sh` 恢复并运行结构守卫。验证完成后终止该库连接并删除验证库。

- [ ] **Step 4: 探测并保护旧容器文件**

再次检查旧容器挂载点和 `/app/uploads`、`/app/public/uploads`、`/app/data`。如果存在用户文件，复制到备份目录并生成 SHA-256；不存在时记录检查结果。

- [ ] **Step 5: 生成生产密钥和 `.env`**

生成新的 JWT 随机密钥和两组 Ed25519 服务密钥。将现有数据库 URL 的主机部分改为 `host.docker.internal`，保留原用户、密码、端口和库名。`.env` 归属 `root:部署用户组` 且权限设为 `640`，让 SSH 部署用户只能读取、不能修改；私钥归属容器 UID/GID `10001:10001` 且权限为 `600`，JWKS 权限设为 `644/root`。

- [ ] **Step 6: 预检宿主机数据库连接**

从临时 Docker 容器通过 `host.docker.internal` 验证 PostgreSQL TCP 和身份认证。如果 `pg_hba.conf` 拒绝连接，只允许精确的 `data_net` 子网，不开放任意公网网段。

### Task 6: 执行维护窗口切换并验收

**Files:**
- Server runtime only

- [ ] **Step 1: 停止旧单体并执行最终备份**

停止 `smart-novel-gen-app-1`，确认其不再写入，然后再次运行 `scripts/backup.sh` 和校验和检查。

- [ ] **Step 2: 记录最终数据库基线**

再次记录 schema 指纹、公共表数量和估算行数；必须与停止旧容器后的最终状态对应。

- [ ] **Step 3: 触发并监控 GitHub Actions**

确认 CI、三镜像构建、镜像上传和远程部署依次成功。部署脚本必须使用当前提交哈希镜像并执行 `--no-build --wait`。

- [ ] **Step 4: 执行无副作用生产冒烟**

检查五个 Compose 服务健康、登录页、Core readiness、Agent readiness、Nginx `/internal/**` 阻断、schema 指纹和事务回滚写入测试。不得运行会创建生产业务记录的 Playwright 流程。

- [ ] **Step 5: 观察稳定状态**

检查容器重启次数、OOM、内存、数据库连接和错误日志。没有持续重启或关键错误后结束维护窗口。

- [ ] **Step 6: 失败时执行回滚**

任一关键检查失败时停止新 Compose，确认 PostgreSQL 健康，使用原 `.env.production` 和旧镜像重启 `smart-novel-gen-app-1`。不自动恢复数据库备份。

- [ ] **Step 7: 保留回滚材料**

旧容器、旧镜像、原 `.env.production`、预备备份和最终备份至少保留 7 天，不在本任务中清理。
