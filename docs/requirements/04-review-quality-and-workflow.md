# 草案审核、质量检查与工作流需求

## 长篇章节影视化方案审核

电影化镜头候选遵循 `proposal -> ReviewArtifact -> 作者结构编辑 -> 用户确认 -> Core 应用`。
Artifact 使用 `kind=video_adaptation_plan`，并通过 `videoAdaptationId + videoAdaptationTaskId` 外键绑定改编根和
来源任务。候选确认前不得创建正式 `VideoShotPlanVersion`、`VideoCinematicScene`、`VideoDramaticBeat`、
`VideoShot` 或来源锚点。

确认请求携带完整编辑后候选、`expectedArtifactRevision`、`expectedAdaptationRevision` 和稳定
`clientRequestId`。Core 锁定 Artifact、AdaptationHead 和来源任务，重新校验不可变章节哈希、Unicode 范围、
Scene/Beat/Goal/Shot 父子关系、连续 Key、镜头职责和切镜理由，然后在同一事务物化全部关系行、创建空 PromptHead、
标记 Artifact applied、切换当前 ShotPlan 指针并写 `VideoAdaptationDecisionCommand`。任一步失败整体回滚。

电影语法和节奏评估以 `reviewSummary + reviewFindings` 随候选进入人工审核。未覆盖目标、空间关系、平均时长、
慢镜比例、景别单调、相邻重复和生成可执行性都只能作为有证据的 notice/warning；不能禁用作者确认。硬门禁只负责
来源、版本、时间线、Key、父子引用、字段完整性和单镜时长合法性。正式方案修订任务必须绑定当前
`baseShotPlanVersionId`，确认后创建新版本并保留旧版本不变。

分集边界是独立不可变 `VideoEpisodePlanVersion`；逐镜 AI 提示词先保存在 `VideoAdaptationTask` 候选，只有用户
明确编辑并保存后才创建 `VideoShotPromptVersion` 和切换 PromptHead。Agent 回调不得直接覆盖正式提示词。

视觉设定图片先进入项目内候选槽。只有用户确认素材权利并点击批准后，Core 才创建不可变
`VideoVisualCanonVersion` 并切换当前版本；AI 不得自行批准。镜头参考集合使用独立 revision CAS。若用户从 AI 候选
保存提示词，PromptVersion 必须复制来源任务冻结的视觉版本；没有候选时复制保存时的当前镜头集合，后续换图不得
静默改变旧提示词依据。

长篇 CLI 通过具名 `long.video.*` 命令复用同一组 `/api/v1/video/**` 公共接口，覆盖项目、章节改编、
候选确认、分集、素材、视觉设定、逐镜参考、提示词保存、逐镜生成、候选 Take、选片确认、关键帧、
粗剪、声音字幕和整集导出。CLI 确认镜头方案前必须回读完整候选并核对
Artifact 与 Adaptation 双 revision；候选可从完整 JSON 文件提交，提示词可从完整 UTF-8 文本文件提交，
不得截断。改编 watcher 只轮询公共改编聚合，渲染 watcher 只轮询公共逐镜任务；停止观察不取消任务。Core 已删除旧 `VideoScene` 选区规划
公共接口，CLI 不连接数据库或内部接口，也不能绕过视频功能开关、人工确认、素材权利或 CAS。

逐镜生成只允许从镜头当前正式 PromptHead 创建任务，并冻结对应 PromptVersion 的视觉参考快照。每个成功任务最多
创建一个不可变 Take；用户选片通过 `clientRequestId + expectedTakeRevision` 切换 `VideoShotTakeHead`，旧 Take 和
旧命令结果必须保留。两个并发确认只有一个 CAS 成功，冲突命令也要持久化稳定回执。此选片确认不属于小说正文
ReviewArtifact 应用，也不得反向覆盖正式镜头或提示词。

关键帧按镜头和角色保存不可变版本；粗剪按正式分集保存完整镜头集合、Take、入出点和基础转场；声音字幕版本
必须固定引用一个粗剪版本。三类当前 head 分别使用 revision CAS，历史版本不随 head 切换而变化。整集导出只接受
没有占位镜头的粗剪，冻结素材哈希、输出参数和声音字幕决定后进入耐久任务；失败重试创建新任务并复用旧清单，
不得覆盖旧成片。以上制作决定不写回小说正文，也不以自动评分代替用户审片。

