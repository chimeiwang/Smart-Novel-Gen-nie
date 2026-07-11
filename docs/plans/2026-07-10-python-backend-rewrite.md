# Python 后端重构实施计划

> **供执行智能体使用：**必须使用 `superpowers:subagent-driven-development`（推荐）或 `superpowers:executing-plans`，逐项实施本计划。步骤使用勾选框（`- [ ]`）跟踪进度。

**目标：**在保留现有 PostgreSQL 数据库结构、用户工作流、搜索引擎优化前端和单命令 Docker Compose 部署的前提下，用生产级 FastAPI 核心接口服务和数据库隔离的 Python 智能体服务替换全部 Next.js 后端能力。

**架构：**在开发期间让 Python 服务与当前 TypeScript 实现并存，并把旧实现作为行为依据；只有证明 Python 契约行为一致后才迁移前端，并在发布前删除旧后端。核心接口服务独占 PostgreSQL、浏览器认证、业务规则、草案、计费和 SSE；智能体服务负责 LangGraph 及模型和工具执行，并通过签名的版本化 HTTP 契约与核心接口服务通信。

**技术栈：**Python 3.12、uv、FastAPI、Pydantic v2、SQLAlchemy 2 异步接口、asyncpg、pgvector、Redis 异步接口、PyJWT 和 Ed25519、独立 `inkforge-service-auth` 共享认证库、bcrypt、LangGraph Python、httpx、pytest、Next.js 16、React 19、OpenAPI 生成的 TypeScript、Nginx、Docker Compose。

**权威规格：**`docs/specs/2026-07-10-python-backend-rewrite.md`

**生命周期：**在所有任务和最终验收门槛完成前，本计划保持当前有效。交付后，本计划移入 `docs/archive/implementation-plans/`，已经实现的事实迁入仓库权威文档和需求文档。

---

## 交付顺序

1. 基础设施和不可变数据库契约。
2. 核心接口服务各领域及全部原服务器操作和接口行为。
3. 智能体服务、核心工具网关、状态恢复和计费授权流程。
4. Next.js 移动和生成客户端迁移。
5. Docker 生产拓扑、旧后端删除和切换证明。

任何阶段都不是可发布的局部产品。只有完成任务 20 后，该分支才可发布。

### 任务 1：建立 Python 和 JavaScript 工作区

**文件：**
- 新建：`.python-version`
- 新建：`pyproject.toml`
- 新建：`tests/architecture/test_repository_layout.py`
- 新建：`apps/core-api/pyproject.toml`
- 新建：`apps/core-api/src/inkforge_core/__init__.py`
- 新建：`apps/agent-service/pyproject.toml`
- 新建：`apps/agent-service/src/inkforge_agents/__init__.py`
- 新建：`packages/service-contracts/pyproject.toml`
- 新建：`packages/service-contracts/src/inkforge_contracts/__init__.py`
- 修改：`.gitignore`

- [ ] **步骤 1：安装并锁定本地 Python 工具链**

运行：`python -m pip install --user "uv>=0.8,<1"`

运行：`uv python install 3.12`

运行：`uv run --python 3.12 python --version`

预期：输出 Python 3.12.x。锁文件或应用环境不得使用机器上的 Python 3.13。

- [ ] **步骤 2：编写失败的仓库布局测试**

```python
from pathlib import Path

ROOT = Path(__file__).parents[2]


def test_required_workspace_members_exist() -> None:
    required = (
        "apps/core-api/pyproject.toml",
        "apps/agent-service/pyproject.toml",
        "packages/service-contracts/pyproject.toml",
    )
    assert all((ROOT / path).is_file() for path in required)


def test_python_services_are_separate_packages() -> None:
    assert (ROOT / "apps/core-api/src/inkforge_core").is_dir()
    assert (ROOT / "apps/agent-service/src/inkforge_agents").is_dir()
```

- [ ] **步骤 3：运行测试并确认失败**

运行：`uv run --python 3.12 --with pytest pytest tests/architecture/test_repository_layout.py -v`

预期：测试失败，因为工作区成员尚不存在。

- [ ] **步骤 4：添加 uv 工作区和包清单**

根目录 `pyproject.toml`：

```toml
[project]
name = "inkforge-workspace"
version = "0.1.0"
requires-python = ">=3.12,<3.13"
dependencies = []

[dependency-groups]
dev = [
  "pytest>=8.3,<9",
  "pytest-asyncio>=0.25,<1",
  "pytest-cov>=6,<7",
  "ruff>=0.9,<1",
  "mypy>=1.14,<2",
]

[tool.uv.workspace]
members = [
  "apps/core-api",
  "apps/agent-service",
  "packages/service-contracts",
]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests", "apps/core-api/tests", "apps/agent-service/tests", "packages/service-contracts/tests"]

[tool.ruff]
line-length = 100
target-version = "py312"

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B", "ASYNC", "S"]

[tool.mypy]
python_version = "3.12"
strict = true
```

每个服务清单都必须使用 `src` 包布局并依赖契约工作区。核心接口服务的依赖包括 FastAPI、SQLAlchemy、asyncpg、pgvector、Redis、PyJWT、cryptography、bcrypt、httpx、structlog、orjson、python-multipart 和 pydantic-settings。智能体服务的依赖包括 FastAPI、Redis、PyJWT、cryptography、httpx、structlog、orjson、LangGraph、LangChain Core 和 LangChain OpenAI。

- [ ] **步骤 5：锁定依赖并确认通过**

运行：`uv lock`

预期：生成 `uv.lock`，其中包均兼容 Python 3.12。

运行：`uv sync --all-packages --group dev`

预期：所有工作区包均成功安装。

运行：`uv run pytest tests/architecture/test_repository_layout.py -v`

预期：通过。

- [ ] **步骤 6：提交**

```bash
git add .python-version pyproject.toml uv.lock .gitignore tests/architecture apps/core-api/pyproject.toml apps/core-api/src apps/agent-service/pyproject.toml apps/agent-service/src packages/service-contracts/pyproject.toml packages/service-contracts/src
git commit -m "构建：建立 Python 服务工作区"
```

### 任务 2：定义版本化核心服务与智能体服务契约

**文件：**
- 新建：`packages/service-contracts/src/inkforge_contracts/version.py`
- 新建：`packages/service-contracts/src/inkforge_contracts/identity.py`
- 新建：`packages/service-contracts/src/inkforge_contracts/runs.py`
- 新建：`packages/service-contracts/src/inkforge_contracts/events.py`
- 新建：`packages/service-contracts/src/inkforge_contracts/tools.py`
- 新建：`packages/service-contracts/tests/test_run_contracts.py`
- 新建：`packages/service-contracts/tests/test_event_contracts.py`

- [ ] **步骤 1：编写失败的严格契约测试**

```python
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from inkforge_contracts.events import AgentEvent
from inkforge_contracts.runs import RunRequest


def test_run_request_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        RunRequest(
            protocolVersion="1.0",
            runId="run-1",
            taskId="task-1",
            novelId="novel-1",
            userId="user-1",
            operation="answer_question",
            unexpected=True,
        )


def test_agent_event_carries_ordering_identity() -> None:
    event = AgentEvent(
        protocolVersion="1.0",
        eventId="event-1",
        runId="run-1",
        taskId="task-1",
        sequence=1,
        event="agent_start",
        data={"agentId": "编辑"},
        occurredAt=datetime.now(UTC),
    )
    assert event.sequence == 1
```

- [ ] **步骤 2：运行并确认失败**

运行：`uv run pytest packages/service-contracts/tests -v`

预期：测试收集失败，因为契约模块尚不存在。

- [ ] **步骤 3：实现严格的 Pydantic 契约**

所有请求模型都使用 `ConfigDict(extra="forbid", populate_by_name=True)`。定义：

```python
PROTOCOL_VERSION = "1.0"

class RunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    protocolVersion: Literal["1.0"]
    runId: str
    taskId: str
    novelId: str
    userId: str
    operation: CreativeOperationKind
    resume: bool = False

class AgentEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    protocolVersion: Literal["1.0"]
    eventId: str
    runId: str
    taskId: str
    sequence: PositiveInt
    event: str
    data: dict[str, JsonValue]
    occurredAt: datetime
```

