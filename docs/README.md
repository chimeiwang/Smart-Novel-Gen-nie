# docs 目录索引

本目录只保留当前说明、当前需求和历史归档。文档治理规则见根目录 `DOCS.md`。

## 当前文档

本次 Java-only 清理结果见 [2026-09-12 审计](audits/2026-09-12-java-only-core-retirement.md)，
区分仓内回归、Windows 安装、受阻的 Compose 验证与未执行的生产发布。

| 文档 | 用途 |
| --- | --- |
| [../AGENTS.md](../AGENTS.md) | 仓库级开发规则、边界、必读入口与验证要求 |
| [../DOCS.md](../DOCS.md) | 文档治理、事实核对与内容归属 |
| [DATA_CHANGE_AUTHORIZATIONS.md](DATA_CHANGE_AUTHORIZATIONS.md) | 具名数据变更的授权范围、目标环境和原始规格索引 |
| [specs/2026-09-10-agents-document-governance.md](specs/2026-09-10-agents-document-governance.md) | 根开发指导职责治理及信息归属 |
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
| `specs/2026-09-09-java-comment-guidelines.md` | Java 必要注释的尺度与健康检查示例 |
| `specs/2026-08-27-aliyun-phone-auth.md` | 阿里云手机号短信登录、自动建号、老账号隔离与上线门禁规格 |
| `specs/2026-08-31-core-owned-durable-agent-execution.md` | Core 权威耐久 Agent 执行、计费、恢复与迁移基线 |
| `specs/2026-09-01-durable-agent-joint-drain.md` | V1/V2 新建入口关闭、联合 drain 快照与稳定零状态判定 |
| `specs/2026-09-01-durable-agent-v2-compose-e2e.md` | 本地隔离跨进程故障注入与脱敏证据边界 |
| `specs/2026-09-01-durable-agent-v2-operator-skill-update.md` | CLI 变化、V1/V2 结果恢复与 Operator Skill 更新清单 |
| `specs/2026-09-04-personal-durable-agent-release-scope.md` | 个人项目信任模型、最小发布流程与退役企业控制面清单 |
| `specs/2026-09-04-java-cli-operator-cutover.md` | macOS 两份 Operator Skill 的 Java CLI 实际入口、配置升级与验证 |
| `specs/2026-09-04-durable-natural-language-entry.md` | 普通新消息、同 Run 澄清、草案返工的持久化与 Web/CLI 分流 |
| `../tools/inkforge-cli-java/README.md` | Java CLI 构建、Windows／macOS Skill 安装入口与受限授权 |
| `DURABLE_AGENT_V2_ROLLOUT.md` | Durable Agent V2 人工迁移、contract 复验、allowlist canary 与回滚手册 |
| `JAVA_CORE_CUTOVER.md` | Java Core 单服务发布、验证和 V2 兼容 Java 回退手册 |
| `architecture-decisions/001-004` | Java 技术栈、契约优先、单 Core 切换与 Python 退役决策 |
| `specs/2026-09-12-java-only-core-contract-and-python-retirement.md` | Java 唯一契约、Python Core／CLI 退役与 Windows Operator 切换 |
| `specs/2026-08-08-novel-to-video-product-architecture.md` | 长篇小说视频制作系统的产品与架构基线 |
| `specs/2026-08-08-novel-to-video-detailed-design.md` | 长篇小说视频制作系统的数据、接口、工作台与迁移详细设计 |
| `specs/2026-08-17-video-preview-hardening.md` | 视频开发预览的数据库约束、结构守卫、生产关闭与真实并发验收 |
| `specs/2026-09-09-serial-drama-production-product-plan.md` | 连载短剧／漫剧生产级产品规划草案：剧集流程、素材与声音、成本恢复、首发范围及验收 |
| `specs/2026-09-09-seedance-25-lore-visual-production.md` | Seedance 2.5 国内官方接口规划：设定定妆、多模态参考、原生声音、生成片段、编辑与延长 |
| `specs/2026-09-09-video-production-redesign.md` | 已落地的视频交互设计：独立分集、单集剧本、三条创作场景、制作基线与返工影响 |
| `specs/2026-09-10-video-episode-production-implementation.md` | 剧集重构实施规格：数据关系、公共契约、V2 接入、共享引用与验收结果 |
| `plans/2026-09-10-video-episode-production-rebuild.md` | 已执行的剧集重构分批计划：准备、剧本、分镜返工、素材后期和旧入口退出 |
| `audits/2026-09-10-video-episode-production-p0.md` | 剧集重构开工现场、暂停补丁取舍、旧入口与共享依赖保护清单 |
| `audits/2026-09-10-video-p3-media-provider-boundary.md` | P3 媒体旧链复用／退役清单、供应商中立适配和默认模拟验证 |
| `audits/2026-09-10-video-episode-production-final.md` | Episode 视频 P0～P4 本地隔离验收、全量门禁、媒体证据与上线前剩余门槛 |
| `specs/2026-09-09-video-v01-v02-implementation.md` | 已暂停的定妆与模拟单镜实施范围；未提交补丁待新设计审视 |
| `plans/2026-09-09-video-product-release-plan.md` | 已被新设计取代的原 V0.1／V0.2 版本计划与估算 |
| `specs/` | 后续需求 spec；先写 spec，再执行修改 |
| `plans/2026-07-13-python-backend-rewrite-handoff.md` | 历史 Python 后端重构记录，非当前实施入口 |

Agent Service 当前架构见 `../apps/agent-service/AGENTS.md`。

## 历史归档

`archive/**` 只用于追溯历史决策。归档文档不作为当前实现依据。

如果归档文档中仍有有效规则，必须迁入当前权威文档后才能作为规则使用。
