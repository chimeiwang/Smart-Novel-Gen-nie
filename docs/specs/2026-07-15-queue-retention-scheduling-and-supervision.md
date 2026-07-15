# 队列保留、调度与后台监督规格

## 状态

- 日期：2026-07-15
- 状态：已实现
- 范围：Redis Agent 队列终态保留、延迟重试调度、Core/Agent 后台协程监督

## 背景

Agent 队列完成或取消作业后永久保留 status 和 score 字段，没有 TTL 或清理索引。生产 Redis 只有 64 MB 且使用 `noeviction`，长期运行后会拒绝新写入。

ready ZSET 的 score 把优先级放在高位、readyAt 放在低位，但 claim 只检查第一项。未来才到期的高优先级重试作业会挡住已经到期的低优先级作业。

Core 和 Agent 的后台任务只创建一次；任务意外结束后 readiness 变红但不会在进程内重启。部分循环还捕获所有 `Exception`，确定性程序错误可能被当成基础设施异常无限吞掉。

## 目标

- 终态 job 在有限窗口内保留幂等查询能力，窗口结束后自动清理全部残留字段。
- 任意未来重试 job 都不能阻塞已经到期的其他优先级 job。
- 只重试明确的基础设施暂态异常；未知程序异常必须退出当前循环并交给监督器。
- Core 与 Agent 后台协程意外退出后按受控退避重启，并在重启/连续失败期间反映为未就绪。
- 保持单模型任务、64 MB Redis 和不修改 PostgreSQL schema 的约束。

## 非目标

- 不引入 Celery、Kafka、RabbitMQ 或新增常驻服务。
- 不增加 Python worker 或模型并发。
- 不处理公网 TLS、域名、备案和证书。

## 设计

### 1. 终态保留与清理

终态状态默认保留 7 天，配置项允许延长但不得短于 24 小时。新增终态时间 ZSET：成员是 jobId，score 是进入终态的 UTC 毫秒时间。

ack/cancel 原子执行：

- 从 ready、processing、payload、lease、attempt 和 score 中删除 job；
- 在 status Hash 保存 completed/failed/cancelled；
- 把 jobId 加入终态时间 ZSET。

队列提供 `purge_terminal(cutoff)`，Lua 原子删除截止时间前的 status 与终态索引。消费者按固定间隔调用清理；清理异常按基础设施异常处理，不影响当前已领取作业的业务终态。PostgreSQL 仍是长期幂等权威，Redis tombstone 只服务短期重复投递和对账。

升级前已存在但没有终态 ZSET 成员的 status 通过游标 HSCAN 分批回填：每轮只处理一个批次，为 terminal status 补当前时间 tombstone，并清除 ready、processing、payload、lease、attempt 和 score 残留。`QUEUE_TERMINAL_RETENTION_DAYS` 默认 7、最少 1，并由 Compose 显式透传。

### 2. 无队头阻塞的 claim

保留现有复合 score 和单一 ready ZSET，避免格式迁移。claim Lua 按优先级 0 到 99 依次执行：

```text
ZRANGEBYSCORE ready priority*factor priority*factor+now LIMIT 0 1
```

第一个命中的成员就是当前已到期作业中的最高优先级，并在该优先级内按最早 readyAt 领取。未来高优先级作业不会进入查询结果，也不会阻塞后续优先级。最多执行 100 次有界 ZSET 查询，不扫描无界队列。遇到缺失 payload 或损坏状态时，脚本原子清理坏成员后继续寻找，不能直接返回空。retry 必须同步更新 score Hash，保证租约过期恢复使用最新 readyAt。

### 3. 异常分类

- Redis 连接、超时和明确的临时写入错误按现有退避继续。
- 数据库连接/事务暂态错误由 Core dispatcher 记录并退避。
- 作业处理器的业务失败继续走 job retry/failed 规则；`CoreServiceError.recoverable` 必须被正确映射，不能继续读取不存在的 `retryable` 属性。
- `TypeError`、Pydantic 程序契约错误和其他未知异常不得在循环最外层无限吞掉；它们应结束循环，让监督器记录并重启。

日志只记录任务名、失败类型、连续失败次数和退避时间，不记录正文、payload、令牌或数据库地址。

### 4. 生命周期监督器

监督器接收可重复调用的 coroutine factory，而不是一次性 coroutine 对象。每个被监督任务维护：当前 task、连续崩溃次数、最近启动/成功时间、当前退避和停止标记。

- 意外正常返回和未分类异常都视为崩溃；
- 1、2、4、8、最高 30 秒退避后重新创建 coroutine；
- 连续稳定运行超过 60 秒后重置崩溃计数；
- shutdown 设置停止标记、请求内部循环停止并等待当前模型任务按既有规则收敛，不把正常关闭视为崩溃；
- readiness 在未启动、退避中、内部 task 已结束或连续失败超过阈值时返回 503，并暴露任务名和稳定错误码。
- readiness 保留原有布尔式 `checks`，同时用 `backgroundTasks` 返回失败任务名和 `BACKGROUND_TASK_NOT_RUNNING`、`BACKGROUND_TASK_BACKOFF`、`BACKGROUND_TASK_REPEATED_FAILURE` 或 `BACKGROUND_SUPERVISOR_STOPPED`。

Agent consumer 和 Core dispatcher/reconciler 使用同一监督语义，但不跨包导入运行时代码。

## 错误处理

- 清理失败不能删除未到期 tombstone，也不能误报业务 job 完成。
- 领取脚本遇到缺失 payload 时清理损坏索引并继续寻找下一候选项，不能让单个坏成员永久挡住队列。
- 监督器重启不得创建两个同时运行的同名消费者。
- Redis OOM/拒绝写入计入连续基础设施失败并使 readiness 失败，不能只用 PING 判断健康。

## 测试与验收

- ack/cancel 删除 payload、lease、attempt、score，并建立带时间的终态 tombstone。
- 保留窗口内重复 enqueue 仍被终态拒绝；过期清理后所有 Redis 字段消失。
- “未来高优先级 + 当前低优先级”时能立即领取已到期低优先级作业。
- 同优先级仍按 readyAt 排序，租约和重试语义保持不变。
- 一次 Redis 暂态异常后循环继续；确定性未知异常会退出并由监督器重启。
- 监督器不会并发启动两个消费者，退避期间 readiness 为 503，恢复后重新为就绪。
- shutdown 不触发重启，也不截断当前模型任务。
- Agent/Core 相关 pytest、Ruff 和 Mypy 全部通过。
