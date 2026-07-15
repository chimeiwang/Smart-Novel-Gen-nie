# 智能体服务架构

本文件描述 Python Agent Service 的当前边界。仓库级规则见根目录 `AGENTS.md` 和 `DOCS.md`。

## 服务职责

Agent Service 负责：

- 五个核心 Agent 的声明式定义与提示词；
- CreativeOperation 的 LangGraph 编排；
- 模型供应商适配和唯一多轮工具循环；
- 运行队列消费、检查点恢复和事件回调；
- 人工工作流日志。

Agent Service 不负责浏览器认证、数据库查询、正式业务写入、草案最终应用或计费落账。它不得接收 `DATABASE_URL`，不得导入 SQLAlchemy、asyncpg 或其他数据库客户端。

## 关键入口

- 应用工厂：`src/inkforge_agents/app.py`
- Agent 定义：`src/inkforge_agents/definitions/agents.py`
- 父图：`src/inkforge_agents/graph/parent_graph.py`
- Operation 图：`src/inkforge_agents/operations/graph.py`
- 图状态：`src/inkforge_agents/graph/state.py`
- AgentRunner：`src/inkforge_agents/runtime/agent_runner.py`
- 唯一工具循环：`src/inkforge_agents/runtime/agent_runtime.py`
- 模型适配：`src/inkforge_agents/runtime/model_runtime.py`
- 工具注册表：`src/inkforge_agents/tools/registry.py`
- Core 工具网关客户端：`src/inkforge_agents/clients/core.py`
- 运行队列：`src/inkforge_agents/queue/`
- 人工日志：`src/inkforge_agents/observability/`

## Agent 与工具规则

- Agent ID 固定为：设定、剧情、写作、校验、编辑。
- AgentRunner 只向模型暴露当前 Agent 能力白名单允许的工具。
- ToolRegistry 再次校验 Agent 权限；未暴露工具必须拒绝执行。
- 26 个只读工具的名称和参数模型统一定义在 `inkforge_contracts.read_tools`；Agent 与 Core 必须共同引用该契约，禁止分别维护同名参数模型。
- 只读且并发安全的工具可以并行；控制工具按模型返回顺序执行。
- 可见正文使用自然段文本，控制信息通过工具调用或明确产物边界提交。
- 禁止从可见正文解析路由、评分或 JSON 控制信封。
- 更新构建器在单次运行中只能启动一次；启动后 Runtime 不再暴露 `start_update_builder`，追加和完成必须沿用同一 `artifactKey`。重复开始事件在跨纠正重试合并时按幂等处理，不得清空已追加批次。
- Agent 的产物提交工具必须配置为终止控制工具；`propose_updates`、`finish_update_builder` 等产物完成事件成功后应立即结束本轮工具循环。
- `sync_lore` 已从当前可执行 Operation 和前端入口中删除；共享类型仅保留历史快照解析兼容，路由和分类器不得生成新的同步设定任务。
- 当前运行创建草案后，`CoreArtifactPort` 保存已提交 Core 的完整请求快照；复审执行器把该快照作为权威草案上下文注入 reviewer，并使用 `control_only` 模式。没有本地快照时必须显式收敛失败，不得猜测或从正文反推草案。
- 首版不提供跨服务草案局部 patch。复审请求局部修改时，`CoreArtifactPort.apply_patch()` 会明确拒绝该路径，工作流按完整草案重新生成；这是已接受的成本降级，不得伪装成局部修订成功，也不得绕过 ReviewArtifact 直接修改正式内容。

## 数据与信任边界

- 所有业务读取和草案提交都通过 Core `/internal/v1/**`。
- `semantic_search_references` 的查询向量由 Agent Service 复用现有 embedding 客户端生成，Core 只接收内部查询向量并在当前用户和小说范围内执行 pgvector 检索；未配置 embedding 时必须明确返回未启用。
- 只有 Core 与 Agent 同时设置 `RAG_INDEX_ENABLED=true` 且 Agent 已配置完整 embedding 客户端时才允许启用索引；启用后 embedding 不可用必须使就绪检查失败，不能静默降级为已就绪。
- 请求使用 Ed25519 短期服务令牌，绑定受众、权限、任务、运行、小说、请求体摘要和查询摘要。
- 写入类内部请求必须经过 Redis 重放保护。
- Agent 只能生成 ReviewArtifact 或评审结果，不能直接写章节、设定、大纲或计费表。
- 运行恢复以 Core 持久化的 `WritingTask.graphStateJson` 为权威；Redis 只承载队列、短期事件和重放保护。
- 写作事件、检查点、完成和失败回调必须携带当前队列 `jobId`，协议版本为 `1.1`；来源事件 ID 也必须绑定 jobId，禁止只靠 runId 猜测命令身份。
- 当前 job 已锚定 `completed/error` 持久快照时，重试必须从快照序号直接重放终态回调，禁止重新执行图；终态回调自身暂时不可用时必须保留可重试异常。
- 图进入等待用户确认时，必须先发送 `artifact_awaiting_user_approval`，再保存包含最新事件序号的稳定快照，确保前端能刷新草案入口且恢复时不会复用旧序号。
- 图稳定结束于 `phase=error` 时必须保存错误快照并调用 Core 失败回调，禁止用完成回调表达失败终态。
- Core 强制对账只允许修复 Redis 中缺失的 queued 索引或完全丢失的运行键；Redis 已记录为 completed、failed 或 cancelled 的运行不得被 `force` 重新打开。
- 队列消费者必须由生命周期任务监督器托管；基础设施异常按退避策略重试，消费者协程意外结束必须使就绪检查失败并触发重启，不能只凭消费者对象存在判断健康。
- 队列终态必须进入时间 ZSET 并在保留窗口后有界清理；ack/cancel 同时删除 payload、lease、attempt 和 score。领取任务时按优先级查询已到期成员，不能让未来重试任务形成队头阻塞。
- 升级前旧终态使用 HSCAN 游标分批补齐 tombstone；保留天数由 `QUEUE_TERMINAL_RETENTION_DAYS` 配置，默认 7、最少 1。
- Redis OOM、MISCONF、READONLY 和达到阈值的连续基础设施失败必须交给监督器并使 readiness 失败；TypeError、Pydantic 契约错误和未知程序异常不得在消费循环中无限吞掉。

## LangGraph 规则

- 编排必须复用现有 `StateGraph`、conditional edges、`Send`、`Command` 和 `interrupt()`。
- 复审、返工和用户确认不得另写 while/switch 状态机。
- runtime-only 客户端、回调和聚合上下文不能进入可恢复快照。
- 快照必须使用版本化信封；无法兼容的版本明确失败，不能静默猜测。

## 验证

修改运行时、工具或图后至少运行对应目录 pytest、Ruff 和 Mypy。修改服务契约或内部鉴权时，还要运行 `packages/service-contracts/tests` 与 `packages/service-auth/tests`。
