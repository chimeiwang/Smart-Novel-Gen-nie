# Python Backend Rewrite Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace every Next.js backend capability with a production FastAPI Core API and a database-isolated Python Agent Service while preserving the existing PostgreSQL schema, user workflows, SEO frontend, and one-command Docker Compose deployment.

**Architecture:** Build the Python services alongside the current TypeScript implementation as a behavior oracle, migrate the frontend only after Python contract parity is proven, then delete the old backend before release. Core API exclusively owns PostgreSQL, browser auth, business rules, artifacts, billing, and SSE; Agent Service owns LangGraph and model/tool execution and communicates with Core through signed versioned HTTP contracts.

**Tech Stack:** Python 3.12, uv, FastAPI, Pydantic v2, SQLAlchemy 2 async, asyncpg, pgvector, Redis asyncio, PyJWT/Ed25519, bcrypt, LangGraph Python, httpx, pytest, Next.js 16, React 19, OpenAPI-generated TypeScript, Nginx, Docker Compose.

**Authoritative spec:** `docs/specs/2026-07-10-python-backend-rewrite.md`

**Lifecycle:** This plan is current until every task and final acceptance gate is complete. After delivery it moves to `docs/archive/implementation-plans/` and the implemented facts move into repository authority and requirements documents.

---

## Delivery Order

1. Foundation and immutable database contract.
2. Core API domains and all former Server Action/API behavior.
3. Agent Service, Core tool gateway, state recovery, and billing grant flow.
4. Next.js move and generated-client migration.
5. Docker production topology, old backend deletion, and cutover proof.

No phase is a releasable partial product. The branch is releasable only after Task 20.

### Task 1: Establish the Python and JavaScript workspaces

**Files:**
- Create: `.python-version`
- Create: `pyproject.toml`
- Create: `tests/architecture/test_repository_layout.py`
- Create: `apps/core-api/pyproject.toml`
- Create: `apps/core-api/src/inkforge_core/__init__.py`
- Create: `apps/agent-service/pyproject.toml`
- Create: `apps/agent-service/src/inkforge_agents/__init__.py`
- Create: `packages/service-contracts/pyproject.toml`
- Create: `packages/service-contracts/src/inkforge_contracts/__init__.py`
- Modify: `.gitignore`

- [ ] **Step 1: Install and pin the local Python toolchain**

Run: `python -m pip install --user "uv>=0.8,<1"`

Run: `uv python install 3.12`

Run: `uv run --python 3.12 python --version`

Expected: Python 3.12.x. Do not use the machine's Python 3.13 for the lock or application environment.

- [ ] **Step 2: Write the failing repository-layout test**

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

- [ ] **Step 3: Run the test and verify RED**

Run: `uv run --python 3.12 --with pytest pytest tests/architecture/test_repository_layout.py -v`

Expected: FAIL because the workspace members do not exist.

- [ ] **Step 4: Add the uv workspace and package manifests**

Root `pyproject.toml`:

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

Each service manifest must use a `src` package and the contracts workspace dependency. Core dependencies include FastAPI, SQLAlchemy, asyncpg, pgvector, Redis, PyJWT, cryptography, bcrypt, httpx, structlog, orjson, python-multipart and pydantic-settings. Agent dependencies include FastAPI, Redis, PyJWT, cryptography, httpx, structlog, orjson, LangGraph, LangChain Core and LangChain OpenAI.

- [ ] **Step 5: Lock dependencies and verify GREEN**

Run: `uv lock`

Expected: `uv.lock` is created with Python 3.12-compatible packages.

Run: `uv sync --all-packages --group dev`

Expected: all workspace packages install successfully.

Run: `uv run pytest tests/architecture/test_repository_layout.py -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add .python-version pyproject.toml uv.lock .gitignore tests/architecture apps/core-api/pyproject.toml apps/core-api/src apps/agent-service/pyproject.toml apps/agent-service/src packages/service-contracts/pyproject.toml packages/service-contracts/src
git commit -m "build: establish Python service workspace"
```

### Task 2: Define versioned Core-Agent service contracts

**Files:**
- Create: `packages/service-contracts/src/inkforge_contracts/version.py`
- Create: `packages/service-contracts/src/inkforge_contracts/identity.py`
- Create: `packages/service-contracts/src/inkforge_contracts/runs.py`
- Create: `packages/service-contracts/src/inkforge_contracts/events.py`
- Create: `packages/service-contracts/src/inkforge_contracts/tools.py`
- Create: `packages/service-contracts/tests/test_run_contracts.py`
- Create: `packages/service-contracts/tests/test_event_contracts.py`

- [ ] **Step 1: Write failing strict-contract tests**

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

- [ ] **Step 2: Run and verify RED**

Run: `uv run pytest packages/service-contracts/tests -v`

Expected: collection FAIL because contract modules do not exist.

- [ ] **Step 3: Implement strict Pydantic contracts**

All request models use `ConfigDict(extra="forbid", populate_by_name=True)`. Define:

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

Define exact `CreativeOperationKind`, five Agent IDs, tool request/result envelopes, checkpoint callback, completion callback and failure callback from the current TypeScript contracts. Do not include ORM models or repositories.

- [ ] **Step 4: Verify contracts and type quality**

Run: `uv run pytest packages/service-contracts/tests -v`

Expected: PASS.

Run: `uv run mypy packages/service-contracts/src`

Expected: no errors.

- [ ] **Step 5: Commit**

```bash
git add packages/service-contracts
git commit -m "feat: define Core Agent service protocol"
```

### Task 3: Bootstrap Core API with stable errors and health endpoints

**Files:**
- Create: `apps/core-api/src/inkforge_core/config.py`
- Create: `apps/core-api/src/inkforge_core/app.py`
- Create: `apps/core-api/src/inkforge_core/errors.py`
- Create: `apps/core-api/src/inkforge_core/http/request_id.py`
- Create: `apps/core-api/src/inkforge_core/operations/router.py`
- Create: `apps/core-api/tests/test_health.py`
- Create: `apps/core-api/tests/test_errors.py`

- [ ] **Step 1: Write failing API tests**

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

- [ ] **Step 2: Run and verify RED**

Run: `uv run pytest apps/core-api/tests/test_health.py apps/core-api/tests/test_errors.py -v`

Expected: FAIL because the Core app does not exist.

- [ ] **Step 3: Implement the application factory**

`create_app(testing=False)` must register request IDs, stable exception handlers and `/api/v1/health/live`. Settings must reject production startup when `JWT_SECRET`, service-key paths or database URL are missing. Testing mode accepts explicit dependency overrides and never reads developer secrets.

- [ ] **Step 4: Verify GREEN and formatting**

