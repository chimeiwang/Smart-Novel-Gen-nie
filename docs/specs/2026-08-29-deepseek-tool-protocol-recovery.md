# DeepSeek 工具协议恢复规格

## 背景

2026-08-29 生产日志显示，Agent Service 当天有三次业务失败落在 DeepSeek 工具调用链：供应商已返回
HTTP 成功响应，但 `DeepSeekV4Provider` 在解析工具参数时直接抛出 `ValueError`。其中一致性终检已经部署
`submit_quality_report` 专用 Beta strict wire，部署后的调用仍出现同类 Provider 解析失败；另一次包含
23 个普通工具的写作 Agent 也出现相同顶层异常。因此，问题不能只归因于“没有开启 strict”。

DeepSeek 官方 Function Calling 文档明确要求客户端校验普通模式返回的 arguments；strict 模式能提高 Schema
遵循度，但不能替代客户端对 HTTP 响应、JSON、完成原因和本地业务契约的处理。当前代码已有安全的无效工具调用
诊断字段和“只追加缺失容器闭合符”的恢复算法，但 DeepSeek 原生 transport 没有使用它们：

- `json.loads(arguments)` 失败会直接抛 `ValueError`，可靠 usage 因而无法进入计费回报；
- AgentRuntime 不读取 `invalidToolCallCount`，即使其他 Provider 返回了安全诊断，也会退化成完成原因不一致；
- 本地 Pydantic 参数校验失败后立即结束任务，没有一次受控的协议纠正机会；
- 成功 HTTP 响应中的 envelope、usage 和工具协议错误都被人工日志归类为 `unexpected_error`，无法区分根因。

本规格扩展
[`2026-08-29-deepseek-quality-strict-tool-hotfix.md`](./2026-08-29-deepseek-quality-strict-tool-hotfix.md)。
后者关于“不增加自动重试”的约束继续禁止 SDK 隐式重发、队列盲重试和同一坏参数原样重放；本规格新增的是
AgentRuntime 在任何工具副作用之前发起的一次显式、独立计费、无原始坏参数的协议纠正调用。

## 目标

- DeepSeek 工具 arguments 无法解析时返回安全的 `ModelTurnResult` 诊断，而不是让原始 `ValueError` 穿透。
- 对只缺少对象或数组闭合符、且补齐后通过本轮原始 JSON Schema 的参数做确定性本地恢复。
- 对仍无效的 JSON 或本地 Pydantic 参数，在整个 AgentRuntime 运行中最多发起一次协议纠正模型调用。
- 一次响应只要包含任一无效工具调用，该响应中的正文和全部有效工具调用都不得被接受或执行。
- 原调用和纠正调用分别经过 `ModelRuntime` 授权、usage 回报和人工日志，Token 不合并冒充单次调用。
- 纠正仍失败时抛出稳定、不可重试的 `MODEL_TOOL_PROTOCOL_RECOVERY_FAILED`，使业务任务收敛失败而不重启消费者。
- 成功 HTTP 响应的 JSON、envelope 或 usage 无效时使用脱敏的 Provider 协议错误分类，不记录响应正文。
- 人工模型日志记录无效调用数量、允许列表内工具名、分类、参数字符数以及确定性恢复方法，不记录 arguments。

## 非目标

- 不对同一 HTTP 请求做 SDK 隐式重发，不切换模型、端点或协议。
- 不使用 `json_repair` 等宽松修复，不补键、值、引号、逗号或字符串，不删除、截断或改写业务字段。
- 不把普通写作 Agent 的全部工具切换到 DeepSeek Beta strict；23 个混合工具继续使用普通通道。
- 不把供应商 strict 当成本地 `ToolDefinition`/Pydantic 校验的替代品。
- 不保存部分质量报告，不执行同一坏响应中的“看起来有效”的其他工具调用。
- 不修改 Core API、公共契约、数据库、前端、视频路由或队列持久化结构。
- 不授权部署、生产重跑或远程数据变更。

## 设计

### DeepSeek 安全解析

`DeepSeekV4Provider` 使用本轮 `ModelTurnRequest.tools` 作为唯一工具允许列表。每个供应商工具调用独立解析：

1. 顶层 item、ID、function、name 或 arguments 类型不合法时，生成
   `unknown_invalid_tool_call`；缺少工具名时使用 `missing_tool_name`。
2. arguments 是字符串但标准 `json.loads()` 失败时，分类为 `json_decode_error`。
3. 诊断中的工具名只有在精确匹配本轮允许列表时才保留，否则固定为 `未知工具`；arguments 只记录字符数。
4. 解析成功但根值不是对象时，同样作为无效调用，不进入 `ModelToolCall`。
5. 有效调用和无效诊断可以同时存在于 `ModelTurnResult`，但 AgentRuntime 将整轮视为原子协议包，存在任一无效项
   就不得接受该轮的任何正文或调用。

Provider 仍必须先解析并校验 usage，再返回无效工具诊断，使该次供应商调用可以按真实 Token 独立结算。若响应
JSON、单 choice envelope 或 usage 本身无效，则无法构造可靠 `ModelTurnResult`，抛出不带正文的
`ProviderProtocolError`：

- `invalid_response_json`：HTTP 成功正文不是可解析 JSON；
- `invalid_response_envelope`：choices、message、文本字段或其他响应骨架不合法；
- `invalid_usage`：必填用量缺失、类型非法或内部算术矛盾。

这三类错误固定 `retryable=False`。它们可以携带经过白名单限制的供应商请求 ID、HTTP 状态和错误分类，但不得携带
底层异常、响应正文或请求正文；在 usage 不可靠时不得自动再调用模型，以免形成不可对账的重复计费。

### 确定性本地恢复

