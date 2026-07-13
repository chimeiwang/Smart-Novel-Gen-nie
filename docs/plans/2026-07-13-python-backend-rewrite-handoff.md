# Python 后端重构剩余任务交接计划

> **供执行智能体使用：**必须使用 `superpowers:subagent-driven-development`（推荐）或 `superpowers:executing-plans`，逐项实施本计划。步骤使用勾选框（`- [ ]`）跟踪进度。

**目标：**完成 Python 后端重构的本地端到端验收、已知降级决策和分支集成，使该迁移可以在不修改数据库结构的前提下交付。

**架构：**Next.js 只负责页面、SSR/SEO 和浏览器交互；FastAPI Core API 独占 PostgreSQL、认证、业务规则、草案、计费和 SSE；FastAPI Agent Service 负责 LangGraph、模型和工具执行且不连接数据库。当前功能迁移和自动化测试已基本完成，后续工作只允许修复验收发现的问题，不得重新建立 Next.js 后端或修改 PostgreSQL schema。

**技术栈：**Next.js 16、React 19、TypeScript、FastAPI、Pydantic v2、SQLAlchemy 2、PostgreSQL、Redis、LangGraph Python、Playwright、Docker Compose。

**权威规格：**`docs/specs/2026-07-10-python-backend-rewrite.md`

---

## 1. 接手位置与当前状态

只能在以下工作树继续：

```text
C:\Users\niebo\.config\superpowers\worktrees\inkForge\python-backend-rewrite
```

当前分支：

```text
codex/python-backend-rewrite
```

根仓库 `F:\code\inkForge` 当前仍是 `main`，不要直接在根仓库重做迁移，也不要覆盖工作树中的未提交修改。

截至 2026-07-13，工作树包含大量未提交的迁移修改和新增文件。接手后第一条命令必须是：

```powershell
git status --short
```

禁止使用 `git reset --hard`、`git checkout --` 或其他会丢弃现有改动的命令。

## 2. 已完成事实与验证基线

以下内容已经完成，不要重复实现：

- Next.js 业务后端已迁出；`apps/web` 未发现 Prisma、`DATABASE_URL`、业务 API Route 或业务 Server Action 残留。
- Core API 已承接 PostgreSQL、认证、业务 CRUD、ReviewArtifact、计费、SSE 和写作任务。
- Agent Service 已承接五个 Agent、LangGraph、模型运行时、工具循环和 Redis 队列，且不连接数据库。
- “同步设定”流程已删除；共享枚举只保留历史快照兼容。
- Agent 的 26 个读取工具已通过共享 Pydantic 契约接入 Core API。
- `get_review_artifact` 已统一使用 `artifact_id`。
- 参考资料语义检索由 Agent 生成查询向量，Core 在当前用户和小说范围内执行 pgvector 检索。
- 数据库 schema、迁移和现有数据均未修改。

最近一次验证结果：

```text
Python 全量测试：820 passed，3 skipped
Web 与 API Client 测试：7 passed
TypeScript 类型检查：通过
ESLint：通过
OpenAPI 客户端漂移检查：通过
Next.js 生产构建：通过
Ruff：通过
Mypy：通过
```

