# 中短篇专用写作工作流规格

## 状态

- 日期：2026-07-18
- 状态：实施中
- 范围：作品创建入口、篇幅分流、中短篇大纲、整稿生成、全稿审核、ReviewArtifact 版本与正式应用

## 背景

现有写作流程以长篇连载为中心：作品创建后进入章节工作区，正文依赖章节目标和 Beat Plan，生成、审核和正式应用也围绕单章进行。这个流程适合持续连载，但不适合以一个开头、结尾、设定或数句话大纲为起点，完成 6000～80000 字中短篇的作者。

中短篇的主要协作成本不在逐章排产，而在“灵感到大纲”的多轮反复修改，以及整稿生成后的通读、斟酌和返工。中短篇仍需要让读者可理解的分节结构，但分节不是固定字数切片，也不应成为逐节生成、逐节确认或数据库章节。

因此，中短篇必须从创建入口起与长篇连载分流，并使用专用的显式 Operation、上下文和审核策略；长篇现有章节、Beat Plan、逐章写作和质量检查保持不变。

## 目标

- 新建作品时先由用户明确选择 `short_medium` 或 `long_serial`，界面不默认选中任一模式。
- 为 `short_medium` 提供“灵感 → 可反复修改的大纲 → 完整正文 → 全稿审核与返工 → 用户确认”的专用流程。
- 由 Core 强制校验中短篇目标总字数为 6000～80000 字。
- 大纲一次展示完整、适合人阅读；允许长期反复修改局部或整体，并可靠保留用户确认的创作重点。
- 正文的每个生成或返工 pass 只调用一次作家模型并输出完整正文，不逐节生成、不自动续写、不拼接截断内容；一次用户发起的整稿运行最多包含首稿和一次自动返工，即最多两次作家调用。
- 完整正文保存到创建项目时的唯一正文 Chapter；“节”只属于大纲和正文的阅读结构。
- 全稿使用固定顺序的编辑审核和一致性校验，最多自动完整返工一次，随后交还用户判断。
- 复用现有 PostgreSQL 表、枚举、JSON 载荷和 ReviewArtifact 状态机，不修改 schema。
- 不改变 `long_serial` 的现有 Operation、章节导航、Beat Plan 和逐章审核行为。

## 非目标

- 不按固定字数、固定节数或固定篇幅比例编排大纲分节。
- 不把大纲分节转换为 Chapter、Beat Plan、SceneBeat、独立任务或独立 ReviewArtifact。
- 不逐节生成正文，也不在各节之间增加用户确认点。
- 不实现供应商截断后的自动续写、片段去重或多轮拼接。
- 不为中短篇构建与长篇相同复杂度的设定库，也不在大纲阶段自动执行编辑或 OOC 审核。
- 不允许创建后直接切换作品篇幅 Profile；跨 Profile 转换属于未来显式迁移能力。
- 不新增 PostgreSQL 表、列、枚举或迁移。

## 术语与不变量

### 篇幅 Profile

| Profile | 产品含义 | 写作单位 | 主要流程 |
| --- | --- | --- | --- |
| `short_medium` | 6000～80000 字中短篇 | 单一完整稿件 | 大纲反复修改、整稿生成、全稿审核 |
| `long_serial` | 长篇连载 | 章节 | Beat Plan、逐章生成、逐章审核 |

Profile 在项目创建后锁定。作品圣经可以继续修改目标总字数、文风和创作信息，但不能直接修改 `storyLengthProfile`。

### 中短篇持久化映射

- 原始灵感保存到现有 `Novel.summary`。
- Profile 和目标总字数继续保存到现有 WritingBible 字段。
- 创建中短篇时仍创建一个 Chapter，标题为“正文”；最终完整正文写入该 Chapter。
- 中短篇大纲和整稿继续复用现有 `ReviewArtifact(kind=outline_draft)` 与 `ReviewArtifact(kind=chapter_draft)`。
- 大纲版本、内部 patch、原始修改要求和整稿来源元数据写入现有 ReviewArtifact 及 revision JSON 载荷。
- 不为“大纲分节”创建数据库记录。

## 1. 创建入口与篇幅分流

### 1.1 联合创建契约

创建请求按 `storyLengthProfile` 使用可辨识联合契约，不提供默认值：

```text
short_medium:
  storyLengthProfile = "short_medium"
  inspiration: 非空，必填
  targetTotalWordCount: 6000..80000，必填
  name: 暂定标题，可选

long_serial:
  storyLengthProfile = "long_serial"
  保留当前长篇表单的名称、题材、主角、核心卖点、第一章目标等字段和校验
```

