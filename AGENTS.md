# InkForge 开发指导

后续所有对话、注释、文档、备注和提交信息必须使用简体中文。回答必须清晰、诚实、明确，不能为了迎合用户忽略事实。

## 权威与流程

- 根目录 `DOCS.md` 是文档治理权威。
- 项目事实优先级：当前代码、数据库结构契约、共享服务契约、生成的 OpenAPI 客户端和测试，高于历史文档。
- 接到新需求后，先在 `docs/specs/` 新增或更新 spec，再修改实现。
- 修改前端 UI 前先读 `DESIGN.md`。
- 修改 Agent、写作流程或草案审核前先读 `apps/agent-service/AGENTS.md`、`docs/requirements/03-ai-writing-and-agents.md` 和 `docs/requirements/04-review-quality-and-workflow.md`。
- 修改 Java Core、CLI 迁移、兼容基线或部署切换前先读
  `docs/specs/2026-08-24-core-java-replacement.md`、`docs/plans/2026-08-24-core-java-tdd-replacement.md` 和
  `docs/architecture-decisions/001-core-java-stack.md` 到 `003-core-java-single-cutover.md`。
- PostgreSQL schema 默认冻结。已批准例外包括
  `scripts/migrations/20260807_video_production_control_plane.sql`、
  `scripts/migrations/20260817_video_review_decision_command.sql`、
  `scripts/migrations/20260817_video_domain_ownership_chain.sql` 与
  `scripts/migrations/20260818_video_chapter_adaptation_domain.sql` 对服务器端
  `novelwriterdev` 开发库执行视频预览控制面、批准命令、章节改编域以及该改编域内视觉设定版本、逐镜参考绑定的具名迁移；
  这些视频迁移不构成生产迁移或完整 production_v2 schema 授权。用户于 2026-08-23 另行批准
  `scripts/migrations/20260823_production_video_adaptation_domain.sql` 只对服务器端 `novelwriter`
  正式库执行上述已验证结构的具名晋升；该脚本不迁移开发数据、不启用视频功能，也不授权其他生产 DDL。
  用户于 2026-08-21 明确批准 `scripts/migrations/20260821_token_usage_task_run.sql`；用户于 2026-08-23
  另行批准 `scripts/migrations/20260823_token_usage_details.sql` 及其固定生产 forward/rollback，只为
  `TokenUsage` 增加可空 `INTEGER` `promptCacheMissTokens`/`reasoningTokens` 和三个 CHECK；无默认值、无回填、
  无索引，旧行保持 `NULL`。这组迁移只能通过已审核的具名脚本和部署门禁执行，不授权其他结构调整。
  用户于 2026-08-24 批准 `scripts/migrations/20260824_video_shot_render_p0.sql` 只对服务器端
  `novelwriterdev` 开发库新增逐镜 Seedance 耐久任务、不可变候选 Take、Take head 与确认命令；同日进一步
  批准 `scripts/migrations/20260824_video_post_production_p1_p3.sql` 只对该开发库新增受控 Take 抽帧来源事实、
  逐镜关键帧版本、分集非破坏性粗剪版本、声音/字幕版本及耐久整集导出任务，并为现有
  `VideoAsset.duty` 增加 `sfx` 与 `episode_export`。这两个 20260824 视频迁移不得对 `novelwriter` 正式库
  执行，不迁移开发数据、不启用生产功能，也不授权图片生成、TTS 或旧
  `VideoScene`/`VideoGenerationTask` 公共语义复活。用户于 2026-08-27 先批准起草并在隔离 PostgreSQL
  验证 `scripts/migrations/20260827_user_phone_identity.sql`，后进一步明确批准该具名脚本只对服务器端
  `novelwriterdev` 开发库执行。该开发迁移已在迁移前备份后成功执行两次并验证幂等，真实开发库已只读导出包含
  `UserPhoneIdentity` 的 `schema-contract.json`，完整指纹为
  `4f8cbf58820c7e601026012249f1896e4f8ad0231cfa6b9bd2fdad1c83c3d195`。用户随后于同日进一步明确批准：
  备份后将同一具名脚本对服务器端 `novelwriter` 正式库执行，并开启手机号登录与真实短信发送。脚本必须保持
  数据库名校验，正式库执行还必须提供精确确认令牌；迁移创建的 `UserPhoneIdentity` 必须在同一事务内将所有者
  对齐到现有 `User` 表所有者，以保证应用角色的最小读写权限。该授权不包含其他生产 DDL、手机号数据删除、
  老账号绑定或账号合并。正式库已在受保护备份后完成两次幂等迁移，所有者已对齐应用角色，70 张表的真实
  contract 在“视频关闭、手机号开启”投影下与冻结契约零差异，投影指纹为
  `b5d2c319303f1ca52d411b8f986aa98a5d48168338c75c65d675d23968c22c78`；生产手机号登录与真实发送开关已开启，
  用户名新注册已关闭，老账号密码登录保留。任何其他持久化改动必须先更新 spec 和本文件、
  核对 `apps/core-api/src/inkforge_core/db/schema-contract.json`，应用启动仍不得自动建表、删表或执行迁移。