对应命令：

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m mypy apps/core-api/src apps/agent-service/src packages/service-contracts/src packages/service-auth/src scripts tests
npm run test:web
npm run typecheck
npm run lint
npm run api:check
npm run build
```

## 3. 未完成任务

### 任务 1：运行本地三服务端到端验收

**目的：**证明最新的 Core 工具网关、Agent 队列、SSE、草案和前端交互可以在真实本地进程中串联运行。

**涉及文件：**

- 配置：`.env.local`
- 启动脚本：`scripts/dev.mjs`
- Playwright 配置：`playwright.config.ts`
- 端到端测试：`tests/e2e/*.spec.ts`

- [x] **步骤 1：确认本地配置存在且不泄露密钥**

运行：

```powershell
Test-Path .env.local
Test-Path infra\secrets\core-to-agent-private.pem
Test-Path infra\secrets\agent-to-core-private.pem
```

预期：全部返回 `True`。不得把 `.env.local`、Redis 密码、数据库密码、模型密钥或私钥写入文档、测试输出或 Git。

- [x] **步骤 2：确认外部 PostgreSQL 和 Redis 可访问**

使用 `.env.local` 中的现有地址做只读连接检查。不得运行 Prisma migrate、Alembic、`create_all()`、初始化 SQL 或任何 DDL。

预期：PostgreSQL 和 Redis 连接成功；数据库结构和数据不发生变化。

- [x] **步骤 3：启动本地三服务**

在一个持续运行的终端执行：

```powershell
npm run dev
```

预期：

```text
Next.js：http://127.0.0.1:43119
Core API：http://127.0.0.1:8000
Agent Service：http://127.0.0.1:8001
```

- [x] **步骤 4：确认健康检查与页面可访问**

运行：

```powershell
Invoke-WebRequest http://127.0.0.1:43119/login -UseBasicParsing
Invoke-WebRequest http://127.0.0.1:8000/api/v1/health/ready -UseBasicParsing
Invoke-WebRequest http://127.0.0.1:8001/internal/v1/health/ready -UseBasicParsing
```

预期：三个请求均成功。若 readiness 失败，先读取明确错误码，不要通过修改数据库结构绕过检查。

- [x] **步骤 5：运行六个 Playwright 主流程**

这些用例会通过正式 API 注册随机测试用户并创建小说、章节、草案等测试数据，属于正常业务 CRUD，不会修改 schema。运行前必须确认当前 PostgreSQL 允许写入此类测试数据；不得在未经允许的生产数据库上直接执行。

在另一个终端执行：

```powershell
$env:E2E_BASE_URL='http://127.0.0.1:43119'
npm run test:e2e
```

预期：以下六个用例全部通过：

```text
用户可以注册、退出并重新登录
用户可以维护设定、大纲、参考资料和文风画像
用户可以创建小说并自动保存章节
用户可以运行质量检查并查看模拟模型零扣费摘要
模拟模型可以完成写作会话和草案应用
用户可以丢弃待确认草案
```

- [x] **步骤 6：处理端到端失败**

若失败，必须先定位失败边界：浏览器、Next 代理、Core、Redis 队列、Agent、回调、SSE 或草案应用。每个修复先更新或新增 `docs/specs/`，再写失败测试，最后修改实现。不得通过延长固定等待时间、跳过断言或静默吞错让测试假通过。

- [x] **步骤 7：重新运行回归检查**

运行第 2 节全部验证命令，并再次执行：

```powershell
$env:E2E_BASE_URL='http://127.0.0.1:43119'
npm run test:e2e
```

预期：全部退出码为 `0`。

### 任务 2：处理跨服务草案局部 patch 降级

**当前事实：**`apps/agent-service/src/inkforge_agents/jobs/adapters.py` 的 `CoreArtifactPort.apply_patch()` 尚未启用跨服务局部 patch，会抛出错误并由工作流退化为完整返工。主流程可继续，但返工成本更高。

- [x] **步骤 1：由用户确认首版取舍**

只允许二选一：

```text
接受首版完整返工降级：记录为已知限制，本次迁移不再实现 patch。
要求局部 patch：先新增 spec，再实现签名的 Core 内部草案修订接口和测试。
```

未得到用户明确选择前，不要自行扩大实现范围。

已确认选择方案 A：接受首版完整返工降级，本次迁移不实现跨服务局部 patch。

- [x] **步骤 2：若接受降级，补充当前文档事实**

在 `apps/agent-service/AGENTS.md` 和 `docs/requirements/04-review-quality-and-workflow.md` 中说明局部 patch 会退化为完整返工，不承诺局部跨服务修订。

- [x] **步骤 3：若要求实现，先写规格和失败测试（方案 A 下不适用）**

新增：

```text
docs/specs/2026-07-13-cross-service-artifact-patch.md
```

测试至少覆盖：用户、小说、任务和草案绑定；revision 冲突；只允许安全的 `text_replace` patch；幂等重试；不得直接写正式小说表；Agent Service 仍不连接数据库。

### 任务 3：完成最终验收记录

**目的：**让后续维护者可以根据直接证据判断迁移完成，而不是依赖聊天记录。

**文件：**

- 新建：`docs/audits/2026-07-13-python-backend-rewrite-acceptance.md`

- [x] **步骤 1：记录自动化验证证据**

记录第 2 节所有命令的日期、退出码和通过数量。只记录结果摘要，不粘贴密钥、环境变量值或超长日志。

- [x] **步骤 2：记录端到端证据**

列出六个 Playwright 用例及结果；若产生失败截图或 trace，记录 `output/playwright` 下的相对路径。

- [x] **步骤 3：记录架构删除证明**

运行：

```powershell
rg -n "prisma|@prisma|DATABASE_URL|use server" apps/web/src apps/web/package.json --glob '*.ts' --glob '*.tsx' --glob '*.json'
```

预期：无业务后端残留。若命中仅为测试说明或文档，必须人工核对，不得机械删除。

- [x] **步骤 4：记录明确排除项**

本轮不要求在当前机器验证生产 Docker 部署、2 核 2 GB 压测、跨云多实例接管或 PostgreSQL 持久 LangGraph checkpointer。不要把这些排除项写成已经验证。

### 任务 4：审查并集成迁移分支

**目的：**把已经验证的工作树修改安全地提交并交回主仓库。

- [x] **步骤 1：审查全部未提交文件**

运行：

```powershell
git status --short
git diff --check
git diff --stat
```

逐个确认新增 spec、需求文档、Agent 架构、Core、Agent、Web、测试和服务密钥生成脚本属于本次迁移。不得顺手提交 `.env.local`、私钥、日志、上传文件、Playwright 输出或数据库文件。

- [x] **步骤 2：确认数据库零变更**

运行：

```powershell
git status --short -- prisma apps/core-api/src/inkforge_core/db/schema-contract.json
```

预期：没有 schema、迁移或结构契约修改。

- [x] **步骤 3：在当前分支提交**

提交前再次运行第 2 节全部验证命令和任务 1 的 Playwright。全部通过后，在 `codex/python-backend-rewrite` 分支创建清晰的迁移提交。

- [x] **步骤 4：由用户决定集成方式**

只在用户明确选择后执行以下之一：

```text
合并回 main
推送并创建 Pull Request
保留当前分支和工作树
```

禁止未经确认删除工作树或强制删除分支。

用户已确认选择本地合并回 `main`；合并验证通过后，按 Git worktree 流程移除本工作树并删除迁移分支。

## 4. 完成定义

只有同时满足以下条件，才能声明本次迁移完成：

- [x] 六个本地 Playwright 用例全部通过。
- [x] Python、Web、类型检查、Lint、Ruff、Mypy、OpenAPI 漂移检查和 Next.js 构建全部通过。
- [x] 跨服务草案 patch 已实现，或用户明确接受完整返工降级。
- [x] 验收审计已写入 `docs/audits/`，没有把未验证事项写成完成。
- [x] 数据库 schema、迁移和现有数据未被修改。
- [x] 当前工作树改动已经审查并按用户选择提交或保留。

## 5. 不属于本次剩余任务

以下内容是后续能力，不得阻塞首版交付：

- 多实例 Agent 调度和跨云自动接管。
- PostgreSQL 持久 LangGraph checkpointer。
- 章节、角色、伏笔和文风的全面向量化检索。
- LangSmith 评估集和并行质量检查。
- 自动连续生成多章或整卷。
- 已经删除的“同步设定”流程。
- 未经用户要求的生产服务器部署验证和 2 核 2 GB 压测。
