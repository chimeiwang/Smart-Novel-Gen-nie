# 长篇统一工作台与选区修改规格

状态：已确认，待实施

日期：2026-08-10

## 背景

当前长篇工作区通过顶部 `AI 创作 / 阅读与小修 / 创作资料` 三个入口切换内容。章节列表、正文编辑器、
AI 会话、资料详情和审核栏的业务能力已经存在，但正文与 AI 会话不能同时查看，创作资料又拥有第二套
独立侧栏，用户需要频繁切换视图。

本次改造把现有能力重排为稳定的三栏工作台，并且只增加一个产品能力：用户明确选择正文或大纲中的
一段文字后，可以主动要求 AI 只修改该选区。普通文本选择不得进入 AI 上下文，正式修改仍必须经过
ReviewArtifact 审核和用户批准。

## 与既有规格的关系

`docs/specs/2026-08-08-chat-first-ai-creation-workspace.md` 描述了另一轮尚未完整实施的聊天时间线重构。
本规格覆盖其“页面结构”设计：长篇统一工作台以中央正文/资料画布、右侧聊天协作区为准，不把聊天改成
中央唯一主画布。

聊天时间线重构中涉及模型上下文连续性、项目级会话、运行卡重建和 SSE 恢复增强的内容不属于本次范围，
不得借统一布局或选区修改顺带实施。

## 当前事实

- 工作区顶层视图是 `studio | reading | library`；切换前会刷新当前章节的待保存内容。
- 章节导航支持新建、切换、当前章高亮、排序、字数、Beat Plan 摘要和章节状态。
- 章节正文保持“阅读与小修”语义：草稿章需要主动进入小修；审核中和已完成章节只读。
- 章节编辑器独占 1.2 秒自动保存、CAS、本地草稿恢复、章节状态、进展和一致性终检。
- AI 会话当前按 `novelId + chapterId` 创建和查询；切章会用新的 `currentChapter.id` 重建聊天实例。
- AI 会话已有历史对话、新建/删除/恢复、消息编辑/删除/复制/重试、任务建议、SSE 状态、流程日志、
  Artifact 托盘和审核弹窗。
- 右侧审核栏显示当前章待确认 Artifact、Beat Plan 和终检摘要。
- 资料库已经包含角色、地点、势力、物品、术语、故事背景、世界设定、大纲、剧情进度、故事进展、
  作品圣经、文风和参考资料，并按 `lore / planning / resources` 延迟加载。
- 长篇当前没有公开的选区修改 Operation。内部 `rewrite_scene` 仍要求完整正文产物，不能直接承担
  “只返回替换文本”的安全语义。
- PostgreSQL 已有 `chapter_draft`、`outline_draft` 和 `agent_updates` 等 Artifact 类型；本次不修改数据库
  schema 或 enum。

## 目标

1. 将长篇工作区改成“左侧项目导航 + 中央主画布 + 右侧聊天协作区”的稳定三栏结构。
2. 让“章节”和“创作资料”成为左侧栏中两个平级、可独立展开的顶层导航。
3. 在章节态同时显示正文和当前章节 AI 会话，不再要求用户在二者之间切换。
4. 搬迁而不重写现有章节、资料、聊天、Artifact、质量检查和保存能力。
5. 支持用户主动选择章节正文、文本总纲或结构化大纲节点内容，并请求 AI 只修改所选范围。
6. 使用 Unicode 码点范围、来源版本和 SHA-256 绑定选区，保证选区外内容逐字不变。
7. 保留 `proposal -> ReviewArtifact -> 复审/返工 -> 用户确认 -> Core 应用` 边界。

## 非目标

- 不改成项目级会话，不合并不同章节的历史对话。
- 不新增“同一作品只能运行一个 Agent”的项目级互斥规则。
- 不改变新建聊天、历史恢复、任务恢复、SSE 或模型上下文的现有语义。
- 不改变章节状态流、终检门禁、自动保存延迟、CAS 或本地草稿恢复。
- 不把完整资料编辑器缩减为左栏摘要，也不删除任何资料类型或 CRUD 能力。
- 不允许普通文本选中、切换章节或切换资料自动进入 AI 上下文。
- 不支持跨资源、多选区、非连续选区、模糊匹配或自动变基。
- 不允许 Agent 或前端直接覆盖正式正文、大纲或节点内容。
- 不修改 PostgreSQL 表、字段、外键、索引或 enum。
- 不在本次实现 `editedBeatPlan` 规格、聊天时间线重构或其他未完成规格。

