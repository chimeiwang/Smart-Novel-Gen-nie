# DeepSeek 一致性终检 strict 工具最小修复规格

## 背景

生产环境第十三章的一致性终检连续失败两次。只读生产日志确认：

- 运行 `cmtdityph2vt7w7kxkytu558r` 已取得一次可计费用量，供应商返回
  `finish_reason=tool_calls`，随后 Agent 在工具预检或本地报告校验前后抛出 `RuntimeError`；
- 运行 `cmtdn4ds42vtaw7kxb4btbap8` 在供应商返回阶段抛出 `ValueError`，安全分类为
  `unexpected_error`，未形成用量记录；
- 同一质量策略在此前章节曾成功完成，故障不是质量任务恒定不可用，也没有证据指向正文或数据库脏数据。

当前生产使用 `OPENAI_COMPATIBILITY_PROFILE=deepseek_v4`。该 profile 选择原始
`DeepSeekV4Provider`，质量策略虽然通过 named `tool_choice` 强制调用
`submit_quality_report`，但普通工具声明没有发送 `strict: true`，请求也没有进入 DeepSeek
`/beta` strict 通道。因此当前行为只是“必须调用指定工具”，不是“供应商保证工具参数符合 JSON
Schema”。

项目已有视频链路真实调用证据表明，DeepSeek Beta strict 仍不能取代本地完整校验，也不应成为全部结构化
输出的唯一生产支点。本规格只修复当前质量终检缺失 strict wire 的问题，不推翻视频 Responses 主链或扩大到
其他 Agent。

## 目标

- 只为一致性终检的 `submit_quality_report` 启用真实 DeepSeek strict Function Calling。
- strict 请求固定走 DeepSeek Beta 地址，并为本轮全部函数发送 `strict: true`。
- 把完整 Pydantic Schema 确定性投影为 DeepSeek strict 支持的 wire Schema；供应商返回后仍使用原始
  `QualityReportArgs` 完整复验。
- 保持现有 named `tool_choice`、关闭思考、计费、质量回调和 Core 持久化语义不变。
- 质量工具预检失败时，服务日志至少保留已有异常消息开头的稳定大写错误码，不再把
  `MODEL_TOOL_ARGUMENTS_INVALID` 等错误统一压成 `RuntimeError`。

## 非目标

- 不修改 Reviewer、Beat Plan、设定更新、构建器、视频或其他工具的 Provider 路由。
- 不把全部 Function Calling 切换到 DeepSeek Beta strict。
- 不改变 `ConsistencyQualityReport`、Core API、Java Core、数据库结构或前端。
- 不增加自动重试、宽松 JSON 修复、字段猜测、部分报告保存或失败后协议切换。
- 不把 DeepSeek Beta strict 宣称为无需本地校验的可靠业务契约。

## 设计

### 工具声明

`ToolDefinition` 增加默认值为 `False` 的 `strict` 元数据，`as_model_tool()` 将该值传入
`ModelTool.strict`。默认值保证全部既有工具保持当前行为。

`control_tools()` 只把 `submit_quality_report` 标记为 `strict=True`。其他 control、read 和 proposal
工具保持 `strict=False`。质量执行模式当前只暴露这一个终止工具，因此不会产生 strict 与非 strict 混用。

### DeepSeek strict 端点

`DeepSeekV4Provider` 同时维护普通 Chat Completions 端点和可选 strict 端点：

- 普通请求继续使用现有 `OPENAI_BASE_URL`；
- strict 请求优先使用显式 `OPENAI_STRICT_BASE_URL`；
- 未显式配置且普通地址的主机严格等于 `api.deepseek.com` 时，确定性派生
  `https://api.deepseek.com/beta`；
- 自定义普通地址没有显式 strict 地址时，在任何 HTTP 请求前稳定失败，不猜测网关的 Beta 路径。

当请求包含 strict 工具时，Provider 必须确认本轮所有工具均为 strict；混用时零 HTTP 失败，不能静默升级
非 strict 工具，也不能回退普通端点。strict wire 继续发送 named `tool_choice`，不发送官方 strict 文档未要求
的 `parallel_tool_calls`。

### strict wire Schema 投影

新增纯函数，把调用方原始工具 Schema 深复制后投影为 DeepSeek strict wire Schema。投影规则为：

