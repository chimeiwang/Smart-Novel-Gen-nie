# InkForge 开发指导

本文件只维护仓库级执行规则、开发边界和按需阅读入口。产品功能、数量基线、授权明细及验收记录按
[DOCS.md](DOCS.md) 分工维护，不在此复制。

后续所有对话、注释、文档、备注和提交信息必须使用简体中文。回答必须清晰、诚实、明确，不能为了迎合用户忽略事实。

## 开始任务

- 先读 [DOCS.md](DOCS.md)，按其项目事实优先级核对当前代码、结构契约、共享服务契约、生成客户端和测试。
- 先检查工作树与相关文件，保留已有未提交改动；历史文档不能代替当前实现证据。
- 新需求先在 `docs/specs/` 新增或更新 spec，再修改实现；同步受影响的需求与文档入口。
- 按下表读取相关文档；目录内另有 `AGENTS.md` 时一并遵守。
- 区分代码实现、开发可用、生产开放和历史兼容；异步受理、模拟结果或旧验收记录不能证明本次完成。
- 只有通用开发规则改变时才更新本文件；功能变化更新需求，具名授权更新授权清单与 spec，执行结果进入审计。

## 按任务必读

| 任务 | 阅读入口 |
| --- | --- |
| 产品、公共／内部接口、CLI、视频或迁移方案 | [产品总览](docs/requirements/00-overview.md)，再读相关 `docs/requirements/01-05` |
| 前端 UI | [DESIGN.md](DESIGN.md) |
| Agent、写作流程、草案审核 | [Agent 指导](apps/agent-service/AGENTS.md)、[AI 写作](docs/requirements/03-ai-writing-and-agents.md)、[审核与工作流](docs/requirements/04-review-quality-and-workflow.md) |
| Java Core、CLI 迁移、兼容基线或部署切换 | [Java 替换规格](docs/specs/2026-08-24-core-java-replacement.md)、[替换计划](docs/plans/2026-08-24-core-java-tdd-replacement.md)、[技术栈](docs/architecture-decisions/001-core-java-stack.md)、[契约](docs/architecture-decisions/002-core-java-contract-first.md)、[单切](docs/architecture-decisions/003-core-java-single-cutover.md)决策 |
| 数据库、数据迁移、旧执行清理、生产开关或回滚 | [数据变更授权清单](docs/DATA_CHANGE_AUTHORIZATIONS.md)及对应具名 spec、[运维需求](docs/requirements/05-auth-billing-and-ops.md)；耐久执行另读 [V2 运维手册](docs/DURABLE_AGENT_V2_ROLLOUT.md) |
| CLI／Operator Skill | [Java CLI 文档](tools/inkforge-cli-java/README.md)、[Operator 更新契约](docs/specs/2026-09-01-durable-agent-v2-operator-skill-update.md)；底层命令能力不自动扩大 Skill 白名单 |

## 服务与接口边界

- `apps/web` 只负责 Next.js 页面、SSR/SEO、浏览器交互和生成客户端；不得包含业务 API、Server Actions、数据库客户端或模型运行时。
- `apps/core-api-java` 独占 PostgreSQL、浏览器认证、归属校验、业务规则、ReviewArtifact、计费和 SSE。
  `apps/core-api` 保留历史镜像与公共契约来源；生产只运行一个 Core，不双 Core、不双写。
- `apps/agent-service` 负责 LangGraph、模型、工具循环和运行队列；只能通过 Core 内部工具网关读写业务数据，
  禁止导入数据库驱动、读取 `DATABASE_URL` 或直接写正式小说数据。V2 单 Step 使用独立持久 execution Redis，普通队列／认证 Redis 可重建。
- Core 与 Agent 使用 `packages/service-contracts` 的版本化 Pydantic 契约及 `packages/service-auth` 的 Ed25519 服务身份。
  `/internal/v1/**` 同时校验直接对端网段和服务令牌，不得信任转发头决定内部身份。
- 浏览器和 CLI 只访问 Core 公共 `/api/v1/**`，不得访问内部接口；Nginx 是唯一公网入口。
  CLI 凭据使用 macOS Keychain 或 Windows Credential Manager，不允许明文回退。
- 公共接口先改 FastAPI/Pydantic 契约，再运行 `npm run api:generate`；`packages/api-client` 由 OpenAPI 生成，
  禁止手写重复 TypeScript DTO。Java 必须通过版本化 Python OpenAPI 基线的契约差异测试，不依赖注解默认输出；
  不得因 Java 已切换而删除仍在使用的 Python 契约或基线测试。
- Java 业务模块拥有自身 Agent 出站应用端口，`agentgateway` 只能单向依赖并实现这些端口；业务模块不得反向
  导入 `AgentServiceClient` 或网关异常。`operations` 只托管后台生命周期；受配置门禁的数据库、Redis 或供应商
  协作者缺失时，不得让最小健康上下文装配失败。
- 新增 Agent 工具必须注册到 `apps/agent-service/src/inkforge_agents/tools/registry.py`，声明权限和并发属性。
  模型工具循环只能位于 `AgentRuntime`；LangGraph 编排使用现有 `StateGraph`、`Send`、`Command` 和 `interrupt()` 扩展。
