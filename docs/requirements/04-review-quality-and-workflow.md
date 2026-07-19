# 草案审核、质量检查与工作流需求

## 目标

保证 AI/Agent 产物不会绕过作者确认直接写入正式小说数据，同时给章节完成提供最小必要质量门槛。

## ReviewArtifact 待审核草案

ReviewArtifact 是 Agent 产物正式落库前的持久中间层。

### 状态

| 状态 | 含义 |
| --- | --- |
| draft | 草稿 |
| under_review | 复审中 |
| awaiting_user | 等待用户确认 |
| applying | 应用中 |
| applied | 已应用 |

允许流转：

~~~mermaid
stateDiagram-v2
    draft --> under_review
    draft --> awaiting_user
    under_review --> draft
    under_review --> awaiting_user
    awaiting_user --> draft
    awaiting_user --> under_review
    awaiting_user --> applying
    applying --> awaiting_user
    applying --> applied
~~~

### 类型

| 类型 | 用途 |
| --- | --- |
| agent_updates | 设定、大纲节点、伏笔、参考资料等结构化更新 |
| outline_draft | 文本大纲草案 |
| chapter_draft | 章节正文草案 |
| lore_draft | 设定文本草案 |
| revision_brief | 返工说明 |
| beat_plan_draft | 章节计划草案 |
| chapter_content | 章节正文 |
| beat_plan | 结构化 Beat Plan |
| freeform_markdown | 自由 Markdown 文本 |

中短篇复用 `outline_draft` 和 `chapter_draft`，但使用强类型 JSON 载荷：大纲保存原始灵感、核心前提、创作锚点、带稳定 ID 的有序分节、完整可读 content 和修改摘要；正文保存来源大纲 ID/revision/hash、生成时可选篇幅参考、实际字数、目标 Chapter 和正文基线 hash。篇幅参考不参与审核通过门槛，实际字数必须与正文一致。分节不成为独立 Artifact 或 Chapter。详细契约见 `docs/specs/2026-07-18-short-medium-writing-workflow.md`。

## 草案审核主流程

下图的 Reviewer 并行扇出适用于 `long_serial` 和其他非中短篇草案。`short_medium` 大纲不自动复审；中短篇整稿固定串行执行“编辑 → 校验”，最多自动完整返工一次后再串行复审。

~~~mermaid
flowchart TD
    A["Agent 生成产物"] --> B["提交 ReviewArtifact"]
    B --> C{"是否需要复审"}
    C -->|"否"| D["状态 awaiting_user"]
    C -->|"是"| E["向全部 Reviewer 并行扇出复审"]
    E --> F["合并全部 submit_evaluation 结论"]
    F --> G{"合并结果"}
    G -->|"pass"| D
    G -->|"revise"| I["主责 Agent 完整返工生成新 revision"]
    I --> E
    G -->|"block"| D
    D --> J{"用户提交单一决定请求"}
    J -->|"approve"| K["事务内正式落库、标记 applied、创建命令"]
    J -->|"revise"| L["事务内退回 draft、创建命令"]
    J -->|"discard"| M["事务内删除草案、创建命令"]
    K --> N["Agent 持久恢复并收敛任务终态"]
    L --> N
    M --> N
~~~

## 用户决策

用户可对 awaiting_user 草案执行：

- approve：应用到正式数据；
- revise：继续修改；
- discard：丢弃。

公开入口是 `POST /api/v1/review-artifacts/{artifactId}/decision`。请求必须携带 clientRequestId，Core 先按该标识检查幂等结果，再在一个数据库事务中完成正式写入或草案变化并创建 `artifact_decision` 命令，成功返回 202。前端随后只连接该任务 SSE，不再额外调用恢复接口。

所有 ReviewArtifact 决策，包括 `approve`、`revise`、`discard`，都必须携带 `expectedRevision`；Core 必须在正式应用、状态变化或删除前校验其等于当前 revision。直接编辑和恢复历史等内容变更请求同样必须携带并校验 `expectedRevision`。内容实际变化才增加 revision；状态切换、相同内容重放和幂等重试不增加。用户直接编辑大纲必须先保存为新 revision 再批准；恢复历史版本会复制为新的当前 revision，不回退版本号。过期 revision 返回冲突。用户修改要求原文必须保存在 WritingMessage、持久命令和 revision diff 中。