根据当前 TypeScript 契约精确定义 `CreativeOperationKind`、五个智能体标识、工具请求与结果信封、检查点回调、完成回调和失败回调。不得包含对象关系映射模型或仓储。

- [ ] **步骤 4：验证契约和类型质量**

运行：`uv run pytest packages/service-contracts/tests -v`

预期：通过。

运行：`uv run mypy packages/service-contracts/src`

预期：没有错误。

- [ ] **步骤 5：提交**

```bash
git add packages/service-contracts
git commit -m "功能：定义核心服务与智能体服务协议"
```

### 任务 3：搭建具有稳定错误格式和健康接口的核心接口服务

**文件：**
- 新建：`apps/core-api/src/inkforge_core/config.py`
- 新建：`apps/core-api/src/inkforge_core/app.py`
- 新建：`apps/core-api/src/inkforge_core/errors.py`
- 新建：`apps/core-api/src/inkforge_core/http/request_id.py`
- 新建：`apps/core-api/src/inkforge_core/operations/router.py`
- 新建：`apps/core-api/tests/test_health.py`
- 新建：`apps/core-api/tests/test_errors.py`

- [ ] **步骤 1：编写失败的接口测试**

```python
from fastapi.testclient import TestClient

from inkforge_core.app import create_app


def test_liveness_does_not_require_external_services() -> None:
    response = TestClient(create_app(testing=True)).get("/api/v1/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "core-api"}


def test_unknown_route_uses_stable_error_envelope() -> None:
    response = TestClient(create_app(testing=True)).get("/api/v1/missing")
    body = response.json()
    assert response.status_code == 404
    assert set(body) == {"code", "message", "details", "requestId"}
```

- [ ] **步骤 2：运行并确认失败**

运行：`uv run pytest apps/core-api/tests/test_health.py apps/core-api/tests/test_errors.py -v`

预期：测试失败，因为核心应用尚不存在。

- [ ] **步骤 3：实现应用工厂**

`create_app(testing=False)` 必须注册请求标识、稳定异常处理器和 `/api/v1/health/live`。缺少 `JWT_SECRET`、服务密钥路径或数据库地址时，配置必须拒绝生产启动。测试模式接受显式依赖覆盖，并且绝不读取开发者密钥。

- [ ] **步骤 4：确认通过并检查格式**

运行：`uv run pytest apps/core-api/tests/test_health.py apps/core-api/tests/test_errors.py -v`

预期：通过。

运行：`uv run ruff check apps/core-api/src apps/core-api/tests`

预期：没有错误。

- [ ] **步骤 5：提交**

```bash
git add apps/core-api
git commit -m "功能：搭建核心接口服务"
```

### 任务 4：冻结并验证现有 PostgreSQL 数据库结构

**文件：**
- 新建：`apps/core-api/src/inkforge_core/db/base.py`
- 新建：`apps/core-api/src/inkforge_core/db/models.py`
- 新建：`apps/core-api/src/inkforge_core/db/session.py`
- 新建：`apps/core-api/src/inkforge_core/db/schema_guard.py`
- 新建：`apps/core-api/src/inkforge_core/db/schema-contract.json`
- 新建：`apps/core-api/tests/db/test_model_metadata.py`
- 新建：`apps/core-api/tests/db/test_schema_guard.py`
- 新建：`scripts/export_schema_contract.py`

- [ ] **步骤 1：为不可变数据库结构编写失败的元数据测试**

```python
from pathlib import Path

from inkforge_core.db.base import Base


EXPECTED_TABLES = {
    "User", "Novel", "Chapter", "ChapterQualityCheck", "ChapterProgress",
    "Character", "CharacterRelation", "CharacterExperience", "Item", "Location",
    "Faction", "Glossary", "StoryBackground", "WorldSetting", "WritingBible",
    "Outline", "PlotProgress", "ReferenceMaterial", "RagDocument", "RagChunk",
    "WritingStyle", "StyleReference", "StylePortraitTask", "Foreshadowing",
    "OutlineNode", "CharacterStateChange", "WritingConfig", "WritingTask",
    "WritingSession", "WritingMessage", "TokenUsage", "CreditLedger", "WorkflowRun",
    "WorkflowStep", "ReviewArtifact", "ReviewArtifactRevision",
    "ReviewArtifactEvaluation", "ChapterWritingGoal", "ChapterBeatPlan", "SceneBeat",
}


def test_sqlalchemy_maps_every_existing_table_without_extra_tables() -> None:
    assert set(Base.metadata.tables) == EXPECTED_TABLES


def test_runtime_never_calls_schema_creation() -> None:
    source_root = Path(__file__).parents[2] / "src" / "inkforge_core"
    source = "\n".join(path.read_text("utf-8") for path in source_root.rglob("*.py"))
    assert ".create_all(" not in source
    assert ".drop_all(" not in source
```

Prisma 当前包含 40 个实体表。测试以当前 `schema.prisma` 为权威，防止计划固化过时的数量。

- [ ] **步骤 2：运行并确认失败**

运行：`uv run pytest apps/core-api/tests/db/test_model_metadata.py -v`

预期：测试失败，因为对象关系映射尚不存在。

- [ ] **步骤 3：实现精确的 SQLAlchemy 映射**

映射 `prisma/schema.prisma` 中的每个表、带引号列、关系、PostgreSQL 枚举、大整数和向量字段。使用应用生成的字符串标识和带时区的协调世界时日期。不得调用 `create_all`、导入 Alembic 或添加数据定义语句事件监听器。

- [ ] **步骤 4：导出只读数据库结构契约**

`scripts/export_schema_contract.py` 必须要求提供 `--database-url`，查询 `information_schema` 和 `pg_catalog`，打印来源服务器标识，并且只在显式提供 `--output` 时写入。它绝不能执行数据定义语句。

以只读模式对当前数据库运行：

```bash
uv run python scripts/export_schema_contract.py --database-url "$DATABASE_URL" --output apps/core-api/src/inkforge_core/db/schema-contract.json
```

预期：契约包含表、列、类型、可空性、默认值、键、索引、枚举和向量维度。

- [ ] **步骤 5：验证守卫成功路径和漂移拒绝路径**

测试使用模拟检查器快照覆盖精确匹配，以及可空性、类型或索引值发生一处变化的情况。精确匹配返回就绪；任何漂移都返回字段级差异，并将就绪状态设为否。

运行：`uv run pytest apps/core-api/tests/db -v`

预期：通过。

- [ ] **步骤 6：提交**

```bash
git add apps/core-api/src/inkforge_core/db apps/core-api/tests/db scripts/export_schema_contract.py
git commit -m "功能：映射并守卫不可变 PostgreSQL 数据库结构"
```

### 任务 5：实现签名服务身份和重放保护

**文件：**
- 新建：`apps/core-api/src/inkforge_core/service_auth.py`
- 新建：`apps/agent-service/src/inkforge_agents/service_auth.py`
- 新建：`packages/service-contracts/src/inkforge_contracts/jwt_claims.py`
- 新建：`packages/service-auth/pyproject.toml`
- 新建：`packages/service-auth/src/inkforge_service_auth/__init__.py`
- 新建：`packages/service-auth/src/inkforge_service_auth/service_auth.py`
- 新建：`packages/service-auth/src/inkforge_service_auth/py.typed`
- 新建：`packages/service-auth/tests/test_service_auth_security.py`
- 新建：`packages/service-auth/tests/test_package_wheel.py`
- 新建：`apps/core-api/tests/test_service_auth.py`
- 新建：`apps/agent-service/tests/test_agent_service_auth.py`
- 新建：`scripts/generate_service_keys.py`

- [ ] **步骤 1：编写失败的信任边界测试**

测试有效的 Ed25519 令牌只能用于预期的 `aud`、权限范围、任务、运行和小说。测试过期令牌、错误签发者、错误受众、缺少权限范围、重复使用的 `jti`、不匹配的请求体摘要，以及超出允许时钟偏差的令牌。

