# 人工工作流日志格式

当前实现位于 `apps/agent-service/src/inkforge_agents/observability/`。Agent Service 把日志写入 `/data/agent-logs`，Compose 使用 `agent_logs` 命名卷持久化；Core API 通过签名内部接口按用户归属读取，浏览器不能直接访问 Agent Service。

## 文件与追加规则

文件名由运行标识的安全哈希生成，禁止把任务标识直接拼接为路径。同一任务首次执行和恢复运行追加到同一文件。没有模型调用或图状态变化的短路操作不创建空日志。

新日志使用 `INKFORGE-HUMAN-LOG/2` 魔数和长度分帧格式。每帧由固定前缀、JSON 结构头的字节长度、
正文的 UTF-8 字节长度和正文组成；读取器只按长度识别边界，正文即使包含帧标记、JSON 或旧版运行
信息，也不能污染元数据、运行身份或后续帧解析。每次追加都在校验已有日志的 `taskId`、`runId`、
`userId`、`novelId` 和适用时的 `chapterId` 与当前调用一致后进行。

每个运行区块记录：

1. 实际发送给模型的完整 messages 和模型返回的完整正文；
2. 每次模型调用的 `taskId`、`runId`、Core 计费 `requestId`、provider/model、四项实际 token、规范化
   完成原因和供应商原始完成原因；工具协议异常时还记录无效调用数量、允许列表内工具名、稳定分类与
   arguments 字符数，确定性闭合符恢复时记录恢复方法与追加容器数；
3. 中文 LangGraph 状态切换、阶段和结束状态。

四项 token 是 `promptTokens`、`cachedTokens`、`completionTokens`、`totalTokens`；其中缓存 token 是输入
token 子集，合计等于输入加输出。billable Provider 成功形成规范化 `ModelTurnResult` 后，Agent 先向
Core 上报 usage；只有 Core 成功接受 report 且配置了 observer，才写入该次人工模型区块。report 失败
时异常向上传播，不留下该次模型区块。非 billable Provider 成功后直接调用 observer，但只有 observer
与运行 context 都存在时才写入，且显示“计费请求标识：无”。Provider 在返回可靠 usage 前失败时不得
伪造 token。AgentRuntime 的一次显式工具协议纠正属于新的模型调用，必须形成独立计费 `requestId`、usage
回报和模型区块，不能与首次无效调用合并成一条记录。

人工日志不记录 `grantToken`、tools schema、供应商 reasoning、模型 tool_calls、工具参数、工具返回、
完整运行时对象或底层 checkpoint metadata。工具协议诊断中的 arguments 字符数只是整数，不得附带或重建
原始 arguments。禁止对已记录的正文、消息、模型输出或状态进行静默截断。

## 旧版兼容与恢复

首次继续写入旧版文本日志时，服务先校验可解析的旧版运行身份，再把完整旧版原文迁入
`type=legacy, trust=unverified` 的只读帧。读取时以明确的“旧版日志边界”展示，其内容不参与新版
结构解析，也不能提升为可信元数据。

v2 日志尾部残缺时，读取只展示最后一个完整可信帧之前的内容并标记尾部损坏。下一次写入前，服务
只有在完整可信运行元数据仍可识别时才恢复：把原始残缺字节隔离为独立 `.bin` 文件，文件名和恢复帧
记录 SHA-256 与字节数，然后保留完整前缀、追加恢复帧并继续写入。缺少可信运行元数据时明确拒绝
自动恢复，不能猜测归属或静默丢弃残尾。

## 配置

```bash
WORKFLOW_HUMAN_LOG_DIR=/data/agent-logs
WORKFLOW_EVENT_DEBUG_ENABLED=false
```

调试读取默认关闭。开启后，用户仍必须通过 Core API 浏览器鉴权和归属校验；Core 到 Agent 的读取请求还必须具有 `agent:debug:read` 服务权限。
