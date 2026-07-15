# 写作回调身份与 SSE 恢复规格

## 状态

- 日期：2026-07-15
- 状态：主要功能已实现，保留一项已知恢复风险
- 范围：写作作业回调身份、持久命令隔离、事件序号恢复

## 背景

写作作业使用 `WritingTask.id` 作为 `runId`，持久命令使用 `WritingRunCommand.id` 作为队列 `jobId`。当前事件、检查点、完成和失败回调只携带 `runId/taskId`，Core 无法确认回调是否来自当前活动命令。部分回调还会先修改 PostgreSQL，再由 Redis SSE 检查来源事件和序号。旧命令在“Core 已提交但 Agent 未收到响应”后重试时，可能先覆盖新命令或新检查点，再被 SSE 识别为重复或缺口。

Redis 事件流、来源去重键和序号键统一使用 24 小时 TTL，生产 Redis 不持久化且使用 tmpfs。Redis 丢失后，Agent 会从 PostgreSQL 检查点的 `eventSequence + 1` 继续，而空 Redis 固定要求首条序号为 1，导致等待用户超过 TTL 或 Redis 重启后的任务无法恢复。

## 目标

- 每个写作回调都携带产生它的 `jobId`，并在任何持久状态修改前确认它仍对应当前活动命令。
- 旧命令的重复回调只能幂等返回，不得修改新命令、任务快照或用户可见事件。
- 检查点序号只能单调前进，旧检查点不得覆盖新快照。
- Redis 事件状态丢失后，Core 能以 PostgreSQL 检查点和已验证的当前 `jobId` 安全重建序号基线。
- 不修改 PostgreSQL schema，不削弱 Ed25519、请求摘要和重放保护。

## 非目标

- 不改变 LangGraph 结构、ReviewArtifact 决策入口或模型执行策略。
- 不把 Redis 改成持久事实来源，也不在本轮启用 AOF。
- 不处理公网 TLS、域名、备案或生产证书。

## 已知保留风险

当 checkpoint 已经写入 PostgreSQL、但对应 Redis SSE 事件发布失败时，同一 job 的终态重试当前会直接发送 `eventSequence + 1` 的 completion/failure，没有先幂等补发已持久 checkpoint。Redis 序号仍停留在前一位时可能持续返回序号缺口；等待用户的快照也可能缺少对应 checkpoint 事件。本轮按产品决策保留该边缘故障，后续修复时必须先重放持久 checkpoint，再发送终态或结束等待状态。

## 设计

### 1. 回调契约绑定队列作业

`AgentEvent`、`CheckpointCallback`、`RunCompletionCallback` 和 `RunFailureCallback` 增加必填 `jobId`，回调协议从 `1.0` 升级为 `1.1`，不能在旧协议号下静默加入破坏性字段。Agent Service 从当前 `QueueJob.jobId` 构造写作 `RunResource`，所有写作回调复用同一个值。`jobId` 进入签名请求体摘要和幂等键，不能由 Core 根据 `runId` 猜测。

Core 对存在活动持久命令的任务执行以下规则：

- `jobId == WritingRunCommand.id` 才能处理回调；
- 不匹配的旧回调记录稳定错误码后幂等返回 204，不改变任务、命令和事件流，也不让已经失效的 Agent job 永久重试；
- 尚无任何持久命令的历史运行可短暂继续使用快照中锚定的 legacy job 身份；对账器必须先在任务行锁内创建唯一 `WritingRunCommand`，随后只接受该命令 ID，旧 legacy job 立即失效。
- 没有活动命令时，只允许最新一条终态命令重试其原回调；更早的历史命令和已被持久命令取代的 legacy job 都必须被身份层拒绝。

### 2. 校验顺序与事务边界

所有回调采用“锁定精确身份 -> 校验序号/状态 -> 条件持久化 -> 发布事件”的顺序。持久化方法必须按 `taskId + jobId` 锁定精确命令，禁止再按 taskId 选择任意活动命令。

