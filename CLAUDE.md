# CLAUDE.md

本文件为 Claude Code (claude.ai/code) 在本仓库中工作时提供指导。

**重要：后续所有对话必须使用简体中文进行。**

## 需求追溯系统

所有功能需求沉淀在 `docs/requirements/`，代码通过 `// @X.X` 标注所属需求。AI 负责维护需求文档与代码的一致。

### 编号规则

`大类.子功能` — 如 `5.1`（Agent核心编排）、`3.1`（AI续写）。主索引见 `docs/REQUIREMENTS.md`。

### 代码注释

格式：`// @X.X` 或 `// @X.X — 说明`。标注在**函数/逻辑块**上，不标在文件头。

**粒度规则**：
- 函数 ≤100 行 → 函数头标注
- 函数 >100 行且被 ≤2 个需求使用 → 函数头标注
- 函数 >100 行且被 >2 个需求使用 → 内部按逻辑块标注 `// @X.X: 块描述`

**使用关系**：共享函数标注被哪些需求调用，如 `// @5.2 — 被 @5.5 @5.6 @5.7 @5.8 @5.9 调用`

### 需求文件格式

`docs/requirements/X.X-slug.md`，版本倒序（最新在最前），只保留：状态、版本历史、代码列表、注意事项。模板见 `docs/requirements/REQ-TEMPLATE.md`。

### 修改流程

```
用户指令
  ↓
1. 理解意图 → 找到要改的代码
  ↓
2. 从代码中的 @X.X → 找到所属需求文件
  ↓
3. 更新需求文件：状态 + 新增版本条目 + 变更说明
  ↓
4. 修改代码
  ↓
5. 如果影响到其他 @X.X 的代码 → 同步更新对应需求文件
  ↓
6. 用户确认 → commit & push
```

**新功能流程**：先在 `docs/REQUIREMENTS.md` 分配编号 → 创建需求文件 → 写代码时标注 `@X.X`。

## 项目概述

InkForge（墨铸）是一款面向中文小说作者的本地优先智能创作工具。帮助作者管理小说、章节、设定、大纲、剧情进度、参考资料和文风，并提供 AI 续写能力。

## 常用命令

```bash
npm run dev          # 启动开发服务器
npm run build        # 构建生产版本
npm run lint         # 运行 ESLint 检查
npm run typecheck    # 运行 TypeScript 类型检查
npm run db:generate  # 生成 Prisma Client
npm run db:migrate   # 运行 Prisma 数据库迁移
```

## 技术栈

- Next.js 16 + App Router
- TypeScript（strict 模式）
- Prisma + SQLite 本地数据库
- OpenAI SDK（兼容 API）用于 AI 集成
- 原生 CSS + CSS 自定义属性（无 Tailwind）
- React Markdown 用于预览

## 目录结构

```
src/
├── app/                    # Next.js App Router 页面与服务端操作
│   ├── actions.ts          # 所有服务端操作（"use server"）
│   ├── page.tsx            # 首页（项目列表）
│   └── workspace/[novelId] # 主创作工作台
├── features/               # 功能组件
│   ├── chapters/           # 章节列表侧边栏
│   ├── editor/             # Markdown 编辑器（含自动保存）
│   ├── lore/               # 设定面板
│   ├── outline/            # 大纲面板
│   ├── progress/           # 剧情进度面板
│   ├── references/         # 参考资料面板
│   ├── styles/             # 文风面板
│   └── workspace/          # 右侧检查器 Tab 容器
├── shared/
│   ├── db/prisma.ts        # Prisma 单例（防止开发环境重复实例）
│   ├── env.ts              # AI 配置读取
│   └── lib/
│       ├── ai.ts           # AI 服务（文风提取、续写生成）
│       └── word-count.ts   # 中文字数统计
```

## 关键模式

- **服务端操作**：所有数据变更使用 `"use server"`，集中在 `src/app/actions.ts`
- **路径别名**：`@/*` 映射到 `./src/*`
- **无全局状态库**：使用服务端数据 + 组件本地状态
- **Prisma 单例**：使用 globalThis 模式防止开发环境热更新时重复创建客户端
- **前端设计规范**：新增或修改前端 UI、组件、CSS、交互状态前，必须先阅读并遵守根目录 `DESIGN.md`。整体方向以 Linear 为主参考、Vercel 为辅助参考，服务 InkForge（墨铸）的中文长篇写作工作台。
- **CSS 规范**：使用原生 CSS + 自定义属性，定义在 `globals.css`。优先使用已有类（`.panel`、`.stack`、`.button`、`.badge` 等），避免新增；新增视觉方案必须符合 `DESIGN.md`。
- **无响应式设计**：本项目仅针对 PC 端，不需要响应式适配（不写 media query、不考虑移动端）。不同屏幕尺寸通过 CSS minmax 和 flex 自适应处理。

