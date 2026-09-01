# 长篇 CLI 服务端控制面规格

## 状态

- 日期：2026-08-05
- 状态：已确认，实施计划已编写，待实施
- 范围：长篇公共控制契约、任务恢复、ReviewArtifact 来源保护、CLI 命令面与生产操作边界
- 数据库：禁止修改 PostgreSQL schema

## 背景

仓库中的 `inkforge-cli` 当前只覆盖 `short_medium`。它已经具备登录、Windows Credential
Manager、公共 `/api/v1/**` 路径门禁、JSON 输入输出、SSE 重连、错误映射和完整文件写入等通用
基础，但业务调度、快照、版本和 Agent 操作都直接绑定中短篇：

- `tools/inkforge-cli/src/inkforge_cli/cli.py` 只注册 `short.*`，并把 Agent 操作固定映射为四种
  中短篇操作；
- `short.pull` 和 `tools/inkforge-cli/src/inkforge_cli/files.py` 假设一本作品只有一份文本大纲和
  一个全文章节，并用本地 manifest 与 dirty gate 管理它们；
- 生产 Skill、PowerShell wrapper 和 CLI 分别维护命令清单；
- 长篇已有章节、规划、设定、参考资料、文风、CreativeOperation、ReviewArtifact、质量检查和
  WritingTask，但公共接口缺少显式 Operation、任务列表、服务端取消和 Artifact 来源版本保护。

长篇不是“放大的中短篇文档”。它是以 Core 为权威的多章节、结构化资料、长任务和人工审核系统。
把中短篇 manifest 扩展为数百个章节文件，会在本地制造第二套正式状态，与现有产品边界冲突。

## 已确认决策

1. 长篇 CLI 是服务端控制台，不是本地同步工作区。
2. PostgreSQL 与 Core API 始终是小说、章节、任务、草案、质量状态和结构化资料的唯一权威来源。
3. 长篇不创建、不读取、不维护 manifest、dirty 文件树、章节镜像或本地任务账本。
4. Web 与 CLI 共用 `/api/v1/**` 公共业务契约；不新增 `/api/v1/cli/**` 专用业务层。
5. 保留一个 `inkforge` 可执行程序，复用认证、HTTP、SSE、配置和错误协议；内部按命令注册表和
   `short`、`long` 模块拆分。
6. 人工正式写入与 Agent 写入明确分开：人工章节编辑使用 CAS，Agent 产物必须经过
   ReviewArtifact。
7. 长篇 Agent 启动使用显式 operation、target 和 scope；Agent Service 不得再次用自然语言分类
   覆盖显式意图。
8. Core 提供可重新发现的任务列表、权威 outcome、SSE 恢复和幂等服务端取消。
9. 可应用 Artifact 必须绑定 Core 冻结的来源版本；来源漂移后禁止静默覆盖或自动变基。
10. 首个可写版本只开放已经具备幂等或 CAS 的命令。长篇小说创建、章节创建和缺少并发前置条件
    的结构化写入暂不开放给 CLI。
11. 不为本需求增加通用篇幅模式不可变守卫，不修改作品圣经 UI，也不设计篇幅迁移。只有显式
    `workflow="long_serial"` 的运行启动校验目标作品确实是 `long_serial`，这是请求契约校验。
12. 本规格一次定义目标架构和完整命令位置，代码按“Core 控制面、只读 CLI、章节闭环、资料能力”
    分阶段交付；任何长篇写命令都必须等对应服务端正确性门槛完成后才开放。

## 目标

- 让 CLI 能查询长篇作品、章节、规划、设定、资源、任务、草案和质量状态。
- 让 CLI 能安全完成人工章节保存、章节状态流转和章节进展维护。
- 让 CLI 能显式启动章节规划、正文生成和章节审核等 CreativeOperation。
- 让调用方在进程退出、SSE 断流或网络结果不确定后，只靠 Core 重新发现并恢复任务。
- 让用户通过 CLI 查看、返工、批准或丢弃 ReviewArtifact，但不能绕过正式审核边界。
- 让 Web 与 CLI 并发修改时由 Core 确定性拒绝过期写入。
- 保持中短篇现有版本、快照、Diff 和确认流程不变。

## 非目标

- 不把完整小说、章节树或任务账本同步到本地。
- 不直连 PostgreSQL、Redis、Agent Service 或 `/internal/v1/**`。
- 不允许 Agent、CLI 或生产 Skill 直接写正式 Agent 产物。
- 不自动批准、自动返工、自动连续启动下一阶段或自动完成章节。
- 不在首个章节闭环中实现跨章节批量生成、卷级自动编排或全书自动生产。
- 不在首个可写版本开放小说创建、章节创建、章节删除、章节重排或批量管理。
- 不在本需求修改 PostgreSQL enum、增加幂等表、增加来源绑定列或执行任何 DDL。
- 不处理全局篇幅模式不可变或长短篇迁移。

## 已接受风险

现有作品圣经入口仍能修改 `storyLengthProfile`。按本次已确认边界，长篇任务只在 start 校验
`long_serial`，后续 resume、Artifact decision/apply 和 cancel 不重复校验，也不把篇幅模式加入
sourceBindings。也就是说，若用户在任务进行中主动切换篇幅模式，旧长篇任务仍按启动时冻结的
workflow 继续；这是单用户前提下明确接受的风险，不得在实施时擅自扩成全局守卫。未来若开放多用户
或篇幅迁移，必须另立规格处理跨模式中的任务与 Artifact。

## 方案选择

已比较三种服务端方案：

1. **只包装现有接口（拒绝）**：能快速增加读取命令，但无法解决 Operation 猜测、任务丢失、取消、
   幂等指纹和 Artifact 覆盖。
2. **增加 CLI 专用聚合接口（拒绝）**：会复制 Web 已有业务规则，形成第二套权限、并发和审核语义。
3. **扩展共享公共控制契约（采用）**：由 Core 统一承担归属、幂等、并发、任务、Artifact 和正式
   写入规则，Web 与 CLI 只是不同客户端。

已比较三种 CLI 组织方式：

1. **继续扩展单文件 `cli.py`（拒绝）**：当前文件已经同时承担解析、校验、业务映射、文件写入、
   SSE 和错误处理，继续堆叠会放大分支耦合。
2. **新增独立长篇二进制（拒绝）**：会复制登录、凭据、origin、HTTP、SSE 和错误协议。
3. **单二进制、模块化命令注册表（采用）**：保留现有入口和公共基础设施，隔离中短篇本地快照
   语义与长篇服务端控制语义。

## 权威数据流

```text
作者或 Codex
    -> inkforge CLI
       -> Core /api/v1/**
          -> PostgreSQL 业务事实
          -> Redis 执行队列与 SSE
          -> Agent Service
             -> Core 内部工具网关
             -> ReviewArtifact
```

本地允许保存：

- profile 中的 origin 和用户名；
- Windows Credential Manager 中的会话 Cookie；
- 单次命令显式指定的输入文件或输出文件；
- 当前 CLI 进程内的 SSE `Last-Event-ID`。

本地禁止成为权威状态的内容：

- 章节、总纲、Beat Plan、设定或参考资料镜像；
- taskId、artifactId、revision、updatedAt 或质量运行的持久账本；
- 长篇 manifest、dirty 标志或本地版本号；
- 由日志、聊天记录或 SSE 片段推断的正式正文和终态。

`contentFile`、`editedContentFile` 和 `outputFile` 只是一次命令的数据载体。CLI 不追踪其后续变化，
也不根据它们判断服务端是否可写。

## 显式长篇运行契约

### 公共请求

`POST /api/v1/writing/runs` 新增显式长篇判别分支。现有 Web 自然语言聊天请求和中短篇请求保留
兼容；CLI 只使用新分支。

```json
{
  "clientRequestId": "long-plan-20260805-0001",
  "workflow": "long_serial",
  "novelId": "novel-id",
  "chapterId": "chapter-id",
  "writingSessionId": "session-id",
  "operation": "plan_chapter",
  "target": {
    "type": "chapter",
    "id": "chapter-id"
  },
  "scope": {
    "kind": "chapter",
    "chapterId": "chapter-id"
  },
  "targetWordCount": 4000,
  "userInstruction": "规划本章，强化结尾悬念"
}
```

