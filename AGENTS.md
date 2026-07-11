# InkForge 开发指导

后续所有对话、注释、文档、备注和提交信息必须使用简体中文。回答必须清晰、诚实、明确，不能为了迎合用户忽略事实。

## 权威与流程

- 根目录 `DOCS.md` 是文档治理权威。
- 项目事实优先级：当前代码、数据库结构契约、共享服务契约、生成的 OpenAPI 客户端和测试，高于历史文档。
- 接到新需求后，先在 `docs/specs/` 新增或更新 spec，再修改实现。
- 修改前端 UI 前先读 `DESIGN.md`。
- 修改 Agent、写作流程或草案审核前先读 `apps/agent-service/AGENTS.md`、`docs/requirements/03-ai-writing-and-agents.md` 和 `docs/requirements/04-review-quality-and-workflow.md`。
- 禁止修改现有 PostgreSQL schema。任何持久化改动必须先核对 `apps/core-api/src/inkforge_core/db/schema-contract.json`，不得执行自动建表、删表或迁移。

## 当前架构

```text
浏览器 -> Nginx -> Next.js 页面与 SSR
              -> Core API 公共接口与 SSE -> PostgreSQL
                                         -> Redis
                         Core API <-> Agent Service
                                         -> Redis
```

- `apps/web`：Next.js 16，仅页面、SSR/SEO、浏览器交互和生成客户端，不得包含业务 API、Server Actions、数据库客户端或模型运行时。
- `apps/core-api`：FastAPI 核心接口服务，独占 PostgreSQL 访问、浏览器认证、归属校验、业务规则、ReviewArtifact、计费和 SSE。
- `apps/agent-service`：FastAPI 智能体服务，负责 LangGraph、模型、工具循环和运行队列。禁止导入数据库驱动、读取 `DATABASE_URL` 或直接写正式小说数据。
- `packages/service-contracts`：Core 与 Agent 的版本化 Pydantic 契约。
- `packages/service-auth`：Ed25519 服务身份、请求绑定和重放保护。
- `packages/api-client`：由 Core OpenAPI 生成的 TypeScript 客户端。
- `infra/compose.yaml`：单机生产编排；Nginx 是唯一公网入口。

## 常用命令

```bash
npm run dev
npm run typecheck
npm run lint
npm run test:web
npm run build
npm run api:generate
npm run api:check

uv sync --frozen --all-packages --group dev
uv run pytest
uv run ruff check .
uv run mypy apps/core-api/src apps/agent-service/src packages/service-contracts/src packages/service-auth/src

docker compose -f infra/compose.yaml up --build -d
```

## 不可突破的边界

- 禁止静默截断正文、草案、工具结果、Agent 回复、日志或持久化数据。
- 正式内容变更必须遵循 `proposal -> ReviewArtifact -> 复审/返工 -> 用户确认 -> Core API 应用`。
- Agent Service 只能通过 Core 内部工具网关读写业务数据，不得连接 PostgreSQL。
- 内部接口统一位于 `/internal/v1/**`，同时校验直接对端网段和 Ed25519 服务令牌；不得信任转发头决定内部身份。
- 浏览器只访问 `/api/v1/**`，不得访问内部接口。
- 新增或修改公共接口时，先改 FastAPI/Pydantic 契约，再运行 `npm run api:generate`，禁止手写重复 TypeScript DTO。
- 新增 Agent 工具必须注册到 `apps/agent-service/src/inkforge_agents/tools/registry.py`，同时声明权限和并发属性。
- 模型工具循环只能位于 `AgentRuntime`，LangGraph 编排只能使用现有 `StateGraph`、`Send`、`Command` 和 `interrupt()` 扩展。
- 2 核 2 GB 部署默认每个 Python 服务一个 worker，同一时刻只执行一个模型任务。

## 前端规则

- 使用原生 CSS 和已有 CSS 自定义属性，不引入 Tailwind。
- PC 优先，使用 flex、grid 和 `minmax` 适配桌面宽度。
- 章节编辑器继续使用 `textarea`，自动保存延迟 1.2 秒。
- 字数统计统一使用 `countTextLength()`。
- Agent 聊天正文按普通段落文本渲染，不使用 Markdown 解析。

## 验证要求

- 前端修改至少运行相关测试、`npm run typecheck` 和 `npm run lint`。
- Python 修改至少运行相关 pytest、Ruff；共享协议、鉴权或工作流修改还要运行 Mypy。
- 部署修改运行 `tests/architecture/test_compose_security.py`，有 Docker 的环境再运行 Compose 健康检查。
- 数据库结构只能做只读指纹校验，不能为了让测试通过修改数据库。