## 产品结构

### 总体布局

```text
长篇工作区
├── 左侧项目导航：220px—280px
│   ├── 章节（顶层）
│   └── 创作资料（顶层）
├── 中央主画布：最小 640px，正文内容列目标 680px—820px
└── 右侧聊天协作区：380px—440px
    ├── 当前章节 AI 会话
    └── 审核与确认区域
```

继续采用 PC 优先和现有最小桌面宽度策略，不新增移动端方案。面板使用现有 CSS 变量、原生 CSS、
hairline 边框和低阴影，不引入 Tailwind。

### 左侧项目导航

“章节”和“创作资料”是两个平级顶层节点，不把创作资料放在章节之下，也不把角色、势力、大纲等
子项与具体章节混成同一层列表。

```text
▾ 章节
  第一章
  第二章
  ＋ 新增章节

▾ 创作资料
  角色
  地点
  势力
  物品
  术语
  故事背景
  世界设定
  大纲
  剧情进度
  故事进展
  作品圣经
  文风
  参考资料
```

两个顶层节点可以独立展开和收起。章节列表继续使用现有新增、切换、保存屏障、状态、字数和 Beat Plan
摘要逻辑；创作资料继续使用现有分类、延迟加载、错误重试和失效刷新逻辑。

### 中央主画布

- 点击章节时显示现有 `ChapterEditor`。
- 点击资料子项时显示现有资料详情组件，而不是在左栏复制一份简化表单。
- 离开正文打开资料前继续刷新章节自动保存；失败时停留正文并显示现有错误。
- 打开资料不卸载资料控制器，保留当前资料项、已经加载的分组和未提交表单状态。
- 返回章节继续保持当前章节、阅读/小修状态和自动保存协调器。
- `studio`、`reading` 和 `library` 旧 URL 继续可解析为初始焦点，旧链接不失效；页面不再显示三项顶部模式开关。

章节态继续保留当前阅读/小修策略，不能因为正文长期可见就默认把草稿章变成可编辑 textarea。审核中和已完成
章节的只读原因、送审、退回、完成、重新编辑、进展和终检入口均保持现有行为。

### 右侧聊天协作区

右侧主体仍是现有聊天式 `WritingConversation`，保留：

- 当前章节任务建议；
- 历史对话、新建、选择和删除；
- 用户消息与 Agent 消息；
- 消息编辑、删除、复制和重试；
- Agent 流式状态、当前 Operation、阶段和流程日志；
- 正文预览、当前章/下一章目标选择；
- 待确认托盘、Artifact 弹窗、批准、返工和丢弃。

聊天仍绑定当前章节，继续使用当前 `novelId + chapterId` 查询和 `currentChapter.id` 生命周期。查看资料不会
自动改变聊天或会话；切换章节仍按现有规则切换到该章聊天。

现有审核栏不新增第四列。它作为聊天协作区底部的“审核与确认”区域保留：无待确认项时收敛为当前章摘要，
有待确认项时显示计数和现有卡片；完整候选、结构化 Diff 和决定操作继续使用现有 body portal 弹窗，避免被
右栏的滚动和 overflow 截断。

## 功能保持矩阵

| 能力 | 本次处理 |
| --- | --- |
| 章节新建、切换和元信息 | 只搬导航位置，行为不变 |
| 阅读、进入/退出小修 | 保留原状态与权限 |
| 1.2 秒自动保存、CAS、本地草稿 | 不变 |
| 章节进展、送审、完成、终检 | 不变 |
| 资料分类、加载、编辑、保存、删除 | 复用原组件与 API |
| 当前章节会话与历史会话 | 复用原查询、创建和恢复规则 |
| 普通聊天和任务建议 | 不变 |
| SSE、运行状态和流程日志 | 不变 |
| ReviewArtifact 状态机与决定 | 不变 |
| 项目级会话或项目级 Agent 锁 | 不增加 |
| 正文/大纲选区修改 | 唯一新增能力 |

## 选区修改交互

### 支持来源

首版只支持一个非空、连续选区，来源为：

1. 草稿章节进入小修后的正文 textarea；
2. 大纲页面的文本总纲 textarea；
3. 已存在结构化大纲节点的“节点内容” textarea。

新增节点、标题、状态、层级、字数输入以及其他设定表单不属于首版选区修改范围。