## AI 集成

环境变量配置（`.env`）：
```
OPENAI_API_KEY=your_key
OPENAI_BASE_URL=https://api.deepseek.com/v1
OPENAI_MODEL=deepseek-v4-flash
```

使用 OpenAI 兼容 API 格式，默认接入 DeepSeek。未配置 `OPENAI_API_KEY` 时，AI 功能返回 Mock 响应。

## 数据模型（Prisma）

- **Novel**：小说项目，包含章节、设定、大纲、剧情进度、参考资料、应用的文风
- **Chapter**：章节，含标题、内容、排序
- **LoreEntry**：设定条目（角色、地点、物品、技能）
- **Outline/OutlineNode**：大纲与大纲节点，支持层级结构
- **PlotProgress**：剧情进度（当前阶段、目标、冲突、里程碑）
- **ReferenceMaterial**：参考资料
- **WritingStyle**：文风（样本文本 + 提取的文风画像）
- **StyleExtractionTask**：文风提取任务记录

## 产品说明

- 中文界面与内容
- Markdown 优先编辑，实时预览
- 自动保存（1.2 秒防抖延迟）
- 字数统计去除空白字符（中文计字方式）
- 文风在独立 `/styles` 页面管理，小说内仅选择和应用文风

## Agent 模块

所有 Agent 位于 `src/agents/` 目录，统一从 `src/agents/index.ts` 导出。

**重要规则**：`src/agents/AGENTS.md` 是 Agent 流程图的文档，**每次修改 Agent 流程后必须更新该文档**。

### v5.2 四Agent架构（工具调用 + 分层上下文 + 智能路由）

Agent 系统基于 **@langchain/langgraph** 的 StateGraph 实现多 Agent 协作编排。v5.2 核心升级：启用 `callLLMWithTools`、分层上下文、LLM 智能路由、JSON 结构化输出。

```
src/agents/
├── lib/
│   ├── llm-wrapper.ts           # LLM 调用封装（callLLM / callLLMWithTools）
│   ├── langsmith-tracer.ts      # LangSmith 追踪
│   └── tools.ts                 # Agent 工具定义（按角色分组）
│
├── graph/
│   ├── state.ts              # WritingState 类型 + AgentInsight/ProactiveSuggestion
│   ├── context-manager.ts    # 对话历史管理器
│   ├── context-builder.ts    # 分层上下文构建（index/minimal/full 三种模式）
│   ├── response-parser.ts    # 统一 JSON 响应解析（v5.2 新增）
│   ├── executor.ts           # StateGraph + LLM 意图分类 + SSE 流式输出
│   └── nodes/
│       ├── index.ts          # 统一导出
│       ├── lore-advisor-node.ts    # 设定顾问（★工具调用）
│       ├── plot-advisor-node.ts    # 剧情顾问（★工具调用）
│       ├── author-node.ts          # 作家（★JSON输出+流式）
│       └── validator-node.ts       # 校验员（★工具调用）
│
├── portrait-agent-stream.ts  # 文风画像流式生成
├── types.ts                 # Agent 公共类型
├── registry.ts              # Agent 元信息注册表
├── client.ts               # 客户端安全导出
└── index.ts                # 统一导出
```

### v5.2 关键设计决策

1. **工具调用**：设定顾问、剧情顾问、校验员使用 `callLLMWithTools`，Agent 按需查询数据
2. **分层上下文**：设定/剧情顾问使用 `buildContextIndex()`（~200 token），作家/校验员使用完整上下文
3. **智能路由**：`@Agent` 前缀快速匹配 + LLM 意图分类回退，confidence < 0.7 回退 statusReport
4. **JSON 输出**：所有 Agent 统一输出 JSON（content + wantsToCall + insights + proactiveSuggestions）
5. **回退兼容**：JSON 解析失败时自动回退到原有正则/字符串匹配