前端需求：

- 聊天流显示草案卡片。
- 用户点击后打开审核弹窗。
- 文本草案可在弹窗内本地编辑，点击应用时提交 editedContent。
- 中短篇大纲提供锚点和分节直接编辑、自然语言修改、完整版本列表/详情、历史恢复和当前版本批准；内部 patch 合并后仍展示完整大纲。
- 生成正文预览必须保留完整正文并使用统一字数统计；有限桌面高度内通过纵向滚动查看尾部，不得以隐藏、渐变遮挡或裁切替代完整显示。该显示方式不改变 ReviewArtifact 状态机、草案编辑、采纳动作或 Core 正式应用流程。
- agent_updates 草案支持勾选部分 section/item 后应用。
- 应用、丢弃或修改过程中需要展示 pending、success、error 状态。
- 刷新或断流后以任务、命令和草案的持久状态为准，不得依赖前端乐观状态伪造完成。

## 草案应用目标

### agent_updates

应用方式：

- 校验 AgentUpdates 结构；
- 如果用户选择部分应用，先按 selectedUpdateRefs 过滤；
- 调用 executeUpdates 正式写入；
- 写入成功后标记 applied。

可覆盖内容：

- 角色；
- 地点；
- 物品；
- 势力；
- 术语；
- 角色经历；
- 结构化大纲；
- 伏笔；
- 参考资料；
- 文本总纲；
- 世界设定；
- 故事背景。

### outline_draft

应用方式：

- 写入 Outline.content；
- 标记 applied。

中短篇大纲修改不自动进入编辑或 OOC 复审。局部修改按稳定 section ID 合并，未涉及部分原样保留；全局重排必须明确记录被改变的创作锚点。大纲批准后才允许启动完整正文生成。

### beat_plan / beat_plan_draft

应用方式：

- 必须有 chapterId；
- 写入 approved ChapterBeatPlan 和 SceneBeat；
- 旧计划应被 supersede；
- 标记 applied。

### chapter_draft / chapter_content

应用方式：

- 如果目标是 existing_chapter，写入指定章节正文。
- 如果目标是 new_next_chapter，创建下一章并写入正文。
- 应用后确保章节一致性终检项。
- existing_chapter 应用后必须退回 drafting 并清空 completedAt；正文实际变化时复用章节编辑路径，使旧质量结果失效并取消活动质量运行。
- 标记 applied。

中短篇 `chapter_draft` 只能写入创建时的唯一“正文”Chapter。应用前必须复核来源大纲 ID/revision/hash 和目标正文基线 hash；任一来源变化都拒绝旧草案。模型 `finishReason=length`、内容过滤、边界标记不完整或尾部缺失时不得创建草案，也不得自动续写或拼接。

中短篇全稿复审固定串行执行“编辑 → 校验”，不使用长篇并行扇出。首轮要求修改时最多自动完整返工一次，再串行执行第二轮双审核；仍有问题立即停止自动循环并交给用户。用户主动发起新的整稿修改不限制次数。

若最终校验明确通过，正式应用后可以把现有章节一致性检查记录为“已由中短篇全稿审核覆盖”；否则必须保持待处理，不得伪造完成或跳过。

正文草案目标：

~~~mermaid
flowchart TD
    A["chapter_draft"] --> B{"target.mode"}
    B -->|"existing_chapter"| C["覆盖/写入现有章节正文"]
    B -->|"new_next_chapter"| D["创建下一章"]
    C --> E["确保一致性终检"]
    D --> E
    E --> F["ReviewArtifact applied"]
~~~

## 章节质量检查

当前默认质量检查定义只有一致性终检。

检查项：

| 类型 | 标题 | Agent |
| --- | --- | --- |
| consistency | 一致性终检 | 校验 |

保留但非默认章后检查的类型：

- lore_sync；
- editorial；
- craft。

当前 quality-check API 只支持 consistency。设定同步、商业性评审和技法评审应通过写作草案流程或显式 Agent 操作处理。

