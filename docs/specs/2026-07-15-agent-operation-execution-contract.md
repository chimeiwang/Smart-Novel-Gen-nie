# Agent Operation 执行契约与提示词收敛规格

## 状态

- 日期：2026-07-15
- 状态：已实现
- 范围：Agent 执行模式、模型消息拼装、Operation 工具契约、ReviewArtifact 返工与恢复、产物校验、一致性终检、模型截断识别

## 背景

改造前五个 Agent 的静态提示词已经相对简短，主要问题不在角色文案长度，而在运行时语义没有形成单一契约：

- `CoreGraphAgentExecutor` 通过是否存在 `activeArtifactId` 推断当前 Agent 是否为 reviewer，导致主责 Agent 返工时也可能收到复审指令和 `control_only` 工具模式；
- 复审合并结果已经写入 `pendingRevision.requiredChanges`，但返工调用没有把它传给主责 Agent；
- 当前用户请求会同时进入聚合上下文、会话历史、Operation 上下文和最后一条 user 消息，部分作品数据还会被包装为 system 消息；
- 工具只按 Agent 能力过滤，没有按 CreativeOperation 和执行阶段继续收敛；
- `OperationDefinition.textArtifactKind` 已声明但未参与服务端校验，模型仍可提交错误事件、错误 kind 或变化的 artifactKey；
- reviewer 静态提示词要求调用运行时未暴露的 `get_active_review_artifact`，并鼓励进入当前明确不支持的跨服务 patch 路径；
- Agent Service 重启后，Core 已提供 `planning.activeArtifact`，但本地 `CoreArtifactPort` 不会据此恢复权威草案；
- 一致性终检由“编辑”执行，与需求定义的“校验”不一致；
- Provider 没有把 `finish_reason` 传入 Runtime，达到输出上限的截断响应可能被当成成功。

这些问题不能继续通过增加提示词提醒解决。Operation、执行模式、工具、产物和消息角色必须由服务端确定性约束，静态提示词只保留长期稳定的专业角色信息。

## 目标

- 明确区分 `primary`、`reviewer`、`reviser` 和 `quality` 四种执行模式，不再从草案是否存在推断当前角色。
- 返工 Agent 必须获得 Core 权威草案、合并后的修改要求、当前 revision、artifact kind 和稳定 artifactKey。
- 每次模型调用只包含一份当前用户请求；作品数据保持数据语义，不提升为 system 指令。
- 每个 Operation 声明允许的工具、终止控制工具、允许的产物事件和产物类型，Runtime 与图层共同强制执行。
- ReviewArtifact 的 kind、artifactKey 和 revision 由服务端保存并校验，不能由模型在返工时改变身份。
- Agent Service 恢复任务时使用 Core 已返回的 `planning.activeArtifact` 水合本地权威草案记录；缺失或不一致时显式失败。
- 首版所有 reviewer 修改请求直接归一为完整 rewrite，不进入已知不可用的跨服务 patch 路径。
- 一致性终检由“校验”Agent 的专用质量模式执行，并返回固定结构的报告。
- 模型因长度限制截断时不能提交不完整草案、评审或回复。
- 不修改 PostgreSQL schema，不改变 ReviewArtifact 必须经用户确认后才能正式应用的边界。

## 非目标

- 不处理 checkpoint 已写 PostgreSQL 但对应 SSE 发布失败时的补发风险。
- 不修改前端 UI、SSE 事件展示或写作聊天渲染。
- 不升级 CreativeOperation 语义分类器或关键词路由。
- 不优化文风画像的五次模型调用。
- 不实现真正的跨服务局部 patch。
- 不修改 PostgreSQL schema、公共浏览器 API 或正式草案应用事务。
- 不改变 Agent Service 禁止直连数据库的架构边界。

## 设计

### 1. 显式执行模式

新增运行时类型：

```text
AgentExecutionMode = primary | reviewer | reviser | quality
```

执行模式由 LangGraph 节点显式传给 Agent executor：

- `executeOperation` 使用 `primary`；
- `reviewArtifactWorker` 使用 `reviewer`；
- `reviseArtifact` 进入独立的返工执行节点并使用 `reviser`，不能重新落回无法区分语义的普通执行入口；
- `QualityJobHandler` 使用 `quality`。

