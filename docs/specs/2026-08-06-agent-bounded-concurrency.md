# Agent 有界并行执行规格

## 背景

当前 Agent Service 虽然已经在单次 CreativeOperation 内使用 LangGraph `Send` 并行扇出复审，并在 `AgentRuntime` 内并行执行只读且并发安全的工具，但 Redis 队列只有一个消费循环。消费者领取一个 job 后会等待完整 handler、租约续期和终态确认全部结束，才会领取下一个 job。因此画像、质量检查、RAG 和写作任务会共享同一个串行执行槽；一个长时间模型调用会阻塞其他已经到期的任务。

生产目标仍是 2 核 2 GB 单机。直接增加 Uvicorn worker 会复制 Provider、HTTP 客户端、日志对象和消费者，并增加同一队列上多进程生命周期监督的复杂度，不适合作为本次方案。

## 当前项目事实

- Agent Service 使用一个 Uvicorn worker，并在应用生命周期内启动一个受监督的 `QueueConsumer`。
- Redis `claim`、租约 token、续期、重试和终态确认均由 Lua 与稳定 job ID 保护，允许多个执行槽安全竞争不同 job。
- `WritingRunCommand`、WorkflowRun、画像任务和 RAG 文档状态仍由 Core 的 PostgreSQL 持久事实恢复；Redis 不是长期权威。
- 写作 handler、画像 handler、质量 handler 和 RAG handler 共用异步 Core 客户端；模型类任务共用同一个 `ModelRuntime`。
- Agent 与 Core 的共享 Redis 客户端连接池当前各为 4；三个活动租约、队列维护、防重放、事件和后台任务重叠时缺少安全余量。
- 中短篇超过 15000 字后的蓝图分段必须在同一 job 内按顺序生成和保存检查点，不能并行拼接。
- 长篇草案复审已有最多两个 Reviewer 的并行扇出；只读工具调用也已有单轮内并行语义。
- 生产 Agent 容器资源上限为 0.65 CPU、640 MB，Redis 为 64 MB `noeviction`。

## 目标

- 在一个 Agent Service 进程内同时处理最多三个不同项目的队列 job，避免长任务阻塞全部其他项目。
- 同一 `novelId` 同时只执行一个队列 job；同项目后续 job 必须继续排队，不能与当前 job 并行读取、生成或回调。
- 对所有经 `ModelRuntime` 发起的模型请求设置进程级全局上限，避免“三个 job × 两个 Reviewer”放大为六个同时模型请求。
- 保持每个 job 独立的租约续期、重试、终态确认、检查点和回调身份。
- shutdown 停止领取新 job，并等待已经领取的 job 按现有规则稳定收敛。
- 提供单一环境变量把并行度回退为 1，便于模型供应商限流或生产资源异常时快速止损。

## 非目标

- 不增加 Uvicorn worker、容器副本或常驻服务。
- 不引入 Celery、Kafka、RabbitMQ 或新的队列协议。
- 不修改 PostgreSQL schema、公共 OpenAPI、内部服务契约或 ReviewArtifact 状态机。
- 不并行生成中短篇超过 15000 字的内部正文分段。
- 不改变同一 WritingTask 同时只允许一个活动命令的 Core 约束。
- 不把 control 工具或未声明并发安全的工具改为并行执行。
- 不支持多个 Agent Service 进程或容器副本之间的分布式项目锁；生产继续保持单进程单副本。

## 设计方案

### 1. 单进程队列执行槽

`QueueConsumer` 增加 `max_concurrency`，默认构造值保持 1。生产应用通过配置把它设为 3。

`run()` 在同一事件循环内创建固定数量的 worker 协程。每个 worker 继续复用现有 `run_once()` 语义：领取一个 job、运行 handler、独立续租，并按现有异常契约执行 acknowledge 或 retry。Redis 原子 claim 保证同一个 job 不会被两个槽同时领取。

旧终态回填、终态清理、过期租约恢复和 claim 使用同一把异步锁串行进入，避免多个槽竞争消费者进程内的回填游标与清理时钟；锁在 handler 开始前释放，因此不串行化业务任务。

任一 worker 遇到未分类程序异常时，当前 job 仍先按既有规则标记失败。消费周期停止领取新 job，其他已领取 job 继续完成，然后异常交给现有 `CoroutineSupervisor` 退避重启。基础设施异常仍按每个 worker 的有界退避和阈值处理。

worker 一旦确认本轮必须退出，就先设置消费周期失败标记和停止事件，再向外抛错，关闭“另一个槽刚好完成后又领取一个 job”的竞态窗口。运行中 job 被 Core 取消或旧 worker 失去 lease 时，旧 handler 会被取消，但该已知租约失效不能升级为整个消费者程序错误，也不能覆盖 Redis 中当前 lease 或终态。

### 2. 同项目互斥

消费者在单进程内维护当前活动的 `novelId` 集合。合法 handler 开始前在领取临界区内检查并登记项目，handler 的 acknowledge 或 retry 完成后再释放；因此同一事件循环中的三个槽不能同时进入同一项目。

如果新 claim 属于活动项目，消费者不能原地等待项目锁，因为这会占住执行槽并让队列后面的其他项目无法并行。队列新增原子 `defer` 操作：校验 lease token 后把 claim 放回 ready，设置短暂延迟，并撤销本次 claim 增加的 attempts；随后该 worker 继续寻找其他项目。成功 defer 的同项目任务不会消耗失败重试次数，也不会占用三个业务执行槽；进程在 claim 与 defer 之间被强制终止时仍沿用既有 lease 恢复和 attempts 语义。