字段规则：

- `clientRequestId`：调用方生成并在网络结果不确定时稳定复用，长度继续为 16..128。
- `workflow`：固定为 `long_serial`；Core 只在本入口校验作品的实际篇幅类型与其一致。
- `novelId`：必填并校验当前用户归属。
- `chapterId`：现有非空 `WritingTask.chapterId` 所需的执行锚点；章节 scope 中必须与 target 和 scope
  的章节一致。未来 novel/outline_node scope 仍需提供属于同一小说的上下文锚点，除非另有独立
  schema 规格。
- `writingSessionId`：可选；存在时必须与用户、小说和章节目标一致。
- `operation`：使用共享契约中的当前可执行 CreativeOperation；`sync_lore` 只保留历史快照解析兼容，
  不能出现在新请求中。
- `target`：描述本次要评价或产生正式候选的业务对象。
- `scope`：描述 Core 允许投影到 Agent 上下文的权威范围。
- `targetWordCount`：只在对应 Operation 支持时生效，不代表模型最大输出能力。
- `userInstruction`：保留用户原始要求，但不再负责决定 Operation 身份。
- 显式请求不接受 `selectedAgents`；主责 Agent、reviewers、产物类型和工具白名单由服务端
  `OperationDefinition` 推导。

### target 与 scope

target 是可扩展的判别联合，首个章节闭环只实现以下稳定形状：

```text
ChapterTarget
  type = chapter
  id   = 已存在章节 ID
```

scope 从第一版定义以下命名空间：

```text
ChapterScope
  kind = chapter
  chapterId

ChapterRangeScope
  kind = chapter_range
  chapterStartOrder
  chapterEndOrder

OutlineNodeScope
  kind = outline_node
  outlineNodeId

NovelScope
  kind = novel
```

`outline_node` 直接复用现有 `stage -> plot_unit -> chapter_group` 层级；不虚构数据库中不存在的
“卷”实体。`chapter_range`、`outline_node` 和 `novel` 在契约中预留，但未实现的 Operation 组合必须
返回明确 `LONG_SCOPE_NOT_SUPPORTED`，不能静默缩小为当前章节。

首个执行矩阵：

| operation | target | scope | 结果 |
| --- | --- | --- | --- |
| `answer_question` | 已存在章节 | 当前章节 | 直接保存会话中的 Agent 回答；不创建 ReviewArtifact |
| `plan_chapter` | 已存在章节 | 当前章节 | `beat_plan` ReviewArtifact |
| `write_chapter` | 已存在章节 | 当前章节 | `chapter_draft` ReviewArtifact |
| `review_chapter` | 已存在章节 | 当前章节 | 只读审核结果，不正式写入 |

`answer_question` 的耐久 V2 首切额外要求非空 `writingSessionId`，并由 Core 校验其属于同一用户、小说和章节；
字段缺失、显式 `null`、空字符串或其他非字符串类型时 CLI 在联网前返回 `WRITING_SESSION_REQUIRED`。
CLI 仍使用同一个 `long.agent.start`，示例：

```json
{
  "clientRequestId": "long-answer-20260901-0001",
  "novelId": "novel-id",
  "chapterId": "chapter-id",
  "writingSessionId": "session-id",
  "operation": "answer_question",
  "target": {"type": "chapter", "id": "chapter-id"},
  "scope": {"kind": "chapter", "chapterId": "chapter-id"},
  "userInstruction": "这一章的主要冲突是什么？"
}
```

Operator Skill 更新时必须把 `answer_question` 加入 `long.agent.start` 允许集合，但不能把预留的
`novel/chapter_range/outline_node` scope 一并开放。启动返回可能是 V1 或 V2；Skill 必须按响应中的
`engineVersion` 判别，随后复用 `long.task.watch`。V2 问答完成后从任务状态的 `artifact` 读取结果是错误的；
权威回答位于绑定 WritingSession 的消息历史，`completed` 事件仅提供
`outcomeType=chat_answer + resultId=<WritingMessage.id>`。重试必须复用原 `clientRequestId`，不得因超时创建新 ID。

Java CLI 成为正式入口不等于 Python 兼容 CLI 可以提前失去契约能力。在 Python CLI 退役前，两种实现的
`long.agent.start` 都必须显式允许 `answer_question`，并在任何目标业务请求前完成以下校验：

- `target` 必须是当前 `chapterId` 的章节 target，`scope` 必须是同一 `chapterId` 的章节 scope；不能接受
  预留 scope、错章 ID 或依靠 Core 静默缩小范围；
- `writingSessionId` 必须存在且为非空字符串；字段缺失、显式 `null`、空字符串或其他非字符串类型固定返回
  `WRITING_SESSION_REQUIRED`。这个专用错误只适用于 `answer_question`；其他 Operation 对可选
  `writingSessionId` 的既有 `null`/类型校验语义保持不变；
- `userInstruction` 必须包含至少一个非 Unicode 空白字符，但发送时逐字符保留原值，不做 trim、规范化或
  截断；
- `clientRequestId` 继续由调用方提供并在不确定重试时稳定复用；CLI 只增加固定
  `workflow=long_serial`，其余合法业务字段和值按公共请求原样发送。

底层 CLI 单元测试必须证明上述非法输入产生零业务 API 请求。生产 Skill wrapper 仍先执行固定
`auth.whoami`，因此 wrapper 级“零业务请求”不等于整个进程零网络；两种口径不得混写。

后续开放 `rewrite_scene`、大纲、设定和伏笔操作前，必须先为各自 target 增加严格判别模型、来源绑定
和目标互斥规则；不能先接受无类型字典再依靠 Agent 猜测。

### Core 规范化与持久化

Core 在创建任务的同一事务内：

1. 校验登录、小说归属、执行锚点章节归属、可选会话绑定和 `long_serial` workflow。
2. 校验 operation、target、scope 的交叉约束。
3. 从共享公开 Operation 投影推导主责 Agent、reviewers、允许的 target/scope 和 Artifact 类型。
4. 读取并冻结来源绑定。
5. 生成不包含 `clientRequestId` 的规范化请求 JSON 和 SHA-256 指纹。
6. 创建 `WritingTask` 与 `WritingRunCommand`，按后文 `_inkforgeCommand + job` envelope 保存
   `payloadJson`，并把 operation、target、scope、来源绑定等运行恢复所需的稳定投影写入
   `graphStateJson`。

`packages/service-contracts` 增加严格 `LongSerialRunPayload`，替换 Agent job 中对此分支的无类型
payload 字典；同时增加精简、权威且不依赖运行时实现的 `PublicOperationDefinition`，至少包含
operation、workflow、target kind、允许的 scope kind、mutating、principal agent、reviewers 和
artifact kind。Core 只导入这份公开投影，不得反向导入 Agent Service。Agent Service 保留包含工具、
提示词和上下文装配器的完整定义，并在启动/测试时逐项校验其公开字段与共享投影一致，避免复制两份
可漂移映射。完整历史 Operation 类型仍兼容 `sync_lore`，但新增“当前可执行 Operation”类型或校验器，
确保新任务不能生成该历史标识。

Agent Service 收到显式 payload 后直接构造规范化 CreativeOperation，跳过父图的自然语言分类节点。
显式 operation、target 和 scope 必须原样进入稳定快照和状态投影；Agent 不能扩大 scope、切换主责
Agent 或改变 Artifact 类型。

公共契约统一使用 `workflow="long_serial"`。现有 Core 内部 `long_form` 投影名称在实现时归一为
`long_serial`；历史未显式保存 workflow 的长篇任务仍按长篇兼容读取，并在公共响应投影为
`long_serial`，不回写数据库。

## 任务查询与恢复

### 任务列表

新增：

```text
GET /api/v1/writing/runs
```

查询参数：

- `novelId` 必填；
- `chapterId`、`writingSessionId`、`operation`、`outcome` 可选；
- `limit` 默认 50、最大 100；
- 列表按不可变的 `createdAt DESC, id DESC` 排序，cursor 使用 `createdAt + id`，不使用会在任务运行中
  移动的 `updatedAt`，也不使用页码。

列表必须包含未绑定 WritingSession 的任务，并返回：

