# Python LangGraph Studio 接入

LangGraph Studio 只用于查看 Python 图结构、状态、`Send`、`Command` 和 `interrupt()`，不是生产请求入口。

## 配置与入口

```text
langgraph.json
apps/agent-service/src/inkforge_agents/studio.py
```

启动命令：

```bash
uv run langgraph dev --no-browser --port 2024
```

当前 Studio 入口导出与生产相同的父图和 Operation 图，但外部 Core API 端口使用拒绝占位实现。因此它适合结构和状态调试；需要真实数据库上下文、草案写入和完整工具调用时，应通过 Compose 中的 Core API 发起测试运行，不能绕过服务边界让 Studio 直接连接数据库。

Studio 不得新增平行编排。生产图入口仍是：

```text
START -> initSession -> operationWorkflow 或 statusReport -> END
```

真实运行可能产生草案和计费，应只在独立测试数据库副本上执行。正式内容仍必须经过 `ReviewArtifact -> 用户确认 -> Core API 应用`。

生产模型与工具错误应按 task/run 查询 Agent 服务日志与人工日志的 `model_failure`／`diagnostic` 区块，V2 使用
run/step 服务诊断。HTTP 错误及 HTTP 200 的无效参数/响应、授权和计费失败均按
[完整失败诊断规格](specs/2026-10-07-complete-failure-diagnostics.md)保留脱敏载荷、预期 Schema、
全部校验原因与异常链；Studio 图状态和公共失败消息不携带详情，不能替代实际日志。