`AgentRunRequest` 增加 `executionMode` 和 `operationKind`。对于不属于 CreativeOperation 图的质量任务，`operationKind` 为空并由 `quality` 模式选择独立契约。Adapter 不得根据 `activeArtifactId` 自动切换模式。

模式决定动态指令和工具范围：

| 模式 | 权威输入 | 可用控制工具 | 结束条件 |
| --- | --- | --- | --- |
| primary | 当前用户请求、Operation 上下文、必要作品索引 | 当前 Operation 声明的控制工具 | 普通回复或目标产物事件 |
| reviewer | Core 权威草案快照 | 仅 `submit_evaluation` | 成功提交一次 evaluation |
| reviser | 原草案、`requiredChanges`、当前 revision 和固定产物身份 | 原 Operation 的返工工具 | 成功提交同类新 revision |
| quality | Core 保存的章节正文快照、固定检查维度 | 仅一致性质量报告工具 | 成功提交一次报告 |

### 2. Operation 执行契约

`OperationDefinition` 扩展为完整执行契约，新增以下字段：

```text
allowedToolNames
terminalControlTools
artifactEventTypes
artifactKeyPolicy
```

现有 `contextStrategy`、`artifactPolicy` 和 `textArtifactKind` 成为实际运行字段，不再只是描述信息。

工具暴露采用交集：

```text
Agent 能力白名单 ∩ Operation 工具白名单 ∩ 执行模式工具白名单
```

任何一层未允许的工具都不能进入 Provider schema。Runtime 继续拒绝模型调用本轮未暴露的工具，ToolRegistry 继续校验 Agent 权限。Operation 工具白名单由服务端定义，不能由模型或用户消息覆盖。

最低约束如下：

- `answer_question`：只允许必要读取工具，不暴露草案或评审控制工具；
- `create_lore`、`revise_lore`：允许设定读取以及 `propose_updates`/更新构建器终止链；
- `create_outline`、`revise_outline`、`manage_foreshadowing`：允许大纲与必要设定读取以及结构化更新工具；
- `plan_chapter`：只允许必要读取和 `submit_beat_plan`，不能用通用文本草案替代；
- `write_chapter`、`rewrite_scene`：允许必要读取和 `begin_artifact_output`；
- `review_chapter`：只允许读取，不生成 ReviewArtifact；
- reviewer：无读取工具，只允许 `submit_evaluation`；
- quality：只允许一致性报告控制工具。

更新构建器按 Operation 继续收敛：`create_lore/revise_lore` 只使用通用构建器，不暴露 `append_outline_tree`；`create_outline/revise_outline/manage_foreshadowing` 才允许追加结构化大纲树。

`terminalControlTools` 从 Agent 级默认值收敛为当前调用的 Operation/模式值。`begin_artifact_output`、`submit_beat_plan`、`propose_updates`、`finish_update_builder`、`submit_evaluation` 和质量报告工具在对应契约下成功后立即结束本轮，不再额外调用一次模型。

### 3. 模型消息拼装

新增单一消息构造入口，所有 Agent 调用按以下顺序生成消息：

1. 一个静态 Agent system prompt；
2. 一个服务端生成的 Operation 与执行模式 system brief；
3. 一个明确标记为只读资料的低权限作品上下文消息；
4. 不包含当前请求的历史消息；
5. 一条当前 user 消息。

约束：

- 当前用户请求在最终消息列表中只出现一次；
- `parent_graph` 不再把当前请求追加到 `conversationHistory`；
- Core 已持久化的当前用户消息在构建模型历史时排除，只保留当前轮之前的历史；
- 排除动作只移除 Core 已选定为本轮 `userMessage` 的最后一条 user 记录，不能按文本内容删除所有相同历史消息；
- `build_operation_context()` 不再把 `userMessage` 放入上下文 JSON；
- 小说正文、设定、参考资料和用户内容不能包装成 system 消息；
- system 消息只包含仓库控制的身份、执行目标、输出协议和不可突破边界；
- 上下文内容需要明确标记为资料，资料中的命令性文字不能改变 Operation、工具权限或执行模式。

`contextStrategy` 用于生成最小上下文投影：

- `brief`：任务、小说和当前章节的最小标识与摘要；
- `lore`：人物、物品、地点、势力、术语和设置文档的摘要索引，不注入全部详情；
- `outline`：文本大纲、节点、剧情进度、章节组、outlinePath 和伏笔摘要，不注入全部章节正文；
- `chapter`：当前章节、相邻章摘要、章节目标、已批准 Beat Plan、outlinePath 和 Beat Plan 关联人物摘要；
- `review`：当前章节、章节目标和已批准 Beat Plan。