```text
taskId
novelId
chapterId
writingSessionId
workflow
operation
target
scope
phase
outcome
activeArtifactId
recoverable
createdAt
updatedAt
```

所有查询先按 Novel 所有者过滤。不能让调用方用已知 taskId、sessionId 或 chapterId 探测其他用户
任务。

### 单任务状态

现有 `GET /api/v1/writing/runs/{taskId}` 返回 `WritingRunStatusResponse`，保留兼容字段，并补充
workflow、operation、target、scope、当前 checkpoint、activeArtifactId、recoverable、可空的
`reviewReport` 和统一 outcome。

`WritingRunStatusResponse.checkpoint` 是可空的公共投影；非空时只返回以下四个字段：

```text
eventSequence
phase
operationStage
operationStep
```

其中 `operationStage` 和 `operationStep` 可空。公共响应不得直接返回 `graphStateJson`，也不得泄露
完整 LangGraph 快照、消息、工具结果或模型中间状态。

outcome 增加 `cancelled`：

```text
queued | running | waiting_user | succeeded | failed | cancelled | inconsistent
```

CLI 和 Web 只用 outcome 控制生命周期。`phase` 只作兼容展示；`inconsistent` 和 `cancelled` 都可以
由现有数据库事实派生，不增加 `WritingTask.phase` 枚举。

`waiting_user` 必须满足：存在归属正确、状态为 `awaiting_user` 的权威 Artifact，并在
`outcome.result` 中返回其 ID。`succeeded` 必须满足对应 Operation 的真实结果已经由持久数据库事实证明；
显式任务的 `phase=completed` 本身不是成功证据，不能继续沿用旧的“completed 即 succeeded”兼容规则。

显式长篇任务的结果事实按 Operation 固定：

- `plan_chapter`：只接受同 task、kind=`beat_plan` 的权威 Artifact，`outcome.result` 返回该 Artifact ID；
  `waiting_user` 时它必须为 `awaiting_user`，approve 后的 succeeded 必须能证明它已 `applied`，discard 后的
  succeeded 必须有同 task、同 artifactId 且 `deleted=true` 的持久 decision command 结果，revise 后必须
  回到新的 `awaiting_user` revision。
- `write_chapter`：规则与 plan 相同，但 Artifact kind 必须为 `chapter_draft`；Artifact ID 和 decision 事实
  必须来自同一 task 的持久记录，不能从任务 phase、SSE 或图快照猜测。
- `review_chapter`：不创建可应用 Artifact；只有有效结果 command 的持久 `resultJson` 来自终态 callback，
  且其中 `finalResponse` 是非空完整字符串时才可 succeeded。此时 `outcome.result` 固定为
  `kind=final_message, ready=true`，`WritingRunStatusResponse.reviewReport` 原样返回完整 `finalResponse`；
  其他 Operation 或尚未形成该成功事实时，`reviewReport` 为 `null`。

显式任务缺少上述 Artifact、decision command 或结果 command，Artifact/结果 kind 与 Operation 不符，
Artifact/task/command 身份不一致，或者 review 报告为空时，一律投影为 `inconsistent`，不能回退到任务
phase 伪造 succeeded。历史没有 command 的旧任务继续使用既有只读兼容投影，不倒推或补写结果。

有效结果 command 通常就是当前 command。若当前 command 是 `effective=false` 的终态 no-op cancel，
projector 必须沿 `priorOutcome.currentCommand.id` 读取前一个持久 command；连续执行多个终态 no-op cancel
时继续沿链解析，直到找到原业务 command。链缺失、循环、跨 task 或不能回到合法原 command 时投影为
`inconsistent`。当前 cancel command 仍作为审计意义上的 currentCommand 返回，但 plan/write 的 Artifact
事实和 review 的完整 `finalResponse` 必须从有效结果 command 验证，不能因 no-op cancel 丢失或降级。

### resume 边界

`POST /api/v1/writing/runs/{taskId}/resume` 只接受普通继续输入和稳定 checkpoint 所需回答。公开
`ResumeWritingRunRequest` 移除 `artifactId/decision` 分支；草案 approve、revise、discard 只能走
ReviewArtifact decision 接口。

```json
{
  "clientRequestId": "long-resume-20260805-0001",
  "writingSessionId": "session-id",
  "userMessage": "保留当前视角，继续"
}
```

`writingSessionId` 和 `userMessage` 保持可选，额外字段严格拒绝。Core 继续校验可选会话与任务绑定，
并把规范化请求指纹写入 resume command；空消息只能继续一个确实处于可恢复 checkpoint 的任务。

ReviewArtifact decision 生成的内部恢复命令必须继承原始显式长篇 start job 的 `workflow`、`operation`、
`target`、`scope`、`sourceBindings`、`targetWordCount` 和 `userInstruction`，只把 `resume` 改为 true，
并在严格 `resumeInput` 中同时保存 `artifactId`、`decision` 和可选 `userMessage`。这组内部字段不因此开放给
公共 resume 接口；Agent Service 必须从显式 payload 恢复 `resumeDecision`，不能退回无类型字典分支。

现有 Web 已使用 decision 接口处理草案动作；普通聊天和章节目标确认的 resume 行为保持不变。

## 服务端取消

新增：

```text
POST /api/v1/writing/runs/{taskId}/cancel
```

请求：

```json
{
  "clientRequestId": "long-cancel-20260805-0001"
}
```

取消是持久命令，不等同于关闭 SSE：

1. Core 先取得请求幂等锁，再按统一关系锁序锁定小说、章节、任务和当前命令，校验归属并复核状态。
2. 若任务已终态，保存并返回幂等 no-op 取消结果，不改变原业务结果。
3. 若任务正以权威 Artifact 等待用户，在任何状态变更前返回
   `409 ARTIFACT_DECISION_REQUIRED`；取消不能暗中删除草案，用户必须显式执行 discard。
4. 对其他非终态任务，Core 在同一事务中把旧活动命令置为 `failed`，result 记录
   `code=WRITING_RUN_CANCELLED_BY_USER`、旧 jobId 和新 cancel commandId；随后创建 pending
   `cancel` WritingRunCommand，payload 保存被取消的 command/job ID。插入取消命令前必须先把旧命令
   的终态更新 flush 到 PostgreSQL，避免活动命令部分唯一索引把同一事务误判为两条活动命令。任务
   phase 暂不进入终态。
5. cancel dispatcher 调用 Agent Service 的签名 DELETE。Redis 暂时不可用时 cancel command 保持
   pending 并重试；这期间旧 job 的 Core 写型副作用已经因“当前命令身份”变化而被拒绝。
6. Agent 队列对尚未 enqueue 的 job 也必须写入 `cancelled` tombstone，并按现有终态保留期回收；同一
   jobId 的迟到 enqueue 必须识别 tombstone 并拒绝入队。DELETE 204 表示取消意图已经持久接受，不是
   仅表示调用瞬间找到了队列项。
7. 收到 204 后，Core 把 cancel command 标记为 `succeeded`，result 保存
   `effective=true`、cancelledCommandId 和 cancelledJobId，并把任务置为现有 `error` 终态。取消事实
   只存于 command result，不把控制标记塞入稳定图快照。
8. outcome projector 在通用终态冲突判断之前识别 succeeded cancel：`effective=true` 投影为
   `cancelled`；`effective=false` 按 result 中的 priorOutcome 保留原终态。
9. 取消不创建 `WritingEventOutbox`。现有 SSE 会周期读取 PostgreSQL outcome 并发送无 cursor 的
   `run_outcome` 控制帧，因此不与 Agent 的 sourceSequence 账本竞争。
10. 已被取消命令的迟到 checkpoint、complete、fail 和写型内部工具请求都按精确 jobId 拒绝，不能
    重新打开任务或创建/修订 Artifact。

终态 no-op 取消也保存一条 succeeded `cancel` command，使 clientRequestId 能绑定请求指纹；其 result
明确包含 `effective=false`、`alreadyTerminal=true` 和取消前的完整权威 `priorOutcome`（state、code、
result 及前一个 command 身份，不复制 observedAt）。outcome projector 显示本次 cancel 为当前命令，但
必须从 priorOutcome 保留原状态和结果，并按上面的有效结果 command 规则解析原业务证据，不能把原成功
或失败改写成取消，也不能丢失原产物 ID 或 `reviewReport`。

