# 文档规范与权威索引

本文件是仓库文档治理权威。所有新增或修改的自然语言内容必须使用简体中文；代码标识符、协议字段、命令、路径、环境变量和第三方专名除外。

## 项目事实优先级

发生冲突时按以下顺序判断：

1. 当前代码、`apps/core-api/src/inkforge_core/db/schema-contract.json`、共享服务契约、生成客户端和测试。
2. 各自职责范围内的根级权威：`AGENTS.md`、`DOCS.md`、`DESIGN.md`。
3. 当前架构与需求：`apps/agent-service/AGENTS.md`、`docs/requirements/00-overview.md` 到 `05-auth-billing-and-ops.md`，以及对应的架构、协议和运维文档。
4. `docs/specs/**` 中适用于当前任务的设计规格；先读状态、非目标及取代关系。
5. 计划、审计和 `docs/archive/**` 历史材料。

项目事实高于文档历史，不得为了保留旧文档说法而改歪实现。这个排序用于判断已实现行为，不替代用户授权、
开发约束或功能开放门禁；源码、已安装包和实际部署状态分别核对，不能互相代证。

## 内容归属

| 内容 | 维护位置 | 维护规则 |
| --- | --- | --- |
| 仓库级开发指导 | [AGENTS.md](AGENTS.md) | 只保留可执行规则、关键禁令、必读入口与验证要求 |
| 文档治理与分工 | 本文件 | 定义事实核对、文档归属和维护方式，不复制产品或发布快照 |
| 前端设计 | [DESIGN.md](DESIGN.md) | 维护界面与交互规范 |
| 产品能力、限制、数量基线 | [产品总览](docs/requirements/00-overview.md)及 `docs/requirements/01-05` | 区分实现、开发、生产、内部与历史兼容；数量按代码和契约重算 |
| 服务架构与协议 | [Agent 指导](apps/agent-service/AGENTS.md)、`docs/*.md` | 与当前代码路径一致；局部实现约束放在相应领域 |
| 架构取舍 | `docs/architecture-decisions/` | 记录已接受且仍生效的决策；改变决策时新增或取代 ADR |
| 新需求与变更设计 | `docs/specs/` | 实现前写目标、非目标、设计、影响与验收，维护当前状态及取代关系 |
| 数据变更授权 | [授权清单](docs/DATA_CHANGE_AUTHORIZATIONS.md)及对应具名 spec | 索引记录对象、环境与范围，spec 保留完整授权和门禁；不因文档迁移扩大或撤销授权 |
| 运维执行步骤 | `docs/*ROLLOUT.md`、`docs/*CUTOVER.md` 及专题运维文档 | 说明前置条件、适用环境、执行和恢复步骤；历史示例不自动适用于当前生产 |
| 一次性计划 | `docs/plans/` | 维护执行步骤，完成后归档 |
| 验收与发布证据 | `docs/audits/` | 标明日期、环境、状态和直接证据；部署 SHA、指纹、canary 结果在此追溯 |
| 历史材料 | `docs/archive/`、已有 spec／计划中的历史记录 | 只作追溯，不作为当前实现或新一轮执行指令 |

已有 spec 中的验收记录可原位保留并被索引引用，不为整理根文件再次复制。新验收记录优先放审计文档。

## 修改规则

- 新需求先更新 spec，再修改代码或文档。
- 根 `AGENTS.md` 只在通用开发规则改变时更新；不得追加产品清单、API／CLI 数量、部署 SHA、数据库指纹、
  逐次授权或验收流水。产品规则变化更新需求；授权范围变化更新具名 spec 与授权清单；执行结果更新审计。
- 本规则取代历史文档中“每次产品基线或持久化变更都必须更新根 AGENTS.md”的维护要求。
  仅迁移规则的记录位置，原有内容保护、环境范围、迁移门禁及用户授权边界继续生效。
- 修改 Agent、SSE、ReviewArtifact 或服务契约后，同步检查 Agent 指导和 03、04 号需求文档。
- 修改日志、Studio 或部署入口后，同步检查日志文档、Studio 文档和 05 号需求文档。
- 修改公共接口后重新生成 TypeScript 客户端并执行 `npm run api:check`；同步受影响的产品基线，不能机械保留旧数字。
- 数据库访问代码只核对现有结构契约；只有用户明确批准的具名迁移可改变结构。执行前按授权清单读取具体范围，
  完成备份、隔离 PostgreSQL 验证及受控执行，随后从目标库导出并复验 `schema-contract.json`。应用不得自动 DDL。
- 历史归档只在被触及时修正受影响部分，不要求一次性翻译或重写全部历史内容。
- 文档修改检查链接、命令、状态口径和重复事实，运行 `git diff --check`；无代码改动时不要求无关应用测试。

## 常用入口

- [项目概览](README.md)与[完整文档索引](docs/README.md)
- [开发指导](AGENTS.md)、[前端设计](DESIGN.md)、[产品总览](docs/requirements/00-overview.md)
- [Agent 指导](apps/agent-service/AGENTS.md)、[日志格式](docs/WORKFLOW_EVENT_LOG_FORMAT.md)、[Studio](docs/LANGGRAPH_STUDIO.md)
- [Java Core 替换规格](docs/specs/2026-08-24-core-java-replacement.md)、[架构决策目录](docs/architecture-decisions/)、[Java 切换手册](docs/JAVA_CORE_CUTOVER.md)
- [耐久执行规格](docs/specs/2026-08-31-core-owned-durable-agent-execution.md)、[V2 运维手册](docs/DURABLE_AGENT_V2_ROLLOUT.md)
- [Java CLI 文档](tools/inkforge-cli-java/README.md)、[Operator 更新契约](docs/specs/2026-09-01-durable-agent-v2-operator-skill-update.md)
- [数据变更授权清单](docs/DATA_CHANGE_AUTHORIZATIONS.md)、[运维需求](docs/requirements/05-auth-billing-and-ops.md)、[发布审计目录](docs/audits/)
- [生产编排](infra/compose.yaml)、[构建流程](.github/workflows/build.yml)、[生产发布脚本](scripts/deploy-production.sh)