前端同时存在待审镜头候选与当前正式方案时，审镜步骤只展示候选指标，分集、视觉设定和提示词步骤只操作并标明
正式版本；不得用候选镜头数量或 Key 冒充正式上下文。提示词候选/正式版本继续展示自身冻结参考，若当前镜头参考
已经变化，页面必须说明历史快照不会自动更新，并由用户显式重新生成候选。高成本视觉效果没有正式依据时先进入
一次提示词纠正，纠正后仍存在只显示非阻断质量提醒，不得自动修改已确认镜头或正式提示词。

## 长篇选区 ReviewArtifact 应用

选区改写（章节正文或大纲正文/节点）必须保持 `proposal -> ReviewArtifact -> 用户确认 -> Core 应用` 闭环，禁止 CLI、Agent 或前端直接写入正式内容。选区草案的 `payload.target.mode` 为选区模式时，approve 只能提交结构化 `editedReplacement`（V1 CLI 仍可使用既有 `editedReplacementFile`）；V2 公共请求只允许 `editedReplacement`，不得提交 `editedContent`、`selectedUpdateRefs` 或改写 source/prefix/suffix。全文章节/大纲草案继续使用 V1 `editedContent`，Beat Plan 继续按既有结构化应用语义处理；V2 首切只开放 `long_serial/rewrite_chapter_selection/chapter_draft`，其他 kind 必须明确拒绝。

操作者在 approve 前必须先 GET Artifact，读取完整 diff（包括选区前后正文、replacement 和来源绑定），对该 diff 做一次独立确认，再使用稳定 `clientRequestId`、当前 `expectedRevision` 提交决定；V2 中该 wire 字段规范解释为 `expectedArtifactRevision`。Core 仍执行 sourceBinding preflight、幂等 fingerprint 与 revision/source CAS 校验。V1 返回受理后再次 GET Artifact/任务状态核对最终结果；V2 决定响应直接返回 PostgreSQL 权威 `WritingRunV2Response`，断流或结果不确定时仍按 `runId` 回读，不得从 HTTP 状态或前端乐观状态伪造完成。

## 目标

保证 AI/Agent 产物不会绕过作者确认直接写入正式小说数据，同时给章节完成提供最小必要质量门槛。

## ReviewArtifact 待审核草案

ReviewArtifact 是 Agent 产物正式落库前的持久中间层。

## 中短篇不可变版本

中短篇复用 ReviewArtifact 和 Revision 持久化蓝图、正文版本及完整 Diff，不新增 PostgreSQL
表。人工提交和历史恢复创建 `applied` 版本；Agent 文档任务创建 `awaiting_user` 候选。候选只有
在作者查看完整 Diff 并确认与该 Diff 绑定的 `confirmationHash` 后才能采用。

版本预览、提交、采用和恢复都必须校验文档类型、章节、基础版本、当前工作稿更新时间或内容哈希。
过期摘要、dirty 工作稿、过期基础版本和重复采用返回冲突，不能自动变基或静默覆盖。网络结果不
确定时依靠 `clientRequestId`、taskId 或 jobId 对账并幂等重放；版本内容和 Diff 不得截断。

Agent 完成回调必须在同一 Core 事务中创建候选或保存检查报告、收敛 WritingTask 与命令终态，并插入唯一 `WritingEventOutbox` 边界事件；Redis 通知失败不得否定已经提交的业务结果。
任一步失败都整体回滚，不能出现“任务完成但候选不存在”或“候选存在但任务仍运行”的状态。
终态稳定 checkpoint 只保存可重放的图快照，不得提前把数据库任务写成 completed/error；否则在完成回调到达前会形成任务终态、命令仍 processing 的伪冲突。
终态重复回调只有在 Agent 原始 result 与首次应用完全一致时才可视为已应用过；Core 后续补充的候选、报告或展示字段不能反过来放宽该幂等判定。没有命令指纹的历史终态遇到无法从任务字段证明一致的额外 result 必须拒绝。SSE 中的旧边界事件只用于展示，审核动作的成功、失败和释放必须由 PostgreSQL `run_outcome` 决定；旧草案载荷不能直接恢复操作入口，非 waiting_user 终态必须清理所属任务的临时草案界面并使先前在途读取失效；同一成功 outcome 的外部完成副作用只能执行一次。

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
| video_scene_plan | 仅用于历史 VideoScene 任务与数据库快照兼容的场景方案 |
| video_adaptation_plan | 仅限服务器 dev 库章节影视化 v2 的 Scene/Beat/Shot 关系化方案候选 |