竞态由统一锁序决定：完成事务先提交时，取消成为终态 no-op；取消事务先提交时，旧 job 立即失去
当前命令身份。Agent 已进入一次模型调用时不承诺瞬时打断网络请求；Agent 在模型返回后、图节点切换
前和每次工具调用前检查取消信号。所有写型内部工具请求新增 jobId 并纳入服务签名请求体，Core 在写入
事务中按 `taskId + jobId` 复核当前命令。这样即使 Agent 尚未观察到取消，正式副作用也由 Core 硬拒绝。

`WritingRunCommand.status` 继续使用 pending、submitted、processing、succeeded、failed；不增加
cancelled 命令状态。现有 PostgreSQL `WritingRunCommand_kind_check` 只允许 `start`、`resume` 和
`artifact_decision`，且本项目禁止修改正式结构，因此取消命令以 `resume` 作为物理兼容值持久化，
`_inkforgeCommand.commandKind=cancel` 才是权威逻辑命令类型。所有投递、重放和 outcome 投影必须通过
统一解析函数读取逻辑类型，不能直接用物理 `kind` 判断取消语义。取消含义由逻辑 command kind、result
和 outcome 表达。

## ReviewArtifact 来源版本保护

### sourceBindings

所有新建长篇 run（包括现有 Web 自然语言入口和显式 CLI 分支）都在 Agent 使用上下文前，由 Core
冻结首个章节闭环的权威来源。显式 Operation 使用其精确来源集合；现有自然语言入口在尚未分类时
冻结该集合的保守并集。首阶段只把这套绑定声明为 `plan_chapter`、`write_chapter` 及其 Artifact kind 的
强制应用前置条件，其他结构化 Operation 按 C 阶段逐类补齐，不能用这份章节绑定冒充完整保护：

```json
{
  "sourceBindings": [
    {
      "resourceType": "chapter",
      "resourceId": "chapter-id",
      "exists": true,
      "updatedAt": "2026-08-05T10:00:00Z",
      "contentSha256": "64位小写SHA-256",
      "revision": null,
      "absenceSentinel": null
    }
  ]
}
```

不存在的资源也必须使用稳定逻辑 ID，并把 `absenceSentinel` 严格保存为仅含
`resourceType/resourceId` 的父资源引用。例如不存在的小说级文本总纲固定为：

```json
{
  "resourceType": "outline",
  "resourceId": "novel:<novelId>:outline",
  "exists": false,
  "updatedAt": null,
  "contentSha256": null,
  "revision": null,
  "absenceSentinel": {
    "resourceType": "novel",
    "resourceId": "<novelId>"
  }
}
```

`exists=false` 时 `updatedAt/contentSha256/revision` 必须全部为 `null`，`absenceSentinel` 必填；
`exists=true` 时 `absenceSentinel` 必须为 `null`。不存在的已批准 Beat Plan 同样使用稳定逻辑 ID
`chapter:<chapterId>:approved_beat_plan`，sentinel 指向对应 Chapter；不得用空 ID、随机 ID 或父资源 ID
冒充目标资源 ID。

首个章节闭环至少冻结：

- `plan_chapter`：目标章节、文本总纲、当前已批准 Beat Plan（存在时）；
- `write_chapter`：目标章节、文本总纲、当前已批准 Beat Plan；
- 尚未分类的现有 Web 长篇入口：冻结目标章节、文本总纲和当前已批准 Beat Plan，分类结果只能缩小
  使用范围，不能替换这份绑定；
- 不存在的目标资源使用 `exists=false`，使“期间新建了正式资源”也能形成冲突。

Core 把绑定保存到 start command 和稳定 job payload。Agent 创建 Artifact 时不负责声明或重写
sourceBindings；Core 根据 task/command 权威快照附加。返工 revision 继承原绑定，不能借返工切换
来源。需要基于新来源继续工作时必须启动新任务。

在不改 schema 的前提下，原 start command payload 是绑定的唯一权威副本。Core 在 Artifact 及每个
ReviewArtifactRevision 的现有 payloadJson 中注入保留控制字段
`_inkforgeControl.sourceCommandId`；Agent 请求若自带 `_inkforgeControl` 必须拒绝。公共 serializer 从
业务 payload 中剥离该保留字段，再通过 sourceCommandId 读取并返回 sourceBindings。decision 在锁内
校验 source command 与 Artifact 属于同一 task；控制字段或命令缺失时按 `legacy_missing` fail closed，
不能复制当前来源补洞。

每个 `exists=false` 绑定必须同时声明可加锁的父级 absence sentinel：目标章节下 Beat Plan 使用
Chapter，小说级文本总纲使用 Novel。对应资源的所有创建、更新、删除和 Artifact 应用路径都先按统一
锁序锁定同一个 sentinel，再检查子行是否存在；不能尝试给不存在的行加锁。后续新增资源类型时，没有
共同 sentinel 的类型不得进入 sourceBindings 或开放 CLI 写入。

文本资源的 `contentSha256` 对 Core 当前完整字符串的原始 UTF-8 字节计算，不执行 Unicode 规范化、
换行转换或截断。Beat Plan 等结构化聚合按公开响应字段组装完整对象，子项固定按 `order, id` 排序，
再按同一 canonical JSON 规则计算 hash；不能只比较父行 updatedAt 而漏掉 SceneBeat 变化。时间由 Core
规范化为 UTC ISO 8601 后比较。

### 决策与应用

ReviewArtifact 响应增加只读、可空的 `sourceBindings` 和
`sourceBindingStatus=verified | legacy_missing | not_yet_supported`。首阶段新建的 beat_plan/chapter_draft
Artifact 必须为 `verified` 且绑定非空；功能上线前同类 Artifact 无法证明历史快照时返回
`legacy_missing`。这类历史 Artifact 仍可读取和显式 discard，但 approve/revise 必须 fail closed 返回
`409 ARTIFACT_SOURCE_BINDINGS_MISSING`，不能根据当前数据反推一个假历史快照。其他结构化 Artifact
在 C 阶段补齐前标记 `not_yet_supported`，保持现有 Web decision 行为，但长篇 CLI 的
approve/revise 明确拒绝，discard 仍允许。部署前只读列出 `legacy_missing` 的 awaiting_user Artifact，
提示用户先处理或在部署后 discard 并重新生成；不能在发布脚本中自动批准、丢弃或补造绑定。
decision 请求增加 `expectedRevision`：

```json
{
  "clientRequestId": "artifact-approve-20260805-0001",
  "expectedRevision": 2,
  "decision": "approve",
  "editedContent": null,
  "selectedUpdateRefs": null,
  "userMessage": null
}
```

approve、revise 和 discard 都校验 Artifact 当前 revision。decision 先无锁读取关联 ID 以计算锁集合，
随后在正式写入事务内按统一锁序锁定 Novel、目标 Chapter、WritingTask、Artifact 和当前 Command，并
重新校验关联、`awaiting_user`、expectedRevision 和用户归属。

- discard 不读取或校验 sourceBindings；绑定缺失或来源已漂移都不妨碍用户显式丢弃，只要归属、状态和
  expectedRevision 有效。
- approve/revise 再按统一锁序锁定来源子行，比较 sourceBindings 的 exists、updatedAt、内容 hash 或
  revision；任一漂移返回 `409 ARTIFACT_SOURCE_VERSION_CONFLICT`，Artifact 保持 `awaiting_user`。
- 全部一致才应用正式数据或创建返工命令、标记 Artifact，并一次提交。

`editedContent` 只是用户在批准前对候选全文的修改，不能绕过来源校验。来源冲突不自动覆盖、合并或
变基。现有 `ReviewService` 的通用 `ARTIFACT_APPLY_FAILED` 包装必须保留已知 `ApiError` 的稳定冲突
code 和 details，不能抹掉 expected/current 信息。

新增可重新发现的草案列表：

```text
GET /api/v1/review-artifacts
```

`novelId` 必填，支持 chapterId、taskId、status、kind 和稳定 cursor 过滤。现有按 ID 和按 task 查询
接口保留。

结构化大纲、设定、伏笔和参考资料的 Agent 写入在开放对应 CLI 命令前，也必须拥有覆盖所有正式
写目标的 sourceBindings；首个章节闭环不以无类型通用绑定提前开放它们。