- 递归保留 `type`、`properties`、`required`、`additionalProperties`、`enum`、`const`、`anyOf`、
  `items`、`$ref`、`$defs`、`description`、`pattern`、`format`、`minimum`、`maximum`、
  `exclusiveMinimum`、`exclusiveMaximum` 和 `multipleOf`；
- 每个对象的 `required` 固定为该对象全部 `properties` 键，`additionalProperties` 固定为 `false`；
- 可选业务字段继续使用现有 `anyOf[..., {"type": "null"}]` 表达可空，但在 wire 中必须显式出现；
- 移除 `title`、`default`、`minLength`、`maxLength`、`minItems`、`maxItems` 及其他未列入白名单的
  Provider 不兼容关键词；
- 不修改原始 Schema，不把较弱 wire 投影作为业务验证 Schema。

供应商返回的工具参数仍必须通过 `ToolDefinition.validate()` 和原始 `QualityReportArgs`。例如字符串长度、
issue 数量和跨字段业务规则仍由本地完整约束执行。strict 只缩小模型输出包络，不能把供应商结果升级为可信
业务事实。

### 安全失败分类

质量任务日志继续禁止输出异常正文、工具参数、原始响应和章节内容。对于 AgentRuntime 已经以
`UPPER_SNAKE_CASE：说明` 形式抛出的协议错误，`_safe_failure_code()` 只提取冒号前且满足现有字符白名单的
稳定码，例如：

- `MODEL_TOOL_ARGUMENTS_INVALID`
- `MODEL_TOOL_NOT_EXPOSED`
- `MODEL_TERMINAL_TOOL_CONFLICT`
- `PROVIDER_FINISH_REASON_INVALID`

不存在安全前缀时继续回退异常类型。该变化只提高日志分类精度，不把错误详情写入 Core 或公开接口。

## 数据流

```text
QualityJobHandler
  -> AgentRunner / quality policy
  -> submit_quality_report(strict=True)
  -> DeepSeekV4Provider
       -> strict Schema 投影
       -> /beta/chat/completions
       -> function.strict=true
       -> named tool_choice
  -> AgentRuntime 原始 Pydantic 复验
  -> QualityJobHandler 完成回调
  -> Java Core 保存完整质量报告
```

任何 strict 端点缺失、供应商错误、响应解析失败或本地复验失败都沿现有质量失败路径收敛，不保存部分结果。

## 测试

- `ToolDefinition` 默认仍生成 `strict=False`，质量报告工具生成 `strict=True`，其他工具不变。
- 完整质量报告 Schema 的 wire 投影满足：所有对象属性 required、`additionalProperties=false`，且不包含
  DeepSeek 不支持的长度和数组数量关键词。
- strict 质量请求发送到 `/beta/chat/completions`，函数包含 `strict: true`，保留 named
  `tool_choice` 和关闭思考设置。
- 普通工具请求仍发送到标准 `/chat/completions`，不包含 `strict` 字段。
- strict/non-strict 混用在 HTTP 调用前失败；自定义普通端点缺少 strict 地址时同样零 HTTP 失败。
- wire 投影移除的长度和数量约束仍由原始 `QualityReportArgs` 拒绝。
- `MODEL_TOOL_ARGUMENTS_INVALID` 等前缀能进入质量失败日志的 `failure_code`，任意异常文本和工具参数不进入
  日志。
- 现有 Provider、工具注册、质量任务、ModelRuntime 计费和 AgentRuntime 测试全部通过。

## 发布与验收

本修复只影响 Agent Service。合并前至少执行相关 pytest、Ruff 和 Mypy；发布时只允许使用通过完整 CI 的
不可变 Agent 镜像。生产验收先确认运行镜像和安全模型配置，再对当前失败的质量检查执行一次用户明确授权的
重置与重跑，并核对：

- 请求只产生一次模型调用；
- 质量检查形成完整 `result`、五维分数和 `qualityGate`；
- TokenUsage 与人工工作流日志能按同一 runId 对账；
- 若仍失败，日志出现稳定协议错误码，而不是只有 `RuntimeError`。

生产重跑不是本规格实施授权的一部分，必须在代码发布成功后由用户单独批准。
