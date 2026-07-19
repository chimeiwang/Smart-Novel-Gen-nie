# 中短篇会话与版本工作台实施计划

> **执行要求：** 逐项使用测试驱动方式实现；每完成一组任务就运行对应验证，最后执行完整回归与真实浏览器验收。

**目标：** 将中短篇工作区改造成可新建/续接会话、可独立浏览大纲与正文历史版本、可在聊天中精确引用任意版本继续讨论或微调的三栏工作台。

**架构：** 继续复用 `WritingSession` 保存会话，复用 `ReviewArtifactRevision` 保存不可变版本，不修改 PostgreSQL schema。Core 负责项目级版本索引、引用校验、采用状态与并发约束；Agent Service 负责讨论/改纲/改正文三类意图及精确版本读取；Web 只使用生成客户端渲染三栏界面和发起操作。

**技术栈：** FastAPI、Pydantic、SQLAlchemy、LangGraph、Next.js 16、React、原生 CSS、Vitest、pytest。

---

## 任务 1：扩展共享契约与 OpenAPI

**文件：**
- 修改：`packages/service-contracts/src/inkforge_contracts/jobs.py`
- 修改：`packages/service-contracts/src/inkforge_contracts/short_story.py`
- 修改：`apps/core-api/src/inkforge_core/reviews/schemas.py`
- 修改：`apps/core-api/src/inkforge_core/writing/schemas.py`
- 测试：`packages/service-contracts/tests/test_short_story_contracts.py`
- 测试：`apps/core-api/tests/reviews/test_short_story_version_schemas.py`

- [ ] 先添加失败测试，覆盖强类型版本引用、版本列表/详情、会话消息附件和中短篇自由讨论操作。
- [ ] 新增 `ShortStoryVersionReference`、`ShortStoryVersionListItem`、`ShortStoryVersionDetail` 与工作区版本聚合字段。
- [ ] 扩展写作启动/消息命令，持久化用户原文、显式版本引用与中短篇路由结果。
- [ ] 保持长篇现有请求兼容，禁止前端手写重复 DTO。
- [ ] 运行共享契约与 Core schema 测试。

## 任务 2：实现项目级大纲/正文版本引擎

**文件：**
- 修改：`apps/core-api/src/inkforge_core/reviews/repository.py`
- 修改：`apps/core-api/src/inkforge_core/reviews/service.py`
- 修改：`apps/core-api/src/inkforge_core/reviews/router.py`
- 修改：`apps/core-api/src/inkforge_core/reviews/internal_router.py`
- 修改：`apps/core-api/src/inkforge_core/reviews/apply.py`
- 修改：`apps/core-api/src/inkforge_core/reviews/formal_writes.py`
- 修改：`apps/core-api/src/inkforge_core/reviews/short_story_artifacts.py`
- 测试：`apps/core-api/tests/reviews/test_short_story_project_versions.py`
- 测试：`apps/core-api/tests/reviews/test_short_story_version_references.py`

- [ ] 先添加失败测试，证明跨任务/跨会话的大纲与正文 revision 不重置，内容不变时不增版。
- [ ] 短篇专用地复用同一项目、同一 kind 的 ReviewArtifact，并在新持久任务启动时重新绑定 task/run；不放宽长篇状态机。
- [ ] 提供大纲/正文版本列表与详情接口，返回来源会话、来源大纲、修改摘要、hash、审核结果与时间。
- [ ] 从已采用 Outline 内容和正式 Chapter 内容推导当前采用大纲/正式正文版本，明确区分“最新版”和“当前采用版”。
- [ ] 校验版本引用的作品归属、kind、revision 与 hash；不存在或不一致时在模型调用前失败。
- [ ] 确保批准历史版本只改变当前采用内容，不删除版本；批准后仍允许新任务生成后续版本。
- [ ] 添加项目级单模型任务互斥与过期基线检查。
- [ ] 运行 Core 版本、应用事务和兼容性测试。

## 任务 3：让中短篇复用 WritingSession 会话语义

**文件：**
- 修改：`apps/core-api/src/inkforge_core/writing/router.py`
- 修改：`apps/core-api/src/inkforge_core/writing/service.py`
- 修改：`apps/core-api/src/inkforge_core/writing/repository.py`
- 修改：`apps/core-api/src/inkforge_core/writing/tasks.py`
- 测试：`apps/core-api/tests/writing/test_short_story_sessions.py`
- 测试：`apps/core-api/tests/writing/test_short_story_commands.py`

- [ ] 先添加失败测试，覆盖新会话固定当前采用版本、续接旧会话、原文与附件持久化、普通讨论无 Artifact。
- [ ] 新会话通过现有 WritingSession 创建，并在首条 metadata 中固定作品信息、灵感、锚点、当前采用大纲和正式正文引用。
- [ ] 续接会话恢复同一 session 的消息和绑定任务，不复制其他会话历史。
- [ ] 写作命令稳定快照记录显式引用、解析后的引用和用户原文。
- [ ] 只读讨论命令可返回 Agent 消息且不进入 ReviewArtifact 流程。
- [ ] 运行会话、命令、SSE 恢复相关测试。

## 任务 4：实现 Agent 讨论路由与精确版本读取