对 `json_decode_error`，Provider 可以调用现有闭合符恢复算法。恢复只有同时满足以下条件才成功：

- 工具名属于本轮允许列表，调用 ID、name 和 arguments 类型有效；
- 扫描完整字符串后只存在尚未闭合的 `{` 或 `[`；
- 字符串、转义、Unicode 转义、已有闭合顺序和最大嵌套深度全部合法；
- 只在末尾追加对应的 `}` 或 `]` 后，标准 `json.loads()` 得到对象；
- 对象通过该工具在本轮请求中的原始 JSON Schema 完整复验。

恢复不要求工具为 strict，因此普通 DeepSeek 工具也能处理“内容完整但末尾少闭合符”的常见输出。恢复审计只保存
`append_container_closers` 和追加容器数量。任一条件不满足就保留无效诊断，绝不尝试其他修改。

质量工具现有两个空字符串 wire 归一化继续在 Provider 返回后执行；最终仍由原始 `QualityReportArgs` 校验。

### 一次协议纠正

AgentRuntime 在每次模型结果计入本地累计 usage 后、接受正文和执行工具之前做原子预检。`length`、
`content_filter` 与 `insufficient_system_resource` 仍优先按既有不可接受响应失败，不能借协议纠正掩盖截断、过滤或
供应商资源不足。在完成原因允许继续预检时，以下任一情况触发协议纠正：

- `invalidToolCallCount > 0`；
- `ModelToolCall.arguments` 可解析，但未通过对应 `ToolDefinition` 的 Pydantic 校验。

整个 `AgentRuntime.run()` 最多使用一次纠正额度；当前没有暴露任何工具时不存在可行纠正，直接稳定失败，不额外
调用模型。纠正请求：

- 以原业务 conversation 为输入，不追加供应商的无效 assistant 响应，也不回显原始 arguments；
- 在所有前置 system 消息之后插入固定、短小的 system 指令，要求重新生成本轮完整工具调用、只使用当前声明工具、
  arguments 为完整 JSON 对象并符合 Schema；
- 保持同一工具列表、模型策略、输出上限和业务身份；
- 仍通过一次新的 `ModelRuntime.run_turn()` 执行，因此获得独立的计费 requestId、授权、usage 回报和模型日志；
- 不占用业务 `max_iterations` 的工具轮次，但使一次 Agent 运行的模型调用总上限最多增加 1。

纠正响应必须至少形成一个通过全部预检的工具调用。返回纯文本、仍有 Provider 无效调用或仍有 Pydantic 参数错误
都抛出 `MODEL_TOOL_PROTOCOL_RECOVERY_FAILED`；此前已经使用过纠正额度而后续业务轮次再次出现这两类错误时也
使用同一稳定失败码，不再发起第二次纠正。

错误对象只携带安全派生信息。Pydantic 失败继续最多保留 10 条 `loc/type`；Provider 无效调用只保留允许列表内
工具名、分类和参数字符数。错误固定 `retryable=False`，避免质量任务消费者因模型协议错误重启。

### 日志与计费

`ModelRuntime` 对每个成功构造 `ModelTurnResult` 的调用照常先回报 usage，再写一次模型记录。模型记录新增以下安全
字段：

- 无效工具调用的数量、工具名、分类和 arguments 字符数；
- 本地恢复的数量、方法和追加容器数。

人工日志不得序列化 arguments。协议纠正指令是固定文本，可以作为第二次调用的 system 消息记录；无效 assistant
响应不进入第二次请求，也不进入稳定 conversation。Provider 协议错误由失败记录保存稳定分类，普通未知程序错误
仍归类为 `unexpected_error`。

Agent 最终 `AgentTurnResult.usage` 累加首次调用与纠正调用的 usage，供上层展示本次运行总消耗；这不改变 Core 中
每次模型调用各自独立的 `TokenUsage` 事实。

## 测试

- DeepSeek 畸形 arguments 不再抛 `ValueError`，而是返回与 usage 对齐的安全诊断。
- 未知工具名、缺名、非字符串 arguments、非对象 JSON 和结构错误不会泄露原始值。
- 仅缺闭合符且通过原始 Schema 的普通/strict 调用可恢复；缺引号、缺值、错逗号、错误闭合、过深嵌套或 Schema
  不通过时不可恢复。
- 一轮同时包含有效和无效工具调用时，AgentRuntime 在纠正前不执行任何工具、不保留正文。
- Provider 无效 JSON 和 Pydantic 无效参数都只触发一次纠正；纠正成功后正常执行工具。
- 纠正请求不包含原始坏 arguments，固定指令位于前置 system 消息之后，工具和策略保持不变。
- 纠正返回纯文本或再次无效时稳定抛出 `MODEL_TOOL_PROTOCOL_RECOVERY_FAILED`，且无工具副作用。
- 两次调用的 usage 在 Agent 结果中求和；billable 测试证明两次授权、两次 usage 回报和不同 requestId。
- JSON、envelope、usage 协议错误分别进入安全失败分类，异常链和人工日志均不含供应商正文。
- 相关 Agent pytest、Ruff 和 Mypy 全部通过。

## 发布与验收

本修改只涉及 Agent Service。合并前必须完成相关 pytest、Ruff 和 Mypy；发布必须使用通过完整 CI 的不可变镜像。
生产验收需要用户另行批准一次质量检查重跑，并核对同一 runId 下：

- 首次调用若有效，只产生一次授权和一次 usage；
- 首次调用若协议无效，日志显示一次安全诊断和至多一次纠正调用，两次 TokenUsage 可分别对账；
- 纠正成功后只执行纠正响应中的完整工具调用；
- 纠正失败后任务以稳定不可重试错误收敛，不重启消费者、不保存部分报告；
- 任何日志均不出现供应商原始 arguments、响应正文或异常正文。