Run: `uv run pytest apps/core-api/tests/test_health.py apps/core-api/tests/test_errors.py -v`

Expected: PASS.

Run: `uv run ruff check apps/core-api/src apps/core-api/tests`

Expected: no errors.

- [ ] **Step 5: Commit**

```bash
git add apps/core-api
git commit -m "feat: bootstrap Core API"
```

### Task 4: Freeze and verify the existing PostgreSQL schema

**Files:**
- Create: `apps/core-api/src/inkforge_core/db/base.py`
- Create: `apps/core-api/src/inkforge_core/db/models.py`
- Create: `apps/core-api/src/inkforge_core/db/session.py`
- Create: `apps/core-api/src/inkforge_core/db/schema_guard.py`
- Create: `apps/core-api/src/inkforge_core/db/schema-contract.json`
- Create: `apps/core-api/tests/db/test_model_metadata.py`
- Create: `apps/core-api/tests/db/test_schema_guard.py`
- Create: `scripts/export_schema_contract.py`

- [ ] **Step 1: Write failing metadata tests for the immutable schema**

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

Prisma currently contains 40 concrete tables. The test uses current `schema.prisma` as authority and prevents the plan from preserving a stale count.

- [ ] **Step 2: Run and verify RED**

Run: `uv run pytest apps/core-api/tests/db/test_model_metadata.py -v`

Expected: FAIL because ORM mappings do not exist.

- [ ] **Step 3: Implement exact SQLAlchemy mappings**

Map every table, quoted column, relationship, PostgreSQL enum, BigInt and vector field from `prisma/schema.prisma`. Use application-generated string IDs and timezone-aware UTC datetimes. Do not call `create_all`, import Alembic or add DDL event listeners.

- [ ] **Step 4: Export the read-only schema contract**

`scripts/export_schema_contract.py` must require `--database-url`, query `information_schema` and `pg_catalog`, print the source server identity, and write only when `--output` is explicit. It must never execute DDL.

Run against the current database in read-only mode:

```bash
uv run python scripts/export_schema_contract.py --database-url "$DATABASE_URL" --output apps/core-api/src/inkforge_core/db/schema-contract.json
```

Expected: contract includes tables, columns, types, nullability, defaults, keys, indexes, enums and vector dimensions.

- [ ] **Step 5: Verify guard success and drift rejection**

Tests use a fake inspector snapshot for exact match and one changed nullable/type/index value. Exact match returns ready; any drift returns a field-level diff and readiness false.

Run: `uv run pytest apps/core-api/tests/db -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add apps/core-api/src/inkforge_core/db apps/core-api/tests/db scripts/export_schema_contract.py
git commit -m "feat: map and guard immutable PostgreSQL schema"
```

### Task 5: Implement signed service identity and replay protection

**Files:**
- Create: `apps/core-api/src/inkforge_core/service_auth.py`
- Create: `apps/agent-service/src/inkforge_agents/service_auth.py`
- Create: `packages/service-contracts/src/inkforge_contracts/jwt_claims.py`
- Create: `apps/core-api/tests/test_service_auth.py`
- Create: `apps/agent-service/tests/test_service_auth.py`
- Create: `scripts/generate_service_keys.py`

- [ ] **Step 1: Write failing trust-boundary tests**

Test that a valid Ed25519 token succeeds only for the expected `aud`, scope, task, run and novel. Test expired tokens, wrong issuer, wrong audience, missing scope, reused `jti`, mismatched body digest and tokens older than the allowed clock skew.

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

- [ ] **Step 2: Run and verify RED**

Run: `uv run pytest apps/core-api/tests/test_service_auth.py apps/agent-service/tests/test_service_auth.py -v`

Expected: FAIL because service auth is missing.

- [ ] **Step 3: Implement key loading, signing and verification**

Private keys load only from configured files. Claims expire after 120 seconds. Redis replay protection is required for internal write scopes and optional for idempotent reads. `Idempotency-Key`, `X-InkForge-Timestamp` and `X-InkForge-Body-SHA256` are validated before request models reach business services.

- [ ] **Step 4: Verify GREEN**

Run: `uv run pytest apps/core-api/tests/test_service_auth.py apps/agent-service/tests/test_service_auth.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/core-api/src/inkforge_core/service_auth.py apps/core-api/tests/test_service_auth.py apps/agent-service/src/inkforge_agents/service_auth.py apps/agent-service/tests/test_service_auth.py packages/service-contracts scripts/generate_service_keys.py
git commit -m "feat: secure Core Agent service calls"
```

### Task 6: Migrate browser authentication and signup billing

**Files:**
- Create: `apps/core-api/src/inkforge_core/auth/router.py`
- Create: `apps/core-api/src/inkforge_core/auth/schemas.py`
- Create: `apps/core-api/src/inkforge_core/auth/service.py`
- Create: `apps/core-api/src/inkforge_core/auth/repository.py`
- Create: `apps/core-api/src/inkforge_core/auth/dependencies.py`
- Create: `apps/core-api/tests/auth/test_auth_api.py`
- Create: `apps/core-api/tests/auth/test_legacy_cookie.py`

- [ ] **Step 1: Write failing parity tests**

Cover username normalization and regex, password minimum length, duplicate username, bcryptjs hash verification, HS256 cookie compatibility, 30-day expiry, secure production cookie, uniform invalid-login errors, signup bonus balance and CreditLedger transaction.

- [ ] **Step 2: Verify RED**

Run: `uv run pytest apps/core-api/tests/auth -v`

Expected: FAIL because auth routes do not exist.

- [ ] **Step 3: Implement auth endpoints**

Implement `/api/v1/auth/register`, `/login`, `/logout`, `/me`. Preserve `inkforge-token`, HS256 and `sub=userId`. Production refuses the old default secret. Register creates User, increments `creditBalanceMicros` by `1_000_000_000`, writes `signup_bonus`, and sets the Cookie in one successful request.

- [ ] **Step 4: Verify GREEN and unauthorized resource behavior**

Run: `uv run pytest apps/core-api/tests/auth -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/core-api/src/inkforge_core/auth apps/core-api/tests/auth
git commit -m "feat: migrate authentication to Core API"
```

### Task 7: Migrate projects, chapters, workspace aggregation and quality state