### 已完成 Agent 列表（v5.2 四Agent + 工具调用）

| Agent ID | Node 文件 | 功能简介 | LLM 调用方式 |
|---------|----------|---------|------------|
| 设定 | nodes/lore-advisor-node.ts | 设定顾问，通过 11 个工具查询设定，JSON 输出 | callLLMWithTools |
| 剧情 | nodes/plot-advisor-node.ts | 剧情顾问，通过 9 个工具查询大纲/伏笔，JSON 输出 | callLLMWithTools |
| 写作 | nodes/author-node.ts | 作家，JSON 输出 + 流式生成 | callLLM（流式） |
| 校验 | nodes/validator-node.ts | 校验员，通过 7 个工具校验一致性，JSON 输出 | callLLMWithTools |
| PortraitAgentStream | portrait-agent-stream.ts | 文风画像生成（流式版） | callLLM（流式） |

### Agent开发规范（v5.2）

1. **每个 Agent 独立一个文件**：命名格式 `nodes/xxx-node.ts`
2. 文件顶部必须包含完整的 JSDoc 注释
3. 设定/剧情/校验 Agent 使用 `callLLMWithTools` + `buildContextIndex()` 分层上下文
4. 作家 Agent 使用 `callLLM`（流式）+ `buildNovelContext()` 完整上下文
5. 所有 Agent 输出统一使用 `parseAgentResponse()` 解析（JSON 优先，回退正则）
6. 新 Agent 完成后：
   - 在 `src/agents/graph/nodes/index.ts` 添加导出
   - 在 `src/agents/graph/state.ts` 的 `CORE_AGENT_IDS` 中添加 ID
   - 在 `src/agents/graph/executor.ts` 的 `importAgentNode` 中添加路由
   - 在 `executor.ts` 的 `buildGraph()` 中注册节点和边
   - 在 `AGENTS.md` 的 Agent 列表和流程图中添加
   - 在 `CLAUDE.md` 本节的「已完成 Agent 列表」添加一行

### 智能写作系统（v5.2 StateGraph 协作模式）

智能写作功能基于 4 个核心 Agent 协作，通过 LangGraph StateGraph 编排。用户通过 `@xxx` 或自然语言直接调用指定 Agent（LLM 智能路由）。

**图结构**：
```
START → initSession → [LLM分类/关键词路由] → Agent节点 → processResult → [条件路由] → END
```

**核心设计**：

- **工具调用**：设定/剧情/校验 Agent 通过 `callLLMWithTools` 按需查询数据，而非被动接受全部上下文
- **分层上下文**：`buildContextIndex()`（~200 token）替代 `buildNovelContext()`（~5000 token）用于查询型 Agent
- **对话历史机制**：所有 Agent 输出由 `processResult` 节点统一追加到 `conversationHistory`
- **Agent 间调用协议**：Agent 输出 JSON 中的 `wantsToCall` 字段，由 `processResult` 节点处理路由
- **调用链深度限制**：最大 5 层，通过 `callChainDepth` 状态字段跟踪
- **主动智能**：Agent 通过 `insights` 发现缺口/矛盾，通过 `proactiveSuggestions` 建议下一步

**指令路由**：

| 用户输入 | 调度的Agent |
|---------|-----------|
| `@设定` | 设定顾问 |
| `@剧情` | 剧情顾问 |
| `@写作` | 作家 |
| `@校验` | 校验员 |
| 其他 | 输出状态报告 |

**Agent间协作示例**：

```
用户: @写作 生成第一章结尾
  ↓
作家生成正文
  ↓
作家输出 wantsToCall: "校验"
  ↓
executor 自动调用校验员
  ↓
校验员发现冲突 → wantsToCall: "写作"
  ↓
executor 自动调用作家重写
  ↓
作家重写 → 再次校验 → 通过
```

