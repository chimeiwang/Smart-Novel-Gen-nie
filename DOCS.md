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
- Java Core API 独占 PostgreSQL、认证、业务规则、计费、草案和 SSE；FastAPI Core 只保留回滚镜像。
- FastAPI Agent Service 负责 LangGraph、模型和工具执行，不连接数据库。
- Java Core 单体已于 2026-08-26 完成生产切换并处于观察期；生产不得双 Core 或双写，Python Core 只按
  已冻结流程用于整镜像回滚。
- Core 与 Agent 使用版本化 Pydantic 契约和 Ed25519 服务身份通信。
- 生产由 `infra/compose.yaml` 编排，Nginx 是唯一公网入口。
- 生产 SSH 只信任管理员离线核验的主机公钥；部署串行排队，切换前按运行容器的不可变镜像 ID 冻结三服务
  精确回滚组合，新版本失败时由 `scripts/deploy-production.sh` 尝试恢复该组合。
- PostgreSQL schema 默认冻结并由只读 `schema-contract.json` 守卫。当前具名例外包括视频控制面与章节
  改编域迁移 `20260807_video_production_control_plane.sql`、`20260817_video_review_decision_command.sql`、
  `20260817_video_domain_ownership_chain.sql`、`20260818_video_chapter_adaptation_domain.sql`，它们只允许对
  服务器端 `novelwriterdev` 开发库执行视频控制面、批准命令、章节改编域以及该域内视觉设定版本和逐镜参考绑定，
  不授权生产或完整 production_v2 schema。用户于 2026-08-23 另行批准
  `20260823_production_video_adaptation_domain.sql` 只向服务器端 `novelwriter` 正式库晋升这套已验证结构，
  不迁开发数据、不启用视频功能，也不授权完整 production_v2 schema。正式库当前保留视频结构，但
  `VIDEO_PREVIEW_ENABLED` 仍关闭，结构晋升不等同于功能开放。另有用户于 2026-08-21 明确批准的
  `20260821_token_usage_task_run.sql`，以及用户于 2026-08-23 明确批准的第二个迁移
  `20260823_token_usage_details.sql`；后者只能为 `TokenUsage` 增加可空 `INTEGER`
  `promptCacheMissTokens`/`reasoningTokens` 和三个 CHECK；无默认值、无回填、无索引，旧行保持 `NULL`。
  开发迁移只在服务器 dev PostgreSQL 受控执行并重复验证，随后从真实库只读导出
  `schema-contract.json`；生产 forward/rollback 只能由已审核部署门禁调用。它们不构成以后任意迁移的授权。
- `TokenUsage` 两个新增可空诊断字段已完成开发库迁移和真实库契约导出；生产迁移仍只允许使用固定
  forward/rollback、备份和自动回滚流程，不能改写为任意 SQL。
- 用户于 2026-08-24 批准的 `20260824_video_shot_render_p0.sql` 与
  `20260824_video_post_production_p1_p3.sql` 只允许对服务器端 `novelwriterdev` 开发库增加逐镜生成、
  Take、关键帧、粗剪、声音字幕和整集导出结构，并允许开发库 `VideoAsset.duty` 增加 `sfx` 与
  `episode_export`；它们不授权正式库 DDL、开发数据晋升、生产视频开关、图片生成或 TTS。
- 用户于 2026-08-27 先批准起草并在隔离 PostgreSQL 验证 `20260827_user_phone_identity.sql`，后进一步批准
  该具名脚本只对服务器端 `novelwriterdev` 开发库执行。开发库已在备份后成功执行两次并验证幂等，真实开发库
  contract 已导出；完整指纹为 `4f8cbf58820c7e601026012249f1896e4f8ad0231cfa6b9bd2fdad1c83c3d195`。
  用户随后于同日进一步明确批准：先备份，再将同一具名脚本对服务器端 `novelwriter` 正式库执行，并开启手机号
  登录和真实短信发送。脚本必须保持数据库名校验，正式库还必须提供精确确认令牌；该新增授权不包含其他生产
  DDL、手机号数据删除、老账号绑定或账号合并。正式库已在受保护备份后完成两次幂等迁移；迁移表所有者已对齐
  现有 `User` 表应用角色，真实正式库 contract 按“视频关闭、手机号开启”投影后与冻结契约零差异，指纹为
  `b5d2c319303f1ca52d411b8f986aa98a5d48168338c75c65d675d23968c22c78`。生产手机号登录和真实发送已开启，
  用户名新注册已关闭、旧密码登录保留；真实浏览器完整验证码登录仍须用户验收。

## 文档类型

| 类型 | 位置 | 规则 |
| --- | --- | --- |
| authority | 根目录 | 当前、简短、可执行 |
| current-requirement | `docs/requirements/` | 只描述当前产品事实 |
| architecture | `apps/agent-service/AGENTS.md`、`docs/*.md` | 必须与当前代码路径一致 |
| architecture-decision | `docs/architecture-decisions/` | 记录已接受且仍生效的关键架构取舍；改变决策必须新增或取代 ADR |
| spec | `docs/specs/` | 实现前写明目标、非目标、设计、影响和验收 |
| plan | `docs/plans/` | 一次性执行步骤，完成后归档 |
| audit | `docs/audits/` | 标明日期、状态和直接证据 |
| archive | `docs/archive/` | 只作历史追溯，不作为当前实现依据 |

## 修改规则

- 新需求先更新 spec，再修改代码或文档。
- 修改 Agent、SSE、ReviewArtifact 或服务契约后，同步检查 Agent 架构文档和 03、04 号需求文档。
- 修改日志、Studio 或部署入口后，同步检查日志文档、Studio 文档和 05 号需求文档。
- 修改接口后重新生成 TypeScript 客户端并执行 `npm run api:check`。
- 修改数据库访问代码时，除用户明确批准的版本化迁移外，只能核对现有结构契约；禁止自动数据
  定义语句。批准的迁移也必须先备份、在隔离 PostgreSQL 验证，再受控执行并导出新的
  `schema-contract.json`，迁移后的实际结构必须与该 contract 精确一致。
- 历史归档只在被触及时修正受影响部分，不要求一次性翻译全部历史内容。

## 当前入口

- 开发护栏：`AGENTS.md`
- 前端设计：`DESIGN.md`
- 项目概览：`README.md`
- 文档索引：`docs/README.md`
- Agent 架构：`apps/agent-service/AGENTS.md`
- 当前需求：`docs/requirements/00-overview.md`
- Java Core 替换规格：`docs/specs/2026-08-24-core-java-replacement.md`
- Java Core 架构决策：`docs/architecture-decisions/001-core-java-stack.md` 到
  `003-core-java-single-cutover.md`
- Java Core 生产切换：`docs/JAVA_CORE_CUTOVER.md`
- 生产部署：`infra/compose.yaml`
- 生产发布入口：`.github/workflows/build.yml`、`scripts/deploy-production.sh`