**Files:**
- Create: `apps/core-api/src/inkforge_core/novels/router.py`
- Create: `apps/core-api/src/inkforge_core/novels/schemas.py`
- Create: `apps/core-api/src/inkforge_core/novels/service.py`
- Create: `apps/core-api/src/inkforge_core/novels/repository.py`
- Create: `apps/core-api/src/inkforge_core/chapters/router.py`
- Create: `apps/core-api/src/inkforge_core/chapters/schemas.py`
- Create: `apps/core-api/src/inkforge_core/chapters/service.py`
- Create: `apps/core-api/src/inkforge_core/chapters/repository.py`
- Create: `apps/core-api/src/inkforge_core/quality/router.py`
- Create: `apps/core-api/src/inkforge_core/quality/schemas.py`
- Create: `apps/core-api/src/inkforge_core/quality/service.py`
- Create: `apps/core-api/src/inkforge_core/quality/repository.py`
- Create: `apps/core-api/tests/novels/test_novel_api.py`
- Create: `apps/core-api/tests/chapters/test_chapter_api.py`
- Create: `apps/core-api/tests/quality/test_quality_state.py`

- [ ] **Step 1: Write failing business-rule tests**

Cover novel creation with first chapter, empty outline, plot progress and WritingBible profile; dashboard order; chapter numbering; title fallback; exact content saving; 1.2-second autosave remains a frontend rule; chapter status transitions; default consistency check; completion blocked until completed/skipped; and cross-user denial.

- [ ] **Step 2: Verify RED**

Run: `uv run pytest apps/core-api/tests/novels apps/core-api/tests/chapters apps/core-api/tests/quality -v`

Expected: FAIL because routes are missing.

- [ ] **Step 3: Implement transactional services and aggregate endpoints**

Implement `/api/v1/dashboard`, `/api/v1/novels`, `/api/v1/novels/{id}/workspace`, chapter create/update/status, chapter progress, quality status and quality run submission. Workspace response must contain every field currently loaded by `src/app/workspace/[novelId]/page.tsx` without silent list limits.

- [ ] **Step 4: Verify GREEN**

Run: `uv run pytest apps/core-api/tests/novels apps/core-api/tests/chapters apps/core-api/tests/quality -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/core-api/src/inkforge_core/novels apps/core-api/src/inkforge_core/chapters apps/core-api/src/inkforge_core/quality apps/core-api/tests/novels apps/core-api/tests/chapters apps/core-api/tests/quality
git commit -m "feat: migrate project and chapter domains"
```

### Task 8: Migrate lore, outline, progress and reference domains

**Files:**
- Create: `apps/core-api/src/inkforge_core/lore/router.py`
- Create: `apps/core-api/src/inkforge_core/lore/schemas.py`
- Create: `apps/core-api/src/inkforge_core/lore/service.py`
- Create: `apps/core-api/src/inkforge_core/lore/repository.py`
- Create: `apps/core-api/src/inkforge_core/outlines/router.py`
- Create: `apps/core-api/src/inkforge_core/outlines/schemas.py`
- Create: `apps/core-api/src/inkforge_core/outlines/service.py`
- Create: `apps/core-api/src/inkforge_core/outlines/repository.py`
- Create: `apps/core-api/src/inkforge_core/outlines/validation.py`
- Create: `apps/core-api/src/inkforge_core/references/router.py`
- Create: `apps/core-api/src/inkforge_core/references/schemas.py`
- Create: `apps/core-api/src/inkforge_core/references/service.py`
- Create: `apps/core-api/src/inkforge_core/references/repository.py`
- Create: `apps/core-api/src/inkforge_core/references/rag.py`
- Create: `apps/core-api/tests/lore/test_lore_api.py`
- Create: `apps/core-api/tests/outlines/test_outline_api.py`
- Create: `apps/core-api/tests/references/test_reference_api.py`
- Create: `apps/core-api/tests/references/test_rag.py`

- [ ] **Step 1: Write failing domain parity tests**

Cover every create/update/delete action for Character, CharacterExperience, CharacterRelation, Item, Location, Faction and Glossary; StoryBackground, WorldSetting, WritingBible, story/chapter progress; Outline text, three-level node hierarchy, child compatibility, chapter-range containment and sibling non-overlap; PlotProgress, Foreshadowing and ReferenceMaterial.

- [ ] **Step 2: Add lossless RAG tests**

Port the current chunking tests and assert `"".join(chunks with separators removed)` retains all source characters. Test disabled embedding, successful vector insert, failed indexing status and novel-scoped cosine search.

- [ ] **Step 3: Verify RED**

Run: `uv run pytest apps/core-api/tests/lore apps/core-api/tests/outlines apps/core-api/tests/references -v`

Expected: FAIL because domains do not exist.

- [ ] **Step 4: Implement repositories and services**

Use resource-scoped update/delete statements and assert affected row count. Preserve exact enum values, all optional fields and current Chinese errors. RAG raw SQL binds every value and never interpolates vector/user input into SQL text.

- [ ] **Step 5: Verify GREEN**

Run: `uv run pytest apps/core-api/tests/lore apps/core-api/tests/outlines apps/core-api/tests/references -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add apps/core-api/src/inkforge_core/lore apps/core-api/src/inkforge_core/outlines apps/core-api/src/inkforge_core/references apps/core-api/tests/lore apps/core-api/tests/outlines apps/core-api/tests/references
git commit -m "feat: migrate creative knowledge domains"
```

### Task 9: Migrate style files and portrait task state

**Files:**
- Create: `apps/core-api/src/inkforge_core/styles/router.py`
- Create: `apps/core-api/src/inkforge_core/styles/schemas.py`
- Create: `apps/core-api/src/inkforge_core/styles/service.py`
- Create: `apps/core-api/src/inkforge_core/styles/repository.py`
- Create: `apps/core-api/src/inkforge_core/styles/storage.py`
- Create: `apps/core-api/tests/styles/test_style_api.py`
- Create: `apps/core-api/tests/styles/test_storage.py`

- [ ] **Step 1: Write failing storage and API tests**

Cover `.txt` only, non-empty content, 50 MB rejection, Unicode filename sanitization, traversal rejection, symlink escape rejection, character counting without whitespace, legacy Windows filepath resolution, file deletion, style cascade behavior, portrait task creation/status, section update and application to a novel.

- [ ] **Step 2: Verify RED**

Run: `uv run pytest apps/core-api/tests/styles -v`

Expected: FAIL.

- [ ] **Step 3: Implement storage root and style services**

All writes resolve below `/data/uploads`. Store rollback-compatible `/app/uploads/styles/...` paths while resolving existing Windows paths by their `uploads/styles/` suffix. Portrait generation is submitted to Agent Service; Core alone updates task and style rows from signed callbacks.

- [ ] **Step 4: Verify GREEN**

Run: `uv run pytest apps/core-api/tests/styles -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/core-api/src/inkforge_core/styles apps/core-api/tests/styles
git commit -m "feat: migrate writing style workflows"
```

### Task 10: Migrate billing and idempotent model grants