**文件：**
- 修改：`apps/agent-service/src/inkforge_agents/jobs/writing.py`
- 修改：`apps/agent-service/src/inkforge_agents/short_story/story_graph.py`
- 修改：`apps/agent-service/src/inkforge_agents/short_story/context.py`
- 修改：`apps/agent-service/src/inkforge_agents/clients/core.py`
- 修改：`apps/agent-service/src/inkforge_agents/tools/registry.py`
- 新增：`apps/agent-service/src/inkforge_agents/tools/short_story_versions.py`
- 测试：`apps/agent-service/tests/short_story/test_short_story_chat_routing.py`
- 测试：`apps/agent-service/tests/short_story/test_short_story_version_context.py`
- 测试：`apps/agent-service/tests/tools/test_short_story_version_tool.py`

- [ ] 先添加失败测试，覆盖普通讨论、改纲、改正文、显式附件优先级和自然语言版本引用。
- [ ] 增加中短篇自由会话路由，模型只可选择讨论、改纲、改正文三类合法行为，不用前端关键词猜测。
- [ ] 上下文按已确认优先级组装，只带精简版本索引与当前会话近期消息。
- [ ] 注册只读历史版本工具，通过 Core 内部网关读取精确 payload；Agent Service 不接触数据库。
- [ ] 对自然语言中的“纲 vN/正文 vN”执行唯一解析；缺失、歧义或冲突时停止并明确说明。
- [ ] 讨论只返回消息；改纲提交完整大纲新版本；改正文提交完整正文并继续现有双审核/一次自动返工规则。
- [ ] 运行 Agent 路由、上下文、工具和短篇图测试。

## 任务 5：生成客户端并建立前端会话/版本模型

**文件：**
- 生成：`packages/api-client/src/generated/**`
- 新增：`apps/web/src/features/workspace/short-story/short-story-version-model.ts`
- 新增：`apps/web/src/features/workspace/short-story/short-story-session-model.ts`
- 测试：`apps/web/src/features/workspace/__tests__/short-story-version-model.test.ts`
- 测试：`apps/web/src/features/workspace/__tests__/short-story-session-model.test.ts`

- [ ] 运行 `npm run api:generate`，禁止手写 DTO。
- [ ] 先添加失败测试，覆盖版本排序、采用状态、正文来源大纲、附件去重和会话恢复。
- [ ] 建立纯函数模型，把生成 DTO 转换为左栏版本轨道、当前查看对象和聊天附件。
- [ ] 复用长篇会话的加载/新建/选择/恢复语义，避免复制其整块页面组件。
- [ ] 运行模型测试与 `npm run api:check`。

## 任务 6：重构中短篇三栏工作区

**文件：**
- 修改：`apps/web/src/features/workspace/short-story/short-story-workspace.tsx`
- 修改：`apps/web/src/features/workspace/short-story/short-story-workspace.css`
- 新增：`apps/web/src/features/workspace/short-story/short-story-left-rail.tsx`
- 新增：`apps/web/src/features/workspace/short-story/short-story-content-pane.tsx`
- 新增：`apps/web/src/features/workspace/short-story/short-story-chat-pane.tsx`
- 修改/替换：`apps/web/src/features/workspace/short-story/short-story-outline-conversation.tsx`
- 测试：`apps/web/src/features/workspace/__tests__/short-story-layout-source.test.ts`
- 测试：`apps/web/src/features/workspace/__tests__/short-story-chat-pane.test.tsx`
- 测试：`apps/web/src/features/workspace/__tests__/short-story-version-navigation.test.tsx`

- [ ] 先更新失败测试，强制左栏只放进度和两类版本，中栏顶部放标题/篇幅/内容操作，右栏只放会话。
- [ ] 左栏展示大纲和正文版本轨道、状态、摘要、来源关系，并支持打开和“在对话中引用”。
- [ ] 中栏展示完整版本内容；标题和可选篇幅参考只位于顶部；批准/采用/生成整稿等操作跟随当前内容。
- [ ] 右栏实现历史对话、新建对话、续接旧对话、消息流、版本附件标签与输入框。
- [ ] 批准后输入框仍可用；普通讨论、引用历史版本和继续微调不被状态按钮阻断。
- [ ] 所有状态、操作、错误使用中文展示，保留内部枚举但不泄漏到界面。
- [ ] 用 `minmax` 调整桌面三栏宽度，保证作品信息和正文阅读区不再过窄。
- [ ] 运行相关 Vitest、完整 `npm run test:web`、typecheck 和 lint。

## 任务 7：完整回归与真实浏览器验收

**文件：**
- 更新：`docs/specs/2026-07-18-short-medium-writing-workflow.md`
- 更新：`docs/requirements/03-ai-writing-and-agents.md`
- 更新：`docs/requirements/04-review-quality-and-workflow.md`
- 更新：`DESIGN.md`

- [ ] 同步权威需求与设计文档，删除与“批准即终点”“右栏混放操作”冲突的旧描述。
- [ ] 运行相关 pytest、完整 `uv run pytest`、Ruff、Mypy。
- [ ] 运行 `npm run api:generate`、`npm run api:check`、`npm run test:web`、typecheck、lint、build。
- [ ] 只读校验数据库 schema 指纹，确认没有 schema 或迁移变化。
- [ ] 在本地开发模式启动服务，使用真实账号和真实模型完成：新建会话 → 普通讨论不增版 → 引用历史大纲微调并新增版本 → 批准 → 生成/修改正文版本 → 续接旧会话。
- [ ] 浏览器检查三栏职责、顶部宽度、中文状态、完整正文尾部和刷新恢复。
- [ ] 记录真实请求的任务 ID、版本变化与验收结论；不保存半截正文或伪造审核通过。