```python
def test_agent_token_cannot_call_another_novel(verifier, signed_token) -> None:
    with pytest.raises(ServiceAuthorizationError, match="novel_id"):
        verifier.verify(
            signed_token,
            audience="core-api",
            required_scope="tool:read",
            novel_id="novel-2",
        )
```

- [ ] **步骤 2：运行并确认失败**

运行：`uv run pytest packages/service-auth/tests/test_service_auth_security.py apps/core-api/tests/test_service_auth.py apps/agent-service/tests/test_agent_service_auth.py -v`

预期：测试失败，因为服务认证尚未实现。

- [ ] **步骤 3：实现密钥加载、签名和验证**

私钥只能从拒绝符号链接和非普通文件的安全文件描述符加载；POSIX 私钥必须属于当前用户且禁止组和其他用户访问。声明在 120 秒后过期。内部写入权限范围必须使用 Redis 重放保护，并将已消费 `jti` 固定保留 300 秒；幂等读取可以选择使用。请求模型进入业务服务前，必须验证 `Idempotency-Key`、`X-InkForge-Timestamp` 和 `X-InkForge-Body-SHA256`，并使用 `query_sha256` 绑定 ASGI 原始查询字符串字节。密码学、请求绑定和重放保护的通用实现集中在 `inkforge-service-auth` 工作区库；该库不监听端口、不增加部署进程，两个运行服务只通过各自模块暴露固定方向的构造函数和服务认证异常处理器。

- [ ] **步骤 4：确认通过**

运行：`uv run pytest packages/service-auth/tests/test_service_auth_security.py apps/core-api/tests/test_service_auth.py apps/agent-service/tests/test_agent_service_auth.py -v`

预期：通过。

- [ ] **步骤 5：提交**

```bash
git add apps/core-api/src/inkforge_core/service_auth.py apps/core-api/tests/test_service_auth.py apps/agent-service/src/inkforge_agents/service_auth.py apps/agent-service/tests/test_agent_service_auth.py packages/service-contracts packages/service-auth scripts/generate_service_keys.py
git commit -m "功能：保护核心服务与智能体服务调用"
```

### 任务 6：迁移浏览器认证和注册计费

**文件：**
- 新建：`apps/core-api/src/inkforge_core/auth/router.py`
- 新建：`apps/core-api/src/inkforge_core/auth/schemas.py`
- 新建：`apps/core-api/src/inkforge_core/auth/service.py`
- 新建：`apps/core-api/src/inkforge_core/auth/repository.py`
- 新建：`apps/core-api/src/inkforge_core/auth/dependencies.py`
- 新建：`apps/core-api/tests/auth/test_auth_api.py`
- 新建：`apps/core-api/tests/auth/test_legacy_cookie.py`

- [ ] **步骤 1：编写失败的行为一致性测试**

覆盖用户名规范化和正则表达式、密码最短长度、bcryptjs 的 UTF-8 前 72 字节兼容语义、重复用户名、bcryptjs 固定哈希验证、jose 固定 Cookie 兼容、30 天有效期、安全生产 Cookie、可信代理地址解析、双桶 Redis 限流、统一无效登录错误、注册赠送余额和 CreditLedger 事务。

- [ ] **步骤 2：确认失败**

运行：`uv run pytest apps/core-api/tests/auth -v`

预期：测试失败，因为认证路由尚不存在。

- [ ] **步骤 3：实现认证接口**

实现 `/api/v1/auth/register`、`/login`、`/logout` 和 `/me`。保留 `inkforge-token`、HS256 和 `sub=userId`。生产环境拒绝旧默认密钥和少于 32 个 UTF-8 字节的密钥，并要求配置可信代理网段。注册在同一个成功请求中创建 User、把 `creditBalanceMicros` 增加 `1_000_000_000`、写入 `signup_bonus` 并设置 Cookie。登录和注册使用来源桶加来源/账号桶，两个桶通过 Redis Lua 原子检查；Redis 故障时认证请求失败关闭。

- [ ] **步骤 4：确认通过并验证未授权资源行为**

运行：`uv run pytest apps/core-api/tests/auth -v`

预期：通过。

- [ ] **步骤 5：提交**

```bash
git add apps/core-api/src/inkforge_core/auth apps/core-api/tests/auth
git commit -m "功能：把认证迁移到核心接口服务"
```

### 任务 7：迁移项目、章节、工作区聚合和质量状态

**文件：**
- 新建：`apps/core-api/src/inkforge_core/novels/router.py`
- 新建：`apps/core-api/src/inkforge_core/novels/schemas.py`
- 新建：`apps/core-api/src/inkforge_core/novels/service.py`
- 新建：`apps/core-api/src/inkforge_core/novels/repository.py`
- 新建：`apps/core-api/src/inkforge_core/chapters/router.py`
- 新建：`apps/core-api/src/inkforge_core/chapters/schemas.py`
- 新建：`apps/core-api/src/inkforge_core/chapters/service.py`
- 新建：`apps/core-api/src/inkforge_core/chapters/repository.py`
- 新建：`apps/core-api/src/inkforge_core/quality/router.py`
- 新建：`apps/core-api/src/inkforge_core/quality/schemas.py`
- 新建：`apps/core-api/src/inkforge_core/quality/service.py`
- 新建：`apps/core-api/src/inkforge_core/quality/repository.py`
- 新建：`apps/core-api/tests/novels/test_novel_api.py`
- 新建：`apps/core-api/tests/chapters/test_chapter_api.py`
- 新建：`apps/core-api/tests/quality/test_quality_state.py`

- [ ] **步骤 1：编写失败的业务规则测试**

覆盖创建小说时同时创建第一章、空大纲、剧情进度和 WritingBible 篇幅类型；仪表盘顺序；章节编号；标题回退；正文原样保存；1.2 秒自动保存仍由前端负责；章节状态切换；默认一致性检查；完成或跳过前阻止完成；以及跨用户拒绝。

- [ ] **步骤 2：确认失败**

运行：`uv run pytest apps/core-api/tests/novels apps/core-api/tests/chapters apps/core-api/tests/quality -v`

预期：测试失败，因为路由尚不存在。

- [ ] **步骤 3：实现事务服务和聚合接口**

实现 `/api/v1/dashboard`、`/api/v1/novels`、`/api/v1/novels/{id}/workspace`、章节创建、更新和状态接口、章节进度、质量状态和质量运行提交。工作区响应必须包含 `src/app/workspace/[novelId]/page.tsx` 当前加载的每个字段，不得静默限制列表数量。

质量运行提交在本任务只定义可注入端口。端口未接线时固定返回 503 且不得修改检查项状态；任务 15 接入智能体服务队列后，提交成功才返回 202。真实 PostgreSQL 的并发锁集成验证留到任务 18 的隔离测试数据库执行，本任务的并发测试不得连接或写入现有数据库。

- [ ] **步骤 4：确认通过**

运行：`uv run pytest apps/core-api/tests/novels apps/core-api/tests/chapters apps/core-api/tests/quality -v`

预期：通过。

- [ ] **步骤 5：提交**

```bash
git add apps/core-api/src/inkforge_core/novels apps/core-api/src/inkforge_core/chapters apps/core-api/src/inkforge_core/quality apps/core-api/tests/novels apps/core-api/tests/chapters apps/core-api/tests/quality
git commit -m "功能：迁移项目和章节领域"
```

### 任务 8：迁移设定、大纲、进度和参考资料领域