`video_scene_plan` 不构成生产视频 schema 授权。旧 `VideoScene` 公共创建、查询、重试、返工、批准和
提示词预览入口已经删除；历史表、Artifact、`VideoReviewDecisionCommand`、内部回调和 Agent handler 仅用于
已有任务与结构契约兼容，不得重新形成公开准入或批准路径。完整删除这些历史结构必须另行获得版本化数据库迁移授权。

`video_adaptation_plan` 同样只属于具名 `novelwriterdev` 章节改编域，不授权生产迁移或真实视频渲染。
其批准入口使用独立 `VideoAdaptationDecisionCommand`，不得借用 `VideoReviewDecisionCommand.sceneId` 或
把正式层级重新塞回 `VideoScene.planJson`。

## 草案审核主流程

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
    J -->|"approve"| K["V1 创建命令；V2 事务内应用并完成 Run"]
    J -->|"revise"| L["V1 创建命令；V2 记录决定并创建 generation Step"]
    J -->|"discard"| M["V1 物理删除；V2 保留审计并完成 Run"]
    K --> N["按 engineVersion 收敛权威终态"]
    L --> N
    M --> N
~~~

全部 Reviewer 继续通过 LangGraph `Send` 并行扇出，但并发请求必须经过 Agent Service 共享 `ModelRuntime` 的全局模型门。2 核 2 GB 默认最多同时执行三个模型调用；当其他队列 job 也在运行时，额外 Reviewer 等待模型槽，不能绕过全局预算。同一 `novelId` 的独立队列 job 仍保持串行。

## 用户决策

用户可对 awaiting_user 草案执行：

- approve：应用到正式数据；
- revise：继续修改；
- discard：丢弃。

公开入口是 `POST /api/v1/review-artifacts/{artifactId}/decision`。请求必须携带稳定 `clientRequestId`；省略 `engineVersion` 只按 V1 兼容解释，V2 必须显式提交 `engineVersion=2`。Core 使用 `clientRequestId + requestHash` 做幂等：同标识同请求重放原响应，同标识不同请求稳定冲突。

- V1 保留既有 wire 和行为：事务内完成正式写入或草案变化、创建 `artifact_decision` 命令并返回 202 `ArtifactDecisionAcceptedResponse`，前端随后观察既有任务 SSE。
- V2 以 Artifact 上的 `workflowRunId` 为唯一持久身份，不伪造 WritingTask、WritingRunCommand 或 commandId；响应是权威 `WritingRunV2Response`。approve 在单事务内按 Unicode code point 精确替换选区并完成 Run；discard 不删除 Artifact、Revision 或 Evaluation，而把 Artifact head 移出 `awaiting_user`、保留为非 actionable `draft` 后完成 Run；revise 记录用户决定、使旧 revision 不再 actionable、保持 Run `running`，并创建绑定同一 EvidenceBundle 与旧 revision 的新 generation Step 供异步派发。
- V2 决定锁顺序固定为 Run → Artifact → 精确 Artifact Revision → source target。锁住 Chapter 后必须重算正文哈希、更新时间与 selectedTextHash；任一 revision/source CAS 不匹配都整体回滚。终态一旦提交不得被另一决定翻转。

前端需求：

- 聊天流显示草案卡片。
- 用户点击后打开审核弹窗。
- 文本草案可在弹窗内本地编辑，点击应用时提交 editedContent。
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

只有一致性终检的 `submit_quality_report` 使用 DeepSeek Beta strict Function Calling。Provider 为该工具生成专用 wire 契约：递归内联本地 `$defs`，不发送 `$defs`、`$def`、`$ref` 或 `type:null`；可选的 `location` 与 `rewriteBrief` 在 wire 中以必填字符串传输，无值时返回空字符串，并只在这两个精确路径归一化为 `None`。非质量 strict 工具必须在 HTTP 前拒绝。报告仍须通过原始 `QualityReportArgs`/Pydantic 完整复验，Provider 不截断或猜测修复业务字段；参数失败最多记录 10 条脱敏 `loc/type`，不得记录字段值、异常正文、`input`、`ctx` 或工具参数。无效工具 JSON 或 Pydantic 参数可以在任何工具副作用前触发整个 Agent 运行最多一次显式协议纠正；纠正调用不得回放坏参数，必须独立授权和结算 usage，仍失败时以不可重试的 `MODEL_TOOL_PROTOCOL_RECOVERY_FAILED` 收敛。该行为不是同一请求的 SDK 自动重发或队列盲重试。视频既有路由与能力门禁不变。

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
- 模型授权、供应商传输或用量回报明确声明可重试时，不得提前把检查项标记 failed；队列必须使用同一
  WorkflowRun/jobId 重试。明确不可重试错误在失败回调成功后收敛单条任务，不得因此重启整个消费者；未知
  程序异常仍由消费者监督器暴露为不健康。
