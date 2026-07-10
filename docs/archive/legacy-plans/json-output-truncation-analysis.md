> 状态：历史归档，不作为当前实现依据。当前事实以 `DOCS.md`、`AGENTS.md`、`src/agents/AGENTS.md`、代码和 schema 为准。

# JSON 输出截断问题深度分析

> 状态：历史分析 | 日期：2026-06-10
>
> 当前代码已迁移到 Markdown 正文 + OpenAI tool_calls control tools；服务端 JSON 信封解析主路径已删除。本文只用于解释当时问题，不作为当前实现计划。

## 问题本质

**用 JSON 包裹长篇 Markdown prose 是一个架构级别的矛盾。**

JSON 适合结构化短字段（数字、枚举、短标签），不适合包裹包含大量自然段落的创作正文。`content` 字段里动辄几百上千字，每出现一个字面换行、双引号或反斜杠，就必须按 JSON 标准正确转义。DeepSeek 没有 OpenAI 的 Structured Outputs（constrained decoding）机制兜底，在同时处理工具调用 + 长文输出时，转义失误是大概率事件。

这不是"模型不够好"的问题，是**选错了容器**。

## 完整链路

```
DeepSeek 流式输出 JSON（content 内特殊字符未正确转义）
  ↓
extractJsonObject() — schemas.ts
  三步全失败（代码块提取 → 直接 JSON.parse → {...} 截取）
  ↓
parseAgentResponse() — response-parser.ts
  Zod 校验失败 → 回退 rawContent（整坨原始 JSON 字符串）
  ↓
SSE agent_done → 前端收到原始 JSON 乱码
  ↓
extractDisplayContent() — writing-conversation.tsx
  再次 JSON.parse 失败 → 残片或空
  ↓
用户感知："流式过程中看到了内容 → 流式结束后消失了"
```

每一层都有回退，但每一层回退都在降级用户体验。防线的叠加不解决问题，只延缓了用户感知到问题的时间。

## 为什么已有 `callLLMStructured` 还是出问题

`callLLMStructured`（llm-wrapper.ts:377）有 `response_format: json_object`，能从 API 层面保证 JSON 合法性。但它**不带 tools**，只用在意向分类等场景。

真正出问题的**设定顾问、剧情顾问、校验员**走的是 `callLLMWithTools`（llm-wrapper.ts:587），这一行**没有** `response_format: json_object`——它只传了 `tools`。而 `json_object` + `tools` 能否共存，DeepSeek 文档未明确声明，**至今未验证**。

## mirawork-mono 是怎么做的

### 架构对比

| | txt (InkForge（墨铸）) | mirawork-mono |
|---|---|---|
| Agent 输出格式 | JSON 信封 `{"content": "...", "wantsToCall": "..."}` | 纯 Markdown 文本 |
| 工具调用 | JSON 字段 `wantsToCall` → 代码解析路由 | 原生 OpenAI `tool_calls` 协议 |
| Agent 间协作 | 同一 JSON 中的 `wantsToCall` + `callChainDepth` | 单 Agent 模型，不需要 |
| 内容展示 | JSON.parse → 提取 `content` → 失败回退 | 直接渲染，零中间解析 |
| 截断防护 | 多层 JSON 解析 + 多个回退分支 | 仅 UI 层 120K 字符截断 |

### 关键设计

mirawork-mono 的 Agent 输出就是 Markdown 文本。元数据（工具调用、下一步动作）走 OpenAI 原生的 `tool_calls` 通道，和 prose 输出**物理分离**。整个代码库搜不到 `response_format: json_object`、`json repair` 等关键词——不是它解决了 JSON 截断，而是它**从未制造这个问题**。

它的"防御"只有两个东西，而且都不涉及 JSON：

- `sanitizeAgentMessageForRenderer`（agent-message-sanitizer.ts）——清理 DSML 协议标记泄露，纯文本处理
- `truncateVisibleText`（contentTruncation.ts）——120K 字符 UI 截断，纯性能保护

### 为什么它可以不做 JSON