## 产品基线

- `docs/requirements/00-overview.md` 是当前产品功能、可用状态、限制和 Java 重写验收基线。修改产品、
  公共/内部接口、CLI、视频或迁移方案前必须先读；详细规则继续以 `requirements/01-05` 和当前代码为准。
- 产品是桌面优先的中文小说创作工作台，当前有三条主链：中短篇双文档写作、长篇章节与多 Agent
  写作、长篇章节影视化。代码实现、开发环境可用、生产开放、内部能力和历史兼容必须明确区分，
  不得把“表存在”或“代码已写”宣传为线上已开放。
- `short_medium` 硬限制 6,000～80,000 字，创建时必须保存完整起始素材；只使用蓝图和正文两份
  工作稿，自动保存不创建版本，Agent 文档生成只产生待采用候选，全文检查只产生报告；中短篇不开放视频。
- `long_serial` 使用多章节、创作资料、三层结构化大纲、写作会话、5 个核心 Agent、ReviewArtifact
  和一致性终检。前端显示的 30 万～100 万字、80～300 章属于规划建议，不是 Core 硬上限。
- 当前商业化缺口包括邮箱、账号找回、在线支付、管理员后台、团队协作、移动端、内容发布分发；手机号认证代码、
  开发库与正式库迁移、公开协议、真实短信送达测试和生产启用已完成，真实浏览器完整登录仍待用户验收。
- 章节影视化完整开发链为“章节快照 → Scene/Beat/Shot 人工审镜 → 分集 → 视觉设定版本 → 逐镜
  提示词 → 关键帧 → Seedance Take → 粗剪 → 声音字幕 → 整集导出”。生产必须保持
  `VIDEO_PREVIEW_ENABLED=false`，并拒绝视频调度和真实 Seedance；P0-P3 只获开发库授权，不支持
  图片生成、TTS 或旧 `VideoScene`/`VideoGenerationTask` 公共语义复活。
- 基线提交 `c9afc95` 有 148 个公共 Core 操作、30 个内部 Core 操作和 125 个 CLI 命令；当前公共 Core
  在此基础上增加 2 个受配置门禁的手机号认证操作，共 150 个。CLI 不是公共 API 全量镜像；现行生产 Java CLI 支持
  macOS Keychain 与 Windows Credential Manager，均禁止明文回退。若接口、命令或结构发生获批变化，
  必须重新计算并同步产品基线，不能机械维护旧数字。
- Java Core 已于 2026-08-26 单切生产并处于观察期：生产始终只有一个 Core，不双 Core、不双写；Python
  Core 只保留整镜像回滚，Python Agent 保留，Web 继续遵守 Next.js 现有边界。手机号认证已在切换后另立
  spec 实施；开发库与正式库具名迁移、备份、契约复验和生产启用均已完成，生产仍须保持旧密码登录回退，且不得
  因手机号开放而启用任何视频能力。

## 当前架构

```text
浏览器 -> Nginx -> Next.js 页面与 SSR
              -> Core API 公共接口与 SSE -> PostgreSQL
                                         -> Redis
                         Core API <-> Agent Service
                                         -> Redis
```

