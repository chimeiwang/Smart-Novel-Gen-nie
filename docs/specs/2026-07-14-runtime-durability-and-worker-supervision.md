# 异步任务持久恢复与后台任务监督规格

## 状态

- 日期：2026-07-14
- 状态：已实现
- 范围：Agent 队列消费者、Core 后台循环、画像、质量检查、RAG、Redis 淘汰策略

## 背景

当前队列处理器能重试模型任务异常，但 Redis `claim`、租约恢复或数据库领取异常可以直接终止整个后台协程。readiness 只检查消费者对象是否存在，不检查协程是否已经退出。

此外，画像创建在提交失败后保留永久 `pending` 任务，后续请求又被活动任务约束拒绝。RAG 和质量检查也缺少统一的、可在 Redis 丢失后重建的持久提交事实。Redis 当前使用 `allkeys-lru`，内存压力会随机淘汰任务、租约、事件或重放保护键。

## 目标

- 短暂 Redis、数据库或 HTTP 异常不能静默杀死后台工作。
- 后台任务真正退出时 readiness 返回 503，使容器编排能够发现故障。
- 已被 Core 接受的画像、质量检查和 RAG 意图可以从现有 PostgreSQL 记录重建，不新增表或字段。
- Redis 内存耗尽时拒绝新写入，由持久层稍后重试，而不是随机删除已有关键键。

## 非目标

- 不修改 PostgreSQL schema。
- 不给 Redis 开启 AOF；PostgreSQL 仍是持久恢复权威。
- 不增加 Python worker 数量，也不允许并行执行多个模型任务。
- 不把非写作任务伪装成 `WritingRunCommand`。

## 设计

### 1. 后台任务监督

Agent Service 和 Core API 都维护明确的后台任务注册表，至少记录任务名、`asyncio.Task` 和停止入口。readiness 检查任务对象是否存在、是否完成以及是否有未处理异常，不能只检查 worker 实例。

循环内异常按两层处理：

- 单个业务任务失败继续使用现有任务重试和终态规则；
- Redis claim、数据库批量领取等循环级异常记录中文结构化日志，等待受控退避后继续；
- 协程因程序错误意外退出时 readiness 立即变为 503；
- shutdown 先请求停止，再等待活动任务收敛，不强制截断正在运行的模型正文。

Core 的写作对账器采用与现有命令 dispatcher 一致的循环级异常边界。Agent 消费者为基础设施异常增加有上限的退避，同时保持一次只处理一个队列任务。

### 2. 画像持久恢复

`StylePortraitTask` 继续作为画像任务事实：

- 创建任务事务提交后，即使首次提交 Agent 失败，也保留 `pending`；
- 新增画像对账器查询当前用户归属完整、状态为 `pending` 的任务，并使用 `portrait-{taskId}` 稳定 job ID 补投；
- 对账器也检查长期停留在 `processing` 的任务，但只在 Redis 中对应运行键完全丢失时恢复，不能并发启动第二份模型任务；
- 初次提交失败仍返回持久任务 ID，前端可以查询其状态；
- 删除文风后，外键级联删除对应任务，对账器不能复活已删除任务。

### 3. 质量检查持久恢复

复用现有 `WorkflowRun(kind=quality_check)` 保存每一次运行意图，而不是仅依赖 `ChapterQualityCheck.status`。运行输入 JSON 完整保存 `checkId`、可选源 `taskId` 和用户消息，不能在恢复时丢失可选上下文。

流程为：

1. 校验用户、小说、章节、检查项和可选写作任务绑定；
2. 在事务中创建唯一 WorkflowRun，状态为 `pending`；
3. 使用 WorkflowRun ID 生成唯一稳定队列 job ID；
4. dispatcher 投递成功后推进为 `running`；
5. Agent 完成或失败回调同时收敛检查项和 WorkflowRun；
6. Core 重启或 Redis 丢失后重新投递仍为 pending/running 且没有队列运行键的 WorkflowRun。

同一个检查项允许用户在前一次运行终态后再次运行；新的 WorkflowRun 和 job ID 不能复用旧的 completed Redis job。

### 4. RAG 持久恢复

`RagDocument` 保存当前内容哈希和索引状态，作为每个内容版本的持久事实：

- 参考资料创建或影响索引的更新在配置了 embedding 服务时标记为“等待重新索引”；
- job ID 继续由 `referenceId + contentHash` 生成，同一内容版本幂等；
- 对账器只补投当前哈希仍匹配、状态为 `disabled` 且明确标记等待索引的文档；
- 内容已变化的旧任务由现有哈希校验拒绝，不能覆盖新索引；
- 未配置 embedding 的文档保持明确的“服务未配置”，不进入忙循环；
- 完成和失败回调继续把状态收敛到 `ready` 或 `failed`。

### 5. Redis 内存策略

生产 Redis 保持 64 MB 初始上限和关闭 AOF，但把淘汰策略改为：

```text
maxmemory-policy noeviction
```

任务、事件和重放键继续使用显式 TTL 和现有清理路径。达到上限时，提交方收到错误并由 PostgreSQL 持久事实稍后重试；不得随机淘汰现有键。readiness 和日志需要暴露 Redis 写入失败，部署文档说明监控 `used_memory`、`evicted_keys` 和 rejected calls。

## 错误处理

- 对账查询失败不会终止循环。
- 单条补投失败只影响该条记录，并记录不包含正文和密钥的错误代码。
- 无法重建完整输入的历史记录不得猜测提交；将其明确标记失败并保留可诊断原因。
- Redis OOM 不能被当作任务成功。

## 测试与验收

- Agent 消费者测试注入一次 `recover_expired` 或 `claim` 异常，下一轮仍能处理任务。
- Agent readiness 测试证明消费者任务意外结束后返回 503。
- Core 对账器和 dispatcher 测试证明循环级数据库异常后会继续。
- 画像首次提交失败后，对账器能用同一任务 ID 补投，且不会因活动任务约束永久卡死。
- 质量检查的完整请求输入先持久化；Redis 丢失后能用新 WorkflowRun 的稳定 job ID恢复；重复运行同一检查项会创建不同运行。
- RAG 只补投当前哈希对应的等待记录，不补投未配置或已过期内容。
- 架构测试断言 Redis 使用 `noeviction`，并继续禁止 Agent 数据库依赖。
- 全量 Python 测试、Ruff 和 Mypy 通过。