**文件：**
- 新建：`apps/core-api/src/inkforge_core/lore/router.py`
- 新建：`apps/core-api/src/inkforge_core/lore/schemas.py`
- 新建：`apps/core-api/src/inkforge_core/lore/service.py`
- 新建：`apps/core-api/src/inkforge_core/lore/repository.py`
- 新建：`apps/core-api/src/inkforge_core/outlines/router.py`
- 新建：`apps/core-api/src/inkforge_core/outlines/schemas.py`
- 新建：`apps/core-api/src/inkforge_core/outlines/service.py`
- 新建：`apps/core-api/src/inkforge_core/outlines/repository.py`
- 新建：`apps/core-api/src/inkforge_core/outlines/validation.py`
- 新建：`apps/core-api/src/inkforge_core/references/router.py`
- 新建：`apps/core-api/src/inkforge_core/references/schemas.py`
- 新建：`apps/core-api/src/inkforge_core/references/service.py`
- 新建：`apps/core-api/src/inkforge_core/references/repository.py`
- 新建：`apps/core-api/src/inkforge_core/references/rag.py`
- 新建：`apps/core-api/tests/lore/test_lore_api.py`
- 新建：`apps/core-api/tests/outlines/test_outline_api.py`
- 新建：`apps/core-api/tests/references/test_reference_api.py`
- 新建：`apps/core-api/tests/references/test_rag.py`

- [ ] **步骤 1：编写失败的领域行为一致性测试**

覆盖 Character、CharacterExperience、CharacterRelation、Item、Location、Faction 和 Glossary 的每个创建、更新和删除操作；StoryBackground、WorldSetting、WritingBible、故事和章节进度；大纲文本、三层节点层级、子节点兼容性、章节范围包含和同级范围不重叠；以及 PlotProgress、Foreshadowing 和 ReferenceMaterial。

- [ ] **步骤 2：添加无损检索增强生成测试**

迁移当前分块测试，并断言“移除分隔符后连接所有分块”仍保留源文本的全部字符。测试禁用嵌入、向量插入成功、索引失败状态和小说范围内的余弦搜索。

- [ ] **步骤 3：确认失败**

运行：`uv run pytest apps/core-api/tests/lore apps/core-api/tests/outlines apps/core-api/tests/references -v`

预期：测试失败，因为领域尚不存在。

- [ ] **步骤 4：实现仓储和服务**

使用资源范围内的更新和删除语句，并断言受影响行数。保留精确枚举值、所有可选字段和当前中文错误。检索增强生成的原始 SQL 绑定每个值，绝不把向量或用户输入插入 SQL 文本。

- [ ] **步骤 5：确认通过**

运行：`uv run pytest apps/core-api/tests/lore apps/core-api/tests/outlines apps/core-api/tests/references -v`

预期：通过。

- [ ] **步骤 6：提交**

```bash
git add apps/core-api/src/inkforge_core/lore apps/core-api/src/inkforge_core/outlines apps/core-api/src/inkforge_core/references apps/core-api/tests/lore apps/core-api/tests/outlines apps/core-api/tests/references
git commit -m "功能：迁移创作知识领域"
```

### 任务 9：迁移文风文件和画像任务状态

**文件：**
- 新建：`apps/core-api/src/inkforge_core/styles/router.py`
- 新建：`apps/core-api/src/inkforge_core/styles/schemas.py`
- 新建：`apps/core-api/src/inkforge_core/styles/service.py`
- 新建：`apps/core-api/src/inkforge_core/styles/repository.py`
- 新建：`apps/core-api/src/inkforge_core/styles/storage.py`
- 新建：`apps/core-api/tests/styles/test_style_api.py`
- 新建：`apps/core-api/tests/styles/test_storage.py`

- [ ] **步骤 1：编写失败的存储和接口测试**

覆盖只允许 `.txt`、内容非空、拒绝超过 50 MB、Unicode 文件名净化、拒绝路径穿越、拒绝符号链接逃逸、不计空白的字符统计、旧 Windows 文件路径解析、文件删除、文风级联行为、画像任务创建和状态、分节更新以及应用到小说。

- [ ] **步骤 2：确认失败**

运行：`uv run pytest apps/core-api/tests/styles -v`

预期：失败。

- [ ] **步骤 3：实现存储根目录和文风服务**

所有写入都解析到 `/data/uploads` 之下。保存兼容回滚的 `/app/uploads/styles/...` 路径，同时根据现有 Windows 路径的 `uploads/styles/` 后缀进行解析。画像生成提交到智能体服务；只有核心接口服务能根据签名回调更新任务和文风记录。

- [ ] **步骤 4：确认通过**

运行：`uv run pytest apps/core-api/tests/styles -v`

预期：通过。

- [ ] **步骤 5：提交**

```bash
git add apps/core-api/src/inkforge_core/styles apps/core-api/tests/styles
git commit -m "功能：迁移文风工作流"
```

### 任务 10：迁移计费和幂等模型授权

**文件：**
- 新建：`apps/core-api/src/inkforge_core/billing/router.py`
- 新建：`apps/core-api/src/inkforge_core/billing/schemas.py`
- 新建：`apps/core-api/src/inkforge_core/billing/service.py`
- 新建：`apps/core-api/src/inkforge_core/billing/repository.py`
- 新建：`apps/core-api/src/inkforge_core/billing/pricing.py`
- 新建：`apps/core-api/tests/billing/test_pricing.py`
- 新建：`apps/core-api/tests/billing/test_model_grants.py`
- 新建：`apps/core-api/tests/billing/test_usage_charge.py`

- [ ] **步骤 1：迁移失败的定价测试**

保留积分微单位换算、DeepSeek flash 输入、缓存和输出费率、提示词估算、最小输出预算、余额不足错误和显示格式。

- [ ] **步骤 2：添加并发和重试测试**

使用同一 `requestId` 的两个并发用量回调必须只产生一次扣款、一条 `ai_charge` 账本记录和一条 TokenUsage 记录。使用 PostgreSQL 事务级咨询锁和现有 `CreditLedger.requestId`，不得修改数据库结构。

- [ ] **步骤 3：确认失败**

运行：`uv run pytest apps/core-api/tests/billing -v`

预期：失败。

- [ ] **步骤 4：实现授权、扣费和汇总接口**

实现受任务和运行令牌约束的内部预检与用量接口，以及公开的 `/api/v1/billing/summary` 和 `/usage`。模拟模型提供方授权携带 `billable=false`，并且绝不写入用量。

- [ ] **步骤 5：确认通过**

运行：`uv run pytest apps/core-api/tests/billing -v`

预期：通过。

- [ ] **步骤 6：提交**

```bash
git add apps/core-api/src/inkforge_core/billing apps/core-api/tests/billing
git commit -m "功能：迁移幂等人工智能计费"
```

### 任务 11：迁移写作会话、消息、任务和 ReviewArtifact

**文件：**
- 新建：`apps/core-api/src/inkforge_core/writing/router.py`
- 新建：`apps/core-api/src/inkforge_core/writing/schemas.py`
- 新建：`apps/core-api/src/inkforge_core/writing/service.py`
- 新建：`apps/core-api/src/inkforge_core/writing/repository.py`
- 新建：`apps/core-api/src/inkforge_core/writing/sse.py`
- 新建：`apps/core-api/src/inkforge_core/writing/recovery.py`
- 新建：`apps/core-api/src/inkforge_core/writing/context.py`
- 新建：`apps/core-api/src/inkforge_core/writing/tool_gateway.py`
- 新建：`apps/core-api/src/inkforge_core/reviews/router.py`
- 新建：`apps/core-api/src/inkforge_core/reviews/schemas.py`
- 新建：`apps/core-api/src/inkforge_core/reviews/service.py`
- 新建：`apps/core-api/src/inkforge_core/reviews/repository.py`
- 新建：`apps/core-api/src/inkforge_core/reviews/apply.py`
- 新建：`apps/core-api/src/inkforge_core/reviews/diff.py`
- 新建：`apps/core-api/src/inkforge_core/reviews/updates.py`
- 新建：`apps/core-api/tests/writing/test_sessions.py`
- 新建：`apps/core-api/tests/writing/test_recovery.py`
- 新建：`apps/core-api/tests/writing/test_sse.py`
- 新建：`apps/core-api/tests/writing/test_context.py`
- 新建：`apps/core-api/tests/writing/test_tool_gateway.py`
- 新建：`apps/core-api/tests/reviews/test_artifact_lifecycle.py`
- 新建：`apps/core-api/tests/reviews/test_artifact_apply.py`