中短篇未填写标题时，Core 使用“未命名中短篇”作为可修改的占位标题；不能因为标题为空拒绝创建。中短篇灵感写入 `Novel.summary`，不能只停留在前端或命令快照。

Core 在 Pydantic 边界和业务事务内都校验 `targetTotalWordCount`。`5999`、`80001` 必须被拒绝，`6000`、`80000` 必须被接受。长篇目标范围继续遵循现有规则，不能套用中短篇边界。

### 1.2 创建后的动作

- 中短篇主按钮文案为“创建并生成大纲”。
- Core 先完成项目、WritingBible、空大纲和唯一“正文”Chapter 的事务创建，再启动 `develop_short_outline`。
- 如果项目创建成功但任务启动或投递失败，项目不得回滚或删除；专用中短篇工作区展示稳定错误和“重试生成大纲”入口。
- 长篇继续进入现有章节工作区，不自动进入中短篇流程。

### 1.3 读取与兼容

- Dashboard 小说列表和 Workspace Bootstrap 返回 `storyLengthProfile`、`targetTotalWordCount`。
- 前端只依据权威响应选择中短篇或长篇工作区，不根据标题、章节数或正文关键词猜测。
- 旧中短篇项目允许继续打开。若现有目标小于 6000 或大于 80000，工作区允许查看和修正目标，但禁止启动新的中短篇 Operation，并明确提示先修正目标。
- 新增小说标题修改公开接口，校验登录、归属、非空标题和并发版本，使中短篇暂定标题可后续修改。

## 2. 显式 Workflow 与 Operation

### 2.1 启动契约

公共写作启动请求增加必需的 `workflowKind` 和显式 `operation`。中短篇仅允许以下组合：

| workflowKind | operation | 用途 |
| --- | --- | --- |
| `short_medium` | `develop_short_outline` | 首次生成或按用户要求修改完整大纲 |
| `short_medium` | `write_short_story` | 根据已批准大纲生成或修改完整正文 |

长篇使用 `long_serial` 和现有 CreativeOperation，保留聊天分类与 `@Agent` 路由行为。

Core 必须：

- 校验请求 Profile、WritingBible Profile、Operation 和目标 Chapter 相互一致；
- 校验中短篇目标总字数处于 6000～80000；
- 在创建模型任务前拒绝缺失、不支持或跨 Profile 的组合；
- 将 `workflowKind`、`operation`、目标总字数和来源标识写入持久命令及稳定任务快照。

Agent Service 对中短篇直接执行 Core 指定的 Operation。缺少显式 Operation、快照不一致或 Profile 不匹配时，必须在模型调用前失败；不得根据“短篇”“整稿”“全文”“修改第 N 节”等关键词猜测 Operation。

### 2.2 中短篇上下文权威顺序

每轮 `develop_short_outline` 按以下优先级构造最小上下文：

1. 用户本轮直接编辑并已保存的结构化内容；
2. 用户本轮修改要求原文；
3. 已确认创作锚点；
4. 当前完整大纲；
5. 原始灵感；
6. 最近对话，仅用于理解代词、序号和指代，不能覆盖前五项。

全部 WritingMessage 和版本历史继续持久化，但模型上下文不注入几十轮完整聊天。上下文组装器只投影当前任务需要的权威内容，并在冲突时按上述顺序裁决。任何模型摘要都不能替代用户修改要求原文。

`write_short_story` 的权威输入为已批准大纲及锚点、原始灵感、必要设定、文风、目标总字数、目标 Chapter 和用户本轮整稿修改要求；未批准大纲不得启动首次整稿生成。

## 3. 可反复修改的大纲

### 3.1 强类型载荷

共享契约新增：

```text
ShortStoryAnchors:
  mustKeep: 必须保留的内容
  confirmed: 用户已经确认的创作决定
  avoid: 明确不要的内容

ShortStoryOutlineSection:
  id: 服务端稳定 ID，界面不作为正文标题展示
  title: 人类可读标题
  events: 本节发生了什么

ShortStoryOutlineDraft:
  originalInspiration: 原始灵感
  corePremise: 核心前提
  anchors: ShortStoryAnchors
  sections: 有序 ShortStoryOutlineSection 列表
  content: 一次性展示的完整人类可读大纲
  changeSummary: 本版相对上版的修改摘要
  anchorChanges: 全局修改实际改变的锚点；没有时为空
```