## 幂等与目标并发

### 写作命令请求指纹

新显式 start、resume、cancel、Artifact decision 和质量运行均使用：

```text
requestFingerprint = SHA-256(canonical JSON({commandKind, resourceIdentity, body}))
```

`body` 是移除 clientRequestId 后的规范化请求；`resourceIdentity` 必须包含 URL 或查询路径中的权威
资源身份，例如 start 的 novelId/chapterId、resume/cancel 的 taskId、decision 的 artifactId，质量运行
则包含 novelId/chapterId/checkItemId。这样空 body 的 cancel、不同 Artifact 的相同 decision body 和不同
命令种类不会得到相同指纹。

canonical JSON 使用 UTF-8、递归 key 排序、无多余空白、非 ASCII 原字符和 Core 规范化后的 UTC
时间。指纹只由 Core 计算，客户端不能提交自称的 hash 替代服务端规范化。

所有新建 `WritingRunCommand.payloadJson` 固定使用以下 `_inkforgeCommand + job` envelope：

```json
{
  "_inkforgeCommand": {
    "schemaVersion": 1,
    "clientRequestId": "caller-owned-id",
    "commandKind": "start",
    "resourceIdentity": {
      "novelId": "novel-id",
      "chapterId": "chapter-id"
    },
    "normalizedBody": {},
    "requestFingerprint": "64位小写SHA-256"
  },
  "job": {}
}
```

`_inkforgeCommand` 保存幂等身份、规范化请求和服务端指纹；`job` 保存严格校验后的业务 job，dispatcher
只把 `job` 投递给 Agent Service。历史不含该 envelope 的裸 payload 仅走兼容读取路径，不回填、不参与
新幂等 resolver，即使其中出现相同 `clientRequestId` 或旧 `idempotencyKey` 也不能命中新请求。

命中相同 clientRequestId 时：

- fingerprint 相同：返回原受理结果；
- fingerprint 不同：返回 `409 IDEMPOTENCY_KEY_REUSED`；
- 旧历史命令没有新 envelope 时，不把它冒充为新显式命令结果。

所有新增幂等写入口在事务第一步获取由 `userId + clientRequestId` 派生的 PostgreSQL transaction-level
advisory lock，然后查询已有幂等记录；取得下述关系行锁后、判断业务状态前再查询一次。相同请求返回
首个已保存响应，不同指纹返回 409。不能只依赖事务外预查或最后的唯一约束把并发重复变成随机状态
冲突；start 也必须在 Chapter 锁内重查幂等记录后再判断 `WRITING_TARGET_BUSY`。

Artifact decision 的首次 accepted 公共响应必须在 command result 中独立保留。后续终态 callback 追加结果、
或服务端取消把原 command 标为失败时，都不能覆盖这份响应；同一 clientRequestId 重放仍返回首次 202 的
稳定公共字段，同时 outcome projector 继续读取原有顶层 decision/cancel 事实。

该查询是跨命令族的统一 resolver：同时检查带新幂等 envelope 的 WritingRunCommand 和 WorkflowRun
input。不能让同一 clientRequestId 因为落在不同表、不同 task 或不同 commandKind 而绕过冲突检查。
现有不带 envelope 的历史 WritingRunCommand 和 WorkflowRun 都不参与新请求命中。

网络超时、连接中断或响应丢失后，调用方必须保留同一 ID 和完全相同的请求。CLI 不自动生成一个
新 ID 重试写操作。

### 目标互斥

首个章节闭环对可能产生正式候选的 Operation 使用章节级 conflict key：

```text
chapter:<chapterId>
```

Core 在创建任务事务中先锁目标 Chapter，再查询该章节尚未终结的 mutating WritingTask。running 和
waiting_user 都占用目标；存在时返回 `409 WRITING_TARGET_BUSY`，details 返回占用 taskId。用户只能
等待，或按任务 outcome 处理：queued/running 可显式 cancel；waiting_user 只能 approve、revise 或
discard，不能 cancel。任何状态都不能创建第二个会覆盖同一章节来源的任务。

只读 `review_chapter` 不占用 mutating conflict key。后续大纲和资料写入分别使用 Core 可在现有行锁
下实现的 outline/novel 粗粒度 key；没有可靠互斥前不开放相应 CLI 写命令。

### 统一事务锁序

start、resume、cancel、Artifact decision/apply 和后续正式资料写入统一遵循：

```text
幂等 advisory lock
-> Novel
-> Chapter（按 id 排序）
-> WritingTask
-> ReviewArtifact
-> WritingRunCommand
-> 其他来源子行（按 resourceType + resourceId 排序）
```

调用方可先无锁读取 ID 以确定锁集合，但进入事务锁区后必须重新校验归属、关联关系、revision、状态和
sourceBindings。任何路径都不得先锁 Artifact/Task 再回头锁 Chapter/Novel；absence sentinel 也占用其
在该顺序中的父行位置。首个章节闭环只有一个目标章节，但仍按该规则实现，避免 approve-vs-cancel、
start-vs-decision 和未来多来源写入形成反序死锁。

### 人工写入

- `long.chapter.save` 继续调用现有章节 PATCH，必须携带 `expectedUpdatedAt`；相同标题和正文的重复
  请求由 Core 视为幂等，过期且内容不同返回 `CHAPTER_VERSION_CONFLICT`。
- `long.chapter.status` 必须携带章节 `expectedUpdatedAt`，继续服从 drafting -> review -> completed 和
  质量门禁。
- `long.chapter.progress.save` 在开放前给 `ChapterProgressRequest` 增加进展记录自己的
  `expectedUpdatedAt`；首次创建使用明确的 null/不存在前置条件，不能继续最后写入覆盖。
- 质量运行在开放 `long.quality.run` 前增加 `clientRequestId`。Core 先取得全局
  `userId + clientRequestId` advisory lock，再跨检查项查询现有 WorkflowRun input；随后按统一顺序
  锁定章节和检查项，把 ID、包含 checkItemId 的规范化请求和 fingerprint 保存到现有 WorkflowRun
  input。相同 fingerprint 返回原运行，不同 fingerprint 返回 `IDEMPOTENCY_KEY_REUSED`；不能只在单个
  检查项锁内查询，也不新增表。
- 质量 skip/reset 在开放 CLI 命令前增加检查项 `expectedUpdatedAt`。

长篇 novel create 和 chapter create 当前没有可持久证明的通用幂等标识。在禁止新增通用 mutation
ledger 的约束下，首个 CLI 版本不暴露它们；用户继续通过 Web 创建，再由 CLI 接管。

## CLI 架构

目标目录：

```text
tools/inkforge-cli/src/inkforge_cli/
├── cli.py
├── registry.py
├── runtime.py
├── api.py
├── config.py
├── credentials.py
├── io.py
└── commands/
    ├── auth.py
    ├── short/
    │   ├── documents.py
    │   ├── versions.py
    │   ├── agents.py
    │   └── snapshots.py
    └── long/
        ├── read.py
        ├── chapters.py
        ├── tasks.py
        ├── artifacts.py
        ├── quality.py
        └── knowledge.py
```

`cli.py` 只负责启动、读取输入、查找 CommandSpec、构造公共 runtime、统一输出和顶层异常处理。
`registry.py` 是 CLI 能力的唯一命令注册表。每个 CommandSpec 至少声明：

```text
name
handler
inputMode           argv_tty | json
outputMode          json | jsonl
fileOutput          none | data_json | primary_text(field, mediaType)
mutation            true | false
requiresIdentity
requiresClientRequestId
```

`auth.login` 使用 `inputMode=argv_tty`，保留命令行参数和真实 TTY 隐藏密码读取；其余命令使用
`inputMode=json`。这使启动层不再以命令名硬编码交互特例，同时保持已有登录行为。

生产 Skill 的允许命令是授权策略，不等于 CLI 能力注册表。wrapper 从一份明确 policy 文件读取允许
命令；Skill 参考文档由该 policy 生成或测试核对，不再在 PowerShell 和多份文档里复制数组。未来
新增危险命令不会因为拥有 `long.*` 前缀而自动获得生产授权。

