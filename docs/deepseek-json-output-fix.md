# DeepSeek JSON 输出格式修复方案

> 状态：历史方案，已废弃 | 日期：2026-06-09
>
> 当前代码不再修补 DeepSeek JSON 信封输出，而是改为 Markdown 正文 + OpenAI tool_calls control tools。不要按本文继续增强 JSON 输出方案。

## 问题背景

### 现象

用户在智能写作面板中使用设定顾问（@设定）时，Agent 流式输出过程中能看到内容逐渐出现，但 `agent_done` 事件后**内容消失或显示不完整**。用户反馈："设定顾问输出了这么多，就没有了"。

### 根因分析

完整链路追踪如下：

```
LLM 输出 JSON
  → extractJsonObject() — JSON.parse 失败（特殊字符未正确转义）
  → parseAgentResponse() — 回退策略：rawContent 直接当 content
  → SSE agent_done — 发送原始 JSON 字符串
  → 前端 extractDisplayContent() — 再次 JSON.parse 失败 → 截断
  → 最终展示：空或乱码
```

**根本原因**：DeepSeek 在输出含超长 Markdown 正文的 JSON 时，`content` 字段内的特殊字符（字面换行 `\n`、双引号 `"`、反斜杠 `\`）未按 JSON 标准正确转义。例如：

```json
// 模型可能输出（不合法 JSON）：
{
  "content": "修改总览

| 修改项 | 涉及章节 |
| ① 真相碎片提前 | 第一章",
  "updates": null
}

// 正确应该是：
{
  "content": "修改总览\n\n| 修改项 | 涉及章节 |\n| ① 真相碎片提前 | 第一章",
  "updates": null
}
```

### 关键约束

1. **`response_format: json_object` 与 `tools` 的关系待验证**：OpenAI 禁止同时使用，DeepSeek 文档未明确声明冲突
2. **`response_format: json_schema`**（OpenAI 的 Structured Output）：DeepSeek **不支持**，请求会被拒绝
3. **设定顾问必须使用 tools**（11 个数据库查询工具），无法去掉
4. **项目只接入 DeepSeek**，所有优化围绕 DeepSeek 进行

### 涉及文件

| 文件 | 角色 |
|------|------|
| `src/agents/lib/llm-wrapper.ts` | `callLLMWithTools()` — 工具调用循环，当前 `reasoning_effort: "medium"`，无 `response_format` |
| `src/agents/graph/schemas.ts` | `extractJsonObject()` — JSON 提取，三步回退（code block → JSON.parse → `{...}` 截取） |
| `src/agents/graph/response-parser.ts` | `parseAgentResponse()` — Zod 校验失败后回退为 rawContent |
| `src/features/writing/writing-conversation.tsx` | `extractDisplayContent()` — 前端二次 JSON 提取 |

## DeepSeek 能力分析

### 相关 API 能力

| 能力 | DeepSeek | 说明 |
|------|----------|------|
| `response_format: json_object` | ✅ 支持 | 要求 prompt 中含 "json" 字样 |
| `response_format: json_schema` | ❌ 不支持 | 请求会被拒绝 |
| Tool Calls | ✅ 支持 | 标准 function calling |
| 思考模式 (V3.2+) | ✅ 支持 | `reasoning_effort` 参数 |
| 思考模式 + 工具调用 | ✅ 支持 | V3.2 开始支持 |
| strict 模式 (Beta) | ✅ 支持 | `/beta` 端点，工具参数 schema 强制 |
| **json_object + tools 共存** | **待验证** | 文档未声明冲突 |

### DeepSeek 思考模式的核心价值

DeepSeek 的思考模式天然提供 **"想"和"写"的分离**：

```
┌─ reasoning_content（思考阶段）──────────────────┐
│ 模型深度思考、调用工具、分析结果                    │
│ → "我需要先查纪寻的设定，再看玄天宗的背景..."      │
│ → tool_call: get_character_detail("纪寻")        │
│ → tool_call: get_faction_detail("玄天宗")        │
│ → "综合分析完毕，可以写回复了"                     │
└─────────────────────────────────────────────────┘
┌─ content（输出阶段）─────────────────────────────┐
│ 最终回复，应该是干净的 JSON 格式                    │
│ { "content": "...", "insights": [...], ... }    │
└─────────────────────────────────────────────────┘
```

利用这个特性，模型在思考阶段完成所有"脏活"（查询、分析），输出阶段只做"呈现"（格式化 JSON）。如果再加上 `response_format: json_object`，可以从 API 层面保证输出合法性。

## 方案设计

### 方案 A：json_object + tools 共存（最小改动）⭐ 首选

**前提**：验证 DeepSeek 是否允许 `response_format: json_object` 与 `tools` 同时使用。

**改动**：在 `callLLMWithTools` 中加两行：

```typescript
// src/agents/lib/llm-wrapper.ts l.587-595
const completionParams = {
  model: config.model,
  messages,
  tools: options.tools,
  tool_choice: "auto",
  stream: true,
  max_tokens: MAX_OUTPUT_TOKENS,
  reasoning_effort: "high",                              // ← medium → high
  response_format: { type: "json_object" as const },     // ← 新增
};
```

**优点**：
- 一行代码改动
- API 级保证 JSON 合法，彻底消除解析失败
- `reasoning_effort: "high"` + `json_object` — DeepSeek 思考模式下"想清楚再写对"
- 不增加额外 LLM 调用

**缺点**：
- 依赖 DeepSeek 的兼容行为（需要先验证）
- 如果 DeepSeek 后续版本对齐 OpenAI 限制，可能需要回退

**验证脚本**：

```javascript
// 最小验证：发一个带 tools + json_object 的请求，看 API 是否接受
const response = await client.chat.completions.create({
  model: "deepseek-v4-pro",
  messages: [
    { role: "system", content: "返回 JSON 格式的回复。用 get_weather 工具查天气。" },
    { role: "user", content: "北京天气怎么样？" }
  ],
  tools: [{ type: "function", function: { name: "get_weather", ... }}],
  response_format: { type: "json_object" },
  reasoning_effort: "high",
});
```

### 方案 B：思考模式两阶段（DeepSeek 原生优化）

**场景**：如果方案 A 冲突（json_object + tools 不能共存）。

```
Phase 1: 思考 + 工具查询                     Phase 2: 格式化输出
┌──────────────────────────────┐          ┌──────────────────────────┐
│ reasoning_effort: "high"     │          │ reasoning_effort: "low"  │
│ tools: [全部工具]             │    →     │ response_format: json_obj│
│ stream: true（展示思考过程）   │          │ tools: []（不传工具）     │
│                              │          │                          │
│ 模型深度思考、调用工具、分析   │          │ 基于 Phase 1 的分析结果   │
│ 流式输出 reasoning_content   │          │ 专心格式化 → 100%合法JSON │
└──────────────────────────────┘          └──────────────────────────┘
```

**改动**：`callLLMWithTools` 在工具循环结束后，不直接返回文本，而是追加一次 `callLLM`：

```typescript
// 工具调用循环结束后
if (allToolCallsResolved) {
  // 追加格式化指令
  messages.push({
    role: "user",
    content: "请基于以上所有工具查询结果，按照要求的 JSON 格式输出最终响应。"
  });
  
  // 第二阶段：纯格式化（无 tools，有 json_object）
  return callLLM({
    messages,
    onChunk: options.onChunk,
    metadata: options.metadata,
    // 内部使用 reasoning_effort: "low" + response_format: json_object
  });
}
```

**优点**：
- 100% 可靠（不依赖 DeepSeek 兼容行为）
- 职责彻底分离：思考阶段做分析，输出阶段做格式
- Phase 2 的 `reasoning_effort` 可以设为 `"low"`，几乎没有额外成本
- 完全围绕 DeepSeek 思考模式设计

**缺点**：
- 多一次 LLM 调用（~1-2 秒）
- 代码改动量中等

### 方案 C：JSON repair 兜底（防守型）

作为方案 A/B 的补充，在 `extractJsonObject()` 中增加 JSON 自动修复：

```typescript
// 在 JSON.parse 之前先 repair
import { repairJson } from "json-llm-repair"; // LLM 专用修复库

