# 文档规范与权威索引

本文件是仓库文档治理权威。所有新增或修改的自然语言内容必须使用简体中文；代码标识符、协议字段、命令、路径、环境变量和第三方专名除外。

## 项目事实优先级

发生冲突时按以下顺序判断：

1. 当前代码、`apps/core-api/src/inkforge_core/db/schema-contract.json`、共享服务契约、生成客户端和测试。
2. 根级权威：`AGENTS.md`、`DOCS.md`、`DESIGN.md`。
3. 当前架构与需求：`apps/agent-service/AGENTS.md`、`docs/requirements/00-overview.md` 到 `05-auth-billing-and-ops.md`、`docs/LANGGRAPH_STUDIO.md`、`docs/WORKFLOW_EVENT_LOG_FORMAT.md`。
4. `docs/specs/**` 中尚未完成或曾用于实现的设计规格。
5. 计划、审计和 `docs/archive/**` 历史材料。

铁律：项目事实高于文档历史。不得为了保留旧文档说法而改歪实现。

## 当前架构事实

- Next.js 只负责页面、SSR/SEO 和浏览器交互。
- FastAPI Core API 独占 PostgreSQL、认证、业务规则、计费、草案和 SSE。
- FastAPI Agent Service 负责 LangGraph、模型和工具执行，不连接数据库。
- Core 与 Agent 使用版本化 Pydantic 契约和 Ed25519 服务身份通信。
- 生产由 `infra/compose.yaml` 编排，Nginx 是唯一公网入口。
- PostgreSQL schema 不允许在本重构中修改；当前结构由只读 `schema-contract.json` 守卫。

## 文档类型

| 类型 | 位置 | 规则 |
| --- | --- | --- |
| authority | 根目录 | 当前、简短、可执行 |
| current-requirement | `docs/requirements/` | 只描述当前产品事实 |
| architecture | `apps/agent-service/AGENTS.md`、`docs/*.md` | 必须与当前代码路径一致 |
| spec | `docs/specs/` | 实现前写明目标、非目标、设计、影响和验收 |
| plan | `docs/plans/` | 一次性执行步骤，完成后归档 |
| audit | `docs/audits/` | 标明日期、状态和直接证据 |
| archive | `docs/archive/` | 只作历史追溯，不作为当前实现依据 |

## 修改规则

- 新需求先更新 spec，再修改代码或文档。
- 修改 Agent、SSE、ReviewArtifact 或服务契约后，同步检查 Agent 架构文档和 03、04 号需求文档。
- 修改日志、Studio 或部署入口后，同步检查日志文档、Studio 文档和 05 号需求文档。
- 修改接口后重新生成 TypeScript 客户端并执行 `npm run api:check`。
- 修改数据库访问代码时，只能核对现有结构契约；禁止新增迁移或自动数据定义语句。
- 历史归档只在被触及时修正受影响部分，不要求一次性翻译全部历史内容。

## 当前入口

- 开发护栏：`AGENTS.md`
- 前端设计：`DESIGN.md`
- 项目概览：`README.md`
- 文档索引：`docs/README.md`
- Agent 架构：`apps/agent-service/AGENTS.md`
- 当前需求：`docs/requirements/00-overview.md`
- 生产部署：`infra/compose.yaml`