载荷禁止包含每节目标字数、章节映射、固定节数或固定节长。`content` 是供用户通读和确认的完整视图，结构化字段是局部编辑、版本合并和稳定引用的权威数据；二者保存时必须保持一致。

### 3.2 首次生成与修改

- 首次运行输出完整 `ShortStoryOutlineDraft`，直接进入 `awaiting_user`，不自动调用编辑、校验或 OOC reviewer。
- 用户可以直接编辑核心前提、锚点、任意分节标题和“发生了什么”，也可以提交“修改第 N 节”等自然语言要求。
- 局部修改时，Agent 输出只描述涉及稳定 section ID 的内部 patch；Core/Agent 服务层合并为新的完整载荷。未涉及分节的结构化值和文本必须原样保留。
- 分节序号只用于当前界面指代，真正合并依据稳定 ID；重排后不能把“第 N 节”永久当成实体标识。
- 全局修改允许新增、删除、替换或重排分节，但必须在 `anchorChanges` 中明确列出被改变的创作锚点，不能静默覆盖已确认决定。
- 每次修改后，前端始终展示完整大纲，不把内部 patch 作为用户主要阅读内容。

### 3.3 版本和并发语义

所有 ReviewArtifact 决策请求，包括 `approve`、`revise`、`discard`，都必须携带 `expectedRevision`，Core 必须在状态变化、正式应用或删除前校验其等于当前 revision。直接编辑、恢复历史等内容变更入口也必须携带 `expectedRevision`：

- 只有大纲可见内容或结构化载荷实际变化时才增加 revision。
- `draft`、`under_review`、`awaiting_user` 等状态切换不增加 revision。
- 相同 `clientRequestId` 的幂等重试和相同内容重放不增加 revision。
- 用户直接编辑必须先保存为一个新 revision，保存成功后才能批准该精确 revision。
- 恢复历史版本不是回退 revision 号，而是把选定历史内容复制成新的当前 revision。
- 过期 `expectedRevision` 返回版本冲突，不能覆盖新版本或批准旧内容。
- 每条用户修改要求原文同时写入 WritingMessage、WritingRunCommand 载荷和 revision diff；diff 可以附带模型摘要，但不能只保存摘要。

公开接口提供当前草案读取、版本列表、版本详情、恢复历史版本和保存用户大纲编辑。所有接口校验用户、小说、任务和 Artifact 归属。

## 4. 完整正文生成

### 4.1 生成门禁

- 首次 `write_short_story` 只接受用户已批准且 ReviewArtifact 状态为 `applied` 的当前大纲来源。
- 命令保存来源 outline Artifact ID、revision 和内容哈希；运行前再次核对，来源变化时拒绝使用旧大纲生成或应用正文。
- 每个首稿或自动返工 pass 只执行一次正文模型调用，并要求模型返回带现有完整正文边界标记的单一完整稿件；一次用户发起的 `write_short_story` 运行最多执行首稿和一次自动返工，即最多两次作家调用。
- 模型可按叙事需要自然分节，但分节不产生额外任务、Artifact、Chapter 或确认点。
- 不要求正文恰好等于目标字数；实际字数完整记录并由产品提示偏差。中短篇目标本身仍必须位于 6000～80000。

### 4.2 完整性边界

- 仅当规范化 `finishReason=stop`、边界标记完整、正文非空且尾部存在时，才创建或修订 `chapter_draft`。
- `length`、`content_filter`、矛盾完成原因、缺少尾部标记或非法 `unknown` 使整轮失败。
- 失败运行不保存半截正文为 Artifact，不自动续写，不把多次模型响应拼成一稿。
- 用户重试会创建新的完整运行，从头生成整稿；不能把失败输出当作下一轮前缀。

### 4.3 草案来源元数据

共享 `ShortStoryDraftMetadata` 至少包含：

```text
sourceOutlineArtifactId
sourceOutlineRevision
sourceOutlineHash
targetWordCount
actualWordCount
targetChapterId
baseChapterHash
```

`chapter_draft` 应用前，Core 锁定目标 Chapter 并核对来源大纲 ID/revision/hash 和正文基线 hash。大纲或目标正文基线变化时拒绝应用旧草案，不能用旧稿覆盖用户较新的修改。

## 5. 全稿审核与返工

中短篇 `chapter_draft` 不复用长篇的并行 reviewer 扇出。审核固定串行执行：

