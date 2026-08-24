# DeepSeek 模型响应等待 300 秒临时修复规格

**日期：** 2026-08-24
**状态：** 已实施并完成本地验证，待推送与生产验证
**范围：** DeepSeek V4 原始 HTTP 传输的模型响应读取等待

## 背景

生产写作任务 `cmt70igarb90kovrib32d19n9` 前四次模型调用成功，第五次调用在
`60817ms` 处以 `timeout_error` 失败。失败没有 HTTP 状态码或供应商请求 ID，与
`DeepSeekV4Provider` 当前 `httpx.Timeout(60, connect=10)` 的读取等待边界吻合。

用户要求先把该等待时间临时扩展到 300 秒并部署，再单独实施统一模型等待策略。

## 目标

- DeepSeek 模型响应读取等待从 60 秒提高到 300 秒。
- 建连等待继续保持 10 秒。
- 请求写入和连接池等待继续保持 60 秒。
- 保持一次业务调用只发送一次 DeepSeek HTTP 请求，不增加自动重试。

## 方案

`DeepSeekV4Provider` 自建客户端时使用显式四项超时：

```python
httpx.Timeout(connect=10, read=300, write=60, pool=60)
```

注入测试客户端的行为保持不变。Provider 的错误分类、安全日志、计费、工具循环和
`MODEL_PROVIDER_FAILED` 终态语义均保持不变。

## 非目标

- 不修改通用 OpenAI-compatible 通道。
- 不增加 SDK、Provider、ModelRuntime 或队列自动重试。
- 不实现流式响应、模型轮次检查点或失败任务恢复。
- 不修改 PostgreSQL schema、Core API 或公共接口。
- 不把 300 秒描述为最终架构；统一等待策略和基础设施错误边界另立规格。

## 验收

- 自动测试证明默认 DeepSeek 客户端的 connect/read/write/pool 分别为
  `10/300/60/60` 秒。
- DeepSeek Provider 全量测试、Ruff 和相关 Mypy 通过。
- 提交推送到 `main` 并完成生产部署。
- 生产容器中的实际代码可只读核验为 `read=300`，服务 readiness 正常。
