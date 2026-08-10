# 长篇统一工作台与选区改写实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use `subagent-driven-development` when executing this plan with delegated tasks, or `executing-plans` for inline execution.

**Goal:** 在不改变现有长篇章节级会话、章节状态、资料 CRUD、草案审核和保存语义的前提下，将长篇工作台重排为左侧“章节/创作资料”双根导航、中央主画布、右侧聊天协作坞，并新增用户主动确认后的章节正文/大纲选区改写能力。

**Architecture:** 保留现有 `WritingConversation`、`ChapterEditor`、`LibraryPane` 的业务状态边界；只由 `WorkspaceShell` 负责三栏组合和资料导航/主画布切换。选区先停留在编辑器本地状态，点击“让 AI 修改这段”后才生成不可变附件；正式任务由 Core 根据服务端权威正文/大纲校验 Unicode 区间、版本和哈希，冻结选区快照，Agent 只返回 replacement，ReviewArtifact 批准时由 Core 确定性拼接并应用。章节与大纲共用产品交互，但后端使用两个明确的长篇 Operation。禁止数据库 schema 变更。

**Tech Stack:** FastAPI/Pydantic、SQLAlchemy 现有 `WritingRunCommand`/`ReviewArtifact` payload、Agent Service 现有 Operation/Artifact 协议、Next.js/React、原生 CSS、Vitest/pytest/Ruff/Mypy。

---

## 1. 建立共享选区身份与公共长篇契约

**文件：**
- `packages/service-contracts/src/inkforge_contracts/long_serial.py`
- `packages/service-contracts/src/inkforge_contracts/operations.py`
- `apps/core-api/src/inkforge_core/writing/schemas.py`
- `apps/core-api/src/inkforge_core/writing/commands.py`
- `apps/core-api/tests/writing/` 下新增/扩展长篇启动契约测试

**步骤：**

1. 先写失败测试，覆盖：章节/总纲/大纲节点三种 `resourceType`；`selectionStart < selectionEnd`、Unicode 码点范围、`baseContentHash`/`selectedTextHash` 64 位小写 SHA-256、空指令拒绝、未知字段拒绝、选区 Operation 不能沿用 `rewrite_scene`。
2. 增加严格的选择目标模型，字段固定为 `resourceType`、`resourceId`、`baseUpdatedAt`、`baseContentHash`、`selectionStart`、`selectionEnd`、`selectedTextHash`；范围 end 为开区间，客户端只发送身份，不发送正文。
3. 扩展长篇公开 Operation：`rewrite_chapter_selection` 与 `rewrite_outline_selection`；分别允许 chapter 内容和 outline 内容/outline node 内容，声明对应主 Agent、reviewer、artifact kind 和 scope；保留 `rewrite_scene` 的完整章节语义不变。
4. 让 `LongSerialStartWritingRunRequest` 对两个选区 Operation 要求选择目标，并由 Core 从权威源派生 `targetWordCount`（选区长度，至少 1）；普通 Operation 继续沿用原有字段和默认字数。
5. 在启动事务中锁定作品及目标资源，验证版本/全文哈希/范围/选区哈希；从服务端内容派生 `selectedText`、前后文和完整源快照，写入既有 `WritingRunCommand.payloadJson.job`，并用现有 source binding 机制记录来源。任何冲突返回 409，且不创建 task/command。
6. 保持 `chapterId` 和 `writingSessionId` 的章节锚点不变；大纲选区任务仍从当前章节会话启动，不改会话模型。
7. 更新共享协议导出与生成 API 类型：`npm run api:generate`、`npm run api:check`。

**验收：** 旧 `plan_chapter`/`write_chapter`/`rewrite_scene` 请求测试继续通过；三类选区目标可以创建任务；旧正文或大纲在 GET→POST 间任意变化都导致 409，数据库中没有半成品任务。

## 2. 实现 Agent 的 replacement-only 选区流程

**文件：**
- `apps/agent-service/src/inkforge_agents/operations/definitions.py`
- `apps/agent-service/src/inkforge_agents/runtime/execution.py`
- `apps/agent-service/src/inkforge_agents/jobs/writing.py`
- `apps/agent-service/src/inkforge_agents/operations/artifact_contract.py`
- `apps/agent-service/src/inkforge_agents/jobs/adapters.py`
- `apps/agent-service/src/inkforge_agents/operations/router.py`
- `apps/agent-service/tests/` 对应 Operation、协议和 Artifact 测试

**步骤：**