1. 编辑：检查整体结构、节奏、高潮和结局对开头及承诺的兑现；
2. 校验：检查人物、规则、时间线、因果与伏笔一致性。

两个 reviewer 都读取同一完整稿件和权威大纲，第二个 reviewer 不修改第一个结果。服务层在两次审核完成后合并结论。

- 首稿任一审核要求修改时，主责写作 Agent 只自动执行一次完整返工。
- 自动返工后的新整稿再次依次执行编辑、校验两轮审核。
- 第二轮仍有 `revise` 或 `block` 时停止自动循环，将完整草案、两轮结论和待处理问题交给用户。
- 因此一次用户发起的整稿运行最多有两个完整正文 pass；每个 pass 都从完整权威输入生成一篇完整稿件，不能把返工当作续写或片段拼接。
- 自动返工计数按本次用户发起的整稿运行记录，最大为 1；服务重启、回调重放和幂等重试不能重置计数。
- 用户可以继续提交新的整稿修改要求，次数不受限制；每个新的用户修改运行仍遵循单次生成和最多一次自动返工。

## 6. 用户确认与正式应用

- 大纲批准后才显示“生成完整初稿”。批准必须针对当前 `expectedRevision`。
- 正文始终通过 `ReviewArtifact -> 用户 approve -> Core 事务应用` 写入唯一“正文”Chapter。
- 正文批准时再次校验 `ShortStoryDraftMetadata`；任何来源过期都返回冲突并保留用户可见草案。
- 若最终一次校验 reviewer 明确通过，应用事务将现有章节一致性检查标记为“已由中短篇全稿审核覆盖”，并保留来源 Artifact/revision 作为可追溯依据。
- 若最终校验未通过、被阻断或用户在未解决问题时仍选择批准，章节一致性检查保持待处理，不能伪造 `completed` 或 `skipped`。
- 应用失败时恢复为可重试的等待用户确认状态，不得只更新 Artifact 而未写正文，或只写正文而未更新 Artifact。

## 7. 专用中短篇工作区

Workspace Bootstrap 的 Profile 决定渲染路径：

- `short_medium`：展示灵感与目标、完整大纲、锚点、分节编辑、自然语言修改、版本历史、恢复、批准、整稿生成、全稿审核结论和完整正文预览。
- `long_serial`：保留现有章节导航、章节编辑器、Beat Plan 和写作会话。

中短篇工作区必须满足：

- 可以直接编辑锚点、核心前提和各节内容；
- 可以提交自然语言修改并保留原文；
- 可以查看版本号、完整历史内容并恢复为新 revision；
- 未批准当前大纲时禁用完整初稿生成；
- 项目已创建但首次大纲任务失败时可重试；
- 正文预览保留完整内容并可滚动到尾部，统一使用 `countTextLength()`；
- 不出现“每节字数”“逐节生成”“下一节任务”或 Profile 切换控件。

## 8. 公共接口与服务契约

### 8.1 共享契约

新增并由 Core 与 Agent 共用：

- `ShortStoryOutlineDraft`
- `ShortStoryAnchors`
- `ShortStoryOutlineSection`
- `ShortStoryDraftMetadata`

同时扩展写作启动请求、ReviewArtifact 决策请求、Workspace Bootstrap 和 Dashboard DTO。公共接口先修改 FastAPI/Pydantic 契约，再运行 `npm run api:generate`；Web 只使用生成客户端类型，不手写重复 DTO。

### 8.2 新增公开能力

- 保存用户直接编辑的大纲并创建新 revision；
- 查询 Artifact revision 列表；
- 查询单一 revision 完整内容；
- 以历史 revision 内容恢复为新的当前 revision；
- 所有草案决策和内容变更都使用 `expectedRevision`，包括批准、返工、丢弃、直接编辑和恢复；
- 修改小说标题。

现有授权、归属、幂等命令和 SSE 恢复规则继续适用。大纲自然语言修改和整稿修改仍通过持久 WritingRunCommand 驱动 Agent；直接编辑、历史读取和恢复由 Core 权威接口处理。

## 9. 失败、幂等与兼容规则

- 项目创建和首次任务启动是两个可恢复阶段；创建成功不能因队列失败而丢失。
- Profile/Operation 不匹配、目标字数越界、未批准大纲、过期 revision、来源 hash 变化和正文基线变化都在模型调用或正式应用前明确失败。
- Artifact 状态重放、等待事件重发和同命令回调不得制造空 revision。
- Agent Service 仍不连接 PostgreSQL，只通过 Core 内部工具网关读取权威大纲、写入草案和审核结果。
- 稳定快照只保存必要上下文和来源标识，不保存全量 Workspace 或仅运行时身份。
- 长篇 `create_outline`、`revise_outline`、`plan_chapter`、`write_chapter`、Beat Plan、并行复审和逐章质量门禁不受本规格改写。