**Files:**
- Create: `apps/core-api/src/inkforge_core/billing/router.py`
- Create: `apps/core-api/src/inkforge_core/billing/schemas.py`
- Create: `apps/core-api/src/inkforge_core/billing/service.py`
- Create: `apps/core-api/src/inkforge_core/billing/repository.py`
- Create: `apps/core-api/src/inkforge_core/billing/pricing.py`
- Create: `apps/core-api/tests/billing/test_pricing.py`
- Create: `apps/core-api/tests/billing/test_model_grants.py`
- Create: `apps/core-api/tests/billing/test_usage_charge.py`

- [ ] **Step 1: Port failing pricing tests**

Preserve credit micros conversion, DeepSeek flash input/cached/output rates, prompt estimation, minimum output budget, insufficient balance errors and display formatting.

- [ ] **Step 2: Add concurrency and retry tests**

Two simultaneous usage callbacks with the same `requestId` must produce one debit, one `ai_charge` ledger row and one TokenUsage record. Use a PostgreSQL advisory transaction lock and existing `CreditLedger.requestId`, without a schema change.

- [ ] **Step 3: Verify RED**

Run: `uv run pytest apps/core-api/tests/billing -v`

Expected: FAIL.

- [ ] **Step 4: Implement grants, charges and summary endpoints**

Implement internal preflight/usage endpoints scoped to task/run tokens and public `/api/v1/billing/summary` and `/usage`. Fake provider grants carry `billable=false` and never write usage.

- [ ] **Step 5: Verify GREEN**

Run: `uv run pytest apps/core-api/tests/billing -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add apps/core-api/src/inkforge_core/billing apps/core-api/tests/billing
git commit -m "feat: migrate idempotent AI billing"
```

### Task 11: Migrate writing sessions, messages, tasks and ReviewArtifact

**Files:**
- Create: `apps/core-api/src/inkforge_core/writing/router.py`
- Create: `apps/core-api/src/inkforge_core/writing/schemas.py`
- Create: `apps/core-api/src/inkforge_core/writing/service.py`
- Create: `apps/core-api/src/inkforge_core/writing/repository.py`
- Create: `apps/core-api/src/inkforge_core/writing/sse.py`
- Create: `apps/core-api/src/inkforge_core/writing/recovery.py`
- Create: `apps/core-api/src/inkforge_core/writing/context.py`
- Create: `apps/core-api/src/inkforge_core/writing/tool_gateway.py`
- Create: `apps/core-api/src/inkforge_core/reviews/router.py`
- Create: `apps/core-api/src/inkforge_core/reviews/schemas.py`
- Create: `apps/core-api/src/inkforge_core/reviews/service.py`
- Create: `apps/core-api/src/inkforge_core/reviews/repository.py`
- Create: `apps/core-api/src/inkforge_core/reviews/apply.py`
- Create: `apps/core-api/src/inkforge_core/reviews/diff.py`
- Create: `apps/core-api/src/inkforge_core/reviews/updates.py`
- Create: `apps/core-api/tests/writing/test_sessions.py`
- Create: `apps/core-api/tests/writing/test_recovery.py`
- Create: `apps/core-api/tests/writing/test_sse.py`
- Create: `apps/core-api/tests/writing/test_context.py`
- Create: `apps/core-api/tests/writing/test_tool_gateway.py`
- Create: `apps/core-api/tests/reviews/test_artifact_lifecycle.py`
- Create: `apps/core-api/tests/reviews/test_artifact_apply.py`

- [ ] **Step 1: Write failing session and recovery tests**

Port explicit session binding, currentTask/lastTask separation, message persistence, completed/error non-resume behavior, malformed snapshot rejection, runtime-only field exclusion and task ownership tests.

- [ ] **Step 2: Write failing ReviewArtifact tests**

Port artifact kinds/statuses, revision uniqueness, evaluation pass/revise/block, patch safety, hard discard, partial agent_updates selection, chapter target resolution, beat-plan application and the prohibition on revision_brief formal writes.

- [ ] **Step 3: Write failing SSE replay tests**

Events have monotonic IDs, heartbeat, typed payload and replay from `Last-Event-ID`. Duplicate callbacks are ignored; a sequence gap returns a recoverable stream error and triggers status reconciliation.

- [ ] **Step 4: Write failing context and Tool Gateway tests**

Port the current operation-scoped context aggregation, approved Beat Plan and unique chapter-group resolution. Test every read/control tool scope, full-result behavior, artifact-only draft visibility, task/novel binding and denial when an Agent attempts a capability it was not granted.

- [ ] **Step 5: Verify RED**

Run: `uv run pytest apps/core-api/tests/writing apps/core-api/tests/reviews -v`

Expected: FAIL.

- [ ] **Step 6: Implement Core-owned task, artifact, context, Tool Gateway and SSE services**

Create all public writing/session/artifact endpoints and internal Agent callback endpoints. Core validates service identity and task binding before accepting event, checkpoint, completion or failure. Stable snapshots write to existing `graphStateJson`; runtime callbacks and novel aggregate data never persist.

- [ ] **Step 7: Verify GREEN**

