# 模型与工具执行完整失败诊断

状态：实现及本地验证完成，待完整 CI 与生产发布验证。

## 背景与授权

用户要求补齐各类错误日志，尽可能完整保留报错信息。最近的章节任务
`cmuxxmplitdiyfz9s9ydp2r3g` 已收到正常 HTTP 响应，但两轮工具参数校验失败只留下工具名、分类和字符数，
无法确认真实参数与预期 Schema 的差异。

本规格扩大[供应商错误诊断](2026-10-07-provider-error-details.md)范围，取代 Agent 指导、AI 写作需求、
人工日志及历史规格中“失败工具参数、字段值与校验异常不得保存”的限制。用户授权只针对错误诊断，
不扩大成功内容采集、凭据访问、业务写入、数据库变更或真实模型调用权限。

## 采集范围

1. HTTP／连接／超时失败：保留原状态、响应头和正文、供应商请求标识、方法／地址、完整异常消息、
   因果链及无局部变量的调用栈；现有完整采集覆盖普通模型、Embedding 和 Responses 适配器。
2. HTTP 成功但响应无效：保存失败的 JSON／envelope／usage／structured output 数据、详细校验异常、
   实际期待的 Schema、供应商状态及失败说明，不能只留下分类码。
3. 工具协议：保存每个失败调用的名称／ID、完整原 arguments、预期 wire 和业务 Schema、具体阶段
   （JSON 解析、wire 校验、解码、业务 Schema 或 Pydantic 校验）、异常路径及全部校验错误。
   已确定性恢复的坏 JSON 同样保留恢复前后证据；正常工具调用不额外复制。
4. 运行时：保存授权、grant 校验、用量回报、工具预检／执行、完成原因拒绝及未知异常的完整诊断。
   记录 task/run/step、provider/model、request/response ID、工具身份及已有纠正次数，保留每次失败。
   Core 内部客户端的 HTTP、网络、JSON、回执和工具返回格式错误保留完整失败响应；写作图、复审降级
   与队列异常同样记录原异常，不能只剩状态收敛后的摘要。
5. V2 结构化执行输出校验、超时与未知异常保存详细诊断，继续遵守原有日志与业务状态边界。

## 表示、脱敏与日志边界

- 在 `providers/error_details.py` 增加统一 `FailureDiagnostic` 和 `capture_failure_diagnostic`：
  `stage`、`code`、完整脱敏 `payloadJson`、`errorDetails`（复用 ProviderErrorDetails）、`captureFailure`。
  payload 可包含 arguments、Schema、校验错误列表和已有请求身份；文本内容不截断。
- 统一 `log_failure_diagnostic(logger, diagnostic, **identity)` 使用单行 JSON 输出，防止换行伪造日志；
  helper 采集、序列化或 sink 故障不得覆盖原失败，也不得使原本成功的模型调用失败。
- `ModelTurnResult.failureDiagnostics` 为 `Field(default_factory=list, exclude=True, repr=False)`；
  仅在进程内向日志层传递，结果重建须显式保留。异常可携带同名私有诊断属性，保持原类型与简短公共消息。
- V1 通过人工日志 observer 把详情写入帧正文，绝不写入受 64 KiB 限制的结构头；Provider 诊断在计费
  回报之前写独立失败帧，以免回报失败掩盖之前的模型错误。正常成功模型记录仍遵守原计费成功后记录规则。
- 原始供应商调用失败继续写 `model_failure`；附属校验、授权和工具等诊断写独立 `diagnostic` 帧及 D 序号，
  不计入模型尝试次数，不用零耗时或零工具数冒充一次真实模型调用。
- V2 只写服务诊断日志。排除字段不得进入 Core 回调、SSE、公共任务错误、模型纠正提示、journal、
  checkpoint、ReviewArtifact 或正常结果序列化；完整诊断不能用作模型重试输入。
- 已知 API key、Authorization、Cookie、grantToken、密码、URL 凭据及嵌套 JSON 中凭据全部脱敏。
  模型 reasoning 内容和栈帧局部变量不采集；正常提示词、成功工具输入和成功模型正文不新增副本。
  若为 HTTP 200 协议失败采集响应正文，须先剔除 reasoning 内容。
- 敏感值在 Pydantic loc/input、异常文本和嵌套 JSON 中的再次回显也须脱敏，包括数字 PIN。异常私有
  属性仅缓存已脱敏的消息、栈帧和方法／地址，防止上层没有原凭据时重新读取原异常而泄漏；不额外缓存
  凭据原值，不改公开异常文本、类型或因果关系。异常组逐项采集全部子异常。
- 既有安全分类、公共错误摘要、计费结算、纠正预算、失败终态、工具权限和供应商 strict 行为不改变。
  不依据尚未取得的真实参数自动放宽校验或修复参数。

## 验收

- 替身复现最近的两个工具失败，日志包含真实失败参数、Schema、阶段与校验原因，首轮及纠正后均可查。
- 覆盖非法 JSON／重复键、未知工具、wire／业务／Pydantic 校验、HTTP 200 的响应与usage错误、
  structured output、Responses failed/incomplete、Embedding、授权／回报、工具执行、完成原因及未知异常。
- 超过 64 KiB 的详情及超过原摘要上限的校验错误完整保存；坏参数中的伪造日志标记不能改变帧结构。
- 全链路凭据脱敏、reasoning 排除；正常 model_dump/repr、持久终态与纠正提示没有完整失败诊断。
- 诊断采集和日志 sink 故障不改变返回值、原异常、实际 usage、纠正次数或终态。旧 Provider/observer 兼容。
- 执行相关 Provider、Runtime、observability、Executor、共享契约测试、全仓 Ruff、共享范围 Mypy 与文档检查。

## 非目标

不恢复已经丢失的历史参数，不新增真实供应商调用，不修改业务 Schema、请求包装、模型预算、数据库或
正式内容。本次聚焦 Agent 的模型与工具执行链，Java Core 的认证、数据库及支付业务错误不在此变更范围。

## 本地验证记录

- 实际模型参数失败的回归覆盖两轮诊断、超过 64 KiB 的原参数、全部 Pydantic/jsonschema 校验错误、
  wire/业务/模型 Schema、JSON 恢复前后证据及多层异常；凭据、数字 PIN、嵌套 JSON、异常与 URL 的
  上层重复采集均有脱敏回归。
- AgentRuntime 最终专项 61 项通过，计费与人工日志 69 项通过，Core 回调与工具结果 36 项通过，
  共享采集器/DeepSeek/strict 163 项通过；正文复审 16 项验证失败内容入日志且不进入公共终态和真实 journal。
- 队列重试、复审降级、Core.fail 和并发工具结果在日志设备或诊断序列化故障时保持原语义；没有放宽
  参数校验或扩大纠正预算。
- 全仓 Ruff、Agent/共享契约/鉴权 Mypy（133 源文件）、文档链接及 diff 空白检查通过。
- 本机没有 uv，使用已有 `.venv/bin` 工具。全仓首次运行在部署脚本测试遇到 `/usr/bin/dd` 等本机
  环境问题而停止；未修改部署脚本或该套件，完整 Linux 门禁由正式 CI 验证。
- 本机排除上述部署脚本套件后运行其他全仓测试，3804 项全部通过；新诊断帧与最终 Core 客户端保护
  的专项另行通过。本记录不把被排除的 Linux 套件算作本机通过。