## 10. 影响范围

- `docs/requirements/01-projects-and-chapters.md`
- `docs/requirements/03-ai-writing-and-agents.md`
- `docs/requirements/04-review-quality-and-workflow.md`
- `packages/service-contracts`
- `apps/core-api` 的小说、工作区、写作命令、ReviewArtifact 和正式应用路径
- `apps/agent-service` 的 CreativeOperation、上下文、产物合并、正文生成和审核编排
- `packages/api-client` 生成代码
- `apps/web` 的创建入口、Dashboard、Workspace Bootstrap 和中短篇专用工作区
- Core、Agent、Web 与端到端测试

明确不修改 `apps/core-api/src/inkforge_core/db/schema-contract.json`、PostgreSQL schema、数据库枚举和迁移目录。

## 11. 验收标准

### 创建与分流

- [ ] 新建入口无默认 Profile，未选择时不能提交。
- [ ] 中短篇和长篇显示各自条件表单，长篇行为不回归。
- [ ] 中短篇 `5999/80001` 被拒绝，`6000/80000` 被接受。
- [ ] 中短篇创建唯一标题为“正文”的 Chapter，并立即尝试生成大纲。
- [ ] 首次任务失败时项目保留且可重试。
- [ ] Profile 创建后不能修改；旧越界中短篇可打开但不能启动新流程。

### Operation 与上下文

- [ ] 中短篇缺少显式 Operation 或组合不匹配时，模型调用次数为零。
- [ ] 纯灵感请求确定进入 `develop_short_outline`，不依赖关键词分类。
- [ ] 上下文严格遵循“直接编辑 → 修改原文 → 锚点 → 当前大纲 → 灵感 → 最近对话”优先级。
- [ ] 几十轮历史仍可查询，但不会全部进入模型输入。

### 大纲与版本

- [ ] 首次返回完整可读大纲，不包含固定节数、节长或每节字数。
- [ ] 局部修改按稳定 ID 合并，未涉及分节逐值保持不变。
- [ ] 用户可无限次改纲、直接编辑、批准、查看历史和恢复旧版。
- [ ] 内容变化才增加 revision；状态切换和幂等重试不增加。
- [ ] 直接编辑先保存新 revision；恢复历史复制为更大的新 revision。
- [ ] `approve`、`revise`、`discard`、直接编辑和恢复都校验 `expectedRevision` 并拒绝过期请求；用户修改要求原文可从消息、命令和 revision diff 追溯。

### 整稿与审核

- [ ] 大纲批准前不能生成正文。
- [ ] 每个生成或返工 pass 只调用一次作家模型并输出完整正文；一次用户发起运行最多首稿加一次自动返工，不逐节、不续写、不拼接。
- [ ] `finishReason=length` 不创建 Artifact，完整尾部标记可见。
- [ ] 正文元数据保存大纲来源、目标/实际字数、目标 Chapter 和正文基线。
- [ ] 编辑与校验固定串行，最多自动完整返工一次；第二轮仍有问题时等待用户。
- [ ] 用户可继续发起任意次数的整稿修改。
- [ ] 来源大纲或正文基线变化时，旧草案不能正式应用。
- [ ] 批准后完整正文写入唯一 Chapter；只有校验明确通过才标记全稿审核覆盖。

### 回归与架构

- [ ] Core 覆盖边界、Profile 锁定、显式 Operation、幂等版本、过期 revision、历史恢复、来源变化和应用事务测试。
- [ ] Agent 覆盖上下文优先级、局部 patch、单次整稿、截断失败、串行双审核和一次自动返工测试。
- [ ] Web 覆盖无默认模式、两套表单、专用工作区、大纲编辑/恢复/批准门禁和完整正文尾部。
- [ ] E2E 覆盖“灵感 → 多次改纲 → 批准 → 整稿 → 审核返工 → 批准 → 正式正文”，并使用 6000、80000 边界样本。
- [ ] 相关 pytest、全量 `uv run pytest`、Ruff、Mypy、`npm run api:generate`、`npm run api:check`、`npm run test:web`、typecheck、lint 和 build 全部通过。
- [ ] 数据库 schema 指纹与实施前完全一致。