- [ ] **步骤 1：编写失败的会话和恢复测试**

迁移显式会话绑定、当前任务与最近任务分离、消息持久化、已完成或错误任务不可恢复、拒绝格式错误快照、排除仅运行时字段和任务归属测试。

- [ ] **步骤 2：编写失败的 ReviewArtifact 测试**

迁移草案种类和状态、修订唯一性、通过、修改或阻断评估、补丁安全、彻底丢弃、部分 `agent_updates` 选择、章节目标解析、章节节拍计划应用，以及禁止把 `revision_brief` 正式写库的规则。

- [ ] **步骤 3：编写失败的 SSE 重放测试**

事件具有单调递增标识、心跳、类型化载荷，并支持从 `Last-Event-ID` 开始重放。重复回调会被忽略；序号缺口返回可恢复的流错误并触发状态对账。

- [ ] **步骤 4：编写失败的上下文和工具网关测试**

迁移当前操作范围内的上下文聚合、已批准章节节拍计划和唯一章节组解析。测试每个只读和控制工具的权限范围、完整结果行为、仅草案可见性、任务与小说绑定，以及智能体尝试未经授权的能力时被拒绝。

- [ ] **步骤 5：确认失败**

运行：`uv run pytest apps/core-api/tests/writing apps/core-api/tests/reviews -v`

预期：失败。

- [ ] **步骤 6：实现核心接口服务拥有的任务、草案、上下文、工具网关和 SSE 服务**

创建全部公开写作、会话和草案接口，以及内部智能体回调接口。核心接口服务在接受事件、检查点、完成或失败回调前验证服务身份和任务绑定。稳定快照写入现有 `graphStateJson`；运行时回调和小说聚合数据绝不持久化。

- [ ] **步骤 7：确认通过**

运行：`uv run pytest apps/core-api/tests/writing apps/core-api/tests/reviews -v`

预期：通过。

- [ ] **步骤 8：提交**

```bash
git add apps/core-api/src/inkforge_core/writing apps/core-api/src/inkforge_core/reviews apps/core-api/tests/writing apps/core-api/tests/reviews
git commit -m "功能：迁移写作和草案持久化"
```

### 任务 12：搭建智能体服务和显式模型提供方

**文件：**
- 新建：`apps/agent-service/src/inkforge_agents/config.py`
- 新建：`apps/agent-service/src/inkforge_agents/app.py`
- 新建：`apps/agent-service/src/inkforge_agents/providers/base.py`
- 新建：`apps/agent-service/src/inkforge_agents/providers/openai_compatible.py`
- 新建：`apps/agent-service/src/inkforge_agents/providers/fake.py`
- 新建：`apps/agent-service/src/inkforge_agents/runtime/model_runtime.py`
- 新建：`apps/agent-service/tests/test_health.py`
- 新建：`apps/agent-service/tests/providers/test_fake_provider.py`
- 新建：`apps/agent-service/tests/providers/test_provider_config.py`

- [ ] **步骤 1：编写失败的模型提供方测试**

测试缺少真实凭据时，只有 `MODEL_PROVIDER=fake` 才选择模拟模型提供方；生产环境的 `openai_compatible` 缺少密钥时就绪检查失败。模拟模型提供方返回确定性的文本、工具调用和用量，并且绝不建立网络连接。

- [ ] **步骤 2：确认失败**

运行：`uv run pytest apps/agent-service/tests/test_health.py apps/agent-service/tests/providers -v`

预期：失败。

- [ ] **步骤 3：实现应用和模型提供方**

模型提供方选择必须显式、通过依赖注入且可测试。模型运行时只执行一个供应商轮次，不解释业务控制工具。智能体服务只暴露存活、就绪和签名内部运行接口。

- [ ] **步骤 4：确认通过**

运行：`uv run pytest apps/agent-service/tests/test_health.py apps/agent-service/tests/providers -v`

预期：通过。

- [ ] **步骤 5：提交**

```bash
git add apps/agent-service/src apps/agent-service/tests
git commit -m "功能：搭建智能体服务运行时"
```

### 任务 13：迁移智能体定义、提示词、能力和工具运行时

**文件：**
- 新建：`apps/agent-service/src/inkforge_agents/definitions/agents.py`
- 新建：`apps/agent-service/src/inkforge_agents/definitions/capabilities.py`
- 新建：`apps/agent-service/src/inkforge_agents/prompts/lore.py`
- 新建：`apps/agent-service/src/inkforge_agents/prompts/plot.py`
- 新建：`apps/agent-service/src/inkforge_agents/prompts/author.py`
- 新建：`apps/agent-service/src/inkforge_agents/prompts/validator.py`
- 新建：`apps/agent-service/src/inkforge_agents/prompts/editor.py`
- 新建：`apps/agent-service/src/inkforge_agents/runtime/agent_runtime.py`
- 新建：`apps/agent-service/src/inkforge_agents/runtime/agent_runner.py`
- 新建：`apps/agent-service/src/inkforge_agents/runtime/turn_result.py`
- 新建：`apps/agent-service/src/inkforge_agents/tools/registry.py`
- 新建：`apps/agent-service/src/inkforge_agents/tools/permissions.py`
- 新建：`apps/agent-service/src/inkforge_agents/tools/read.py`
- 新建：`apps/agent-service/src/inkforge_agents/tools/control.py`
- 新建：`apps/agent-service/src/inkforge_agents/tools/proposals.py`
- 新建：`apps/agent-service/tests/runtime/test_agent_runtime.py`
- 新建：`apps/agent-service/tests/runtime/test_agent_runner.py`
- 新建：`apps/agent-service/tests/runtime/test_visible_content.py`
- 新建：`apps/agent-service/tests/tools/test_registry.py`
- 新建：`apps/agent-service/tests/tools/test_permissions.py`
- 新建：`apps/agent-service/tests/tools/test_arguments.py`
- 新建：`apps/agent-service/tests/golden/prompts/lore.txt`
- 新建：`apps/agent-service/tests/golden/prompts/plot.txt`
- 新建：`apps/agent-service/tests/golden/prompts/author.txt`
- 新建：`apps/agent-service/tests/golden/prompts/validator.txt`
- 新建：`apps/agent-service/tests/golden/prompts/editor.txt`

- [ ] **步骤 1：创建失败的基准文本和权限测试**

迁移五个智能体标识、名称、系统提示词不变量、`paragraph_text_with_control_tools`、能力卡片和当前工具暴露矩阵。断言未获授权的智能体绝不会收到或执行控制工具。

- [ ] **步骤 2：创建失败的多轮运行时测试**

迁移可见文本累积、只读工具并行、控制工具排序、无效参数、拒绝未暴露工具、最大轮次数、供应商失败、禁止静默截断和结构化控制事件捕获。

- [ ] **步骤 3：确认失败**

运行：`uv run pytest apps/agent-service/tests/runtime apps/agent-service/tests/tools -v`

预期：失败。

- [ ] **步骤 4：实现声明式定义和唯一工具循环**

智能体运行时是唯一多轮循环。模型运行时仍只负责供应商调用。只读工具携带运行权限调用核心工具网关。控制工具和提案工具生成类型化事件，绝不直接写数据。

- [ ] **步骤 5：确认通过**

运行：`uv run pytest apps/agent-service/tests/runtime apps/agent-service/tests/tools -v`

预期：通过。

- [ ] **步骤 6：提交**

```bash
git add apps/agent-service/src/inkforge_agents/definitions apps/agent-service/src/inkforge_agents/prompts apps/agent-service/src/inkforge_agents/runtime apps/agent-service/src/inkforge_agents/tools apps/agent-service/tests/runtime apps/agent-service/tests/tools apps/agent-service/tests/golden
git commit -m "功能：迁移智能体运行时和工具"
```

### 任务 14：迁移 CreativeOperation 和 LangGraph 工作流

