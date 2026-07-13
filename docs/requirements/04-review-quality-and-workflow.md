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

## 草案审核主流程

~~~mermaid
flowchart TD
    A["Agent 生成产物"] --> B["提交 ReviewArtifact"]
    B --> C{"是否需要复审"}
    C -->|"否"| D["状态 awaiting_user"]
    C -->|"是"| E["Reviewer Agent 复审"]
    E --> F{"submit_evaluation"}
    F -->|"pass"| G{"是否还有 reviewer"}
    G -->|"有"| E
    G -->|"无"| D
    F -->|"revise patch"| H["服务端应用小修补丁"]
    H --> E
    F -->|"revise rewrite"| I["主责 Agent 返工生成新 revision"]
    I --> E
    F -->|"block"| D
    D --> J{"用户决策"}
    J -->|"approve"| K["applyReviewArtifact"]
    J -->|"revise"| L["继续修改同一草案"]
    J -->|"discard"| M["删除草案"]
    K --> N["正式落库并标记 applied"]
~~~

## 用户决策

用户可对 awaiting_user 草案执行：

- approve：应用到正式数据；
- revise：继续修改；
- discard：丢弃。

前端需求：

- 聊天流显示草案卡片。
- 用户点击后打开审核弹窗。
- 文本草案可在弹窗内本地编辑，点击应用时提交 editedContent。
- agent_updates 草案支持勾选部分 section/item 后应用。
- 应用、丢弃或修改过程中需要展示 pending、success、error 状态。

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

## 一致性终检运行流程

Core API 负责浏览器认证、检查项归属和可选 `taskId` 绑定校验。`taskId` 必须与检查项属于同一用户、小说和章节，否则返回 403。任务成功进入 Redis 队列后接口才返回 202；Agent Service 异步生成报告，并通过签名内部回调更新状态。提交失败时不得提前把检查项改为 `running`。

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
- 用户批准后，不同 payload 类型能写入正确正式数据。
- 用户选择部分 agent_updates 时，只应用被选择的变更。
- 章节送审后能创建一致性终检。
- 一致性终检运行报告能保存到 ChapterQualityCheck。
- 章节完成前必须完成或跳过一致性终检。
- 章节状态和质量检查状态写入使用相同锁顺序：先锁章节并校验所有者，再锁质量检查项。

## Python 重构阶段实现

- Core API 已接管 ReviewArtifact 查询、物理丢弃、状态条件更新、修订记录和复审结论幂等写入。
- Agent 创建或修订草案、提交复审结论必须使用签名内部接口，并绑定同一用户、小说、任务和运行。
- 草案完成复审并进入 `awaiting_user` 后，Agent Service 必须发送草案等待确认事件，前端再通过 Core 查询权威草案内容，不能依赖进程内状态猜测。
- 首版跨服务复审不承诺局部草案 patch；需要修改时退化为完整草案重新生成。该降级必须明确记录并保留原有审核边界，不能把完整返工描述为局部修订，也不能因此直接写正式小说数据。
- 正文、大纲、Beat Plan 和 `agent_updates` 只有在 `awaiting_user` 状态下由用户批准后才能正式写入；应用失败会恢复为等待用户确认。
- `revision_brief` 永远不能正式应用，部分 `agent_updates` 只执行用户明确选择的 section 或 item。
- 正文和长文本不会静默截断；现有数据库无法承载的字段会明确拒绝。