`io.py` 只保留完整 UTF-8 读写、原子替换和 hash 等无业务语义的通用设施。现有 `files.py` 中的
manifest、dirty gate、export 和 snapshot clean 逻辑迁入 `commands/short/snapshots.py`；`long` 模块
不得导入该模块。`short` 模块保留现有 manifest、dirty gate、版本 Diff 和 confirmationHash 语义。
公共重构不得改变现有命令名、JSON 形状或退出码。

## 长篇命令面

### 查询命令

```text
long.novel.list
long.novel.get
long.chapter.list
long.chapter.get
long.session.list
long.session.get
long.planning.get
long.lore.get
long.resources.get
long.outline-node.list
long.foreshadowing.list
long.task.list
long.task.get
long.artifact.list
long.artifact.get
long.quality.get
```

查询命令直接映射共享公共接口。`long.novel.list` 固定过滤 `long_serial`。完整正文、Artifact payload、
Diff 和报告不得静默截断；默认可以完整内联返回，调用方显式提供 `outputFile` 时改为原子写入文件并
在 stdout 返回文件描述符和内容 hash。

### 章节闭环控制命令

```text
long.chapter.save
long.chapter.status
long.chapter.progress.save
long.agent.start
long.task.resume
long.task.watch
long.task.cancel
long.artifact.approve
long.artifact.revise
long.artifact.discard
long.quality.run
long.quality.skip
long.quality.reset
```

命令示例：

```json
{
  "chapterId": "chapter-id",
  "title": "第十二章 风暴前夜",
  "contentFile": "F:\\writing\\chapter-12.txt",
  "expectedUpdatedAt": "2026-08-05T10:00:00Z"
}
```

`long.chapter.save` 的 `content` 与 `contentFile` 二选一。文件必须按完整 UTF-8 读取，不改变换行、
Unicode 规范化或尾部内容；读取后只发送本次请求，不创建本地绑定。

```json
{
  "clientRequestId": "artifact-approve-20260805-0001",
  "artifactId": "artifact-id",
  "expectedRevision": 2,
  "editedContentFile": "F:\\writing\\approved-chapter-12.txt"
}
```

`editedContent` 与 `editedContentFile` 二选一。approve 不提供内容时使用 Artifact 当前完整 payload。
revise 必须提供非空 `userMessage`；discard 不接受编辑内容。

`long.task.resume` 只向 Core 提交稳定 checkpoint 所需的普通继续输入，必须带稳定
`clientRequestId`；它不接受 artifactId 或 approve/revise/discard 决定。

`long.task.watch` 是 `mutation=false`、`outputMode=jsonl` 的只读观察命令，在 A 阶段随查询命令注册并
开放；它不属于 B 阶段写命令，也不获得取消任务的隐含权限。

### 已开放的大纲正文命令

```text
long.outline.save
```

该命令按 `2026-08-07-long-serial-outline-cli-write.md` 使用现有公共 Core CAS 契约开放。

### 后续结构化资料命令

```text
long.outline-node.create
long.outline-node.update
long.outline-node.delete
long.foreshadowing.create
long.foreshadowing.update
long.foreshadowing.delete
long.lore.<resource>.create
long.lore.<resource>.update
long.lore.<resource>.delete
long.reference.create
long.reference.update
long.reference.delete
long.reference.reindex
long.style.apply
long.style.clear
```

这些名称预留在目标命令面中，但只有对应公共接口具备请求幂等、版本前置条件、原子事务和明确删除
影响后才能注册为可写命令。CLI 不通过批量调用现有非原子接口伪造一个“完整保存”。

## 输入输出与文件规则

- `auth.login` 继续是唯一 `argv_tty` 交互命令，密码只从真实 TTY 隐藏读取。
- 其他普通命令从 stdin 读取一个 UTF-8 JSON 对象，stdout 返回一个 JSON 对象。
- `long.task.watch` 输出 JSONL；诊断只写 stderr。
- `profile` 是 CLI 本地字段，不发送给 Core。
- 所有 ID 进入 URL 前编码；CLI 继续拒绝非 `/api/v1/**` 和任何 `/internal/**` 路径。
- 大文本不设置隐式阈值截断。使用文件时必须原子写入，并按下述命名空间契约返回绝对路径、字节数和
  SHA-256。
- CLI 不缓存 GET 结果，不以本地 mtime、hash 或文件是否存在决定服务端写权限。
- 调用方提供 `clientRequestId`；CLI 不在发送写请求时临时生成不可恢复的新 ID。

以下 `outputFile` 规则只适用于新增 `long.*` 命令。现有 `short.*` 继续返回
`path/contentHash/byteLength/charCount` 形状，由兼容适配层调用新的公共 I/O 设施，不借重构改名。
长篇使用一套确定规则：

- 若响应 `data` 有一个由 CommandSpec 明确声明的主要顶层文本字段，例如章节 `content`，文件写入该
  字段的原始 UTF-8 文本；stdout 保留其他元数据，并把该字段替换为同名 `<field>File` 描述符。
- 其余响应把未包装的完整 `data` 以 `ensure_ascii=false`、两空格缩进和一个尾部换行写为格式化
  UTF-8 JSON；stdout 返回 `resultFile` 描述符。Artifact 的 payload 和 diff 可能同时存在，因此固定
  写入一个完整 Artifact JSON 文件，不拆成多个文件。
- 文件描述符固定为
  `{"path":"绝对路径","bytes":123,"sha256":"64位小写SHA-256","mediaType":"text/plain; charset=utf-8"}`；
  JSON 文件使用
  `application/json; charset=utf-8`。原子写入完成后才输出描述符。
- 不按大小自动切换输出方式，也不对字段做省略、摘要或截断。

## Watch、退出与恢复

### 生命周期

```text
V1: queued -> running -> waiting_user -> running -> succeeded
                     \-> failed | cancelled | inconsistent
V2: pending -> running -> waiting_user -> running -> completed
                    \-> failed | cancelled
```

`long.task.watch`：

1. 建连前先 GET 持久任务状态，并输出 `snapshot` 帧。响应显式携带 `engineVersion` 时只能按该值分派；
   只有字段完全缺失的历史响应兼容为 V1。显式 `null`、错误类型、未知版本或观察期间版本变化都按契约错误
   失败，不能根据 `outcome`、`status` 或其他字段是否存在反猜引擎。
2. V1 只使用 `outcome.state`：`queued/running` 继续观察，`waiting_user` 从
   `outcome.result.id` 返回 Artifact，`succeeded` 成功，`failed/cancelled/inconsistent` 失败。
3. V2 只使用顶层 `status`、`activeSteps`、`artifact` 和 `error`，不要求也不读取 `outcome`。
   `activeSteps` 必须存在且是 JSON 数组；`artifact` 与 `error` 出现时必须是 `null` 或 JSON 对象，显式
   标量/数组类型都按 `CORE_RESPONSE_CONTRACT_ERROR` 失败关闭，不能把畸形状态继续观察为正常任务：
   `pending/running` 继续观察，`waiting_user` 从 `artifact.artifactId` 返回 Artifact，`completed` 成功，
   `failed/cancelled` 失败。`completed` 只证明 Run 已成功，不得从状态或 SSE 虚构问答正文。
4. 运行中连接现有 SSE，保存本进程内最新 `Last-Event-ID`。V1 文本游标与 V2 非负整数游标都必须支持；
   JSONL `event` 帧保留服务端原始 ID 类型，重连请求统一发送其字符串形式。V2 `run_snapshot` 事件完整透传，
   其 snapshot 仍只是观察投影，不替代下一次 PostgreSQL 状态回读。
5. 断线后立即 GET 权威状态；仍运行时按有上限退避携带 cursor 重连。
6. Core 可达但暂时没有过程事件不算失败。
7. Core 连续不可达默认超过 300 秒后退出 5，并在最后一行返回 taskId、最后 cursor 和当前已知状态；
   任务继续运行。
8. waiting_user 输出最终 `waiting_user` 帧和 artifactId，退出 0。
9. V1 succeeded 或 V2 completed 输出最终 `terminal` 帧，退出 0。若该 Run 是
   `answer_question`，随后必须以原 `writingSessionId` 调用 `long.session.get` 回读权威 Agent 消息。
