# docs 目录索引

本目录只保留当前说明、当前需求和历史归档。文档治理规则见根目录 `DOCS.md`。

## 当前文档

| 文档 | 用途 |
| --- | --- |
| `REQUIREMENTS.md` | 当前需求入口索引 |
| `requirements/00-overview.md` | 当前产品功能、可用状态、限制与 Java 重写验收基线 |
| `requirements/01-projects-and-chapters.md` | 项目与章节 |
| `requirements/02-creative-knowledge-base.md` | 创作资料库 |
| `requirements/03-ai-writing-and-agents.md` | AI 写作与 Agent |
| `requirements/04-review-quality-and-workflow.md` | 草案审核、质量检查与工作流 |
| `requirements/05-auth-billing-and-ops.md` | 认证、计费与运维 |
| `LANGGRAPH_STUDIO.md` | Python LangGraph Studio 调试边界 |
| `WORKFLOW_EVENT_LOG_FORMAT.md` | 人工工作流日志格式 |
| `BACKLOG.md` | 后续能力备忘，不代表当前承诺 |
| `specs/2026-08-24-core-java-replacement.md` | Java Core 单体替换范围、TDD、dev 数据库与部署验收规格 |
| `specs/2026-08-27-aliyun-phone-auth.md` | 阿里云手机号短信登录、自动建号、老账号隔离与上线门禁规格 |
| `specs/2026-08-31-core-owned-durable-agent-execution.md` | Core 权威耐久 Agent 执行、计费、恢复与发布安全基线 |
| `specs/2026-09-01-durable-agent-v2-release-workflow.md` | 受保护 Durable Agent V2 发布事务与 fail-closed 门禁 |
| `specs/2026-09-01-durable-agent-v2-compose-e2e.md` | 本地隔离跨进程故障注入与脱敏证据边界 |
| `specs/2026-09-01-durable-agent-v2-operator-skill-update.md` | CLI 变化、V1/V2 结果恢复与 Operator Skill 更新清单 |
| `specs/2026-09-01-durable-agent-v2-development-evidence-v2.md` | 迁移资格与每提交开发 evidence v2 的离线严格契约 |
| `specs/2026-09-01-durable-agent-v2-ssh-genesis-trust-root.md` | 生产 SSH attestation/broker 与首个 receipt 信任根契约 |
| `JAVA_CORE_CUTOVER.md` | Java Core 单服务生产切换、验证和历史 Python 回退手册 |
| `architecture-decisions/001-003` | Java 技术栈、契约优先和生产单 Core 切换决策 |
| `specs/2026-08-08-novel-to-video-product-architecture.md` | 长篇小说视频制作系统的产品与架构基线 |
| `specs/2026-08-08-novel-to-video-detailed-design.md` | 长篇小说视频制作系统的数据、接口、工作台与迁移详细设计 |
| `specs/2026-08-17-video-preview-hardening.md` | 视频开发预览的数据库约束、结构守卫、生产关闭与真实并发验收 |
| `specs/` | 后续需求 spec；先写 spec，再执行修改 |
| `plans/2026-07-13-python-backend-rewrite-handoff.md` | Python 后端重构当前剩余任务与接手入口 |

Agent Service 当前架构见 `../apps/agent-service/AGENTS.md`。

## 历史归档

`archive/**` 只用于追溯历史决策。归档文档不作为当前实现依据。

如果归档文档中仍有有效规则，必须迁入当前权威文档后才能作为规则使用。
