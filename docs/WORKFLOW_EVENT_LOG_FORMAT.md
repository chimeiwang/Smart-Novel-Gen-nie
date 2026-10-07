# 人工工作流日志格式

当前实现位于 `apps/agent-service/src/inkforge_agents/observability/`。Agent Service 把日志写入 `/data/agent-logs`，Compose 使用 `agent_logs` 命名卷持久化；Core API 通过签名内部接口按用户归属读取，浏览器不能直接访问 Agent Service。

## 文件与追加规则

V2 单 Step 不经过 V1 人工日志 observer。结构化输出失败由 Executor 记录 run、step、输出 Schema、
失败载荷、全部校验原因和异常链，凭据先脱敏；公共终态仍只保留原安全分类。
该诊断只帮助定位格式错误，不改变失败终态或触发模型纠正调用。

供应商请求失败时，DeepSeek 和通用 OpenAI-compatible 适配器另行保留完整错误诊断：非成功 HTTP
响应正文与响应头、状态码、方法、脱敏地址、异常消息、因果链和无局部变量的调用栈。错误响应可以是
JSON、纯文本或 HTML，不按长度截断。API Key、授权头、Cookie、密码及令牌在采集时脱敏。
V1 的 `model_failure` 帧将详情写入正文，不放入受长度限制的结构头；服务日志使用单行 JSON 转义
换行，并携带 task/run 身份。V2 不写 V1 人工日志，详情由 Executor 按 run/step 写入服务日志。
公共错误码、任务状态和计费结果不包含这些详情；详见[完整错误诊断规格](specs/2026-10-07-provider-error-details.md)。

HTTP 200 但响应、usage、工具参数或结构化输出不合法也属于失败诊断。统一 `failureDiagnostics` 仅在
进程内向日志层传递，普通序列化与 repr 排除；包含阶段、失败代码、完整脱敏载荷与异常链。V1 在计费
回报前写独立 `diagnostic` 帧正文，即使后续回报失败也保留原模型失败证据；正常成功模型区块仍在
计费回报成功后写入。授权、grant、回报、工具预检／执行与完成原因拒绝同样有独立诊断。
全部校验错误及失败原参数不截断，超长详情不进入结构头。详见
[完整失败诊断规格](specs/2026-10-07-complete-failure-diagnostics.md)。

`diagnostic` 使用独立 D 序号，不算作模型尝试，不输出伪造的耗时、工具数或用量；只有实际 `model` 和
`model_failure` 帧推进模型尝试序号。同一次响应的多个失败调用和模型调用之前的授权错误不会虚增调用次数。

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
伪造 token。AgentRuntime 的每次显式工具协议纠正属于新的模型调用，必须形成独立计费 `requestId`、usage
回报和模型区块，不能与首次无效调用合并成一条记录。

人工日志不记录凭据、供应商 reasoning、完整运行时对象或底层 checkpoint metadata。正常成功的工具
Schema、tool_calls、参数和结果不另行复制；失败时保存完整脱敏 arguments、对应 Schema、校验错误
及恢复前后证据。完整诊断不进入公共错误、Core、SSE、业务快照或模型纠正提示。
禁止对已记录的正文、消息、模型输出或错误进行静默截断。

普通章节正文提交的有界例外见 [临时修补规格](specs/2026-09-28-chapter-artifact-protocol-hotfix.md)。
工具预检发生在人工模型区块写入之后；Agent 服务运行日志另行记录每次预检失败的 runId、脱敏工具分类、
loc/type、`corrections_used` 和 `action`，包括后来纠正成功的失败。正文跨字段校验使用稳定的
`artifact_content_required`、`artifact_content_blank` 和 `artifact_selection_*` 分类，
不再全部退化为根级 `value_error`。纠正请求的 system 消息只加入脱敏诊断和服务端固定指令，
不回放失败包。这些服务诊断不新增人工日志帧格式或公共接口。

## 旧版兼容与恢复

首次继续写入旧版文本日志时，服务先校验可解析的旧版运行身份，再把完整旧版原文迁入
`type=legacy, trust=unverified` 的只读帧。读取时以明确的“旧版日志边界”展示，其内容不参与新版
结构解析，也不能提升为可信元数据。

v2 日志尾部残缺时，读取只展示最后一个完整可信帧之前的内容并标记尾部损坏。下一次写入前，服务
只有在完整可信运行元数据仍可识别时才恢复：把原始残缺字节隔离为独立 `.bin` 文件，文件名和恢复帧
记录 SHA-256 与字节数，然后保留完整前缀、追加恢复帧并继续写入。缺少可信运行元数据时明确拒绝
自动恢复，不能猜测归属或静默丢弃残尾。

## 配置

工具预检的根级定位、复审组合和操作产物范围错误使用稳定类型与固定纠正说明；完整失败参数和校验
详情仅进入脱敏诊断正文，模型纠正提示仍只带安全分类和字段路径。新模型 Beat Plan 的数量由运行时边界派生，持久事件
保持原有结果形状，人工日志帧格式不变。

Core 后台监督器日志独立于本人工日志：控制台显示任务、失败分类、重试次数、退避与稳定恢复，
异常诊断只保留白名单类型及栈帧，不输出异常消息、SQL 或凭据。

```bash
WORKFLOW_HUMAN_LOG_DIR=/data/agent-logs
WORKFLOW_EVENT_DEBUG_ENABLED=false
```

调试读取默认关闭。开启后，用户仍必须通过 Core API 浏览器鉴权和归属校验；Core 到 Agent 的读取请求还必须具有 `agent:debug:read` 服务权限。