Run: `uv run pytest apps/core-api/tests/writing apps/core-api/tests/reviews -v`

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add apps/core-api/src/inkforge_core/writing apps/core-api/src/inkforge_core/reviews apps/core-api/tests/writing apps/core-api/tests/reviews
git commit -m "feat: migrate writing and artifact persistence"
```

### Task 12: Bootstrap Agent Service and explicit providers

**Files:**
- Create: `apps/agent-service/src/inkforge_agents/config.py`
- Create: `apps/agent-service/src/inkforge_agents/app.py`
- Create: `apps/agent-service/src/inkforge_agents/providers/base.py`
- Create: `apps/agent-service/src/inkforge_agents/providers/openai_compatible.py`
- Create: `apps/agent-service/src/inkforge_agents/providers/fake.py`
- Create: `apps/agent-service/src/inkforge_agents/runtime/model_runtime.py`
- Create: `apps/agent-service/tests/test_health.py`
- Create: `apps/agent-service/tests/providers/test_fake_provider.py`
- Create: `apps/agent-service/tests/providers/test_provider_config.py`

- [ ] **Step 1: Write failing provider tests**

Test that missing real credentials select fake provider only when `MODEL_PROVIDER=fake`; production `openai_compatible` without key fails readiness. Fake provider returns deterministic text/tool calls/usage and never opens a network connection.

- [ ] **Step 2: Verify RED**

Run: `uv run pytest apps/agent-service/tests/test_health.py apps/agent-service/tests/providers -v`

Expected: FAIL.

- [ ] **Step 3: Implement app and providers**

Provider selection is explicit, dependency-injected and testable. Model Runtime performs one supplier turn only; it does not interpret business control tools. Agent Service exposes live/ready and signed internal run endpoints only.

- [ ] **Step 4: Verify GREEN**

Run: `uv run pytest apps/agent-service/tests/test_health.py apps/agent-service/tests/providers -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/agent-service/src apps/agent-service/tests
git commit -m "feat: bootstrap Agent Service runtime"
```

### Task 13: Port Agent definitions, prompts, capabilities and tool runtime

**Files:**
- Create: `apps/agent-service/src/inkforge_agents/definitions/agents.py`
- Create: `apps/agent-service/src/inkforge_agents/definitions/capabilities.py`
- Create: `apps/agent-service/src/inkforge_agents/prompts/lore.py`
- Create: `apps/agent-service/src/inkforge_agents/prompts/plot.py`
- Create: `apps/agent-service/src/inkforge_agents/prompts/author.py`
- Create: `apps/agent-service/src/inkforge_agents/prompts/validator.py`
- Create: `apps/agent-service/src/inkforge_agents/prompts/editor.py`
- Create: `apps/agent-service/src/inkforge_agents/runtime/agent_runtime.py`
- Create: `apps/agent-service/src/inkforge_agents/runtime/agent_runner.py`
- Create: `apps/agent-service/src/inkforge_agents/runtime/turn_result.py`
- Create: `apps/agent-service/src/inkforge_agents/tools/registry.py`
- Create: `apps/agent-service/src/inkforge_agents/tools/permissions.py`
- Create: `apps/agent-service/src/inkforge_agents/tools/read.py`
- Create: `apps/agent-service/src/inkforge_agents/tools/control.py`
- Create: `apps/agent-service/src/inkforge_agents/tools/proposals.py`
- Create: `apps/agent-service/tests/runtime/test_agent_runtime.py`
- Create: `apps/agent-service/tests/runtime/test_agent_runner.py`
- Create: `apps/agent-service/tests/runtime/test_visible_content.py`
- Create: `apps/agent-service/tests/tools/test_registry.py`
- Create: `apps/agent-service/tests/tools/test_permissions.py`
- Create: `apps/agent-service/tests/tools/test_arguments.py`
- Create: `apps/agent-service/tests/golden/prompts/lore.txt`
- Create: `apps/agent-service/tests/golden/prompts/plot.txt`
- Create: `apps/agent-service/tests/golden/prompts/author.txt`
- Create: `apps/agent-service/tests/golden/prompts/validator.txt`
- Create: `apps/agent-service/tests/golden/prompts/editor.txt`

- [ ] **Step 1: Create failing golden and permission tests**

Port five Agent IDs, names, system prompt invariants, `paragraph_text_with_control_tools`, capability cards and current tool exposure matrix. Assert non-authorized agents never receive or execute a control tool.

- [ ] **Step 2: Create failing multi-turn runtime tests**

Port visible text accumulation, read-tool parallelism, control-tool ordering, invalid arguments, unexposed tool rejection, maximum turn count, supplier failure, no silent truncation and structured control event capture.

- [ ] **Step 3: Verify RED**

Run: `uv run pytest apps/agent-service/tests/runtime apps/agent-service/tests/tools -v`

Expected: FAIL.

- [ ] **Step 4: Implement declarative definitions and the unique tool loop**

Agent Runtime is the only multi-turn loop. Model Runtime remains supplier-only. Read tools call Core Tool Gateway with the run capability. Control/proposal tools produce typed events and never write data directly.

- [ ] **Step 5: Verify GREEN**

Run: `uv run pytest apps/agent-service/tests/runtime apps/agent-service/tests/tools -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add apps/agent-service/src/inkforge_agents/definitions apps/agent-service/src/inkforge_agents/prompts apps/agent-service/src/inkforge_agents/runtime apps/agent-service/src/inkforge_agents/tools apps/agent-service/tests/runtime apps/agent-service/tests/tools apps/agent-service/tests/golden
git commit -m "feat: port Agent runtime and tools"
```

### Task 14: Port CreativeOperation and LangGraph workflow

**Files:**
- Create: `apps/agent-service/src/inkforge_agents/operations/contracts.py`
- Create: `apps/agent-service/src/inkforge_agents/operations/definitions.py`
- Create: `apps/agent-service/src/inkforge_agents/operations/router.py`
- Create: `apps/agent-service/src/inkforge_agents/operations/graph.py`
- Create: `apps/agent-service/src/inkforge_agents/graph/state.py`
- Create: `apps/agent-service/src/inkforge_agents/graph/parent_graph.py`
- Create: `apps/agent-service/src/inkforge_agents/graph/snapshots.py`
- Create: `apps/agent-service/src/inkforge_agents/graph/context.py`
- Create: `apps/agent-service/src/inkforge_agents/artifacts/updates.py`
- Create: `apps/agent-service/src/inkforge_agents/artifacts/diff.py`
- Create: `apps/agent-service/src/inkforge_agents/artifacts/patch.py`
- Create: `apps/agent-service/src/inkforge_agents/studio.py`
- Modify: `langgraph.json`
- Create: `apps/agent-service/tests/operations/test_definitions.py`
- Create: `apps/agent-service/tests/operations/test_router.py`
- Create: `apps/agent-service/tests/operations/test_review_routing.py`
- Create: `apps/agent-service/tests/graph/test_parent_graph.py`
- Create: `apps/agent-service/tests/graph/test_operation_graph.py`
- Create: `apps/agent-service/tests/graph/test_snapshots.py`
- Create: `apps/agent-service/tests/graph/test_context.py`

- [ ] **Step 1: Write failing operation-definition and routing tests**

Port all CreativeOperation kinds, legacy `@Agent` mapping, primary Agent, reviewers, artifact strategy, chapter target resolution and low-confidence fallback.

- [ ] **Step 2: Write failing graph tests**

Cover prepare, execute, direct response, artifact submission, reviewer fan-out, deterministic verdict precedence, patch/rewrite, maximum revision count, interrupt payload, resume, user approve/revise/discard and next-action completion.

- [ ] **Step 3: Write failing snapshot tests**

Snapshot schema must preserve current recoverable fields and reject runtime-only data. Serialize with a version envelope that the rollback adapter can translate to the existing TypeScript shape.

- [ ] **Step 4: Verify RED**

Run: `uv run pytest apps/agent-service/tests/operations apps/agent-service/tests/graph -v`

Expected: FAIL.

- [ ] **Step 5: Implement LangGraph Python state and graphs**

Use StateGraph, conditional edges, Send for reviewers, Command/resume and interrupt. Do not implement a parallel while/switch workflow engine. All persistence and tool effects go through signed Core clients.

- [ ] **Step 6: Verify GREEN**

Run: `uv run pytest apps/agent-service/tests/operations apps/agent-service/tests/graph -v`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add apps/agent-service/src/inkforge_agents/operations apps/agent-service/src/inkforge_agents/graph apps/agent-service/src/inkforge_agents/artifacts apps/agent-service/src/inkforge_agents/studio.py apps/agent-service/tests/operations apps/agent-service/tests/graph langgraph.json
git commit -m "feat: port LangGraph writing workflow"
```