详细内容继续通过 Core 只读工具按需获取。聚合 `workspace` 不能直接进入稳定快照。

写作处理器为每次队列执行附加一个仅运行时 `runtimeContext` 信封，分别保存当前 Core 聚合上下文和当前 QueueJob 构造的 `RunResource`。Agent executor、工具上下文、草案创建、评审回调和恢复水合统一从该 `RunResource` 取得真实 `runId/jobId`，不得再用 `taskId` 代替 `runId`。`runtimeContext` 在初次运行、命令恢复和当前 job 快照恢复时都重新附加，在整个图调用期间保留且不得被上下文投影节点提前清除；它列入 `RUNTIME_ONLY_FIELDS` 并在稳定快照序列化前移除，`runId/jobId` 不成为可持久化图业务状态。

### 4. Reviewer 与 Reviser 动态指令

Reviewer 的动态指令只表达当前复审任务：

```text
当前处于复审模式。下方草案是 Core 提供的权威快照。
不要重新读取或猜测草案。完成评审后只调用一次 submit_evaluation。
```

Reviser 的动态上下文必须包含：

```text
artifactId
artifactKey
revision
artifactKind
artifactIteration
requiredChanges
原草案 payload
```

Reviser 不暴露 `submit_evaluation`，也不能收到“请直接审阅”的 reviewer 指令。返工完成后必须生成与原 Operation 相同类型的新 revision。

### 5. 草案身份与产物校验

在图层提交 Core 之前执行确定性校验：

- 控制事件类型必须属于当前 Operation 的 `artifactEventTypes`；
- 文本草案 kind 必须等于 `textArtifactKind`；
- Beat Plan 只能由 `submit_beat_plan` 提交；
- 结构化设定、大纲和伏笔更新只能产生 `agent_updates`；
- 模型返回错误事件或 kind 时明确失败，不选择其他“看起来可用”的控制事件兜底；
- 同一轮出现多个互相冲突的终止产物事件时明确失败。

artifactKey 规则：

- 首次提交时，如果构建器已经产生 key，则使用构建器 key；
- 文本草案未提供 key 时由 Agent Service 生成稳定 key；
- Core 返回的 artifactKey、artifactId 和 revision 成为后续复审与返工的权威身份；
- reviewer 的 `submit_evaluation` 以服务端当前 artifactId/revision 为准，模型不再必须搬运 artifactKey；
- reviser 返回的 key 只能与原 key 一致；缺失时由运行时补入，变化时拒绝；
- revision 必须更新同一个 ReviewArtifact，不能创建身份不同的孤立草案。

### 6. 重启后的权威草案水合

Core 内部写作上下文的 `planning.activeArtifact` 已扩展为可重建 Agent Service 完整草案请求的对象：

```text
id
taskId
novelId
chapterId
workflowRunId
artifactKey
kind
status
title
summary
payload
diff
createdByAgent
reviewerAgent
revision
```

`payload/diff` 是数据库 JSON 文本解析后的完整 JSON 值；无效 JSON 必须作为上下文错误失败，不能把原始 JSON 字符串嵌套进草案请求。这些字段全部来自现有 `ReviewArtifact`，运行与回调身份继续使用当前 QueueJob 对应的 `RunResource`，不伪造 `ReviewArtifact` 不存在的 `runId` 字段，不新增数据库字段，也不进入公共浏览器 API。写作处理器在恢复图之前执行：

1. 反序列化稳定快照；
2. 判断本次恢复是否仍需读取草案：`revise` 决定、自动复审或自动返工必须读取；已经由 Core 事务完成的 `approve/discard` 只推进图终态，不要求草案仍存在；
3. 需要草案且快照包含 `activeArtifactId` 时，读取 `planning.activeArtifact`；
4. 校验 artifact ID、taskId、novelId、kind、artifactKey 和 revision；
5. 使用当前 QueueJob 对应的 `RunResource` 水合 `CoreArtifactPort`；
6. 再执行 reviewer、reviser 或用户决定恢复节点。

以下情况必须显式失败：

- 本次仍需复审或返工，快照存在 activeArtifactId，但 Core 没有返回 activeArtifact；
- artifact ID、task、novel 或 revision 与快照/任务不一致；
- payload 不符合对应 artifact kind；
- 当前 Operation 不允许该 artifact kind。