项目互斥约束的是独立 QueueJob。单个 job 内现有的只读工具并发和 Reviewer `Send` 可以保留，它们共享同一不可变上下文或权威草案，不会启动第二个同项目业务任务；正文分段、控制工具、草案提交和回调顺序仍保持串行。

`writing`、`quality` 和 RAG job 的 `novelId` 是实际小说 ID，因此可以跨 kind 归并同一项目。`portrait` job 使用既有的 `style:{styleId}` 合成作用域，按文风画像串行，不与引用该文风的小说项目互斥。

### 3. 全局模型调用上限

`ModelRuntime` 增加进程级 `asyncio.Semaphore`。模型调用在申请计费 grant 之前获取槽位，并在用量上报或异常结束后释放，防止 grant 在等待模型槽期间过期。

全局上限与队列执行槽使用同一个配置值。生产默认值为 3：

- 三个不同项目的 job 可以各执行一个模型调用；
- 单个写作 job 的两个 Reviewer 可以并行；
- 当多个 job 与 Reviewer 扇出重叠时，总模型调用仍不超过三个；
- RAG embedding 不经过 `ModelRuntime`，但总活动队列 job 仍不超过三个且 `novelId` 不重复。

### 4. 配置与资源边界

新增 `AGENT_MAX_CONCURRENCY`：

- 默认值：3；
- 合法值：1、2 或 3；
- `1` 恢复原串行行为；
- 同时控制队列 handler 数和 `ModelRuntime` 模型调用数。

生产仍只运行一个 Uvicorn worker，不提高 Agent 容器的 CPU、内存上限，也不修改 Redis 内存上限。三个槽主要重叠远程模型和 Core HTTP 等 I/O 等待；当前生产 CPU 为个位数、宿主机内存使用约 60%，且供应商已确认没有 429，具备直接试运行并发 3 的条件。若生产监控出现持续内存压力或 Core/Redis 超时，应先把该配置降为 2 或 1，而不是增加进程数。

Agent 与 Core 的 Redis 客户端连接池各从 4 提高到 8，为三个 heartbeat、claim/维护、内部请求防重放、事件和后台发布提供小幅余量。Agent → Core HTTP 仍保持最多 4 个连接，Embedding HTTP 仍保持最多 2 个连接，让 Core 数据库与远程 embedding 服务继续承担明确背压；PostgreSQL 连接池不变。

### 5. 生命周期与可观测性

- `request_stop()` 唤醒全部空闲 worker；正在运行的 worker 完成当前 job 后退出。
- 监督器仍只监督一个 `QueueConsumer.run()`，不会启动第二个消费者实例。
- 满载本身不影响 readiness。消费槽确认致命错误后立即把消费者标记为不健康；其他活动 job 排空期间 readiness 返回 503 和 `BACKGROUND_TASK_FAILURE_DRAINING`，随后进入既有监督器 backoff/重启路径。
- 同项目冲突成功回队记录 `QUEUE_PROJECT_DEFERRED`，用于观察积压和回队频率；若该日志持续高频，应检查单项目批量任务并评估更长延迟或队列项目索引。
- 本次新增的队列调度日志不记录正文、工具结果、密钥或完整 job payload；既有人工模型日志规则保持不变。

## 影响范围

- `apps/agent-service/src/inkforge_agents/queue/consumer.py`
- `apps/agent-service/src/inkforge_agents/runtime/model_runtime.py`
- `apps/agent-service/src/inkforge_agents/config.py`
- `apps/agent-service/src/inkforge_agents/app.py`
- `apps/core-api/src/inkforge_core/app.py`
- Agent 配置、队列、模型运行时与健康检查相关测试
- `infra/compose.yaml`、`.env.example`、`.env.local.example` 和部署架构测试
- 根级开发约束、Agent 架构以及 03、04、05 号当前需求文档

## 验收标准

- 配置为 3 时，三个不同 `novelId` 的队列 job 能同时进入，第四个必须等待其中一个结束。
- 配置为 1 时保持严格串行。
- 同一 `novelId` 的两个 job 不能同时进入 handler；被项目互斥挡住的 claim 成功原子 defer 后不占执行槽，并撤销本次增加的 attempts，其他项目仍可运行。
- 三个槽不能领取同一个 job，每个 claim 继续独立续租并使用自己的 lease token 收敛。
- 三个活跃 job 中的复审扇出重叠时，同时执行的 `ModelRuntime` 调用不超过配置值。
- 单个 worker 的未知程序异常停止本轮领取，已领取的其他 job 不被强制截断，之后由监督器重启消费者。
- 消费周期等待其他已领取 job 收敛期间 readiness 已返回 503；正常满载仍保持就绪。
- 运行中 job 被取消导致 lease 失效时，只停止旧 handler，不重启整个消费者，也不改写当前队列终态。
- shutdown 不领取新 job、不取消正在生成的正文，并能在活动 job 完成后退出。
- 超过 15000 字的中短篇内部段落仍按蓝图顺序串行生成。
- 配置只接受 1、2 或 3，Compose 和 `.env.example` 显式提供默认值 3。
- Agent 与 Core Redis 客户端连接池均为 8，HTTP、Embedding 和 PostgreSQL 连接上限保持不变。
- 不修改 PostgreSQL schema、公共 OpenAPI、共享服务契约和生成客户端。
- Agent 相关 pytest、Ruff、Mypy 与 `tests/architecture/test_compose_security.py` 通过。