### Task 15: Implement the recoverable run queue and Core-Agent integration

**Files:**
- Create: `apps/agent-service/src/inkforge_agents/queue/consumer.py`
- Create: `apps/agent-service/src/inkforge_agents/queue/repository.py`
- Create: `apps/agent-service/src/inkforge_agents/queue/recovery.py`
- Create: `apps/agent-service/src/inkforge_agents/clients/core.py`
- Create: `apps/agent-service/src/inkforge_agents/jobs/portrait.py`
- Create: `apps/agent-service/src/inkforge_agents/jobs/rag.py`
- Create: `apps/agent-service/src/inkforge_agents/jobs/quality.py`
- Create: `apps/agent-service/src/inkforge_agents/observability/workflow_log.py`
- Create: `apps/agent-service/src/inkforge_agents/debug/router.py`
- Create: `apps/core-api/src/inkforge_core/agent_client.py`
- Create: `apps/core-api/src/inkforge_core/writing/reconciler.py`
- Create: `apps/core-api/src/inkforge_core/operations/debug_proxy.py`
- Create: `apps/agent-service/tests/queue/test_consumer.py`
- Create: `apps/agent-service/tests/integration/test_core_callbacks.py`
- Create: `apps/agent-service/tests/jobs/test_portrait.py`
- Create: `apps/agent-service/tests/jobs/test_rag.py`
- Create: `apps/agent-service/tests/jobs/test_quality.py`
- Create: `apps/agent-service/tests/observability/test_workflow_log.py`
- Create: `apps/core-api/tests/operations/test_debug_proxy.py`
- Create: `apps/core-api/tests/writing/test_reconciler.py`

- [ ] **Step 1: Write failing queue and crash tests**

Cover priority ordering, single concurrency, visibility timeout, explicit ack, graceful shutdown, duplicate run idempotency, Redis message loss, Agent restart, Core re-submit and stale task cancellation.

- [ ] **Step 2: Write failing signed integration tests**

Run request, context/tool read, event batches, checkpoint, complete, fail and billing callbacks must succeed with correct claims and fail with wrong task/novel/run/audience/scope.

- [ ] **Step 3: Write failing non-writing job and log tests**

Port portrait generation, portrait section regeneration, RAG embedding and quality-check jobs through the same single-concurrency queue. Port the human workflow log contract (`REQUEST`/`RESPONSE` plus Chinese state transitions) and verify Core can query it only after browser authorization and signed Agent debug access.

- [ ] **Step 4: Verify RED**

Run: `uv run pytest apps/agent-service/tests/queue apps/agent-service/tests/integration apps/agent-service/tests/jobs apps/agent-service/tests/observability apps/core-api/tests/writing/test_reconciler.py apps/core-api/tests/operations/test_debug_proxy.py -v`

Expected: FAIL.

- [ ] **Step 5: Implement Redis queue, job handlers, debug proxy and reconciliation**

Redis is a delivery optimization. Core periodically scans existing non-terminal WritingTask rows and re-submits missing runs with the same deterministic idempotency key. Agent verifies Core state before every recovered execution.

- [ ] **Step 6: Verify GREEN**

