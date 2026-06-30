# InkForge 项目需求总览（代码反推）

## 文档说明

本文档基于当前代码、Prisma schema、App Router 页面/API、Server Actions、前端组件、Agent 契约和已有项目文档反向整理。它描述的是现有系统已经表达出的产品需求，不把未落地构想写成已实现需求。

相关拆分文档：

- 01-projects-and-chapters.md：小说项目、章节编辑、送审和字数统计。
- 02-creative-knowledge-base.md：设定库、大纲、剧情进度、参考资料、文风画像。
- 03-ai-writing-and-agents.md：写作会话、CreativeOperation、多 Agent、SSE。
- 04-review-quality-and-workflow.md：ReviewArtifact、质量检查、Beat Plan、用户确认流。
- 05-auth-billing-and-ops.md：认证、鉴权、积分计费、调试和运行配置。

## 产品定位

InkForge（墨铸）是面向中文小说作者的本地创作工作台。系统围绕长篇小说创作，提供项目/章节管理、设定资料库、文风画像、AI 续写与多 Agent 协作、草案审核、质量终检、写作会话恢复和基础计费能力。

核心原则：

- 作者始终拥有正式内容的最终写入权。
- 手动编辑可以直接保存，Agent 产物必须先进入待审核草案。
- 正文、设定、大纲、伏笔和章节计划是不同数据层，不能互相混写。
- 写作流程要能恢复，聊天记录和可恢复 GraphState 分工存储。
- 项目以 PostgreSQL Prisma schema 为数据事实来源。

## 用户与权限

| 角色 | 需求 |
| --- | --- |
| 未登录用户 | 访问登录页，完成注册或登录。 |
| 已登录作者 | 创建小说、进入工作台、编辑章节和设定、使用 AI/Agent、审核草案、查看积分。 |
| 本地开发/调试者 | 运行开发服务器、查看工作流事件日志、使用 LangGraph Studio 调试 Agent 图。 |

访问约束：

- 小说、章节、写作任务、写作会话、质量检查和草案都必须校验归属。
- 历史 novel.userId 为空只作为兼容问题处理，不应作为新数据规则。
- 真实模型调用必须有登录用户，用于积分余额预检和扣费。

## 功能域总览

| 功能域 | 主要能力 | 主要入口 |
| --- | --- | --- |
| 项目与章节 | 小说创建、章节列表、章节编辑、自动保存、送审、完成、字数统计 | 首页、工作台、Server Actions |
| 创作资料库 | 角色、关系、经历、物品、地点、势力、术语、故事背景、世界设定、作品圣经、参考资料 | 工作台左侧/右侧面板 |
| 大纲与进度 | 文本总纲、三层结构化大纲、剧情进度、章节进展、伏笔数据模型 | 大纲面板、进度面板、Agent 草案 |
| 文风画像 | 文风创建、TXT 参考资料上传、异步画像生成、分节重生成、应用到小说 | 文风库、工作台文风面板 |
| AI 写作会话 | 会话 CRUD、消息持久化、流式 Agent 输出、恢复、继续修改草案 | 写作面板、写作 API |
| Agent 工作流 | CreativeOperation 分类、五个核心 Agent、工具调用、复审/返工、SSE 事件 | LangGraph workflow |
| 草案审核 | ReviewArtifact 创建、复审、用户批准/丢弃/返工、部分应用 | 草案卡片、审核弹窗、resume API |
| 质量检查 | 章节送审后一致性终检、运行/跳过/重置、报告保存 | 章节编辑器、quality-check API |
| 认证计费运维 | 注册登录、JWT Cookie、积分账户、Token 用量、工作流日志、LangSmith | 登录页、计费页、调试页 |

## 产品主流程

~~~mermaid
flowchart TD
    A["注册/登录"] --> B["创建小说"]
    B --> C["进入工作台"]
    C --> D["维护设定、大纲、文风、参考资料"]
    C --> E["编辑章节正文"]
    D --> F["发起写作会话或 Agent 请求"]
    E --> F
    F --> G{"是否生成正式变更草案"}
    G -->|"否：问答/报告"| H["聊天流展示结果"]
    G -->|"是"| I["ReviewArtifact 待审核草案"]
    I --> J["Agent 复审/返工"]
    J --> K["等待用户确认"]
    K -->|"应用"| L["写入正式小说数据"]
    K -->|"继续修改"| F
    K -->|"丢弃"| M["删除草案"]
    E --> N["章节送审"]
    N --> O["一致性终检"]
    O --> P["标记章节完成"]
~~~

## 核心数据视图

~~~mermaid
erDiagram
    User ||--o{ Novel : owns
    User ||--o{ TokenUsage : records
    User ||--o{ CreditLedger : pays
    Novel ||--o{ Chapter : contains
    Novel ||--o{ Character : defines
    Novel ||--o{ Item : defines
    Novel ||--o{ Location : defines
    Novel ||--o{ Faction : defines
    Novel ||--o{ Glossary : defines
    Novel ||--|| Outline : has
    Novel ||--o{ OutlineNode : structures
    Novel ||--|| PlotProgress : tracks
    Novel ||--o{ ReferenceMaterial : stores
    Novel ||--o{ WritingSession : discusses
    Novel ||--o{ WritingTask : runs
    Novel ||--o{ ReviewArtifact : reviews
    Chapter ||--o{ ChapterQualityCheck : checks
    Chapter ||--o{ WritingTask : targets
    Chapter ||--o{ ChapterBeatPlan : plans
    WritingSession ||--o{ WritingMessage : persists
    WritingTask ||--o{ ReviewArtifact : produces
    ReviewArtifact ||--o{ ReviewArtifactRevision : versions
    ReviewArtifact ||--o{ ReviewArtifactEvaluation : evaluates
~~~

## 关键业务规则

- 新建小说时默认创建第一章、空文本总纲和默认剧情进度。
- 章节正文保存为正式章节内容；Agent 生成正文默认保存为草案，用户应用后才写入章节。
- 章节状态包括草稿中、待审核、已完成；完成前必须处理一致性终检。
- 结构化大纲只有三层：阶段/卷、剧情单元、章节组。
- Agent 修改设定、大纲、伏笔、正文或 Beat Plan 必须进入 ReviewArtifact。
- 用户可对结构化 agent_updates 草案选择部分应用。
- 写作会话恢复以 WritingSession 绑定 WritingTask 和 WritingTask.graphStateJson 为主。
- TokenUsage 和 CreditLedger 是计费审计数据；扣费属于关键写入，不能异步丢弃。

## 当前边界

- 当前章节终检 API 只支持 consistency 一致性终检。
- 商业性和技法评审主要在写作草案复审循环中体现，不是默认章后检查项。
- 文风参考资料上传只支持 TXT 文件。
- 移动端适配不是当前主要目标，产品以桌面写作工作台为主。