- 普通事件只把匹配命令推进为 `processing`，随后发布 SSE；旧 job 不执行两者中的任何一步。
- checkpoint 在事务内验证 checkpoint 序号和当前持久序号，再更新 `graphStateJson/phase` 与精确命令，提交成功后发布 SSE。
- completion/failure 只结算匹配命令；重复终态回调保持幂等。
- 数据库条件校验失败时，不得以另一个活动命令作为默认目标。

由于 Redis 与 PostgreSQL 不能形成单一事务，重复回调必须允许“数据库已提交、事件发布失败”后安全重放：精确命令和 checkpoint 写入保持幂等，Redis 来源事件去重最终补发事件。任何数据库写入都不能发生在 job 身份和 PostgreSQL 单调性校验之前。

### 3. 检查点单调性

Core 从当前 `graphStateJson` 读取已持久 `eventSequence`。收到 checkpoint 时：

- `sequence` 和 checkpoint 内 `eventSequence` 必须一致；
- 小于当前持久序号的 checkpoint 作为旧回调忽略；
- 等于当前序号且 `eventId/jobId` 相同的重试幂等成功；
- 大于当前序号的 checkpoint 只有在当前作业身份匹配且 SSE 序号校验成功后才能保存。

### 4. Redis 丢失后的序号恢复

事件存储在序号键存在时继续严格要求 `received == last + 1`。序号键缺失时，Callback Service 先从 PostgreSQL 获取当前检查点序号并验证当前 `jobId`：

- `received <= persisted` 的旧事件不再修改状态；
- `received > persisted` 时，以 `received - 1` 原子初始化 Redis 基线并追加当前事件；
- 初始化只允许当前受信作业执行，不能让任意高序号或旧作业重置基线；
- 并发初始化使用 Lua/CAS，只有一个调用能够建立基线，其余调用按正常连续序号或来源去重处理。

Redis 丢失意味着短期 UI 事件历史已经不可恢复，前端应以会话、任务、命令和草案的 PostgreSQL 状态对账；系统不得因此阻断任务继续执行。

### 5. 终态回调可靠重放

Agent 重试同一队列 job 时，如果 Core 返回的持久快照包含相同 `callbackJobId`，则该快照属于当前 job。`completed/error` 快照必须从持久 `eventSequence + 1` 直接重放 completion/failure，不能重新执行图或重新生成正文；等待用户的稳定快照直接收敛队列消费。失败回调自身遇到 Core 5xx、超时或断线时必须保留可重试异常，只有回调成功后才把原模型/图错误转成不可重试业务失败。

## 错误处理

- 作业身份不匹配记录 `WRITING_JOB_MISMATCH` 后幂等返回 204，且无持久副作用。
- checkpoint 回退返回幂等 204 或明确冲突，但不能覆盖新快照。
- 当前作业的真实连续序号缺口继续返回 `EVENT_SEQUENCE_GAP`。
- Redis 暂时不可用时回调失败并由同一作业重试，不能绕过事件校验直接修改数据库。
- completion/failure 传输失败时，同一 job 从持久终态快照重放，不能把传输错误覆盖成不可重试结果。

## 测试与验收

- 命令 A 已提交 checkpoint、命令 B 已创建后，A 的事件和 checkpoint 重试不会改变 B 或任务快照。
- checkpoint 的 PostgreSQL 写入发生在作业身份与 SSE 序号校验之后。
- checkpoint 序号回退不会覆盖当前快照。
- Redis `FLUSHDB` 或 TTL 丢失后，从持久序号 `N` 恢复的当前作业可以从 `N+1` 继续。
- Redis 丢失后，旧作业和小于等于持久序号的回调不能抬高或回退基线。
- 服务契约、Agent/Core 回调、写作测试、Ruff 和 Mypy 全部通过。