- 2 核 2 GB 部署默认每个 Python 服务一个 worker；Agent 单进程最多并行三个不同项目队列任务，
  同一 `novelId` 同时只能执行一个任务；同一 `AGENT_MAX_CONCURRENCY` 全局限制最多三个模型调用，配置为 1 时回退串行。

## 内容与状态保护

- 禁止静默截断正文、草案、工具结果、Agent 回复、日志或持久化数据。
- 正式内容变更必须遵循 `proposal -> ReviewArtifact -> 复审/返工 -> 用户确认 -> Core API 应用`。
- 正文、章节进展、故事进展、设定、大纲、伏笔、Beat Plan、视频方案和后期决定是不同数据层，不得互相覆盖或混写。
- 选区、章节改编、提示词、渲染和导出必须冻结可重建的来源版本、哈希或不可变清单；历史版本只读，恢复和修改创建新版本。
- 写入口优先使用稳定 `clientRequestId` 幂等，状态 head 使用时间戳或 revision CAS；202、SSE 或 JSONL
  只表示受理／观察，完成状态必须通过 Core 回读 PostgreSQL 权威结果。
- 节奏、景别、空镜、平均时长和风格等软质量建议不得无证据升级为硬门禁或替代作者确认。

## 数据库与运行环境

- PostgreSQL schema 默认冻结；应用启动不得自动建表、删表或执行迁移，不得为了通过测试修改数据库结构。
- 结构变更必须有用户明确授权、具名 spec 和迁移脚本；执行前按[授权清单](docs/DATA_CHANGE_AUTHORIZATIONS.md)
  核对目标数据库、允许范围和门禁。已有授权按原范围沿用，不能因文档整理扩大或重新授予权限。
- 迁移前备份并在隔离 PostgreSQL 验证，完成后从真实目标库重新导出
  `apps/core-api/src/inkforge_core/db/schema-contract.json` 并复验精确一致；未获批变更只能只读核对契约。
- 当前正式库已有 V2 Run，永久禁止 DDL rollback；应用回滚必须保留 V2 查询与收敛能力，
  不得使用 V1-only Python Core 或不兼容的旧 Agent 镜像。不得物理删除会断开小说成果来源的 Task／Command 或候选。
- 生产必须保持 `VIDEO_PREVIEW_ENABLED=false`，拒绝视频调度和真实 Seedance；开发结构授权不等于生产迁移或功能开放。
  视频任务先核对[授权清单](docs/DATA_CHANGE_AUTHORIZATIONS.md)中链接的有效规格与暂停状态，不能凭历史摘要恢复实施或真实调用。
- 部署按[运维需求](docs/requirements/05-auth-billing-and-ops.md)及对应手册执行；普通应用部署不得自动执行 Durable Agent V2 DDL。

## Java 注释规则

- 对不直观的类职责和公开应用接口调用约束使用简短 Javadoc；业务规则、事务边界、并发与幂等、状态流转、异常恢复和兼容处理中的关键约束必须说明原因。
- 方法的用途若不能从名称和上下文一眼判断，使用一句简短 Javadoc 说明整体职责；只有方法包含多个关键阶段或容易误用时才增加必要细节，不逐字段解释参数和返回值。
- 注释优先解释“为什么这样写”和必须保持的约束，不逐行翻译语法，不重复清晰的命名，不为简单访问器、普通赋值或每个字段机械添加注释。
- 注释使用简体中文，靠近对应实现；以当前代码、契约和测试为依据，不把推测写成历史设计事实。代码变更时同步更新注释，删除或修正过时说明。
- 新增或修改 Java 代码时一并检查必要注释；不以注释数量、比例或全量模板覆盖作为验收目标。

## 前端规则

- 使用原生 CSS 和已有 CSS 自定义属性，不引入 Tailwind。
- PC 优先，使用 flex、grid 和 `minmax` 适配桌面宽度。
- 章节编辑器继续使用 `textarea`，自动保存延迟 1.2 秒。
- 字数统计统一使用 `countTextLength()`。
- Agent 聊天正文按普通段落文本渲染，不使用 Markdown 解析。

## 命令与验证

以下命令从仓库根目录执行。开发入口为 `npm run dev`，Web 构建为 `npm run build`；
Python 依赖使用 `uv sync --frozen --all-packages --group dev`。

| 修改范围 | 最低验证要求 |
| --- | --- |
| 前端 | 相关测试（`npm run test:web` 或对应测试文件）、`npm run typecheck`、`npm run lint` |
| Python | 相关 `uv run pytest`、`uv run ruff check .`；共享协议、鉴权或工作流修改还要运行下述 Mypy |
| Java | 相关 JUnit；提交前运行 `./mvnw verify`。数据库行为使用 PostgreSQL Testcontainers 或获准 dev 库，不得用 H2 证明兼容 |
| 公共接口 | `npm run api:generate`、`npm run api:check`，以及相关契约差异测试 |
| 部署配置／脚本 | `uv run pytest tests/architecture/test_compose_security.py`；有 Docker 时按对应环境的部署手册完成 Compose 健康检查 |
| 纯文档 | 检查引用、命令、事实归属和 `git diff --check`；不要求运行无关应用测试 |

共享协议、鉴权或工作流的 Mypy 命令：

```bash
uv run mypy apps/core-api/src apps/agent-service/src packages/service-contracts/src packages/service-auth/src
```