`CoreGraphAgentExecutor` 不得捕获本地记录缺失后静默回退为普通工具模式。等待态仅在等待事件和稳定 checkpoint 成功后释放，完成态与错误态仅在相应 Core 回调成功后释放；释放还必须匹配当前 `RunResource.runId/jobId`。checkpoint 或回调失败时保留记录，下次命令重新从 Core 水合，防止单例缓存长期保存完整正文或被其他 job 抢占/误删。

### 7. Rewrite-only 返工

本轮不实现跨服务 patch。复审结果中的 `patch` 在合并时立即归一为 `rewrite`：

- 不进入 `CoreArtifactPort.apply_patch()`；
- 保留原 `requiredChanges`、reviewer、summary 和补丁意图摘要；
- 不用“patch 未启用”异常文本覆盖具体修改意见；
- 用户可见日志明确记录本次采用完整返工，而不是伪装为局部修改成功。

`applyArtifactPatch` 节点及其仅为当前禁用能力服务的分支从活动图中删除；共享历史快照兼容字段可继续解析，但不能创建新的 patch 执行。

### 8. 一致性终检

`QualityJobHandler` 使用“校验”Agent 和 `quality` 执行模式，不再调用“编辑”。质量模式只暴露一致性报告工具，并使用固定结构：

```text
scores:
  characterConsistency: 0..100
  worldRuleConsistency: 0..100
  timelineConsistency: 0..100
  causalityConsistency: 0..100
  foreshadowingConsistency: 0..100
qualityGate: pass | revise
issues: 结构化冲突列表
report: 非空的完整自然语言终检报告
rewriteBrief: 可选的完整返工要求
```

每个 issue 使用固定结构：

```text
dimension: character | world_rule | timeline | causality | foreshadowing
severity: warning | error
message: 冲突结论
evidence: 证据原文或事实摘要
location: 可选的章节/段落定位
suggestion: 具体修改建议
```

固定分数、issue 和报告模型放入 `packages/service-contracts`，Agent 工具参数和 Core 内部质量回调共同复用，禁止再维护两份可能漂移的 schema。数据库继续保存现有 JSON/文本字段，不新增 schema。五项一致性分数、完整 issues 和 report 随质量回调保存在 `WorkflowRun.output`；`ChapterQualityCheck.scoreOverall` 是五项分数算术平均值经过现有 `_score()` 的 Python `round()` 后保存的整数，旧的 `scoreHook/scoreTension/scorePayoff/scorePacing/scoreEndingHook/scoreReaderPromise` 商业评分列保持空值，不能借用这些列承载一致性维度。`ChapterQualityCheck.result` 保存契约内必填、非空的 `report`，不能依赖可能为空的模型可见正文。报告模型负责校验字段完整性、范围和额外字段，不能接受任意 score key。商业性、追读和爽点评审继续由“编辑”在写作复审或显式章节评审中处理。

### 9. Provider 完成原因

`ModelTurnResult` 增加规范化 `finishReason`，至少支持：

```text
stop | tool_calls | length | content_filter | unknown
```

OpenAI-compatible Provider 从供应商响应元数据读取并归一化完成原因。Runtime 处理规则：

- `stop`：允许普通文本完成；
- `tool_calls`：继续执行工具循环；
- `length`：明确失败，不提交当前轮草案、评审或质量报告；
- `content_filter`：明确失败并记录稳定错误；
- `unknown`：当响应包含合法工具调用时继续，否则明确失败，不能静默视为成功。

Runtime 在接受正文和产生工具副作用前先校验完成原因与工具调用的一致性：`stop` 不能携带工具，`tool_calls` 不能缺少工具，`unknown` 的全部工具必须属于本轮暴露集合并通过参数校验，同一响应不能包含多个冲突终止工具。OpenAI-compatible Provider 同时保留供应商原始完成原因；模型调用日志记录原始值和归一化值，便于区分元数据缺失与供应商新增状态。

本轮只保证截断不会被当成成功，不实现自动续写。后续若需要续写，必须另行设计段落去重、边界标记和计费语义。

### 10. 静态提示词收敛

五个静态提示词只保留：

- Agent 身份与职责；
- 专业判断维度；
- 可见文本表达风格；
- 长期稳定且无法由工具契约表达的边界。

