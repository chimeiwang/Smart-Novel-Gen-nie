# 人工工作流日志格式

本日志用于直接阅读一次 LangGraph 写作任务的真实执行过程，不以机器审计为主要目标。

## 人工入口

```text
logs/workflow-events/runs/YYYY-MM-DD/<task短号>.log
```

同一 `WritingTask` 的首次执行和后续 resume 按实际发生时间连续追加。每次运行只写一次任务类型等固定上下文，后续事件不重复长 ID 和固定 metadata。

文件按发生顺序包含：

1. 工作流开始、完成、中断或失败。
2. 完整可序列化 LangGraph 初始状态。
3. LangGraph 节点完成顺序、关键状态前后差异和节点返回的完整 state patch。
4. Agent 开始、完成和调用顺序。
5. 实际发送给 LLM 的完整 messages 和 tools。
6. LLM 返回的正文、供应商实际返回的 reasoning 和 tool calls。
7. 每次 LLM 响应的输入、输出、缓存命中和总 token 数。
8. 每个工具的完整解析参数和完整返回结果。

人工日志不记录 token chunk、`on_chain_*`、Runnable、checkpoint namespace 等底层包装事件。callback、函数、循环引用和 `UntrackedValue` 的 `novelData` 属于 runtime-only 数据，会显式标记后排除；普通 tracked state、正文、LLM 内容和工具结果不得静默截断。

## 配置

```bash
WORKFLOW_EVENT_LOG_ENABLED=true
LLM_LOG_MODE=full
WORKFLOW_EVENT_LOG_DIR=/absolute/path/to/workflow-events
```

- `WORKFLOW_EVENT_LOG_ENABLED=true`：生成统一人工工作流日志。
- `LLM_LOG_MODE=full`：保证日志包含 LLM 输入、输出和工具内容原文。`summary` 不能满足人工还原调用过程的要求。
- `WORKFLOW_EVENT_LOG_DIR`：覆盖默认目录。
- `LLM_SPLIT_LOG_ENABLED=false`：有 `taskId` 的 Agent LLM 只写统一工作流日志，不再重复生成 `logs/llm/runs`、`logs/llm/tasks` 和每日索引。设为 `true` 才恢复旧分片。

`logs/app-YYYY-MM-DD.log` 只记录应用运行、错误和 SSE 等普通程序日志。没有 `taskId` 的独立 LLM 调用无法归入某个工作流，仍会写入 `logs/llm` 作为兜底。

## 可选机器审计

机器 JSONL 与人工日志分离，默认关闭：

```bash
WORKFLOW_MACHINE_EVENT_LOG_ENABLED=false
WORKFLOW_EVENT_DEBUG_ENABLED=false
```

只有显式设置 `WORKFLOW_MACHINE_EVENT_LOG_ENABLED=true` 才会继续写入 `workflow-events-YYYY-MM-DD.jsonl`。`/debug/workflow-events` 依赖这些 JSONL，不是人工排查入口。

## 示例

```text
====================================================================================================
工作流运行
开始时间: 2026-07-03T01:02:03.004Z
任务: p9j1s | 类型: writing-workflow
阅读顺序: LangGraph 状态 → 节点 → Agent → LLM 输入/输出 → 工具输入/返回。
====================================================================================================

#0002 ... LANGGRAPH 初始状态
  【完整 GraphState】
  { ... }

#0003 ... LANGGRAPH 节点 #1 完成：initSession
  状态变化：...
  【节点返回的完整 state patch】
  { ... }

#0004 ... AGENT 调用 #1 开始：写作

[01:02:04.123] 第 1 轮 LLM 输入 >>>
【发送给模型的消息原文】
...

[01:02:06.456] 第 1 轮 LLM 输出 <<<
Token 消耗: 输入 1200 | 输出 300 | 缓存 800 | 合计 1500
【模型正文原文】
...

[01:02:06.789] 第 1 轮 工具 1/1：get_outline
【工具输入原文 >>>】
...
【工具返回原文 <<<】
...
```
