# LangGraph Studio 接入说明

本文档说明 InkForge（墨铸）如何接入 LangGraph Studio 做本地可视化调试。

## 启动 Studio

```bash
npm run studio:dev -- --no-browser --port 2024
```

启动成功后终端会输出：

```text
API: http://localhost:2024
Studio UI: https://smith.langchain.com/studio?baseUrl=http://localhost:2024
```

打开 Studio UI 后选择 `novel_writer` 图。

## 图入口

Studio 配置文件：

```text
langgraph.json
```

图导出文件：

```text
src/agents/graph/studio-app.ts
```

该入口只导出 `getGraph()` 的 compiled graph，不新增平行编排。Studio 看到的是现有：

```text
START → initSession → operationWorkflow/statusReport → END
```

## 生成运行输入

Studio 直接运行图时需要完整 `GraphState`。使用脚本基于真实小说和章节生成输入：

```bash
npm run studio:input -- \
  --novel-id <novelId> \
  --chapter-id <chapterId> \
  --user-id <userId> \
  --message "继续写本章"
```

脚本会：

- 校验 `novel.userId` 归属。
- 复用 `aggregateNovelContextLightweight()` 聚合上下文。
- 创建一条调试用 `WritingTask`。
- 输出可粘贴到 Studio 的完整 JSON state。

可选参数：

```bash
--target-word-count 1200
```

## 副作用边界

Studio 运行会真实执行 Graph 节点，因此可能产生这些副作用：

- 创建或更新 `WritingTask`。
- 创建或更新 `ReviewArtifact`、revision、evaluation。
- 在审核通过后进入 LangGraph `interrupt()`，等待用户决策。

正式章节正文仍不会被 Agent 直接写入。正文、设定、大纲等正式落库仍必须经过：

```text
ReviewArtifact → 用户确认应用 → applyReviewArtifact()
```

## 和本地 workflow event 日志的分工

LangGraph Studio 适合调试：

- 图结构。
- 节点执行路径。
- State patch。
- interrupt/resume。
- LangSmith trace。

`/debug/workflow-events` 和 `logs/workflow-events/*.jsonl` 继续用于调试：

- Next API/SSE 端到端事件。
- 前端实际收到的事件。
- 本地持久化副作用。
- 一次真实写作请求的回放审计。

两者互补，不互相替代。

## 常用命令

```bash
npm run studio:dev
npm run studio:dev -- --no-browser --port 2024
npm run studio:input -- --novel-id <id> --chapter-id <id> --user-id <id> --message "..."
npm run studio:build
```

## LangSmith Monitoring

Studio 入口 `src/agents/graph/studio-app.ts` 会在导出 graph 前初始化 LangSmith；因此 `npm run studio:dev` 不依赖 Next.js API 路由的 `initServer()`。

在 `.env` 中配置：

```bash
LANGSMITH_API_KEY="your_langsmith_api_key"
LANGSMITH_PROJECT="inkforge"
LANGSMITH_TRACING="true"
LANGCHAIN_API_KEY="your_langsmith_api_key"
LANGCHAIN_PROJECT="inkforge"
LANGCHAIN_TRACING_V2="true"
```

一次 Studio 调试运行应能在 LangSmith 中看到这些层级：

- `workflow:writing-workflow` 或 Studio 图运行的顶层 trace。
- `workflow:operation:<stage>`，例如 `operation:prepare_context`、`operation:execute_operation`、`operation:review_artifact`。
- `llm:<callType>`，来自 `AgentRuntimeImpl` 和普通 LLM wrapper。
- `tool:<toolName>`，来自 Agent 读取工具、proposal 工具等非 control tool 调用。

如果缺少 API key 或 tracing 变量不是 `true`，系统会继续本地运行，但不会上报 LangSmith trace。