从静态提示词删除：

- reviewer 专用的 `get_active_review_artifact` 和 `submit_evaluation` 流程；
- patch/rewrite 选择；
- “系统会先提供摘要索引”等与实际动态上下文绑定的描述；
- 主责返工时读取当前草案和沿用 artifactKey 的运行协议；
- Runtime、ToolRegistry、Core 权限已经确定性保证的重复规则。

产物标记、更新构建器、Beat Plan、复审和返工协议由当前 Operation/模式动态 brief 注入。无关 Operation 不携带这些规则。

## 数据流

### 初次执行

```text
Core 写作上下文
  -> Agent Service 创建最小初始状态
  -> 父图识别 CreativeOperation
  -> OperationDefinition 选择上下文和工具契约
  -> 消息构造器生成唯一当前 user 消息
  -> AgentRuntime 执行 Operation 允许的工具
  -> 图层校验终止事件、kind 和 artifactKey
  -> Core 创建 ReviewArtifact
```

### 复审与返工

```text
CoreArtifactPort 权威草案
  -> reviewer 模式，仅 submit_evaluation
  -> 合并 requiredChanges
  -> rewrite-only 归一
  -> reviser 模式，注入原草案和修改要求
  -> 校验同一 artifact 身份与 kind
  -> Core 保存新 revision
  -> reviewer 再次复审
```

### 服务重启恢复

```text
Core graphState + planning.activeArtifact
  -> 校验身份与 revision
  -> 水合 CoreArtifactPort
  -> 恢复 reviewer/reviser/用户决定节点
```

## 错误处理

- 执行模式缺失或与图节点不匹配：`AGENT_EXECUTION_MODE_INVALID`。
- Operation 调用未允许工具：沿用 Runtime 未暴露工具错误，并终止当前运行。
- 产物事件或 kind 不匹配：`ARTIFACT_CONTRACT_MISMATCH`。
- 返工 artifactKey 或 revision 不匹配：`ARTIFACT_REVISION_IDENTITY_MISMATCH`。
- 其他 runId/jobId 试图覆盖或释放草案缓存：`ARTIFACT_RUNTIME_IDENTITY_MISMATCH`。
- 恢复时权威草案缺失：`ACTIVE_ARTIFACT_CONTEXT_MISSING`。
- 权威草案 payload/diff 不是合法 JSON 或 payload kind 不一致：`ARTIFACT_PAYLOAD_INVALID`。
- 模型输出被长度限制截断：`MODEL_OUTPUT_TRUNCATED`。
- 模型内容过滤：`MODEL_OUTPUT_FILTERED`。
- 一致性报告缺字段、越界或包含未知字段：质量任务失败，不保存部分报告。

所有错误都必须保留完整内部诊断，不静默截断工具结果或用户可见回复；对外错误继续遵循现有 Core 回调和日志边界。本规格不改变 checkpoint/SSE 补发策略。

## 文件影响

预计修改以下职责范围，实施计划必须在当前代码上重新核对精确行号：

- `apps/agent-service/src/inkforge_agents/operations/definitions.py`：Operation 执行契约；
- `apps/agent-service/src/inkforge_agents/operations/graph.py`：显式 reviewer/reviser 节点、rewrite-only、产物校验；
- `apps/agent-service/src/inkforge_agents/runtime/agent_runner.py`：模式、Operation 工具交集、消息构造；
- `apps/agent-service/src/inkforge_agents/runtime/agent_runtime.py`：调用级终止工具和完成原因处理；
- `apps/agent-service/src/inkforge_agents/providers/base.py`、`openai_compatible.py`：完成原因；
- `apps/agent-service/src/inkforge_agents/jobs/adapters.py`：权威草案水合、reviewer/reviser 上下文和身份校验；
- `apps/agent-service/src/inkforge_agents/jobs/writing.py`：恢复前水合、最小上下文；
- `apps/agent-service/src/inkforge_agents/jobs/quality.py`：校验 Agent 的质量模式；
- `apps/agent-service/src/inkforge_agents/graph/context.py`、`parent_graph.py`、`state.py`：上下文投影和当前消息去重；
- `apps/agent-service/src/inkforge_agents/tools/control.py`：评审与质量报告参数契约；
- `packages/service-contracts/src/inkforge_contracts/quality.py`：Agent 与 Core 共用的一致性质量报告模型；
- `apps/agent-service/src/inkforge_agents/prompts/*.py`：静态提示词收敛；
- `apps/core-api/src/inkforge_core/writing/context.py`：内部写作上下文排除当前轮重复历史，并返回可水合的完整 activeArtifact；
- `apps/core-api/src/inkforge_core/quality/schemas.py`、`repository.py`：固定一致性报告回调契约、保存完整 WorkflowRun 输出并只映射平均总分；
- 对应 Agent Service 测试、架构文档和 03、04 号需求文档。