一致性终检固定使用“校验”Agent 的 `quality` 执行模式，只暴露 `submit_quality_report`。报告契约由 Agent Service 与 Core API 共用，禁止分别维护可漂移的字段：

- `scores` 必须包含 characterConsistency、worldRuleConsistency、timelineConsistency、causalityConsistency、foreshadowingConsistency 五项 0..100 分数；
- `qualityGate` 只能是 pass 或 revise；
- 每个 issue 必须包含 dimension、severity、message、evidence、suggestion，可选 location；
- `report` 必须是非空完整自然语言报告，`rewriteBrief` 可选；
- 缺字段、额外字段、越界分数、非法 dimension/severity 或空报告都使质量任务失败，不能保存部分报告。

Core 把完整 scores、issues、report、qualityGate 和 rewriteBrief 保存到 `WorkflowRun.output`；`ChapterQualityCheck.result` 保存 report，`scoreOverall` 保存五项分数平均值经现有 Python `round()` 取整的结果。商业性评分列 `scoreHook/scoreTension/scorePayoff/scorePacing/scoreEndingHook/scoreReaderPromise` 保持空值，不能借用来存一致性维度。

## 一致性终检运行流程

Core API 负责浏览器认证、检查项归属和可选 `taskId` 绑定校验。`taskId` 必须与检查项属于同一用户、小说和章节，否则返回 403；只有 review 章节允许创建质量运行，drafting/completed 调用返回 409。Core 先把本次检查的完整正文快照、正文 SHA-256、章节更新时间、检查项和可选任务绑定保存到独立的 `WorkflowRun(kind=quality_check)`，并立即把公共检查置为 running，再使用该运行 ID 作为稳定队列标识投递；同一检查项已有 `pending/running` 运行时返回 409，只有前一次运行终态后才能创建新运行。Redis 暂时不可用时由 dispatcher 补投，不得丢失已受理任务，也不得与同一检查项的其他运行混淆。Agent Service 只分析 WorkflowRun 中的正文快照并异步生成报告，通过签名内部回调结算对应运行终态；回调时当前正文哈希必须仍与来源一致，且只有该检查项的最新运行可以更新公共检查结果。旧正文或旧运行的延迟回调收敛为 cancelled/failed，不能覆盖新结果或满足完成门禁。

~~~mermaid
sequenceDiagram
    participant U as 用户
    participant UI as 章节编辑器
    participant API as quality-check API
    participant V as 校验 Agent
    participant DB as 数据库

    U->>UI: 点击运行一致性终检
    UI->>API: POST checkId
    API->>DB: 校验登录、检查项归属、章节归属
    API->>DB: 校验可选 WritingTask 与检查项绑定
    API->>V: 提交异步质量检查任务
    API-->>UI: 返回 202、checkId、taskId
    V->>DB: 通过核心接口服务回写运行状态和报告
~~~

错误处理：

- 请求体不符合 Pydantic 契约时，按全局错误契约返回 422。
- 已通过请求体校验但业务类型不受支持时返回 400。
- 未登录返回 401。
- 越权返回 403。
- 检查项不存在返回 404。
- Agent 无报告或保存失败时，检查项标记 failed，任务标记 error。
- 模型返回长度截断、内容过滤、矛盾完成原因或无合法工具调用的 unknown 响应时，Agent Service 在接受报告或执行回调前失败；日志保留供应商原始完成原因。
- 内部回调必须校验用户、小说、检查项和运行的绑定关系，不得使用另一次运行的结果覆盖当前检查。
- 正文变化后，检查项重置为 pending，仍在 pending/running 的旧 WorkflowRun 标记 cancelled，错误码为 `QUALITY_SOURCE_CHANGED`。
- 浏览器在运行受理后轮询检查项到终态；pending/running 期间禁用重复运行、跳过和章节完成操作。
- 轮询失败或超时后保留 running 权威状态，并提供继续查询入口；活动运行期间公开状态接口拒绝重置/跳过，completed 章节拒绝任何检查状态修改。

## Beat Plan

Beat Plan 是章节写前规划的一等数据。

相关模型：

- ChapterWritingGoal：章节写作目标。
- ChapterBeatPlan：章节计划。
- SceneBeat：场景节拍。

SceneBeat 字段：