mirawork-mono 是一个**单 Agent 编码助手**。它不需要 Agent A 输出 `wantsToCall: "校验"` 来触发 Agent B——它的 Agent 通过原生的 `tool_calls` 调用 bash、read、write 等工具，工具有结果后模型继续推理。这就是标准的 OpenAI/Anthropic function calling 循环，是行业基础设施，成熟可靠。

txt 项目则不同——它是一个**多 Agent 创意写作系统**，需要设定顾问→校验员→作家的协作链。JSON 信封中的 `wantsToCall` 和 `callChainDepth` 是它自己发明的 Agent 路由协议。问题在于，这个协议和创作 prose 被塞进了同一个 JSON 对象。

## 建议路径

### 路径 1：修 JSON（治标）

按 `docs/deepseek-json-output-fix.md` 的方案 B 执行——工具调用循环结束后，追加一次轻量格式化调用（`reasoning_effort: "low"` + `response_format: json_object`，不带 tools）。

| 维度 | 评价 |
|------|------|
| 可靠性 | 高（API 级保证 JSON 合法） |
| 改动量 | 中等（~100 行，llm-wrapper.ts + schemas.ts） |
| 额外成本 | 每次工具调用后多 1 次 LLM 调用（~1-2 秒） |
| 能解决根本矛盾吗 | 不能。JSON 包裹 prose 的结构性矛盾依然存在 |

适合作为**短期修复**，快速止血。

### 路径 2：分离协议与内容（治本）

不要让 prose 穿过 JSON。两种实现方式：

**方式 A：元数据走 tool_calls**

```typescript
// 模型直接输出 prose，结构化意图通过 tool call 表达
// 模型输出:
//   content: "第一章写完了，现在需要检查设定一致性..."
//   tool_calls: [{ function: { name: "route_to_agent", arguments: '{"agent":"校验"}' } }]
```

把 `wantsToCall` 从 JSON 字段改成工具调用，由代码处理路由，prose 保持在 `content` 里自由流淌。

**方式 B：标记分隔符**

```
***CONTENT***
第一章写完了。现在需要检查设定一致性...

***META***
{"wantsToCall": "校验", "callReason": "..."}
```

prose 和元数据用约定标记分隔，各自独立解析，互不干扰。标记分隔符比 JSON 对特殊字符包容得多。

| 维度 | 评价 |
|------|------|
| 可靠性 | 彻底（prose 不再需要 JSON 转义） |
| 改动量 | 大（协议层、解析层、前端渲染全链路） |
| 额外成本 | 零（不增加 LLM 调用） |
| 能解决根本矛盾吗 | 能。不再把 prose 塞进 JSON |

适合作为**长期架构演进方向**。

### 路径 3：换模型（回避问题）

使用 OpenAI 的 Structured Outputs（constrained decoding）能从模型推理层面保证 JSON 合法性。但这意味着放弃 DeepSeek，引入新的成本和依赖。

不推荐。问题在架构选择，不在模型选择。

## 推荐策略

```
短期（本周）：
  → 验证 DeepSeek json_object + tools 是否共存
    → 可共存 → 方案 A（一行代码，最快）
    → 不可共存 → 方案 B（两阶段格式化，可靠）
  → + 方案 C（json-llm-repair 兜底，零风险）

中期（下个迭代）：
  → 评估路径 2 的改动范围
  → 优先考虑方式 A（元数据走 tool_calls），改动最小但效果最好

长期：
  → 彻底分离协议层与内容层
  → prose 不再经过 JSON
```

## 相关文件

- `docs/deepseek-json-output-fix.md` — 原始修复方案文档
- `docs/json-output-truncation-analysis.md` — 本文档
- `src/agents/lib/llm-wrapper.ts` — LLM 调用封装（`callLLMWithTools` 缺少 `response_format`）
- `src/agents/graph/schemas.ts` — JSON 提取 + Zod 校验
- `src/agents/graph/response-parser.ts` — Agent 响应解析 + 回退逻辑
- `src/features/writing/writing-conversation.tsx` — 前端 `extractDisplayContent`
- `~/mirawork-mono/` — 参考项目（mirawork-mono 不制造此问题的架构）
