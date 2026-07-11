# 人工工作流日志格式

当前实现位于 `apps/agent-service/src/inkforge_agents/observability/`。Agent Service 把日志写入 `/data/agent-logs`，Compose 使用 `agent_logs` 命名卷持久化；Core API 通过签名内部接口按用户归属读取，浏览器不能直接访问 Agent Service。

## 文件与追加规则

文件名由运行标识的安全哈希生成，禁止把任务标识直接拼接为路径。同一任务首次执行和恢复运行追加到同一文件。没有模型调用或图状态变化的短路操作不创建空日志。

每个运行区块只记录：

1. 实际发送给模型的完整 messages 和模型返回的完整正文；
2. 中文 LangGraph 状态切换、阶段和结束状态。

人工日志不记录 tools schema、供应商 reasoning、模型 tool_calls、工具参数、工具返回、完整运行时对象或底层 checkpoint metadata。禁止对已记录的正文、消息或状态进行静默截断。

## 配置

```bash
WORKFLOW_HUMAN_LOG_DIR=/data/agent-logs
WORKFLOW_EVENT_DEBUG_ENABLED=false
```

调试读取默认关闭。开启后，用户仍必须通过 Core API 浏览器鉴权和归属校验；Core 到 Agent 的读取请求还必须具有 `agent:debug:read` 服务权限。