function extractJsonObject(text: string): Record<string, unknown> | null {
  const cleaned = text.trim();
  
  // 新增：repair 后解析
  try {
    return JSON.parse(repairJson(cleaned));
  } catch { /* 继续现有逻辑 */ }
  
  // ... 现有三步回退 ...
}
```

**优点**：改动极小，独立于 API 行为
**缺点**：纯规则修复，不能保证 100% 成功率

## 推荐实施路径

```
第一步：写验证脚本，测试 json_object + tools + reasoning_effort:"high"
   ├─ 成功 → 实施方案 A（一行代码）
   └─ 失败 → 实施方案 B（两阶段）
   
第二步（可选）：方案 C 作为兜底，追加 JSON repair
```

## 业界参考

| 方案 | 代表 | 适用场景 |
|------|------|---------|
| API 级约束 | OpenAI Structured Outputs、DeepSeek json_object | 首选，源头保证 |
| 两阶段分离 | LangChain `AgentExecutor` + `OutputParser` | tools 冲突时 |
| JSON repair 库 | `json-llm-repair`（npm，LLM 专用） | 兜底防御 |
| LLM 自修复 | LangChain `OutputFixingParser` | 复杂错误，成本高 |
| 协议分离 | Vercel AI SDK `streamText` + `onFinish` | 大重构 |

## 与本次数据迁移的关系

本次 SQLite → PostgreSQL 迁移后发现的问题链：

```
1. 数据迁移完成 → Novel、Character、Outline 等入库 ✅
2. 用户进入工作台 → userId 不匹配 → 404 ❌ → 修复 ✅
3. Chapter 未迁移 → 空白页 ❌ → 修复 ✅
4. 用户使用设定顾问 → 输出内容丢失 ❌ → 本文档分析中
```

问题 1-3 已修复，问题 4 由本文档给出方案。

## 相关文件

- `docs/deepseek-json-output-fix.md` — 本文档
- `scripts/migrate-sqlite-to-pg.mjs` — 数据迁移脚本
- `src/agents/lib/llm-wrapper.ts` — LLM 调用封装（主要改动文件）
- `src/agents/graph/schemas.ts` — JSON 提取逻辑
- `src/agents/graph/response-parser.ts` — Agent 响应解析