### 显式授权

1. 用户选中文字时，选区只保存在当前编辑器本地状态。
2. 编辑器底部出现固定选区条：`已选择 N 字 · 尚未交给 AI`。
3. 用户点击“让 AI 修改这段”后，才把选区身份复制到聊天输入区。
4. 聊天输入框上方显示不可混淆的附件卡：来源类型、章节或大纲节点、字数、短预览、定位和移除。
5. 用户输入修改要求并发送，才创建正式选区任务。

右键菜单不作为首版入口。原生 textarea 无法可靠提供跨行选区的屏幕矩形，自定义右键菜单又会覆盖复制、
粘贴和拼写检查。固定操作条同时适配鼠标与键盘选择，也便于正文和大纲复用。

普通选中不能进入聊天 props、消息 metadata、API 请求、日志或模型提示。新选区不能静默覆盖已经附加的选区；
首版一次只能存在一个待发送附件。用户移除、发送、切章或开始新对话后清理待发送附件。

### 保存与来源版本

- 章节正文启动前先刷新现有自动保存；保存失败或冲突时不创建任务。
- 大纲总纲和节点内容必须先通过原有保存路径完成保存；存在未保存修改时按钮提示先保存，不以本地草稿替代
  Core 权威来源。
- 保存完成后再建立选区身份。若保存或刷新使当前选区失效，用户必须重新选择。
- 来源内容变化后不自动移动选区、不搜索相似文本，也不允许继续应用旧候选。

### 聊天表现

选区修改复用当前章节会话和现有任务展示。附件卡是本次输入的明确作用范围，不是一个新的通用资料附件系统。
发送后，用户消息 metadata 只保存来源标签、资源身份、码点范围、哈希和明确标为 UI 预览的短文本，不把它
当作运行来源；完整选中文字只从 Core 冻结任务快照读取。历史消息据此恢复折叠来源卡。Agent 运行、复审、
等待确认和决定仍按现有聊天与 Artifact 状态展示。

## 服务契约

### 产品入口与内部操作

产品只展示一个“选区修改”入口。服务端按来源路由为两个严格 Operation，避免让单个 Operation 动态切换
Artifact 类型：

| 内部 Operation | 来源 | 主责 Agent | Reviewer | Artifact |
| --- | --- | --- | --- | --- |
| `rewrite_chapter_selection` | 章节正文 | 写作 | 校验、编辑 | `chapter_draft` |
| `rewrite_outline_selection` | 文本总纲、节点内容 | 剧情 | 编辑 | `outline_draft` |

两者都是显式 mutating Operation，不经过自然语言分类器猜测。现有 `rewrite_scene` 保持完整正文草案语义，
不得改造成 replacement-only 协议。

大纲选区任务仍使用当前章节的 `chapterId` 和当前章节会话作为聊天与任务锚点，但正式目标由 selection target
明确指向 Outline 或 OutlineNode。不得因此改变会话的章节级查询、创建或恢复语义。

### 选区身份

公共请求只提交身份，不提交正文全文或选中文字：

```text
resourceType: chapter_content | outline_content | outline_node_content
resourceId: 章节、总纲或大纲节点 ID
baseUpdatedAt: 用户建立选区时的权威更新时间
baseContentHash: 权威字段全文 SHA-256
selectionStart: Unicode 码点起点，闭区间
selectionEnd: Unicode 码点终点，开区间
selectedTextHash: 选区 SHA-256
userInstruction: 用户修改要求
```

Web 从 textarea 的 UTF-16 `selectionStart/selectionEnd` 转换为 Unicode 码点，复用并上移当前中短篇的选择范围
工具，不能按 JavaScript UTF-16 索引直接提交。

`packages/service-contracts` 增加对应 target、scope、Operation 和严格结果契约。公共 API 先修改 Pydantic，
再重新生成 TypeScript Client，不手写重复 DTO。

选区操作不沿用整章默认 4000 字目标。Core 以选区码点数派生本次 `targetWordCount`，至少为 1；它只用于本次
模型调用的篇幅参考，不限制用户在 instruction 中明确要求扩写或压缩。

### Core 启动快照

Core 在创建任务前：

