# 人工工作流日志格式

本文件描述当前人工可读工作流日志。机器审计日志、调试 API 和旧分片 LLM 日志不属于人工主入口。

铁律：日志文档必须服从当前 `src/agents/graph/workflow-event-log.ts` 和运行输出事实；若实现变化，先核对代码再修正文档。

## 人工入口

```text
logs/workflow-events/runs/YYYY-MM-DD/<task短号>.log
```

同一 `WritingTask` 的首次执行和后续 resume 追加到同一文件。审批、丢弃等既没有 LLM 调用也没有 LangGraph 状态变化的短路操作，不创建空壳人工日志。

## 当前结构

每个运行区块只保留两类记录：

1. **LLM 完整请求/返回**
   - 按 Agent 调用编号分组，例如 `A01`。
   - 包含发送给模型的完整 messages、工具定义、模型正文、供应商返回的 reasoning、tool calls。
   - 包含工具解析参数和完整工具返回。
   - 同一模型轮次内并行安全工具完成后，仍按模型声明顺序写入。

2. **LangGraph 中文状态切换**
   - 按状态编号排列，例如 `S001`。
   - 记录节点名、阶段、关键字段和枚举值的中文含义。
   - 用于确认 operationWorkflow 的真实推进顺序。

人工日志不再写入：

- Workflow/SSE 事件 JSON；
- 完整 GraphState/raw patch；
- 独立状态索引；
- Agent 最终汇总重复层；
- token stream；
- Runnable / callback / checkpoint metadata；
- 需要跨文件关联的 task index 或 LLM index。

## 配置

```bash
WORKFLOW_EVENT_LOG_ENABLED=true
WORKFLOW_EVENT_LOG_DIR=/absolute/path/to/workflow-events
WORKFLOW_MACHINE_EVENT_LOG_ENABLED=false
```

- `WORKFLOW_EVENT_LOG_ENABLED=true`：生成人工日志。
- `WORKFLOW_EVENT_LOG_DIR`：覆盖默认日志目录。
- `WORKFLOW_MACHINE_EVENT_LOG_ENABLED=true`：额外生成机器 JSONL，默认关闭。

`logs/app-YYYY-MM-DD.log` 只记录应用运行、错误和普通程序日志。没有 `taskId` 的独立 LLM 调用不能归入某个工作流时，才使用 `logs/llm` 兜底。

## 阅读顺序

1. 先看运行区块标题，确认 task 短号和时间。
2. 再看 `Sxxx` 状态切换，确认 Graph 走到哪个阶段。
3. 最后看对应 `Axx` Agent 调用里的 LLM 输入、输出和工具结果。

如果日志和代码行为冲突，以代码和实际日志文件为准，更新本文。