**文件：**
- 新建：`apps/agent-service/src/inkforge_agents/operations/contracts.py`
- 新建：`apps/agent-service/src/inkforge_agents/operations/definitions.py`
- 新建：`apps/agent-service/src/inkforge_agents/operations/router.py`
- 新建：`apps/agent-service/src/inkforge_agents/operations/graph.py`
- 新建：`apps/agent-service/src/inkforge_agents/graph/state.py`
- 新建：`apps/agent-service/src/inkforge_agents/graph/parent_graph.py`
- 新建：`apps/agent-service/src/inkforge_agents/graph/snapshots.py`
- 新建：`apps/agent-service/src/inkforge_agents/graph/context.py`
- 新建：`apps/agent-service/src/inkforge_agents/artifacts/updates.py`
- 新建：`apps/agent-service/src/inkforge_agents/artifacts/diff.py`
- 新建：`apps/agent-service/src/inkforge_agents/artifacts/patch.py`
- 新建：`apps/agent-service/src/inkforge_agents/studio.py`
- 修改：`langgraph.json`
- 新建：`apps/agent-service/tests/operations/test_definitions.py`
- 新建：`apps/agent-service/tests/operations/test_router.py`
- 新建：`apps/agent-service/tests/operations/test_review_routing.py`
- 新建：`apps/agent-service/tests/graph/test_parent_graph.py`
- 新建：`apps/agent-service/tests/graph/test_operation_graph.py`
- 新建：`apps/agent-service/tests/graph/test_snapshots.py`
- 新建：`apps/agent-service/tests/graph/test_context.py`

- [ ] **步骤 1：编写失败的操作定义和路由测试**

迁移全部 CreativeOperation 种类、旧 `@Agent` 映射、主责智能体、复审智能体、草案策略、章节目标解析和低置信度回退。

- [ ] **步骤 2：编写失败的图测试**

覆盖准备、执行、直接响应、草案提交、复审智能体扇出、确定性结论优先级、补丁或重写、最大修订次数、中断载荷、恢复、用户批准、修改或丢弃，以及下一步动作完成。

- [ ] **步骤 3：编写失败的快照测试**

快照结构必须保留当前可恢复字段，并拒绝仅运行时数据。使用版本信封进行序列化，使回滚适配器可以转换为现有 TypeScript 形状。

- [ ] **步骤 4：确认失败**

运行：`uv run pytest apps/agent-service/tests/operations apps/agent-service/tests/graph -v`

预期：失败。

- [ ] **步骤 5：实现 LangGraph Python 状态和图**

使用 StateGraph、条件边、面向复审智能体的 Send、Command 恢复和中断。不得实现平行的 while 或 switch 工作流引擎。所有持久化和工具副作用都通过签名的核心接口服务客户端完成。

- [ ] **步骤 6：确认通过**

运行：`uv run pytest apps/agent-service/tests/operations apps/agent-service/tests/graph -v`

预期：通过。

- [ ] **步骤 7：提交**

```bash
git add apps/agent-service/src/inkforge_agents/operations apps/agent-service/src/inkforge_agents/graph apps/agent-service/src/inkforge_agents/artifacts apps/agent-service/src/inkforge_agents/studio.py apps/agent-service/tests/operations apps/agent-service/tests/graph langgraph.json
git commit -m "功能：迁移 LangGraph 写作工作流"
```

### 任务 15：实现可恢复运行队列和核心服务与智能体服务集成

**文件：**
- 新建：`apps/agent-service/src/inkforge_agents/queue/consumer.py`
- 新建：`apps/agent-service/src/inkforge_agents/queue/repository.py`
- 新建：`apps/agent-service/src/inkforge_agents/queue/recovery.py`
- 新建：`apps/agent-service/src/inkforge_agents/clients/core.py`
- 新建：`apps/agent-service/src/inkforge_agents/jobs/portrait.py`
- 新建：`apps/agent-service/src/inkforge_agents/jobs/rag.py`
- 新建：`apps/agent-service/src/inkforge_agents/jobs/quality.py`
- 新建：`apps/agent-service/src/inkforge_agents/observability/workflow_log.py`
- 新建：`apps/agent-service/src/inkforge_agents/debug/router.py`
- 新建：`apps/core-api/src/inkforge_core/agent_client.py`
- 新建：`apps/core-api/src/inkforge_core/writing/reconciler.py`
- 新建：`apps/core-api/src/inkforge_core/operations/debug_proxy.py`
- 新建：`apps/agent-service/tests/queue/test_consumer.py`
- 新建：`apps/agent-service/tests/integration/test_core_callbacks.py`
- 新建：`apps/agent-service/tests/jobs/test_portrait.py`
- 新建：`apps/agent-service/tests/jobs/test_rag.py`
- 新建：`apps/agent-service/tests/jobs/test_quality.py`
- 新建：`apps/agent-service/tests/observability/test_workflow_log.py`
- 新建：`apps/core-api/tests/operations/test_debug_proxy.py`
- 新建：`apps/core-api/tests/writing/test_reconciler.py`

- [ ] **步骤 1：编写失败的队列和崩溃测试**

覆盖优先级排序、单并发、可见性超时、显式确认、优雅关闭、重复运行幂等、Redis 消息丢失、智能体服务重启、核心接口服务重新提交和过期任务取消。

- [ ] **步骤 2：编写失败的签名集成测试**

运行请求、上下文和工具读取、事件批次、检查点、完成、失败和计费回调必须在声明正确时成功，并在任务、小说、运行、受众或权限范围错误时失败。

- [ ] **步骤 3：编写失败的非写作任务和日志测试**

通过同一个单并发队列迁移画像生成、画像分节重新生成、检索增强生成嵌入和质量检查任务。迁移人工工作流日志契约，即请求、响应和中文状态切换，并验证核心接口服务只有在浏览器授权和签名智能体调试访问后才能查询日志。

- [ ] **步骤 4：确认失败**

运行：`uv run pytest apps/agent-service/tests/queue apps/agent-service/tests/integration apps/agent-service/tests/jobs apps/agent-service/tests/observability apps/core-api/tests/writing/test_reconciler.py apps/core-api/tests/operations/test_debug_proxy.py -v`

预期：失败。

- [ ] **步骤 5：实现 Redis 队列、任务处理器、调试代理和对账**

Redis 只是投递优化。核心接口服务定期扫描现有非终态 WritingTask 记录，并使用相同的确定性幂等键重新提交缺失运行。智能体服务在每次恢复执行前验证核心接口服务状态。

- [ ] **步骤 6：确认通过**

运行：`uv run pytest apps/agent-service/tests/queue apps/agent-service/tests/integration apps/agent-service/tests/jobs apps/agent-service/tests/observability apps/core-api/tests/writing/test_reconciler.py apps/core-api/tests/operations/test_debug_proxy.py -v`

预期：通过。

- [ ] **步骤 7：提交**

```bash
git add apps/agent-service/src/inkforge_agents/queue apps/agent-service/src/inkforge_agents/clients apps/agent-service/src/inkforge_agents/jobs apps/agent-service/src/inkforge_agents/observability apps/agent-service/src/inkforge_agents/debug apps/agent-service/tests/queue apps/agent-service/tests/integration apps/agent-service/tests/jobs apps/agent-service/tests/observability apps/core-api/src/inkforge_core/agent_client.py apps/core-api/src/inkforge_core/writing/reconciler.py apps/core-api/src/inkforge_core/operations/debug_proxy.py apps/core-api/tests/writing/test_reconciler.py apps/core-api/tests/operations/test_debug_proxy.py
git commit -m "功能：集成可恢复智能体运行"
```

### 任务 16：生成 TypeScript 接口客户端并把 Next.js 移入 apps/web

**文件：**
- 新建：`packages/api-client/package.json`
- 新建：`packages/api-client/src/generated/**`
- 新建：`packages/api-client/src/sse.ts`
- 新建：`scripts/export_openapi.py`
- 新建：`scripts/generate_api_client.mjs`
- 移动：把当前 Next.js 配置、`src`、`public`、TypeScript 配置和 CSS 移入 `apps/web/**`
- 修改：根目录 `package.json`
- 修改：`package-lock.json`
- 新建：`apps/web/src/lib/api/server.ts`
- 新建：`apps/web/src/lib/api/browser.ts`
- 新建：`apps/web/src/lib/api/__tests__/sse.test.ts`