1. 校验登录、小说、当前章节会话和目标资源归属；
2. 锁定目标章节、Outline 或 OutlineNode；
3. 校验 `baseUpdatedAt` 和全文 SHA-256；
4. 校验码点范围合法且非空；
5. 从权威文本切出 selectedText 并校验 `selectedTextHash`；
6. 由 Core 派生 selectedText、contextBefore 和 contextAfter；
7. 把完整来源、范围、哈希和上下文冻结到现有 WritingRunCommand payload；
8. 捕获对应 SourceBinding 后再提交 Agent 队列。

失败必须在任务创建前返回，不产生空任务或 Artifact。快照使用现有 JSON 字段，不新增数据库列。

### Agent 结果

两个 Operation 共用新的严格终止控制工具，只允许返回：

```text
operation
resourceType
resourceId
baseContentHash
selectionStart
selectionEnd
selectedTextHash
replacement
```

Agent 只能通过严格字段生成 replacement，不能提交 `content` 等完整文档字段，也不能控制正式拼接。Agent
Service 必须核对结果身份与冻结快照完全一致；返回错误结构、额外全文字段、改变来源身份、空结果、模型长度
截断、内容过滤或错误完成原因都使任务失败。

Reviewer 和 reviser 继续使用同一个冻结目标。返工只能修改 replacement，不能改变来源、范围、Artifact kind
或 artifactKey。

### Artifact 物化

Core 根据冻结来源确定性构造候选：

```text
candidate = base[:selectionStart] + replacement + base[selectionEnd:]
```

并断言候选的前缀与后缀逐字等于基础文本。Core 生成完整、未截断的选区 Diff，再创建现有 Artifact：

- 章节选区：`chapter_draft`，target.mode=`replace_selection`；
- 总纲选区：`outline_draft`，target.mode=`outline_content_selection`；
- 节点选区：`outline_draft`，target.mode=`outline_node_content_selection`。

Artifact payload 保存 replacement、完整 selection identity、目标信息和供展示的完整候选；正式应用不得信任
候选全文覆盖来源。选区 Artifact 不接受现有 `editedContent` 全文编辑；用户可批准、要求返工或丢弃。

不增加新的 ReviewArtifact kind，因此数据库 enum 不变。`outline_draft` 加入来源绑定验证范围。

### 正式应用

批准时继续使用现有 ReviewArtifact revision、幂等决定和 SourceBinding 锁内校验。Core 根据 target.mode 进入
专用 selection apply 分支：

1. 锁定当前目标字段；
2. 再次核对更新时间、全文哈希、范围和选区哈希；
3. 使用当前文本与已批准 replacement 重新拼接；
4. 断言选区外前缀和后缀不变；
5. 章节继续复用 `replace_chapter_content(..., reopen=True)`，使旧质量结果失效；
6. 总纲只更新 Outline.content；
7. 节点只更新 OutlineNode.content，不触碰标题、层级、状态、顺序和字数字段；
8. 正式写入、Artifact 状态和持久决定命令仍在同一事务收敛。

来源冲突发生在批准前或应用中时返回 409，Artifact 保持 `awaiting_user`，不自动变基、不部分写入。

## 组件边界

### Web

- `WorkspaceShell` 或新的长篇组合层只负责三栏布局、左侧焦点和保存屏障。
- `ChapterEditor` 继续负责正文、本地草稿、保存、章节状态和质量检查；只新增本地选区桥接。
- `LibraryPane` 拆出受控导航与详情边界，但继续共享同一个 DeferredWorkspaceLoader 和现有详情组件。
- `OutlinePanel` 继续负责总纲和节点表单，只新增可复用选区桥接。
- `SmartWritingPanel/WritingConversation` 继续负责现有会话、任务、SSE 和 Artifact；新增单个待发送选区附件。
- 不把 ChapterEditor 的全文状态或 WritingConversation 的运行时合并进全局 reducer。

### Core API

- 扩展公共长篇 Operation、target、scope 和选区请求校验。
- 增加章节、总纲和大纲节点选择快照构建器。
- 增加 replacement 结果物化和 selection Artifact 应用分支。
- 扩展 SourceBinding 对 outline_draft 的验证。
- 不修改 PostgreSQL schema。

### Agent Service

- 注册两个选区 Operation 和共享 replacement 终止工具。
- 为章节和大纲选区分别提供最小上下文策略和提示约束。
- primary、reviewer、reviser 只处理 replacement 与冻结身份。
- 不读取数据库，不负责拼接或正式应用完整文本。

## 错误处理