- `apps/web`：Next.js 16，仅页面、SSR/SEO、浏览器交互和生成客户端，不得包含业务 API、Server Actions、数据库客户端或模型运行时。
- `apps/core-api-java`：当前生产 Core，独占 PostgreSQL 访问、浏览器认证、归属校验、业务规则、ReviewArtifact、计费和 SSE。
- `apps/core-api`：FastAPI Core 回滚镜像与公共契约来源，不与 Java Core 并行运行。
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

Java 迁移工程建立后统一使用：

```bash
./mvnw verify
```

## 不可突破的边界

- 禁止静默截断正文、草案、工具结果、Agent 回复、日志或持久化数据。
- 正式内容变更必须遵循 `proposal -> ReviewArtifact -> 复审/返工 -> 用户确认 -> Core API 应用`。
- 正文、章节进展、故事进展、设定、大纲、伏笔、Beat Plan、视频方案和后期决定是不同数据层，
  不得为方便实现互相覆盖或混写。
- 选区、章节改编、提示词、渲染和导出必须冻结可重建的来源版本、哈希或不可变清单；历史版本只读，
  恢复和修改必须创建新版本。
- 写入口优先使用稳定 `clientRequestId` 幂等，状态 head 使用时间戳或 revision CAS；异步 202、SSE 或
  JSONL 只表示受理/观察，完成状态必须回读 PostgreSQL 权威结果。
- 节奏、景别、空镜、平均时长和风格等软质量建议不得无证据升级为硬门禁或替代作者确认。
- Agent Service 只能通过 Core 内部工具网关读写业务数据，不得连接 PostgreSQL。
- 内部接口统一位于 `/internal/v1/**`，同时校验直接对端网段和 Ed25519 服务令牌；不得信任转发头决定内部身份。
- 浏览器只访问 `/api/v1/**`，不得访问内部接口。
- 新增或修改公共接口时，先改 FastAPI/Pydantic 契约，再运行 `npm run api:generate`，禁止手写重复 TypeScript DTO。
- Java 迁移期间公共接口以版本化 Python OpenAPI 基线为准；Java 不得依赖注解默认输出碰巧兼容，
  必须通过契约差异测试。获批切换前不得删除 Python 契约或基线测试。
- Java 业务模块拥有自身 Agent 出站应用端口，`agentgateway` 只能单向依赖并实现这些端口；视频、写作、
  质量等业务模块不得反向导入 `AgentServiceClient` 或网关异常。`operations` 只托管后台生命周期，受数据库、
  Redis 或供应商配置门禁的协作者缺失时不得让最小健康上下文装配失败。
- 新增 Agent 工具必须注册到 `apps/agent-service/src/inkforge_agents/tools/registry.py`，同时声明权限和并发属性。
- 模型工具循环只能位于 `AgentRuntime`，LangGraph 编排只能使用现有 `StateGraph`、`Send`、`Command` 和 `interrupt()` 扩展。
- 2 核 2 GB 部署默认每个 Python 服务一个 worker；Agent 在单进程内最多并行三个不同项目的队列任务，
  同一 `novelId` 同时只能执行一个任务，并通过同一 `AGENT_MAX_CONCURRENCY` 全局限制最多三个模型调用，配置为 1 时回退串行。

## 前端规则

- 使用原生 CSS 和已有 CSS 自定义属性，不引入 Tailwind。
- PC 优先，使用 flex、grid 和 `minmax` 适配桌面宽度。
- 章节编辑器继续使用 `textarea`，自动保存延迟 1.2 秒。
- 字数统计统一使用 `countTextLength()`。
- Agent 聊天正文按普通段落文本渲染，不使用 Markdown 解析。

## 验证要求

- 前端修改至少运行相关测试、`npm run typecheck` 和 `npm run lint`。
- Python 修改至少运行相关 pytest、Ruff；共享协议、鉴权或工作流修改还要运行 Mypy。
- Java 修改至少运行相关 JUnit；提交前运行 `./mvnw verify`。数据库行为必须使用 PostgreSQL
  Testcontainers 或获准的 dev 数据库，不得用 H2 证明兼容。
- 部署修改运行 `tests/architecture/test_compose_security.py`，有 Docker 的环境再运行 Compose 健康检查。
- 除用户明确批准的版本化迁移外，数据库结构只能做只读指纹校验，不能为了让测试通过修改数据库；
  已批准迁移完成后必须重新导出 contract，并保持实际结构与 contract 精确一致。
