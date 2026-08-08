# 长篇写作失败分层错误码

## 背景

本地使用生产章节只读快照、真实 Operation 上下文、真实模型、计费包装、模型观察器和 Artifact 校验均可完成正文生成；生产任务仍在模型调用前后约两秒内失败。当前 `WritingJobHandler` 把图执行期间的所有异常统一上报为 `AGENT_RUN_FAILED`，Core 又不公开原始异常文本，因此无法判断失败发生在模型授权、供应商调用、用量回报、工具参数还是 Core 工具网关。

## 目标

- 保持公开响应只包含稳定错误码，不公开原始供应商响应、URL、密钥或内部堆栈。
- 对可识别的模型运行边界分别使用 `MODEL_AUTHORIZATION_FAILED`、`MODEL_PROVIDER_FAILED`、`MODEL_USAGE_REPORT_FAILED`。
- 对现有以大写错误码开头的运行时错误，向写作任务透传该稳定错误码。
- 无法识别的异常继续使用 `AGENT_RUN_FAILED`。
- 不修改 PostgreSQL schema、公共请求 DTO、任务状态机或重试语义。

## 设计

`ModelRuntime` 在三个外部边界捕获异常并抛出带稳定前缀的 `RuntimeError`：模型授权、供应商调用、用量回报。原异常保留为异常链，仅供服务端日志使用。

`WritingJobHandler` 从异常链中提取首个符合 `^[A-Z][A-Z0-9_]+` 的稳定错误码并用于失败回调；若不存在则回退 `AGENT_RUN_FAILED`。失败回调中的 `message` 仍保留服务端诊断文本，但公开任务投影只显示错误码。

## 验证

- 测试三个模型运行边界分别产生稳定错误码。
- 测试写作 Job 能从异常链提取稳定错误码，未知异常仍回退。
- 运行 Agent Service 全量测试、Ruff 与 Mypy。
- 部署后只启动一次新的 `write_chapter` 任务；根据稳定错误码继续修复，不重复盲试。