1. 先补失败测试：选区 Operation 必须输出结构化 replacement；结果缺少资源身份、身份与快照不一致、包含完整 `content`/未知字段、空 replacement 或错误终止工具时失败；`rewrite_scene` 仍要求完整正文。
2. 为章节选区和大纲选区分别添加 Operation 定义和允许的读取范围，复用现有审校 Agent，但把输出协议切为 replacement-only。
3. 在显式长篇任务状态构建中读取 Core 冻结的 selection snapshot，向 Agent 暴露选区正文、有限前后文和来源标签；不让 Agent 重新读取并选择目标，也不让 Agent 连接数据库。
4. 增加结构化选区产物事件/适配：返回 `operation`、`resourceType`、`resourceId`、区间、两个哈希和 `replacement`；禁止返回整篇正文。审校与返工只能修改 replacement，必须继承原选区身份和 artifactKey。
5. 更新 runtime 协议提示、fake provider、事件校验和恢复快照校验；保留 ReviewArtifact 生命周期，不直写正式内容。

**验收：** Agent 只产出替换文本；错误身份不会创建有效草案；返工不允许变更选区范围/来源；普通长篇正文生成流程无回归。

## 3. 生成和应用选区 ReviewArtifact

**文件：**
- `apps/agent-service/src/inkforge_agents/jobs/adapters.py`
- `apps/core-api/src/inkforge_core/reviews/apply.py`
- `apps/core-api/src/inkforge_core/reviews/formal_writes.py`
- `apps/core-api/src/inkforge_core/reviews/repository.py` / source binding 相关模块
- `apps/core-api/src/inkforge_core/reviews/schemas.py`
- `apps/core-api/tests/reviews/`、`apps/core-api/tests/writing/`

**步骤：**

1. 先写失败测试：选区 artifact payload 必须保存 target mode、完整身份、原选区、replacement 和 Core 物化的完整候选；候选前缀/后缀必须与冻结源逐字一致；大纲节点只允许改变节点 content。
2. 扩展现有 `chapter_draft`/`outline_draft` payload 以支持：`replace_selection`、`outline_content_selection`、`outline_node_content_selection` 三种 target mode；不新增数据库表或 Artifact kind。
3. 创建 artifact 时由 Core 根据 snapshot 计算完整 candidate，不信任 Agent 自报完整正文；review/revise 重新验证同一 target identity。
4. 扩展 `FormalArtifactApplier`：选区 artifact 拒绝现有 `editedContent` 全文编辑字段，改用结构化 replacement；批准时锁定当前资源、复核 source binding/范围/选区哈希，再由 `base[:start] + replacement + base[end:]` 确定性拼接。章节沿用 `replace_chapter_content(..., reopen=True)`；总纲只更新 `Outline.content`，节点只更新 `OutlineNode.content`。
5. 处理 CAS 冲突、旧 artifact 版本、重复批准和事务回滚；继续保留 approved/revise/discard 状态和完整历史。
6. 若现有批准请求模型需要编辑选区，新增 `editedReplacement`（及 CLI 文件输入）而不是复用 `editedContent`；普通全文草案继续使用原字段。

**验收：** 选区外正文/大纲内容永不改变；资源版本变化返回来源冲突；批准前后读取结果与预览一致；普通章节草案、普通总纲草案、Beat Plan 审批全部保持原行为。

## 4. 前端统一三栏工作台，但不改现有业务状态

**文件：**
- `apps/web/src/features/workspace/workspace-shell.tsx`
- `apps/web/src/features/workspace/library-pane.tsx`（拆出受控导航/详情组合，但复用现有详情和懒加载）
- `apps/web/src/features/workspace/smart-writing-panel.tsx`
- `apps/web/src/features/writing/writing-conversation.tsx`
- `apps/web/src/features/chapters/chapter-list.tsx`
- `apps/web/src/app/globals.css`
- `apps/web/src/features/workspace/__tests__/workspace-shell-source.test.ts`
- `apps/web/src/features/workspace/__tests__/workspace-page.test.ts`

**步骤：**

1. 先更新源码测试，锁定新的结构：左侧两个平级根入口“章节”“创作资料”；中央主画布；右侧当前章节聊天与审核区；旧 `view=studio|reading|library` URL 仍能映射初始焦点。
2. 将 `ChapterList` 和资料分类导航放入左栏两个独立可展开分组；资料详情仍在中央使用现有 `LibraryPane` 详情组件、延迟加载、错误/重试和 CRUD，不把完整表单压缩进窄侧栏。
3. 章节态同时挂载 `ChapterEditor` 与 `SmartWritingPanel`，保持 `currentChapter.id` key、章节级会话查询、新建/历史/删除、SSE、Artifact 和 onComplete 刷新逻辑；仅移动容器，不提升聊天或编辑器内部状态。
4. 将 `workspace-review-rail` 的展示内容并入右侧协作坞底部，保留 portal host、待确认托盘、Artifact 弹窗和所有审核动作；不新增第四列。
5. 保留切章节/切资料/切旧视图前的 `flushActiveChapterSave`、1.2 秒 autosave、CAS、阅读/小修权限和章节状态流；资料详情切换前同样先保存当前章节。
6. 用原生 CSS 实现 220–280 / `minmax(640px,1fr)` / 380–440 三栏，窄屏沿用项目现有水平滚动/收缩策略，不引入 Tailwind 或新 UI 框架。