- 模型返回长度截断、内容过滤、矛盾完成原因或无合法工具调用的 unknown 响应时，Agent Service 在接受报告或执行回调前失败；日志可以保留原始完成原因字符串。
- 质量协议错误日志可以保留安全大写 `failure_code` 和必要分类元数据，但不得保留供应商响应正文、异常正文或工具参数。
- 内部回调必须校验用户、小说、检查项和运行的绑定关系，不得使用另一次运行的结果覆盖当前检查。
- 正文变化后，检查项重置为 pending，仍在 pending/running 的旧 WorkflowRun 标记 cancelled，错误码为 `QUALITY_SOURCE_CHANGED`。
- 浏览器在运行受理后轮询检查项到终态；pending/running 期间禁用重复运行、跳过和章节完成操作。
- 轮询失败或超时后保留 running 权威状态，并提供继续查询入口；活动运行期间公开状态接口拒绝重置/跳过，completed 章节拒绝任何检查状态修改。

## Beat Plan

Beat Plan 是章节写前规划的一等数据。

Beat Plan 只承担正文前的剧情骨架职责。每个节拍说明目标、阻力或变化、参与角色、伏笔引用、预估字数和落点；验收标准如填写，只写一句可观察结果。全局设定、禁令、文风要求和专业规程不得复制进每个节拍，转折、代价、结果与余波应融入实际发生的节拍。

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
- `plan_chapter` 的 reviewer 与 reviser 除权威 Artifact 外，还接收 primary 使用的冻结最小作品投影，以核对名称、时间、数值和剧情边界；两者仍无读取工具，不得重新查询。
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
- 草案执行显式区分 primary、reviewer 和 reviser：reviewer 无读取工具，只读取注入的 Core 权威草案并提交一次 evaluation；reviser 获得原 payload、revision、artifactKey 和合并后的 requiredChanges，按原 Operation 产物契约生成同类新 revision。`plan_chapter` 的两种模式额外读取 primary 生成时的冻结最小作品投影，避免复审证据少于生成证据。
- 草案完成复审并进入 `awaiting_user` 后，Agent Service 必须发送草案等待确认事件，前端再通过 Core 查询权威草案内容，不能依赖进程内状态猜测。
- 服务重启或新命令恢复自动复审/返工前，Agent Service 必须从 Core `planning.activeArtifact` 水合权威草案；approve/discard 已由 Core 事务完成，不依赖草案继续存在。等待态、完成态和错误态都只有在对应 checkpoint/回调返回合法 `applied/already_applied` 凭证后，才能按当前 QueueJob 的 `runId/jobId` 释放进程内记录；等待态不再依赖先发 Redis 事件。
- Reviewer 的 `revise + rewrite` 使用现有 Reviser 完整返工；全部结论为严格 `revise + patch` 时，Agent 使用确定性 patch 节点创建同一 ReviewArtifact 的新 revision，不调用 Primary 或 Reviser。patch 目标找不到、多命中、重叠、非章节文本或 `ARTIFACT_REVISION_CONFLICT` 时不应用任何修改、不自动降级为 rewrite，进入带脱敏 failure code 的 `blocked`/`waiting_user`；其他 Core、网络或协议错误作为运行错误上抛，不能伪装成内容不通过。
- 一致性终检由“校验”Agent 的 quality 模式执行，并通过共享严格报告契约保存完整 WorkflowRun 输出；旧商业评分列不承载一致性数据。
- 正文、大纲、Beat Plan 和 `agent_updates` 只有在 `awaiting_user` 状态下由用户批准后才能正式写入；应用失败会恢复为等待用户确认。
- `revision_brief` 永远不能正式应用，部分 `agent_updates` 只执行用户明确选择的 section 或 item。
- 正文和长文本不会静默截断；现有数据库无法承载的字段会明确拒绝。
