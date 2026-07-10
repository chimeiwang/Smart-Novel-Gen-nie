# 文档规范与权威索引

本文件是仓库最外层的文档治理权威。任何新增、修改、删除文档都必须先遵守这里的规则。

铁律：**项目事实高于文档历史**。当文档与当前代码、schema、脚本或测试冲突时，以当前项目事实为准，先纠正文档，不能为了保留旧说法而扭曲实现。

需求铁律：**后续所有需求必须先写 spec，再执行修改**。spec 必须先基于当前项目事实说明目标、非目标、设计、影响范围和验收标准；没有 spec 的需求不得直接进入代码或文档实现。

## 当前项目事实

- 项目：InkForge（墨铸），面向中文小说作者的本地创作工作台。
- 技术栈：Next.js 16、React 19、TypeScript strict、Prisma 6、PostgreSQL、LangChain / LangGraph / LangSmith、Zod。
- 主数据库：`prisma/schema.prisma` 的 PostgreSQL schema。旧 SQLite 迁移、`dev.db`、SQLite 早期方案只作为历史背景。
- Agent 主路径：`CreativeOperation -> operationWorkflow -> ReviewArtifact -> 用户确认 -> 正式落库`。
- Agent 输出协议：可见正文是 `paragraph_text_with_control_tools`，控制信息走 OpenAI-compatible tool calls。禁止恢复 JSON 信封、正文解析控制字段或临时文本协议。
- 写作会话恢复：以 `WritingSession -> WritingTask.writingSessionId -> WritingTask.graphStateJson` 为主链路；禁止按小说、章节或时间窗猜测任务归属。
- 当前重要能力：篇幅 Profile、结构化三层大纲、ReviewArtifact 待审核草案、章节 Beat Plan、RAG 参考资料只读召回、人工工作流日志。

## 权威层级

同一主题出现冲突时，按以下顺序判定：

1. 当前代码、`prisma/schema.prisma`、`package.json`、共享 contract、测试。
2. 根级开发护栏：`AGENTS.md`、`DOCS.md`、`DESIGN.md`。
3. 当前架构文档：`src/agents/AGENTS.md`、`docs/requirements/00-overview.md` 到 `05-auth-billing-and-ops.md`、`docs/LANGGRAPH_STUDIO.md`、`docs/WORKFLOW_EVENT_LOG_FORMAT.md`。
4. 设计 spec：`docs/specs/**`。只描述尚需实现或曾用于实现的设计，不自动代表当前事实。旧 `docs/superpowers/**` 已归档。
5. 执行计划、审计、蓝图、问题记录：默认是历史材料，除非文件头明确标为 current。
6. 根目录临时计划文件、旧总方案、旧 Claude 指南：默认不具备权威性。

## 文档类型

| 类型 | 用途 | 放置位置 | 维护规则 |
| --- | --- | --- | --- |
| authority | 仓库级规则、权威索引、设计规范 | 根目录 | 必须短、当前、可执行 |
| current-requirement | 代码反推的当前需求事实 | `docs/requirements/00-05*.md` | 只能写当前事实，不写未落地想象 |
| architecture | 当前系统结构、协议和运行边界 | `src/agents/AGENTS.md`、`docs/*.md` | 必须和代码路径一致 |
| spec | 新能力或重构的设计规格 | `docs/specs/` | 必须有目标、非目标、契约、验收 |
| plan | 一次性执行步骤 | `docs/plans/` 或临时工作文件 | 完成后归档，不再当事实 |
| audit | 审计、问题清单、调查记录 | `docs/` 或 `docs/archive/` | 必须标明日期和状态 |
| archive | 历史方案、废弃方案、旧迁移记录 | `docs/archive/` | 不允许作为新开发依据 |
| prompt | 模型提示词素材 | `prompts/**` | 只约束对应运行时提示词 |

## 新增文档规则

- 能更新现有权威文档就不要新增。
- 所有后续需求先新增或更新 spec，再执行修改。spec 放在 `docs/specs/`，文件名使用 `YYYY-MM-DD-short-name.md`。
- 新增 spec 前必须核对当前代码、schema、契约和测试，不能从旧文档倒推事实。
- 新增计划文件必须写明生命周期：何时完成、完成后如何归档。
- 不再新增根目录临时 `task_plan.md`、`findings.md`、`progress.md`、`TODO.md`。需要长期保存的调查结论放进 `docs/archive/working-notes/` 或对应 spec/architecture 文档；后续能力备忘放进 `docs/BACKLOG.md`。
- 不再新增第二套 AI 助手指南。`CLAUDE.md`、其他助手入口都只能指向 `AGENTS.md` 和本文件。

## 需求执行规则

任何新需求、功能修改、行为调整、重构、数据模型变更、协议变更、UI 调整或文档体系变更，都必须按以下顺序执行：

1. 查当前事实：读相关代码、schema、contract、测试和当前权威文档。
2. 写 spec：在 `docs/specs/` 新增或更新 spec。
3. spec 至少包含：背景、当前事实、目标、非目标、设计方案、影响范围、验收标准。
4. 再执行修改：代码、schema、迁移、文档或测试都必须按 spec 落地。
5. 验证：按 spec 的验收标准检查，必要时更新当前需求文档。

例外只允许三类：

- 用户明确只要调查/审计/解释，不要求改动实现；
- 纯粹修正错别字、链接或格式且不改变语义；
- 紧急止血修复。止血后必须补 spec，说明事实、原因和后续处理。

## 修改文档规则

- 修改 Agent、共享协议、SSE、ReviewArtifact、LangGraph 路由后，必须同步检查 `src/agents/AGENTS.md` 和相关 `docs/requirements/00-05*.md`。
- 修改 UI/CSS/交互后，必须检查 `DESIGN.md` 是否受影响。
- 修改数据库或持久化后，必须以 `prisma/schema.prisma` 为准更新文档，禁止引用旧 SQLite 方案作为当前事实。
- 修改日志、调试、Studio、运维入口后，必须同步 `docs/WORKFLOW_EVENT_LOG_FORMAT.md`、`docs/LANGGRAPH_STUDIO.md` 或 `docs/requirements/05-auth-billing-and-ops.md`。
- 文档不确定时，先写“未知/需核对”，不要把猜测写成事实。

## 删除与归档规则

- 与当前事实冲突且无保留价值的文档可以删除。
- 有历史排查价值但会误导开发的文档必须归档，并在文件头写清：`状态：历史归档，不作为当前实现依据`。
- 旧方案中仍有有效规则时，只把有效规则迁入当前权威文档；不要让读者回旧文档里找规则。

## 当前入口

- 开发护栏：`AGENTS.md`
- 文档治理：`DOCS.md`
- 前端设计：`DESIGN.md`
- 项目概览：`README.md`
- docs 索引：`docs/README.md`
- Agent 架构：`src/agents/AGENTS.md`
- 当前需求：`docs/requirements/00-overview.md`
- 需求索引：`docs/REQUIREMENTS.md`