10. V1 failed/cancelled/inconsistent 或 V2 failed/cancelled 输出最终 `terminal` 帧，退出 5。
11. `Ctrl+C` 输出 `WATCH_INTERRUPTED`，说明只停止观察，退出 130；真正取消必须执行
   `long.task.cancel`。

重新启动进程后的标准恢复只有：

```text
long.task.list -> long.task.get -> long.task.watch
```

不要求找回本地 cursor。没有 cursor 时允许重复收到展示事件，但最终状态仍只由 PostgreSQL 权威投影
（V1 `outcome` 或 V2 `status`）决定，调用方不得重复执行正式副作用。

### 退出码

下表定义新 `long.*` 命令和 `long.task.watch` 的退出行为。现有 `short.*` 保持当前映射；特别是普通
HTTP 传输异常在 `long.*` 中映射为 5，但本规格不顺带改变 `short.*` 的既有退出码。若未来统一映射，
必须另行设计并提供兼容性测试。

| 退出码 | 含义 |
| --- | --- |
| 0 | 请求成功、任务成功或进入 waiting_user |
| 1 | CLI 未预期错误 |
| 2 | 输入、命令或本地契约错误 |
| 3 | 登录失效、凭据缺失或身份不匹配 |
| 4 | 版本、幂等、Artifact 来源或目标占用冲突 |
| 5 | 远端服务失败、任务失败、取消、状态不一致或重连耗尽 |
| 6 | 本地输入输出文件错误 |
| 130 | 用户中断 watcher，服务端任务未取消 |

新 `long.task.watch` 不继承当前 watcher 在失败终态仍返回 0 的行为。中短篇 watcher 保持既有行为；
是否同步采用新行为不在本规格范围内。

## 错误与恢复规则

CLI 保留 Core 的 code、message、details 和 requestId，禁止把服务端错误替换成无细节的通用文字。

- `CHAPTER_VERSION_CONFLICT`：重新读取章节；不自动覆盖或合并。
- `ARTIFACT_REVISION_CONFLICT`：重新读取 Artifact；旧确认不能继续使用。
- `ARTIFACT_SOURCE_VERSION_CONFLICT`：保留草案，读取正式来源并启动新任务；不自动变基。
- `IDEMPOTENCY_KEY_REUSED`：同一 ID 已绑定不同请求，不能换 payload 重放。
- `WRITING_TARGET_BUSY`：details 返回占用 taskId；queued/running 可等待或显式取消，waiting_user 只能
  approve、revise 或 discard。
- `ARTIFACT_DECISION_REQUIRED`：任务正在等待草案决定；选择 approve、revise 或 discard，不能用
  cancel 隐式丢弃。
- `LONG_SCOPE_NOT_SUPPORTED`：当前 scope/operation 尚未实现；不能缩小范围执行。
- 401、凭据缺失、预期用户名不匹配或无法完成 `auth.whoami` 身份核验：退出 3，停止全部写操作，
  重新登录并核验身份。
- 403：退出 5，报告权限或资源归属问题；不能默认通过重新登录掩盖授权失败。
- 422：保留字段详情和 requestId，不猜测改写请求。
- `long.*` 的 DNS、连接、超时和其他 HTTP 传输失败：退出 5；写请求仍按下述结果不确定规则恢复。
- 写请求网络结果不确定：读取权威状态并使用同一 clientRequestId 与完全相同的请求重放。
- 人工章节保存网络结果不确定：重新 GET；若服务端标题和正文已经相同则视为成功，否则用原
  `expectedUpdatedAt` 重放并接受 Core 的 CAS 结果。

CLI 不从错误文本、SSE 事件名、Agent 聊天正文或本地文件猜测任务是否成功。

## 生产长篇操作 Skill

章节闭环稳定后新增独立个人 Skill `inkforge-production-long-novel-operator`。它调用同一个仓库 CLI，
并以已批准的生产 HTTPS 规格和实施计划完成为前置，固定：

```text
origin  = https://inkforge.cn
profile = production
```

新 Skill 不保留公网 IP HTTP 回退、`acceptedInsecureHttp`、`-AcceptInsecureHttp` 或
`INKFORGE_CLI_ALLOW_INSECURE_HTTP_ORIGIN`，也不登录服务器、不使用 SSH、不直连数据库或内部接口。

新 Skill 复用现有 `production` CLI profile、Windows Credential Manager 凭据和已配置的预期用户名，
不创建第二份登录凭据或长篇业务配置。

长篇 Skill 与现有中短篇 Skill 分离，因为两者的正式写入、文件、Artifact 和授权规则不同。长篇
policy 必须同时允许共享 `auth.login`、`auth.whoami`、`auth.logout` 和当前已发布的具体 `long.*`
命令；不能使用 `long.*` 通配授权。新 Skill：

- 每轮接管先执行 `auth.whoami`；每个业务命令前由 wrapper 再做身份预检；
- 使用独立 policy 文件只允许已经发布的长篇命令；
- 不创建 production snapshot 目录；
- Agent start 只启动一次显式 Operation；
- 不自动 approve、revise、discard、取消、运行质量检查或完成章节；
- 网络结果不确定时保留原 clientRequestId、taskId 和 artifactId 对账。

为落实“授权清单只有一个来源”，实施时同时把现有 `inkforge-production-short-story-operator` wrapper
的硬编码命令白名单迁入独立中短篇 policy 文件。该迁移只改变授权清单的存放与读取方式，不改变
任何中短篇业务命令、身份预检、manifest、dirty gate 或版本语义。

## 实施分段与开放门槛

### A. Core 控制面与 CLI 只读能力并行

Core：

- 显式长篇请求、typed job payload 和 Operation 直通；
- 请求 fingerprint 与章节目标互斥；
- 任务列表、状态扩展和 Artifact 列表；
- 服务端取消；
- 章节/Beat Plan sourceBindings 和 expectedRevision；
- 质量运行幂等和进展/质量状态 CAS。

Service Contracts / Agent Service：

- `LongSerialRunPayload`、`PublicOperationDefinition` 和完整定义一致性校验；
- Redis cancel tombstone 与迟到 enqueue 拒绝；
- 模型/节点/工具前取消检查，以及写型内部工具的 jobId 签名绑定。

CLI：

- 行为保持的 CommandSpec/模块重构；
- 全部长篇查询命令，以及 `mutation=false` 的只读 `long.task.watch`，本阶段即注册开放；
- 新 watcher 和退出码测试；
- 不注册任何长篇写命令。

### B. 章节生产闭环

只有 A 的相关 Core 验收全部通过后，开放：

```text
long.chapter.save
long.chapter.status
long.chapter.progress.save
long.agent.start
long.task.resume
long.task.cancel
long.artifact.approve
long.artifact.revise
long.artifact.discard
long.quality.run
long.quality.skip
long.quality.reset
```

本阶段端到端跑通单章：规划、审核、正文、冲突、批准、质量和完成。

### C. 结构化资料能力

按 planning、outline node、foreshadowing、lore、reference、style 的垂直切片逐类补齐原子写入、
幂等、CAS、删除影响和 sourceBindings，再注册对应 CLI 命令。不得为了凑齐命令表先暴露不安全接口。

`2026-08-06-long-serial-creative-material-cli-writes.md` 规格定义的 32 条长篇创作资料写命令已经实现。
`2026-08-07-long-serial-outline-cli-write.md` 另行开放受非空 `expectedUpdatedAt` 保护的大纲正文保存；大纲节点、
伏笔和用户级文风库的写命令仍未开放。

### D. 生产操作

- 创建并验证生产长篇 Skill 和 policy；
- 先做 `whoami`、列表和状态只读冒烟；
- 再在专用测试长篇章节完成一次写入闭环；
- 生产 push/deploy 成功不等于功能已验证，必须读取部署终态并执行冒烟。

## 影响范围

预计触及：

- `apps/core-api/src/inkforge_core/writing/**`
- `apps/core-api/src/inkforge_core/reviews/**`
- `apps/core-api/src/inkforge_core/chapters/**`
- `apps/core-api/src/inkforge_core/quality/**`
- `apps/core-api/src/inkforge_core/**/internal_router.py`（写型工具 jobId 门禁）
- `apps/agent-service/src/inkforge_agents/graph/**`
- `apps/agent-service/src/inkforge_agents/jobs/**`
- `apps/agent-service/src/inkforge_agents/operations/**`
- `apps/agent-service/src/inkforge_agents/queue/**`
- `apps/agent-service/src/inkforge_agents/tools/**`
- `packages/service-contracts/**`
- `packages/api-client/src/generated/**`
- `tools/inkforge-cli/**`
- 个人生产长篇 Skill 目录
- 现有个人生产中短篇 Skill 的 policy/wrapper 授权清单迁移
- 实现完成后同步更新 `apps/agent-service/AGENTS.md`、需求 03 和需求 04