- [ ] **步骤 1：编写失败的生成漂移和 SSE 测试**

生成检查导出核心接口服务的 OpenAPI，重新生成客户端文件，并在 `git diff --exit-code packages/api-client/src/generated` 非空时失败。SSE 测试覆盖类型化事件解析、`Last-Event-ID`、心跳、重复序号和重新连接。

- [ ] **步骤 2：确认失败**

运行：`npm run api:check`

预期：失败，因为客户端尚不存在。

- [ ] **步骤 3：添加 npm 工作区和生成客户端**

根脚本必须包含 `dev`、`build`、`lint`、`typecheck`、`api:generate`、`api:check`、`test:web` 和 `test:python`。服务端请求只把会话 Cookie 和请求标识转发给核心接口服务；浏览器请求使用同源凭据。

- [ ] **步骤 4：机械移动 Next.js 应用**

使用 `git mv`，使历史仍可追溯。更新别名和 Next.js 输出路径。移动提交不得改变界面行为。

- [ ] **步骤 5：验证移动后的界面基线**

运行：`npm ci`

运行：`npm run typecheck`

预期：通过。

运行：`npm run build`

预期：在没有 `DATABASE_URL`、模型密钥或 Redis 变量时仍通过。

- [ ] **步骤 6：提交**

```bash
git add package.json package-lock.json apps/web packages/api-client scripts/export_openapi.py scripts/generate_api_client.mjs
git commit -m "重构：移动 Next.js 应用并生成接口客户端"
```

### 任务 17：替换全部服务器操作、路由处理器和服务端 Prisma 查询

**文件：**
- 修改：`apps/web/src/app/page.tsx`
- 修改：`apps/web/src/app/dashboard/page.tsx`
- 修改：`apps/web/src/app/workspace/[novelId]/page.tsx`
- 修改：`apps/web/src/app/styles/page.tsx`
- 修改：`apps/web/src/app/billing/page.tsx`
- 修改：`apps/web/src/app/login/page.tsx`
- 修改：`apps/web/src/app/layout.tsx`
- 修改：`apps/web/src/features/auth/login-form.tsx`
- 修改：`apps/web/src/features/auth/user-menu.tsx`
- 修改：`apps/web/src/features/projects/create-novel-modal.tsx`
- 修改：`apps/web/src/features/projects/novel-list-client.tsx`
- 修改：`apps/web/src/features/chapters/chapter-list.tsx`
- 修改：`apps/web/src/features/editor/chapter-editor.tsx`
- 修改：`apps/web/src/features/lore/lore-panel.tsx`
- 修改：`apps/web/src/features/outline/outline-panel.tsx`
- 修改：`apps/web/src/features/progress/progress-panel.tsx`
- 修改：`apps/web/src/features/references/reference-panel.tsx`
- 修改：`apps/web/src/features/styles/style-library-panel.tsx`
- 修改：`apps/web/src/features/styles/style-panel.tsx`
- 修改：`apps/web/src/features/workspace/inspector-tabs.tsx`
- 修改：`apps/web/src/features/workspace/sidebar-tabs.tsx`
- 修改：`apps/web/src/features/writing/writing-conversation.tsx`
- 修改：`apps/web/src/features/debug/workflow-events-inspector.tsx`
- 修改：`apps/web/src/middleware.ts` 或 `apps/web/src/proxy.ts`
- 删除：已迁移的 `apps/web/src/app/actions.ts`
- 删除：已迁移的业务 `apps/web/src/app/api/**`
- 删除：`apps/web/src/shared/db/**`
- 新建：`apps/web/src/lib/api/__tests__/action-mapping.test.ts`
- 新建：`tests/architecture/legacy-backend-map.json`

- [ ] **步骤 1：创建完整且失败的操作映射**

列出全部 50 个导出操作和所有当前接口方法，每项都精确对应一个替代 HTTP 方法、路径和前端调用方。测试解析旧清单，并在条目缺失或重复时失败。

- [ ] **步骤 2：替换页面读取**

仪表盘、工作区、文风和计费服务器组件调用核心接口服务聚合接口。对 401 使用登录重定向，对 403 和 404 使用稳定界面错误。任何页面都不得导入 Prisma 类型。

- [ ] **步骤 3：逐领域替换变更调用**

迁移认证、项目和章节、设定、大纲和进度、参考资料、文风、写作设置、质量、会话和消息、草案及计费。保留 1.2 秒自动保存、交互状态和中文消息。

- [ ] **步骤 4：替换写作 SSE 和恢复逻辑**

前端只连接核心接口服务 SSE，保留现有事件语义并增加序号和重放处理。当前任务、最近任务和草案恢复继续使用显式会话绑定。

- [ ] **步骤 5：删除 Next.js 后端入口并验证架构**

运行：

```bash
rg -n '@/shared/db/prisma|@prisma/client|DATABASE_URL|"use server"|from "openai"|@langchain' apps/web
```

预期：没有后端匹配项。仅框架使用且范围严格受限的匹配项必须记录并测试；禁止业务匹配项。

- [ ] **步骤 6：在不改变用户体验的前提下修复现有代码检查失败**

把渲染期间创建的组件移到模块作用域，用带键组件边界或派生状态替代状态重置副作用，并移除渲染期间的引用访问。为每项行为变更添加聚焦的 React 测试。

- [ ] **步骤 7：验证前端**

运行：`npm run typecheck`

运行：`npm run lint`

运行：`npm run test:web`

运行：`npm run build`

预期：全部通过，且没有后端文件系统追踪造成的警告。

- [ ] **步骤 8：提交**

```bash
git add apps/web packages/api-client tests/architecture/legacy-backend-map.json
git commit -m "重构：把 Next.js 改为纯前端应用"
```

### 任务 18：添加生产 Docker 镜像、编排和 Nginx

**文件：**
- 新建：`infra/docker/core-api.Dockerfile`
- 新建：`infra/docker/agent-service.Dockerfile`
- 新建：`infra/docker/web.Dockerfile`
- 新建：`infra/nginx/nginx.conf`
- 新建：`infra/compose.yaml`
- 新建：`infra/compose.test.yaml`
- 新建：`infra/redis/redis.conf`
- 新建：`.env.example`
- 新建：`scripts/compose_smoke.ps1`
- 新建：`scripts/compose_smoke.sh`
- 新建：`tests/architecture/test_compose_security.py`

- [ ] **步骤 1：编写失败的编排策略测试**

解析编排文件并断言只有 Nginx 发布端口；智能体服务没有 `DATABASE_URL` 且不加入 `data_net`；PostgreSQL 没有初始化脚本；所有应用容器都使用非根用户，具有健康检查和资源限制；Redis 最大内存为 64 MB 且不启用 AOF。

- [ ] **步骤 2：确认失败**

运行：`uv run pytest tests/architecture/test_compose_security.py -v`

预期：失败。

- [ ] **步骤 3：实现多阶段非根用户镜像**

Web 镜像只包含 Next.js 独立输出。Python 运行时镜像包含锁定的 wheel 包和应用包，不包含 uv 缓存或测试文件。容器使用只读根文件系统、显式临时文件系统和可写数据及日志卷。

- [ ] **步骤 4：实现网络、密钥和资源限制**

使用 `public_net`、`agent_net` 和内部 `data_net`；内存上限与规格一致。挂载现有 PostgreSQL 数据卷，不使用初始化 SQL。Nginx 为 SSE 禁用代理缓冲并阻止 `/internal/`。

- [ ] **步骤 5：验证编排配置和健康状态**

运行：`docker compose -f infra/compose.yaml config`

预期：配置有效，插值后不存在缺失的必需密钥。

运行：`uv run pytest tests/architecture/test_compose_security.py -v`

预期：通过。

运行：`docker compose -f infra/compose.test.yaml up --build --wait`

