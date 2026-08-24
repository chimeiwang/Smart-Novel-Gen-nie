# 模型供应商失败可观测性规格

## 背景

生产环境编辑第 11 章时，两个写作任务连续以 `MODEL_PROVIDER_FAILED` 结束。TokenUsage 显示两次运行分别在第 5 次和第 4 次成功模型调用后停止记账，任务均在最后一条成功用量记录约 120 秒后失败。现有人工工作流日志只记录成功调用，失败时直接写入运行终态，无法区分客户端超时、连接失败、供应商 HTTP 错误或本地程序错误。

## 目标

- 保持公开错误码 `MODEL_PROVIDER_FAILED` 和现有任务状态语义不变。
- 每次供应商调用失败时，把安全诊断写入对应运行的人工工作流日志，并同时输出结构化服务日志。
- 对普通工具调用通道补齐与结构化输出通道一致的传输错误归一化，区分 `timeout_error`、`connection_error` 和 `http_error`。
- 日志能够通过 `taskId`、`runId`、Agent、模型、耗时和供应商请求 ID 对账。

## 方案

### Provider 边界

普通 ChatOpenAI 调用捕获 SDK 的超时、连接和 HTTP 状态异常，转换为现有 `ProviderTransportError`。只保留稳定错误码、HTTP 状态码和经过字符白名单校验的供应商请求 ID；原始响应正文、异常消息和底层异常链不得继续传播。

### ModelRuntime 边界

ModelRuntime 负责补齐业务运行上下文和请求形状，形成失败记录：

- userId、novelId、taskId、runId、agentId；
- provider、model；
- failureCode、exceptionType、statusCode、providerRequestId；
- elapsedMs；
- messageCount、toolCount、structuredRoute、requestedMaxOutputTokens。

失败记录不得包含消息正文、工具描述、工具参数、JSON Schema、模型响应、`reasoning_content`、API Key、授权令牌或原始异常文本。记录完成后仍抛出原有 `MODEL_PROVIDER_FAILED`。

### 人工工作流日志

增加 `model_failure` 帧。序号按成功与失败的模型尝试共同递增，因此现场可以直接判断第几次模型请求失败。可读正文与帧头只展示上述安全字段，不复制请求或响应内容。

观察器或日志写入本身失败时不得覆盖原始供应商错误；服务结构化日志仍应保留同一组安全字段。

## 测试

- 普通 ChatOpenAI 超时、连接错误和 HTTP 错误被安全归一化，私有响应正文不进入异常链或日志。
- ModelRuntime 在供应商失败时记录上下文、错误分类、耗时和请求计数，同时继续抛出 `MODEL_PROVIDER_FAILED`。
- 人工工作流日志生成 `model_failure` 帧，并证明提示词、工具参数和原始异常文本未泄露。
- 成功调用、计费授权和用量回报语义保持不变。

## 非目标

- 本次不增加自动重试，不修改任务超时，不硬性限制 Token，也不改变写作或审核流程。
- 本次不修改 PostgreSQL schema，也不补写历史失败记录。