明确不触及：

- PostgreSQL schema、迁移 SQL 和 `schema-contract.json`；
- Web UI 视觉结构和 `DESIGN.md`；
- 全局篇幅模式修改入口；
- 中短篇版本业务语义。

## 测试设计

### Core API

- 显式长篇请求的 Pydantic 判别、OpenAPI 和 operation/target/scope 交叉矩阵。
- 登录、小说、章节、会话、任务和 Artifact 归属。
- 相同 clientRequestId/相同 fingerprint 返回原响应；不同 fingerprint 返回 409。
- 指纹包含 commandKind 与路径资源身份；跨 task、Artifact 或质量检查项复用同一 clientRequestId 能
  确定性返回原结果或 `IDEMPOTENCY_KEY_REUSED`，并发相同请求不会先撞业务状态。
- 并发启动同一章节只有一个 mutating task；waiting_user 继续占用目标。
- 任务列表包含无 session 任务，过滤、cursor 和排序稳定。
- queued/running/terminal 取消、waiting_user 拒绝隐式丢弃、重复取消、cancel-vs-complete 和迟到
  callback。
- cancel command 的 effective/no-op 数据库事实和 outcome 优先投影；取消不创建 Outbox，SSE 仍能靠
  PostgreSQL `run_outcome` 控制帧收敛终态。
- outcome 的 queued、running、waiting_user、succeeded、failed、cancelled、inconsistent。
- sourceBindings 由 Core 附加、revision 继承且不可被 Agent 覆盖。
- `_inkforgeControl.sourceCommandId` 由 Core 注入、公共 payload 不泄漏控制字段、返工 revision 保留同一
  source command；缺失或跨 task 引用 fail closed。
- 章节、总纲或 Beat Plan 漂移时 apply 返回稳定 409，Artifact 保持 awaiting_user。
- `exists=false` 绑定使用父级 sentinel 阻止并发创建；`legacy_missing` Artifact 可读、可 discard，但
  approve/revise 返回 `ARTIFACT_SOURCE_BINDINGS_MISSING`；`not_yet_supported` 保持现有 Web 行为。
- editedContent 不能绕过来源检查。
- resume 请求不能携带 Artifact decision。
- 章节进展 CAS、质量运行幂等、质量状态 CAS。
- start/cancel/decision/apply 并发压力测试遵循统一锁序且不死锁。
- schema 指纹只读校验，确认没有 DDL 或模型元数据变化。

### Service Contracts 与 Agent Service

- `LongSerialRunPayload` 严格拒绝额外字段、无效 Operation 和不完整 target/scope。
- 共享 `PublicOperationDefinition` 与 Agent 完整定义的公开字段逐项一致。
- 显式 Operation 不调用 classifier，主责 Agent 和 reviewers 由定义推导。
- target、scope、sourceBindings 和请求身份完整进入稳定快照。
- Agent 不能扩大 scope、替换 sourceBindings 或提交错误 kind 的 Artifact。
- queued/running cancel 停止后续图步骤；取消早于 enqueue 时 tombstone 阻止迟到入队，且按终态保留期
  清理。
- Agent 在模型返回、节点切换和工具调用前观察取消；旧 job 的 callback 或写型工具即使迟到，也因
  `taskId + jobId` 当前命令校验而不能产生正式副作用。
- Agent Service 继续不导入数据库驱动，不读取 `DATABASE_URL`。

### CLI

- 现有 auth 和 `short.*` 回归测试全部通过。
- registry 中命令唯一，生产 policy 只能引用已注册命令，文档清单与 policy 一致。
- 长篇 policy 显式包含共享 auth 命令和已开放的具体 `long.*` 命令；中短篇 policy 迁移后授权集合与
  现有 wrapper 完全一致，且两个 policy 都不使用前缀通配。
- 普通命令严格一进一出 JSON，watch 为 JSONL。
- 长篇命令不调用 manifest、snapshot clean 或本地版本逻辑。
- 架构测试禁止 `commands/long/**` 导入 `commands.short.snapshots`，公共 `io.py` 不含 manifest、
  dirty gate 或 snapshot clean 业务符号。
- `content`/`contentFile`、`editedContent`/`editedContentFile` 二选一校验。
- 长篇 CLI 对 `legacy_missing` 或 `not_yet_supported` Artifact 拒绝 approve/revise，但允许显式
  discard。
- 80,000 字以上正文、Artifact、Diff、中文和 Unicode 尾部不截断。
- SSE 首次快照、Last-Event-ID 重连、waiting_user、各终态和 300 秒不可达预算。
- watcher 失败不返回 0；Ctrl+C 返回 130 且不调用 cancel。
- 401、409、422、requestId、details 和网络不确定结果保持稳定输出。
- profile、Cookie 和密码不进入 stdout 或日志；生产 wrapper 不注入任何不安全 HTTP 放行值。

### 生成客户端与静态检查

公共接口变化后运行：

```text
npm run api:generate
npm run api:check
npm run typecheck
npm run lint
uv run ruff check .
uv run mypy apps/core-api/src apps/agent-service/src packages/service-contracts/src packages/service-auth/src
```

运行 Core、Agent、service-contracts、service-auth、CLI 的相关 pytest。数据库只运行只读指纹校验。

### 端到端验收

使用专用长篇测试作品跑通：

```text
auth.whoami
-> long.novel.list
-> long.chapter.list/get
-> long.agent.start(plan_chapter)
-> 中断并恢复 long.task.watch
-> long.artifact.revise 或 approve
-> long.agent.start(write_chapter)
-> 制造 Web/CLI 来源冲突并确认拒绝覆盖
-> 重新生成并 approve 正文
-> 章节进入 review
-> long.agent.start(review_chapter)
-> long.task.watch/get 返回完整 reviewReport，且不创建可应用 Artifact
-> long.quality.run
-> long.quality.get 到终态
-> 章节进入 completed
-> 启动另一个任务并验证 long.task.cancel
```

验收过程中不读取数据库、不登录 Agent Service、不从 SSE 片段猜测正文，并核对完整正文尾部未丢失。

## 验收标准

- 长篇 CLI 不创建或依赖任何本地正式状态、manifest 或 dirty gate。
- Web 与 CLI 使用同一 Core 公共契约、归属、CAS、ReviewArtifact 和质量门禁。
- 显式长篇请求不会被 Agent 自然语言分类器改写。
- 丢失 taskId 后可通过任务列表重新发现；进程退出后可只靠 Core 恢复。
- watcher 只停止观察，cancel 才停止服务端任务。
- cancel 即使早于 Agent enqueue 也不会丢失；取消事务提交后，旧 job 无法再通过 Core 写型工具制造
  Artifact 或正式副作用。
- 网络结果不确定时，稳定 clientRequestId 不会创建重复任务、决定或质量运行。
- 同一章节不存在两个可产生正式候选的活动任务。
- Web 修改来源后，旧 Artifact 无法批准覆盖正式数据。
- Agent 产物只有通过 ReviewArtifact decision 才能写入正式内容。
- 人工章节保存使用 expectedUpdatedAt，不自动覆盖或合并。
- 长文本、Diff、报告、错误详情和事件数据不静默截断。
- 中短篇现有 CLI 和版本语义不发生回归。
- PostgreSQL schema 指纹保持不变。

## 后续演进

本规格完成后再单独设计：

- 章节创建、删除、重排和批量管理的通用 mutation idempotency ledger；
- `chapter_range`、`outline_node` 和 `novel` scope 的真正多章节/全书编排；
- 受控长正文分段续写与上下文压缩；
- first-class 数据库 cancelled phase；
- 可查询和索引的规范化 source binding 表；
- 全书质量评估和卷级恢复。

这些后续能力不能倒逼当前 CLI 维护本地权威数据。
