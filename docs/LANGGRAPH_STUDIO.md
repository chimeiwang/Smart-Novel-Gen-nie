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