Run: `uv run pytest apps/agent-service/tests/queue apps/agent-service/tests/integration apps/agent-service/tests/jobs apps/agent-service/tests/observability apps/core-api/tests/writing/test_reconciler.py apps/core-api/tests/operations/test_debug_proxy.py -v`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add apps/agent-service/src/inkforge_agents/queue apps/agent-service/src/inkforge_agents/clients apps/agent-service/src/inkforge_agents/jobs apps/agent-service/src/inkforge_agents/observability apps/agent-service/src/inkforge_agents/debug apps/agent-service/tests/queue apps/agent-service/tests/integration apps/agent-service/tests/jobs apps/agent-service/tests/observability apps/core-api/src/inkforge_core/agent_client.py apps/core-api/src/inkforge_core/writing/reconciler.py apps/core-api/src/inkforge_core/operations/debug_proxy.py apps/core-api/tests/writing/test_reconciler.py apps/core-api/tests/operations/test_debug_proxy.py
git commit -m "feat: integrate recoverable Agent runs"
```

### Task 16: Generate the TypeScript API client and move Next into apps/web

**Files:**
- Create: `packages/api-client/package.json`
- Create: `packages/api-client/src/generated/**`
- Create: `packages/api-client/src/sse.ts`
- Create: `scripts/export_openapi.py`
- Create: `scripts/generate_api_client.mjs`
- Move: current Next config, `src`, `public`, TypeScript config and CSS into `apps/web/**`
- Modify: root `package.json`
- Modify: `package-lock.json`
- Create: `apps/web/src/lib/api/server.ts`
- Create: `apps/web/src/lib/api/browser.ts`
- Create: `apps/web/src/lib/api/__tests__/sse.test.ts`

- [ ] **Step 1: Write failing generation-drift and SSE tests**

The generation check exports Core OpenAPI, regenerates client files and fails when `git diff --exit-code packages/api-client/src/generated` is non-empty. SSE test covers typed event parsing, Last-Event-ID, heartbeat, duplicate sequence and reconnect.

- [ ] **Step 2: Verify RED**

Run: `npm run api:check`

Expected: FAIL because the client does not exist.

- [ ] **Step 3: Add npm workspaces and generated client**

Root scripts must include `dev`, `build`, `lint`, `typecheck`, `api:generate`, `api:check`, `test:web` and `test:python`. Server fetch forwards only the session Cookie and request ID to Core; browser fetch uses same-origin credentials.

- [ ] **Step 4: Move the Next application mechanically**

Use `git mv` so history remains traceable. Update aliases and Next output paths. Do not change UI behavior in the move commit.

- [ ] **Step 5: Verify the moved UI baseline**

Run: `npm ci`

Run: `npm run typecheck`

Expected: PASS.

Run: `npm run build`

Expected: PASS without `DATABASE_URL`, model keys or Redis variables.

- [ ] **Step 6: Commit**

```bash
git add package.json package-lock.json apps/web packages/api-client scripts/export_openapi.py scripts/generate_api_client.mjs
git commit -m "refactor: move Next app and generate API client"
```

### Task 17: Replace every Server Action, Route Handler and server-side Prisma query

**Files:**
- Modify: `apps/web/src/app/page.tsx`
- Modify: `apps/web/src/app/dashboard/page.tsx`
- Modify: `apps/web/src/app/workspace/[novelId]/page.tsx`
- Modify: `apps/web/src/app/styles/page.tsx`
- Modify: `apps/web/src/app/billing/page.tsx`
- Modify: `apps/web/src/app/login/page.tsx`
- Modify: `apps/web/src/app/layout.tsx`
- Modify: `apps/web/src/features/auth/login-form.tsx`
- Modify: `apps/web/src/features/auth/user-menu.tsx`
- Modify: `apps/web/src/features/projects/create-novel-modal.tsx`
- Modify: `apps/web/src/features/projects/novel-list-client.tsx`
- Modify: `apps/web/src/features/chapters/chapter-list.tsx`
- Modify: `apps/web/src/features/editor/chapter-editor.tsx`
- Modify: `apps/web/src/features/lore/lore-panel.tsx`
- Modify: `apps/web/src/features/outline/outline-panel.tsx`
- Modify: `apps/web/src/features/progress/progress-panel.tsx`
- Modify: `apps/web/src/features/references/reference-panel.tsx`
- Modify: `apps/web/src/features/styles/style-library-panel.tsx`
- Modify: `apps/web/src/features/styles/style-panel.tsx`
- Modify: `apps/web/src/features/workspace/inspector-tabs.tsx`
- Modify: `apps/web/src/features/workspace/sidebar-tabs.tsx`
- Modify: `apps/web/src/features/writing/writing-conversation.tsx`
- Modify: `apps/web/src/features/debug/workflow-events-inspector.tsx`
- Modify: `apps/web/src/middleware.ts` or `apps/web/src/proxy.ts`
- Delete: migrated `apps/web/src/app/actions.ts`
- Delete: migrated business `apps/web/src/app/api/**`
- Delete: `apps/web/src/shared/db/**`
- Create: `apps/web/src/lib/api/__tests__/action-mapping.test.ts`
- Create: `tests/architecture/legacy-backend-map.json`

- [ ] **Step 1: Create the exhaustive failing action map**

List all 50 exported actions and all current API methods with exactly one replacement HTTP method/path and frontend caller. The test parses the legacy inventory and fails if an entry is missing or duplicated.

- [ ] **Step 2: Replace page reads**

Dashboard, workspace, styles and billing Server Components call Core aggregate endpoints. Handle 401 with login redirect and 403/404 with stable UI errors. No page imports Prisma types.

- [ ] **Step 3: Replace mutation calls domain by domain**

Migrate auth, project/chapter, lore, outline/progress, references, styles, writing settings, quality, sessions/messages, artifacts and billing. Preserve 1.2-second autosave, interaction states and Chinese messages.

- [ ] **Step 4: Replace writing SSE and recovery**

Frontend connects only to Core SSE, preserves existing event semantics and adds sequence/replay handling. CurrentTask/lastTask and artifact recovery continue to use explicit session bindings.

- [ ] **Step 5: Delete Next backend entrypoints and verify architecture**

Run:

```bash
rg -n '@/shared/db/prisma|@prisma/client|DATABASE_URL|"use server"|from "openai"|@langchain' apps/web
```

Expected: no backend matches. A narrowly scoped framework-only occurrence must be documented and tested; business occurrences are forbidden.

- [ ] **Step 6: Fix existing lint failures without changing UX**

Move render-created components to module scope, replace state-reset effects with keyed component boundaries/derived state, and remove render-time ref access. Add focused React tests for each changed behavior.

- [ ] **Step 7: Verify frontend**

Run: `npm run typecheck`

Run: `npm run lint`

Run: `npm run test:web`

Run: `npm run build`

Expected: all PASS with zero warnings caused by backend filesystem tracing.

- [ ] **Step 8: Commit**

```bash
git add apps/web packages/api-client tests/architecture/legacy-backend-map.json
git commit -m "refactor: make Next a frontend-only application"
```

### Task 18: Add production Docker images, Compose and Nginx

**Files:**
- Create: `infra/docker/core-api.Dockerfile`
- Create: `infra/docker/agent-service.Dockerfile`
- Create: `infra/docker/web.Dockerfile`
- Create: `infra/nginx/nginx.conf`
- Create: `infra/compose.yaml`
- Create: `infra/compose.test.yaml`
- Create: `infra/redis/redis.conf`
- Create: `.env.example`
- Create: `scripts/compose_smoke.ps1`
- Create: `scripts/compose_smoke.sh`
- Create: `tests/architecture/test_compose_security.py`

- [ ] **Step 1: Write failing Compose policy tests**

Parse Compose and assert only Nginx publishes ports; Agent has no `DATABASE_URL` and no `data_net`; Postgres has no init scripts; all application containers are non-root, have health checks and resource limits; Redis maxmemory is 64 MB with no AOF.

- [ ] **Step 2: Verify RED**

Run: `uv run pytest tests/architecture/test_compose_security.py -v`

Expected: FAIL.

- [ ] **Step 3: Implement multi-stage non-root images**

Web image contains only standalone Next output. Python runtime images contain locked wheels and application packages, not uv caches or test files. Containers use read-only roots with explicit tmpfs and writable data/log volumes.

- [ ] **Step 4: Implement networks, secrets and resource limits**

Use `public_net`, `agent_net` and internal `data_net`; memory caps match the spec. Mount existing PostgreSQL data volume without init SQL. Nginx disables proxy buffering for SSE and blocks `/internal/`.

- [ ] **Step 5: Verify Compose config and health**

Run: `docker compose -f infra/compose.yaml config`

Expected: valid configuration with no interpolated missing required secrets.

Run: `uv run pytest tests/architecture/test_compose_security.py -v`

Expected: PASS.

Run: `docker compose -f infra/compose.test.yaml up --build --wait`

Expected: every service healthy.

- [ ] **Step 6: Run smoke and shutdown**

Run: `pwsh scripts/compose_smoke.ps1`

Expected: public page, auth fake flow, Core readiness, Agent readiness, SSE fake run and database fingerprint checks PASS.

Run: `docker compose -f infra/compose.test.yaml down -v`

- [ ] **Step 7: Commit**

```bash
git add infra .env.example scripts/compose_smoke.ps1 scripts/compose_smoke.sh tests/architecture/test_compose_security.py
git commit -m "ops: add production Docker Compose deployment"
```

### Task 19: Delete the TypeScript backend and update authority documents

**Files:**
- Delete: legacy `src/agents/**` after the web move
- Delete: legacy server-only shared libraries and contracts replaced by OpenAPI
- Delete: `prisma/**` runtime tooling after schema contract proof, while archiving the final schema as historical evidence
- Modify: `package.json` and `package-lock.json`
- Modify: `AGENTS.md`
- Modify: `DOCS.md`
- Replace: `src/agents/AGENTS.md` with `apps/agent-service/AGENTS.md`
- Modify: `docs/requirements/00-overview.md`
- Modify: `docs/requirements/01-projects-and-chapters.md`
- Modify: `docs/requirements/02-creative-knowledge-base.md`
- Modify: `docs/requirements/03-ai-writing-and-agents.md`
- Modify: `docs/requirements/04-review-quality-and-workflow.md`
- Modify: `docs/requirements/05-auth-billing-and-ops.md`
- Modify: `docs/LANGGRAPH_STUDIO.md`
- Modify: `docs/WORKFLOW_EVENT_LOG_FORMAT.md`
- Modify: `README.md`

- [ ] **Step 1: Write the failing forbidden-backend scan**

Create `tests/architecture/test_no_typescript_backend.py` that rejects Prisma, LangGraph.js, LangChain.js, Node OpenAI SDK, business Route Handlers, business Server Actions and database/model secrets anywhere in `apps/web` or TypeScript runtime dependencies.

- [ ] **Step 2: Verify RED**

Run: `uv run pytest tests/architecture/test_no_typescript_backend.py -v`

Expected: FAIL while legacy backend files/dependencies remain.

- [ ] **Step 3: Delete migrated code and dependencies**

Retain only frontend-safe TypeScript helpers and generated contracts. Archive the final Prisma schema under `docs/archive/database/` with a header that it is historical evidence, not a migration source. Production Python continues to use `schema-contract.json`.

- [ ] **Step 4: Update current authority and requirements**

Document Core/Agent boundaries, commands, service JWT, no-database Agent rule, Compose deployment, recovery and logs. Remove claims that Prisma or LangGraph.js are current runtime facts.

- [ ] **Step 5: Verify GREEN**

Run: `uv run pytest tests/architecture/test_no_typescript_backend.py -v`

Expected: PASS.

Run: `npm ci`

Run: `npm run typecheck`

Run: `npm run lint`

Run: `npm run build`

Expected: PASS.

Run: `uv sync --frozen --all-packages --group dev`

Run: `uv run ruff check .`

Run: `uv run mypy apps/core-api/src apps/agent-service/src packages/service-contracts/src`

Run: `uv run pytest`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "refactor: remove legacy Next backend"
```

### Task 20: Run production acceptance, recovery, backup and rollback proof

**Files:**
- Create: `tests/e2e/auth.spec.ts`
- Create: `tests/e2e/project-editor.spec.ts`
- Create: `tests/e2e/knowledge-style.spec.ts`
- Create: `tests/e2e/writing-artifact.spec.ts`
- Create: `tests/e2e/quality-billing.spec.ts`
- Create: `scripts/backup.sh`
- Create: `scripts/restore_verify.sh`
- Create: `scripts/schema_fingerprint.sh`
- Create: `scripts/recovery_drill.sh`
- Create: `scripts/rollback_drill.sh`
- Create: `docs/PYTHON_BACKEND_CUTOVER.md`
- Create: `docs/audits/2026-07-10-python-backend-acceptance.md`

- [ ] **Step 1: Implement Playwright end-to-end tests**

Cover registration/login, dashboard, novel creation, chapter autosave, lore CRUD, outline hierarchy, reference upload, style upload/portrait fake task, writing session, Agent fake stream, ReviewArtifact approve/discard/revise, quality check and billing summary.

- [ ] **Step 2: Run complete static and unit gates**

Run: `npm run api:check`

Run: `npm run typecheck`

Run: `npm run lint`

Run: `npm run test:web`

Run: `npm run build`

Run: `uv run ruff check .`

Run: `uv run mypy apps/core-api/src apps/agent-service/src packages/service-contracts/src`

Run: `uv run pytest --cov=inkforge_core --cov=inkforge_agents --cov=inkforge_contracts --cov-report=term-missing`

Expected: all PASS; changed Python business modules have meaningful branch coverage and no untested critical authorization/write path.

- [ ] **Step 3: Run full Compose E2E**

Run: `docker compose -f infra/compose.test.yaml up --build --wait`

Run: `npm run test:e2e`

Expected: all primary workflows PASS through Nginx.

- [ ] **Step 4: Prove restart recovery**

Start a fake Agent run, stop Agent during a model step, restart it and verify the task resumes from the last stable checkpoint. Delete Redis runtime keys and verify Core reconciliation re-submits the existing non-terminal WritingTask without duplicate artifacts or charges.

- [ ] **Step 5: Prove database and upload backup/restore**

Run backup against the test deployment, record checksums, restore into a separate validation volume and compare schema fingerprint plus row counts. The production script must never restore over a running database.

- [ ] **Step 6: Prove rollback compatibility**

Using the staging copy, write representative data with Python, stop the new stack, start the archived old image read-only and verify user Cookie, IDs, bcrypt, artifact payload, graph snapshot adapter and upload paths are readable. Record any task states intentionally excluded from rollback and resolve them before release.

- [ ] **Step 7: Run the 2-core/2-GB soak**

Apply Compose memory limits and CPU quota, execute mixed CRUD plus one Agent run at a time for 30 minutes, and record OOM count, peak RSS, database connections, task loss, p95 CRUD, SSE first-event and run-accept latency.

- [ ] **Step 8: Complete the acceptance audit**

For every spec acceptance bullet, link exact test output, command output, file scan or runtime evidence. Missing or indirect evidence is a failure, not “probably complete”.

- [ ] **Step 9: Commit**

```bash
git add tests/e2e scripts docs/PYTHON_BACKEND_CUTOVER.md docs/audits/2026-07-10-python-backend-acceptance.md
git commit -m "test: prove Python backend production readiness"
```

## Final Completion Gate

- [ ] Every Task 1-20 checkbox is complete.
- [ ] No uncommitted generated files or secrets exist.
- [ ] The immutable database fingerprint is unchanged.
- [ ] The frontend contains no backend implementation.
- [ ] Agent Service has no database access path.
- [ ] All static, unit, integration, E2E, restart, backup, rollback and soak evidence passes.
- [ ] Authority and current-requirement documents describe the Python architecture.
- [ ] The acceptance audit maps every spec requirement to direct evidence.
- [ ] Only after all checks pass, archive this plan according to `DOCS.md` and mark the active goal complete.