不修改公共 Core API。内部 `get_writing_context` 返回值按上述字段扩展，并保持数据库 schema 不变。

## 测试与验收

### 消息与提示词

- [x] 最终模型消息中当前用户请求只出现一次。
- [x] 会话历史不包含当前轮重复消息。
- [x] 作品正文和参考资料不使用 system 角色。
- [x] reviewer 动态指令不包含 `get_active_review_artifact`。
- [x] reviser 必须收到完整 `requiredChanges` 和原草案身份。
- [x] 静态提示词不再包含 reviewer、patch 和运行时 artifactKey 协议。

### 工具与产物

- [x] 每个 Operation 的工具集合有精确断言；设定构建器不含 `append_outline_tree`，大纲和伏笔 Operation 可以使用。
- [x] reviewer 只暴露 `submit_evaluation`，不暴露读取工具。
- [x] quality 只暴露 `submit_quality_report`。
- [x] `plan_chapter` 只能通过 `submit_beat_plan` 完成。
- [x] `write_chapter` 只能提交 `chapter_draft`。
- [x] 错误事件、错误 kind、变化的 artifactKey 和多个冲突终止事件会被拒绝。
- [x] 产物终止工具成功后不会发生额外模型调用。

### 复审、返工与恢复

- [x] reviewer 的无读取工具、仅 `submit_evaluation` 行为由显式模式决定，不再由 `activeArtifactId` 推断。
- [x] reviser 获得原草案、revision、artifactKey 和合并修改意见。
- [x] patch 结论直接归一为 rewrite，不调用 `apply_patch()`，且不丢失原修改意见。
- [x] 新建空 `CoreArtifactPort` 模拟服务重启后，可以从 `planning.activeArtifact` 恢复并继续复审或返工。
- [x] 权威草案缺失、Operation 身份不一致或其他 job 争用缓存时明确失败。
- [x] 已由 Core 完成的 approve/discard 决定即使不再返回 activeArtifact，也能只推进图并稳定结束。
- [x] 等待态在事件和 checkpoint 成功后释放，完成态和错误态在相应回调成功后释放；失败时保留缓存。

### 质量与模型完成态

- [x] consistency 使用“校验”Agent，而不是“编辑”。
- [x] 任意 score key、越界值和缺失字段会被拒绝。
- [x] issues 缺少固定字段、包含未知字段或使用非法 dimension/severity 时会被拒绝。
- [x] 质量报告正文缺失或为空时会被拒绝，不能完成为空报告。
- [x] 五项一致性分数和 issues 完整保存在 WorkflowRun 输出中，公共检查只写平均 `scoreOverall`，旧商业评分列保持空值。
- [x] `finishReason=length` 不会生成成功草案、成功评审或成功质量报告。
- [x] `finishReason=content_filter/unknown` 按设计明确收敛，`stop + toolCalls`、`tool_calls + 无工具` 和非法 `unknown` 工具在正文或副作用产生前失败；模型日志同时保留规范化和供应商原始原因。

### 回归命令

```bash
uv run --frozen pytest -p no:cacheprovider apps/agent-service/tests -q
uv run --frozen pytest -p no:cacheprovider apps/core-api/tests/writing/test_context.py apps/core-api/tests/quality -q
uv run --frozen ruff check apps/agent-service/src apps/agent-service/tests apps/core-api/src apps/core-api/tests packages/service-contracts/src packages/service-contracts/tests
uv run --frozen mypy apps/agent-service/src apps/core-api/src packages/service-contracts/src packages/service-auth/src
```

共享质量契约属于本次范围，因此还要运行：

```bash
uv run --frozen pytest packages/service-contracts/tests packages/service-auth/tests -q
```

验收时 Agent Service 全量测试必须保持通过；历史固定 passed 数不作为当前验收依据，以本计划记录的实际回归命令退出码为准。不得通过放宽断言、保留静默回退或修改数据库结构让测试变绿。