预期：每个服务都健康。

- [ ] **步骤 6：运行冒烟验证并关闭**

运行：`pwsh scripts/compose_smoke.ps1`

预期：公开页面、模拟认证流程、核心接口服务就绪、智能体服务就绪、SSE 模拟运行和数据库指纹检查均通过。

运行：`docker compose -f infra/compose.test.yaml down -v`

- [ ] **步骤 7：提交**

```bash
git add infra .env.example scripts/compose_smoke.ps1 scripts/compose_smoke.sh tests/architecture/test_compose_security.py
git commit -m "运维：添加生产 Docker Compose 部署"
```

### 任务 19：删除 TypeScript 后端并更新权威文档

**文件：**
- 删除：前端移动后的旧 `src/agents/**`
- 删除：已由 OpenAPI 替代的旧服务端专用共享库和契约
- 删除：证明数据库结构契约后删除 `prisma/**` 运行时工具，同时把最终数据库结构归档为历史证据
- 修改：`package.json` 和 `package-lock.json`
- 修改：`AGENTS.md`
- 修改：`DOCS.md`
- 替换：用 `apps/agent-service/AGENTS.md` 替换 `src/agents/AGENTS.md`
- 修改：`docs/requirements/00-overview.md`
- 修改：`docs/requirements/01-projects-and-chapters.md`
- 修改：`docs/requirements/02-creative-knowledge-base.md`
- 修改：`docs/requirements/03-ai-writing-and-agents.md`
- 修改：`docs/requirements/04-review-quality-and-workflow.md`
- 修改：`docs/requirements/05-auth-billing-and-ops.md`
- 修改：`docs/LANGGRAPH_STUDIO.md`
- 修改：`docs/WORKFLOW_EVENT_LOG_FORMAT.md`
- 修改：`README.md`

- [ ] **步骤 1：编写失败的禁用后端扫描**

创建 `tests/architecture/test_no_typescript_backend.py`，拒绝 `apps/web` 或 TypeScript 运行时依赖中任何位置出现 Prisma、LangGraph.js、LangChain.js、Node OpenAI SDK、业务路由处理器、业务服务器操作和数据库或模型密钥。

- [ ] **步骤 2：确认失败**

运行：`uv run pytest tests/architecture/test_no_typescript_backend.py -v`

预期：只要旧后端文件或依赖仍然存在就失败。

- [ ] **步骤 3：删除已迁移代码和依赖**

只保留前端安全的 TypeScript 辅助函数和生成契约。把最终 Prisma 数据库结构归档到 `docs/archive/database/`，并在文件头注明它是历史证据而非迁移来源。生产 Python 继续使用 `schema-contract.json`。

- [ ] **步骤 4：更新当前权威文档和需求文档**

记录核心接口服务与智能体服务边界、命令、服务 JWT、智能体服务不得访问数据库规则、编排部署、恢复和日志。删除把 Prisma 或 LangGraph.js 视为当前运行时事实的说法。

- [ ] **步骤 5：确认通过**

运行：`uv run pytest tests/architecture/test_no_typescript_backend.py -v`

预期：通过。

运行：`npm ci`

运行：`npm run typecheck`

运行：`npm run lint`

运行：`npm run build`

预期：通过。

运行：`uv sync --frozen --all-packages --group dev`

运行：`uv run ruff check .`

运行：`uv run mypy apps/core-api/src apps/agent-service/src packages/service-contracts/src packages/service-auth/src`

运行：`uv run pytest`

预期：通过。

- [ ] **步骤 6：提交**

```bash
git add -A
git commit -m "重构：移除旧 Next.js 后端"
```

### 任务 20：执行生产验收、恢复、备份和回滚证明

**文件：**
- 新建：`tests/e2e/auth.spec.ts`
- 新建：`tests/e2e/project-editor.spec.ts`
- 新建：`tests/e2e/knowledge-style.spec.ts`
- 新建：`tests/e2e/writing-artifact.spec.ts`
- 新建：`tests/e2e/quality-billing.spec.ts`
- 新建：`scripts/backup.sh`
- 新建：`scripts/restore_verify.sh`
- 新建：`scripts/schema_fingerprint.sh`
- 新建：`scripts/recovery_drill.sh`
- 新建：`scripts/rollback_drill.sh`
- 新建：`docs/PYTHON_BACKEND_CUTOVER.md`
- 新建：`docs/audits/2026-07-10-python-backend-acceptance.md`

- [ ] **步骤 1：实现 Playwright 端到端测试**

覆盖注册和登录、仪表盘、创建小说、章节自动保存、设定增删改查、大纲层级、参考资料上传、文风上传和模拟画像任务、写作会话、智能体模拟流、ReviewArtifact 批准、丢弃和修改、质量检查及计费汇总。

- [ ] **步骤 2：运行完整静态和单元测试门槛**

运行：`npm run api:check`

运行：`npm run typecheck`

运行：`npm run lint`

运行：`npm run test:web`

运行：`npm run build`

运行：`uv run ruff check .`

运行：`uv run mypy apps/core-api/src apps/agent-service/src packages/service-contracts/src packages/service-auth/src`

运行：`uv run pytest --cov=inkforge_core --cov=inkforge_agents --cov=inkforge_contracts --cov=inkforge_service_auth --cov-report=term-missing`

预期：全部通过；变更的 Python 业务模块具有有意义的分支覆盖率，并且不存在未测试的关键授权或写入路径。

- [ ] **步骤 3：运行完整编排端到端测试**

运行：`docker compose -f infra/compose.test.yaml up --build --wait`

运行：`npm run test:e2e`

预期：全部主要工作流通过 Nginx 后均通过测试。

- [ ] **步骤 4：证明重启恢复能力**

启动一次模拟智能体运行，在模型步骤中停止智能体服务，重新启动并验证任务从最后一个稳定检查点恢复。删除 Redis 运行时键，并验证核心接口服务对账器重新提交现有非终态 WritingTask，且不产生重复草案或扣费。

- [ ] **步骤 5：证明数据库和上传文件备份恢复能力**

对测试部署运行备份并记录校验和，恢复到单独的验证卷，再比较数据库结构指纹和行数。生产脚本绝不能覆盖正在运行的数据库进行恢复。

- [ ] **步骤 6：证明回滚兼容性**

使用预发布副本，通过 Python 写入代表性数据，停止新服务栈，以只读方式启动归档的旧镜像，并验证用户 Cookie、标识、bcrypt、草案载荷、图快照适配器和上传路径可读。记录任何有意排除在回滚之外的任务状态，并在发布前解决。

- [ ] **步骤 7：运行 2 核 2 GB 稳定性压测**

应用编排内存限制和处理器配额，执行混合增删改查并保持同一时间只有一次智能体运行，持续 30 分钟，记录内存溢出次数、常驻内存峰值、数据库连接数、任务丢失、第 95 百分位增删改查延迟、SSE 首事件延迟和运行接受延迟。

- [ ] **步骤 8：完成验收审计**

为规格中的每条验收项链接精确的测试输出、命令输出、文件扫描或运行时证据。缺失或间接证据都视为失败，不能写成“可能已完成”。

- [ ] **步骤 9：提交**

```bash
git add tests/e2e scripts docs/PYTHON_BACKEND_CUTOVER.md docs/audits/2026-07-10-python-backend-acceptance.md
git commit -m "测试：证明 Python 后端生产就绪"
```

## 最终完成门槛

- [ ] 任务 1 至 20 的每个勾选项都已完成。
- [ ] 不存在未提交的生成文件或密钥。
- [ ] 不可变数据库指纹没有变化。
- [ ] 前端不包含后端实现。
- [ ] 智能体服务不存在数据库访问路径。
- [ ] 所有静态、单元、集成、端到端、重启、备份、回滚和稳定性压测证据均通过。
- [ ] 权威文档和当前需求文档描述 Python 架构。
- [ ] 验收审计把每项规格要求映射到直接证据。
- [ ] 只有全部检查通过后，才按照 `DOCS.md` 归档本计划并把活动目标标记为完成。