**API 端点**：

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/writing/session` | POST | 启动新会话 |
| `/api/writing/resume` | POST | 继续被中断的会话（含对话历史） |

**v5.2 SSE 事件**：

| 事件 | 说明 |
|------|------|
| `intent_classified` | LLM 分类用户意图 |
| `proactive_suggestions` | Agent 主动建议下一步 |
| `agent_insights` | Agent 发现设定缺口/矛盾 |
| `agent_status: querying` | Agent 正在调用工具 |

### LangSmith 监控（GraphOS Dashboard）

项目集成了 LangSmith 进行 Agent 执行监控，便于调试和性能分析。

**配置步骤**：

1. 在 `.env` 中添加 LangSmith API Key：

```bash
LANGCHAIN_API_KEY="your_langsmith_api_key"
LANGCHAIN_PROJECT="inkforge"
LANGCHAIN_TRACING_V2="true"
```

2. 访问 [LangSmith Dashboard](https://smith.langchain.com/) 查看追踪数据

**追踪内容**：

- 工作流执行（writing-workflow, resume-writing-workflow）
- Agent 节点执行（设定顾问、剧情顾问、作家、校验员）
- LLM 调用（token 使用、响应时间）
- 错误和异常

**查看方法**：

- 打开 LangSmith Dashboard
- 选择项目 `inkforge`（或你设置的项目名）
- 在 Traces 页面查看所有执行记录
- 使用过滤条件查找特定任务或 Agent

## 重构心得（2026-05-09 v5.0 重构）

本次重构是一次深度代码审阅的产物，以下是关键心得，供后续开发参考。

### 1. 名实相符是底线

项目自称使用 LangGraph，但代码中完全没有 `StateGraph`、`Annotation`、`.addNode()`、`.compile()` 等 LangGraph API，只是手动 switch-case 递归调度。命名和文档会塑造团队的认知 — 如果名不副实，新人会困惑，老人会误判能力边界。

**教训**：用了什么就说用什么。引入 LangGraph 就要 `StateGraph` + `Annotation.Root` + `conditionalEdges` 全套。图结构从函数调用变成了静态声明的节点和边，路由逻辑从递归变成了条件判断返回值，这才是真正的图执行。

### 2. 重复代码是最大的技术债

四个 Agent Node 各有约 200 行完全相同的上下文构建代码，逐字段遍历 characters → factions → locations → items → glossaries → outlines → foreshadowings → references。数据模型每次调整都要同步改四处，必然会遗漏。

**教训**：当你第三次写出相似代码时，就该抽取共享函数。`context-builder.ts` 的 `buildNovelContext(novelData, options?)` 一次消除了约 800 行重复，options 参数让每个 Agent 只拿自己需要的段。

### 3. 类型定义只能有一个数据源

`types.ts` 和 `state.ts` 各自定义 `CharacterData`、`ItemData` 等十多个相同名称的类型，但字段细节不同（`state.ts` 比 `types.ts` 多了 powerLevel、combatAbility 等字段）。这导致 `tools.ts` 中的类型错误长期存在。

**教训**：所有数据模型类型统一放在 `state.ts`，`types.ts` 只保留 Agent 特有的元类型（`AgentMeta`、`AgentContext`、`AgentResult`）并通过 re-export 暴露数据模型。遵循"单一数据源"原则。

### 4. 死代码要果断删除

旧版 10 个 Agent（host-agent、writer-agent 等）和 2 个废弃 API 路由仍然在 `index.ts` 中导出，但没有任何外部使用者。维持它们会让新开发者困惑"到底该用哪个"，也产生无谓的维护负担。

**教训**：先 grep 确认零引用，然后删除。代码库越小越清晰。本次删除了 15 个文件。

### 5. 图执行需要专门的"处理"节点

用 LangGraph 重写 executor 时，最大的设计决策是引入 `processResult` 节点。Agent 节点只负责调用 LLM 并返回结果，`processResult` 统一负责：

- 将 Agent 输出追加到 `conversationHistory`
- 检查 `wantsToCall` 并设置 `nextAgent`
- 管理 `callChainDepth` 防止死循环

这样 Agent 节点职责单一，调用链逻辑集中管理，条件路由只需查 `nextAgent` 即可。

### 6. SSE 事件传递和状态绑定更安全

v5.0 在 Annotation 中增加了 `sseEvents` 字段，节点通过返回 `{ sseEvents: [...] }` 声明要发送的 SSE 事件。SSE 发送逻辑完全解耦 — 节点不直接操作 `controller`，只声明要发什么事件，外层 `streamEvents` 循环统一处理。这避免了图节点中持有外部引用的问题。

### 7. 审阅应先于修改

本次变更的顺序是：先完整审阅找出所有问题 → 排序严重程度 → 按依赖关系逐步执行。最小的改动（提取共享函数）先做，最大的改动（引入 LangGraph）最后做，每一步都跑类型检查。不要试图一步到位。