- 顺序；
- 场景目标；
- 冲突；
- 角色；
- 伏笔引用；
- 预估字数；
- 验收标准。

应用规则：

- Agent 生成 Beat Plan 后先进入 ReviewArtifact。
- 用户确认后写入 ChapterBeatPlan 和 SceneBeat。
- 正文写作可读取已批准 Beat Plan。

## WorkflowRun 与调试

WorkflowRun 记录工作流运行。

字段：

- novelId；
- chapterId；
- userId；
- kind：chat、chapter_generation、quality_check、lore_sync、beat_plan；
- status：pending、running、waiting_user、completed、failed、cancelled；
- sourceType/sourceId；
- currentAgentId；
- input/output；
- errorMessage。

WorkflowStep 记录运行步骤：

- agent；
- tool；
- user_confirmation；
- persistence。

调试页可读取工作流事件日志，用于查看 run、task 和事件。

## 验收标准

- Agent 正式变更必须先生成 ReviewArtifact。
- 草案状态流转符合契约，不允许非法跳转。
- 用户可以批准、丢弃或继续修改草案。
- 中短篇大纲可以无限次局部或整体修改，未涉及分节不因局部 patch 改变，并可按版本恢复为新的 revision。
- 中短篇整稿只在已批准大纲后生成，编辑和校验串行执行，最多自动完整返工一次。
- 中短篇正文来源过期时不能应用；只有最终校验明确通过才能标记全稿审核覆盖。
- 用户批准后，不同 payload 类型能写入正确正式数据。
- 用户选择部分 agent_updates 时，只应用被选择的变更。
- 章节送审后能创建一致性终检。
- 一致性终检运行报告能保存到 ChapterQualityCheck。
- 章节完成前必须完成或跳过一致性终检。
- 章节状态和质量检查状态写入使用相同锁顺序：先锁章节并校验所有者，再锁质量检查项。

## Python 重构阶段实现

- Core API 已接管 ReviewArtifact 查询、物理丢弃、状态条件更新、修订记录和复审结论幂等写入。
- 草案决定由 Core 事务编排器统一受理；正式数据、草案和持久命令任一写入失败时必须整体回滚。
- Agent 从稳定决定恢复时只推进 LangGraph 状态，不能第二次应用或删除已经由 Core 事务处理的草案。
- Agent 创建或修订草案、提交复审结论必须使用签名内部接口，并绑定同一用户、小说、任务和运行。
- 草案执行显式区分 primary、reviewer 和 reviser：reviewer 无读取工具，只读取注入的 Core 权威草案并提交一次 evaluation；reviser 获得原 payload、revision、artifactKey 和合并后的 requiredChanges，按原 Operation 产物契约生成同类新 revision。
- 草案完成复审并进入 `awaiting_user` 后，Agent Service 必须发送草案等待确认事件，前端再通过 Core 查询权威草案内容，不能依赖进程内状态猜测。
- 服务重启或新命令恢复自动复审/返工前，Agent Service 必须从 Core `planning.activeArtifact` 水合权威草案；approve/discard 已由 Core 事务完成，不依赖草案继续存在。等待态只在事件与 checkpoint 成功后、完成态和错误态只在相应回调成功后，按当前 QueueJob 的 `runId/jobId` 释放进程内记录。
- 长篇跨服务复审不实现局部草案 patch；所有 reviewer 修改结论归一为完整 rewrite，同时保留原 requiredChanges 和 patch 意图。中短篇改纲是显式例外：主责 Agent 可输出按稳定 section ID 定位的内部 patch，由服务层合并并保存完整新 revision；该 patch 不来自 reviewer，也不能直接写正式小说数据。
- 一致性终检由“校验”Agent 的 quality 模式执行，并通过共享严格报告契约保存完整 WorkflowRun 输出；旧商业评分列不承载一致性数据。
- 正文、大纲、Beat Plan 和 `agent_updates` 只有在 `awaiting_user` 状态下由用户批准后才能正式写入；应用失败会恢复为等待用户确认。
- `revision_brief` 永远不能正式应用，部分 `agent_updates` 只执行用户明确选择的 section 或 item。
- 正文和长文本不会静默截断；现有数据库无法承载的字段会明确拒绝。