| 场景 | 处理 |
| --- | --- |
| 没有非空连续选区 | 前端不允许附加 |
| 普通选择但未点击操作 | 不进入任何请求或 AI 上下文 |
| 正文保存失败或 CAS 冲突 | 保留本地选区，阻止任务启动 |
| 大纲存在未保存修改 | 提示先保存，不创建任务 |
| 来源版本、全文 hash 或选区 hash 不一致 | 409，要求重新选择 |
| 选区码点范围越界 | 409，不创建任务 |
| 当前会话不属于小说/章节 | 403 或现有稳定绑定错误 |
| 当前章节已有冲突写入任务 | 沿用现有 `WRITING_TARGET_BUSY` |
| Agent 返回身份不一致、错误结构或额外全文字段 | 任务失败，不创建 Artifact |
| 模型输出截断或内容过滤 | 任务失败，不接受半截 replacement |
| Artifact 来源发生变化 | 禁止批准，提示重新发起 |
| 正式应用任一步失败 | 事务回滚，Artifact 恢复等待确认 |
| 网络结果不确定 | 使用原 clientRequestId 对账，不生成新 ID 重试 |

## 测试

### Web

- 左栏“章节”和“创作资料”是平级顶层节点，展开/收起和当前项状态正确。
- 章节态正文和聊天同时可见；资料态完整资料详情和聊天同时可见。
- 新建/切章前保存、阅读/小修、章节流程、资料延迟加载和错误重试不变。
- 切章仍重建为该章聊天；切资料不重建当前聊天。
- 历史、新建、消息动作、SSE、流程日志、Artifact 托盘和弹窗回归通过。
- 普通选择不产生网络请求、聊天附件或消息 metadata。
- 显式操作后显示正确来源、字数、短预览、定位和移除。
- UTF-16 到 Unicode 码点转换覆盖中文、emoji 和代理对边界。
- 新选区不静默覆盖已附加选区；发送、移除、切章和新聊天正确清理。

### Core

- 三种来源的归属、更新时间、全文 hash、范围和选区 hash 校验。
- 选择快照只从 Core 权威文本派生，不信任浏览器 selectedText。
- 章节会话和现有目标忙锁语义不变。
- replacement 身份不一致、越界、空结果、错误结构和额外全文字段被拒绝。
- Core 拼接后的前缀和后缀逐字不变。
- chapter_draft 和两种 outline_draft target.mode 正确。
- approve 前来源漂移返回 409；成功后只修改目标字段。
- 章节应用继续重置质量结果；节点应用不修改任何其他字段。
- 决定事务失败整体回滚，幂等重放不重复应用。
- schema-contract 指纹保持不变。

### Agent Service 与共享契约

- 两个 Operation 的目标、scope、Agent、Reviewer、Artifact kind 和工具白名单正确。
- replacement 控制工具为终止工具，结果严格、身份稳定。
- reviewer/reviser 不能改变范围、资源、artifactKey 或 Artifact kind。
- 完成原因、输出截断和恢复快照回归通过。
- OpenAPI 重新生成并通过 `npm run api:check`。

### 验证命令

- 相关 Web 测试、`npm run typecheck`、`npm run lint`。
- Core writing/reviews/outline/chapter 相关 pytest、Ruff、Mypy。
- Agent operations/runtime/jobs 相关 pytest、Ruff、Mypy。
- `packages/service-contracts/tests`。
- 数据库 schema-contract 只读指纹校验。

## 验收标准

1. 页面不再显示顶部三模式切换；左栏以平级“章节”和“创作资料”导航整个作品。
2. 章节态同时显示现有阅读/小修画布和当前章节聊天，资料态显示完整资料详情和同一聊天。
3. 除布局与入口位置外，章节、资料、聊天、SSE、Artifact 和审核功能行为不变。
4. 选中文字本身不会把内容交给 AI；只有用户点击明确操作并发送要求后才创建任务。
5. 正文、总纲和大纲节点内容均可提交一个连续选区进行修改。
6. Agent 只返回 replacement，Core 负责拼接，选区外文本逐字不变。
7. 所有修改均经过完整 Diff、复审和 ReviewArtifact 用户决定；不能直接覆盖正式内容。
8. 来源变化时明确冲突，不自动变基、不模糊定位、不部分应用。
9. 不新增项目级会话、项目级 Agent 锁或其他业务语义。
10. 不修改 PostgreSQL schema，现有旧 URL 和未携带选区的普通长篇请求保持兼容。
