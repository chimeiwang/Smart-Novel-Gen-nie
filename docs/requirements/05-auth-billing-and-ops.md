# 认证、计费与运维需求

## 目标

为本地创作工具提供基础账号体系、资源归属校验、AI 使用计费、运行配置和调试观测能力。

## 用户认证

### 注册

用户可以注册账号。

输入：

- 用户名；
- 密码；
- 确认密码。

校验规则：

- 用户名、密码、确认密码必填。
- 用户名只能包含 3-32 位小写字母、数字、下划线或短横线。
- 密码至少 6 位。
- 两次密码必须一致。
- 用户名必须唯一。

注册成功后：

- 密码使用 bcryptjs 哈希保存。
- 创建用户。
- 发放注册赠送积分。
- 写入 CreditLedger signup_bonus 流水。
- 创建 JWT 会话并写入 httpOnly Cookie。
- 刷新首页。

### 登录

输入：

- 用户名；
- 密码。

业务规则：

- 用户名统一转小写。
- 用户名或密码错误时返回统一错误。
- 登录成功后写入 JWT Cookie。
- 登录时会把历史 userId 为空的孤儿小说分配给当前用户。

### 登出

用户可以登出。

业务规则：

- 删除会话 Cookie。
- 刷新首页。

## 会话 Cookie

认证实现：

- JWT 使用 jose 签发。
- Cookie 名称为 inkforge-token。
- Cookie 为 httpOnly。
- sameSite 为 lax。
- 有效期 30 天。

## 授权边界

系统必须校验以下资源归属：

- Novel；
- Chapter；
- WritingTask；
- WritingSession；
- ChapterQualityCheck；
- ReviewArtifact；
- 写作消息。

通用规则：

~~~mermaid
flowchart TD
    A["请求进入"] --> B["读取登录会话"]
    B --> C{"是否登录"}
    C -->|"否"| D["401 未登录"]
    C -->|"是"| E["读取目标资源"]
    E --> F{"资源是否存在"}
    F -->|"否"| G["404 或 403"]
    F -->|"是"| H["沿关系找到 Novel.userId"]
    H --> I{"是否属于当前用户"}
    I -->|"否"| J["403 无权访问"]
    I -->|"是"| K["继续执行业务"]
~~~

历史兼容：

- novel.userId 为空默认拒绝。
- 本地开发可通过 ALLOW_LEGACY_NULL_USERID=true 临时放行。
- 生产环境不应放行 userId 为空数据。

## 积分与 Token 计费

### 数据模型

User：

- creditBalanceMicros：积分余额，微积分单位。

TokenUsage：

- userId；
- model；
- promptTokens；
- completionTokens；
- cachedTokens；
- totalTokens；
- agentId；
- novelId。

CreditLedger：

- userId；
- type；
- amountMicros；
- balanceAfterMicros；
- model；
- token 明细；
- agentId；
- novelId；
- requestId；
- note。

流水类型：

- signup_bonus；
- manual_recharge；
- ai_charge；
- ai_refund。

### 注册赠送

注册成功发放 1000 积分。

### 模型调用前预检

真实模型调用前必须：

- 有 userId；
- 查询用户积分余额；
- 估算 prompt token 成本；
- 根据余额计算可负担 output token；
- 若余额不足，拒绝调用。

### 模型调用后扣费

调用完成后：

- 根据实际 usage 计算成本；
- 同步扣减 User.creditBalanceMicros；
- 写入 CreditLedger ai_charge；
- 记录 TokenUsage。

计费写入属于关键写入，不能进入可丢弃的非关键队列。

## 计费页面

计费页需要展示：

- 当前积分余额；
- 总 Token 用量；
- 当月 Token 用量；
- prompt、cached、completion、total 明细。

未登录时返回 0。

## 环境变量

常用配置：