**验收：** 普通聊天、章节编辑、资料编辑和审核在新布局下行为与旧版一致；切章节不会错误复用会话；资料分类和详情状态不会因布局切换丢失；既有工作区源码测试改为验证新结构。

## 5. 增加编辑器本地选区与显式附件

**文件：**
- 新增 `apps/web/src/features/editor/selection-identity.ts`
- `apps/web/src/features/editor/chapter-editor.tsx`
- `apps/web/src/features/outline/outline-panel.tsx`
- `apps/web/src/features/writing/writing-conversation.tsx`
- `apps/web/src/features/workspace/smart-writing-panel.tsx`
- `apps/web/src/features/workspace/workspace-shell.tsx`
- `apps/web/src/features/short-medium/selection-range.ts`（抽取共享 Unicode/hash 工具）
- 相关 editor/outline/writing 测试

**步骤：**

1. 先写失败测试：普通 textarea 选中不发送请求；UTF-16 DOM 位置转换为 Unicode 码点；单个非空连续选区生成正确哈希；内容编辑、切章、切资料或新建聊天会清理未附加选区；已附加快照不被新选区静默覆盖。
2. 抽取并复用短中篇的 `toCodePointRange`、`sha256Text` 和身份构造，保证换行/emoji 不做归一化。
3. 在 `ChapterEditor` 和 `OutlinePanel` 的目标 content textarea 上暴露本地 `TransientSelection`，底部显示固定操作条：`已选择 N 字 · 尚未交给 AI`；只有点击“让 AI 修改这段”才转为 attachment，不把普通选择注入聊天上下文。
4. 在 `WritingConversation` composer 上方显示单个来源附件卡：来源类型、资源 id/章节或节点路径、字数、首尾预览、移除/重新选择；发送普通消息无附件时完全走旧路径，带附件时显式选择章节/大纲选区 Operation。
5. 发送前 flush 章节编辑器；大纲必须已有保存版本。Core 重新校验身份，前端不发送全文作为权威来源；附件发送后写入用户消息 metadata 的来源快照并清空 composer 附件。
6. 选区 artifact 在右侧协作坞中显示聚焦 diff，明确“选区外内容未变化（Core 已校验）”；审批入口使用 replacement 编辑，不允许整章/整份大纲编辑。

**验收：** 用户必须主动点击附加并发送指令才会让 AI 获取选区；普通聊天上下文与现有历史行为不变；选区来源变化时提示重新选择；章节正文和大纲总纲/节点三类来源均可走同一交互。

## 6. CLI、生成客户端与文档契约

**文件：**
- `tools/inkforge-cli/` 长篇 task mutation/Artifact approve 相关模块
- `packages/api-client` 生成文件（只通过生成命令更新）
- `docs/requirements/03-ai-writing-and-agents.md`
- `docs/requirements/04-review-quality-and-workflow.md`
- 相关 CLI 测试、OpenAPI 检查

**步骤：**

1. 扩展长篇 Agent start 的 operation/target/scope 输入，提供章节/总纲/节点选区身份字段；CLI 不接受客户端传入的 selectedText 作为权威正文。
2. 扩展 Artifact approve 的结构化 `editedReplacement`/文件输入，严格限制只用于选区 artifact，保持全文草案的 `editedContent` 语义。
3. 按项目现有 Skill 流程执行 GET→显示完整 Diff→用户确认→单次批准→回读资源版本；更新文档中“Beat Plan/草案需 ReviewArtifact”的说明，明确选区改写同样不能直写。
4. 运行 `npm run api:generate` 与 `npm run api:check`，检查 CLI body、未知字段和幂等 fingerprint。

**验收：** CLI 与浏览器使用同一公共契约；选区批准不会绕过 Artifact/source binding；OpenAPI 和生成客户端一致。

## 7. 回归验证与交付

**步骤：**

1. 先跑 Core 选区/审核/写作相关 pytest，Agent Operation/Artifact pytest，Web workspace/editor/outline/writing 相关测试；修复失败后再扩大范围。
2. 运行 `uv run ruff check .`、必要的 `uv run mypy apps/core-api/src apps/agent-service/src packages/service-contracts/src packages/service-auth/src`。
3. 运行 `npm run typecheck`、`npm run lint`、`npm run test:web`，并执行 `npm run api:check`。
4. 只读核对 schema-contract 无迁移/表结构改动，检查 git diff 仅包含本计划范围及必要生成文件；保留用户已有未相关修改。
5. 用最小手工验收流程：章节草稿选区→附加→发送→Artifact→批准→章节只改变选区；总纲/节点重复一次；普通聊天、切章节、历史会话、资料 CRUD 和审核托盘各走一遍。

**完成标准：** 现有功能回归通过；选区外字节不变的 Core 测试通过；三类选区来源均完成完整的 proposal→ReviewArtifact→用户确认→应用链路；无 schema 变更、无直接写入、无静默截断。