| 变量 | 用途 |
| --- | --- |
| DATABASE_URL | PostgreSQL 连接地址 |
| JWT_SECRET | JWT 签名密钥 |
| OPENAI_API_KEY | OpenAI/DeepSeek 兼容 API Key |
| OPENAI_BASE_URL | 模型服务地址 |
| OPENAI_MODEL | 模型名称 |
| LANGCHAIN_API_KEY | LangSmith 可选追踪 |
| LANGCHAIN_PROJECT | LangSmith 项目名 |
| LANGCHAIN_TRACING_V2 | LangSmith 追踪开关 |
| LANGGRAPH_STUDIO_ENABLED | 是否启用 LangGraph Studio 本地调试 |
| LANGGRAPH_MEMORY_SAVER_TTL_MS | 等待确认 checkpoint TTL |
| ALLOW_LEGACY_NULL_USERID | 本地兼容历史无归属小说 |
| RAG_EMBEDDING_API_KEY | 参考资料 RAG embedding API Key |
| RAG_EMBEDDING_BASE_URL | 参考资料 RAG embedding 服务地址 |
| RAG_EMBEDDING_MODEL | 参考资料 RAG embedding 模型 |

## 常用命令

| 命令 | 用途 |
| --- | --- |
| npm run dev | 启动 Next.js 开发服务器，端口 43119 |
| npm run build | 生产构建 |
| npm run lint | ESLint |
| npm run typecheck | TypeScript 检查 |
| npm run db:generate | 生成 Prisma Client |
| npm run db:migrate | 运行迁移 |
| npm run studio:dev | 启动 LangGraph Studio/Agent Server 调试 |
| npm run studio:input | 生成 Studio 输入 |

## 调试与观测

### Workflow event debug

调试 API 和页面用于查看机器 JSONL 工作流事件。机器 JSONL 默认关闭。

能力：

- 按 runId 查询；
- 按 taskId 查询；
- 查看近期 workflow runs；
- 在 WORKFLOW_MACHINE_EVENT_LOG_ENABLED=true 时读取 workflow event JSONL 日志。

访问规则：

- 必须登录。
- 只能查看当前用户相关运行。

### LangGraph Studio

Studio 用于查看节点、状态、interrupt/resume 和 trace。

约束：

- 使用现有 compiled graph。
- 不新增平行 Agent 编排。
- Studio 运行会真实执行 Graph 节点，可能创建或更新 ReviewArtifact 和 WritingTask。

### LangSmith

LangSmith 可选启用。

用途：

- 追踪模型调用；
- 追踪 operationWorkflow 节点；
- 追踪工具调用摘要。

### 日志和内存

系统包含：

- logger；
- 人工工作流日志；
- 可选 workflow JSONL logging；
- MemorySaver checkpoint；
- MemorySaver TTL 清理；
- SSE 断连和异常路径清理。

原则：

- ReviewArtifact、WritingTask 状态和计费是关键写入，必须同步。
- TokenUsage 和 workflow 派生 WritingMessage 可进入有界非关键写入队列。
- MemorySaver 只做当前进程内 interrupt/resume 优化，持久恢复依赖数据库快照。
- 人工排查优先读取 `logs/workflow-events/runs/YYYY-MM-DD/<task短号>.log`。

## 安全与非功能需求

- 所有外部请求参数需要校验。
- 资源访问必须走归属校验。
- 正式写库不能信任前端传入的章节 ID 覆盖 task.chapterId。
- 真实模型调用必须校验余额。
- 关键业务错误要返回明确错误信息。
- 本地上传文件不得保存真实密钥或生产配置。

## 验收标准

- 用户可以注册、登录、登出。
- 注册后获得积分流水和余额。
- 未登录用户不能访问写作、会话、草案、质量检查等受保护接口。
- 越权访问他人小说、任务、会话、草案会被拒绝。
- AI 调用前余额不足会被拒绝。
- AI 调用后能记录 TokenUsage 和 CreditLedger。
- 开发者可以通过调试页或 Studio 排查工作流。
