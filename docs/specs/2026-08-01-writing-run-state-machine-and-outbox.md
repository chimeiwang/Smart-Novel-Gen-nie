# 写作运行状态机与事务 Outbox 规格

## 状态

- 日期：2026-08-01
- 状态：已完成
- 范围：写作任务状态投影、回调处置回执、PostgreSQL Outbox、SSE 收敛

## 背景

当前一次写作运行同时存在 PostgreSQL `WritingTask`、`WritingRunCommand`、Agent 稳定快照、Redis
队列终态、Redis Stream 和真实产物等多份状态。它们各自承担不同职责，但公开状态接口、SSE 和
客户端仍会拼接原始字段并自行判断是否完成。

已复现的故障中，Core 已把任务和命令写成失败，随后迟到的 Agent 完成回调被当作无副作用请求
返回 204；Agent 因此把 Redis 作业确认成完成，但 Core 没有候选产物，Redis Stream 也没有终态
事件。问题不是某一个字段写错，而是缺少以下系统边界：

- 没有一处统一解释任务、当前命令和真实产物能否组成合法业务结果；
- 无副作用、重复应用和真正应用都可能返回相同的空成功响应；
- PostgreSQL 业务提交与 Redis SSE 发布是跨系统双写；
- SSE 和客户端用事件名称猜测生命周期，Redis 丢失后无法只靠业务事实收敛。

## 已确认决策

- 本次不统一长篇与中短篇 `WritingTask` 的业务终点。两种 workflow 保留各自状态策略。
- 本次引入 PostgreSQL 事务 Outbox，解决持久业务边界与 SSE 通知的双写窗口。
- 不把 `WritingRunCommand` 泛化成 Outbox。它继续只负责 Core 到 Agent 的持久投递。
- 不把 Redis、Outbox 投递状态或 Agent 队列终态提升为业务真相。
- 本次允许新增 PostgreSQL 表并直接迁移项目配置指向的共享远程数据库，但必须先完成可恢复备份。

## 目标

- 由 Core 从 PostgreSQL 任务、当前命令和真实产物派生唯一运行 outcome。
- 回调明确返回已应用、已应用过或已拒绝，Agent 只在收到合法回执后确认队列作业。
- 业务状态、命令、候选/报告/消息和边界事件在同一 PostgreSQL 事务提交。
- Redis 故障不再回滚或否定已经提交的业务结果。
- SSE 即使缺少 Redis 终态事件，也能从 PostgreSQL outcome 收敛并结束观察。
- 长篇和中短篇客户端使用相同 outcome 字段控制生命周期，不再各自猜测原始状态组合。

## 非目标

- 不合并长篇和中短篇的业务流程、产物类型或用户采用语义。
- 不改变 ReviewArtifact 的用户确认与正式应用边界。
- 不把所有 Agent 流式 chunk 写入 PostgreSQL。
- 不替换现有 Redis 执行队列，不引入 Kafka、LISTEN/NOTIFY 或通用事件总线。
- 不保证 PostgreSQL 与 Redis 的物理 exactly-once；Redis 采用稳定来源标识下的幂等至少一次投递。
- 不在本次把 Ed25519 请求重放保护从 Redis 迁入 PostgreSQL。

## 权威层级

```text
PostgreSQL 业务事实
WritingTask + 当前命令 + 真实产物
              |
              v
    WritingRunOutcomeProjector
              |
              v
       唯一业务 outcome

PostgreSQL WritingEventOutbox
只记录“已提交事实需要通知”
              |
              v
      Redis Stream -> SSE
```

规则：

- outcome 不能读取 Outbox、Redis Stream 或 Agent Redis 作业状态。
- Outbox `published` 只表示通知已经写入 Redis，不能反推任务成功。
- Publisher 不能修改任务、命令、候选或报告，也不能充当业务对账器。
- 对账冲突由 outcome 显式报告 `inconsistent`，不能伪造缺失产物或静默改写历史终态。

## 运行 outcome

公开状态增加以下只增不删字段，原始字段保留一个兼容周期：

```text
state                 queued | running | waiting_user | succeeded | failed | inconsistent
code                  稳定原因码
taskTerminal          PostgreSQL 任务本身是否已进入终态
streamShouldClose     当前观察是否应结束
reconciliationRequired
currentCommand        id、kind、status、updatedAt
result                kind、ready、id
observedAt
```

`inconsistent` 是派生结果，不新增数据库任务枚举。它用于表达以下事实冲突：

- 任务 completed，但当前命令失败或要求的候选/报告不存在；
- 任务 error，但当前命令成功或真实产物被当成成功结果；
- 中短篇命令成功，但 candidateVersionId 指向不存在或错误归属的候选；
- 等待用户时没有可归属的 awaiting_user ReviewArtifact；
- 其他不能由当前 workflow 策略解释的终态组合。

### 长篇策略

- active/waiting_call 且存在活动命令：queued 或 running。
- awaiting_user_review 且不存在新的活动决定命令、并存在权威待确认草案：waiting_user。
- completed 且当前命令和任务收敛：succeeded。
- error 且当前命令失败：failed。
- 草案决定命令必须参与 currentCommand 选择，不能只查询 start/resume。

### 中短篇策略

- pending 命令：queued；submitted/processing：running。
- generate_outline、generate_manuscript、replace_selection 成功时必须存在对应候选：succeeded。
- full_check 成功时必须存在完整 checkReport：succeeded。
- 任务完成只表示本次文档操作已经产生候选或报告，不表示候选已被用户采用。

`waiting_user`、`succeeded`、`failed` 和 `inconsistent` 都令 `streamShouldClose=true`；queued/running 为 false。

## 回调处置回执

写作 event、checkpoint、complete 和 fail 内部接口改为返回版本化 JSON 回执：

```text
disposition            applied | already_applied | rejected
reasonCode
recoverable
taskPhase
commandStatus
outboxEventId          仅持久边界事件存在时返回
```

- applied：本次请求完成了预期副作用，或业务事务已可靠提交给 Core。
- already_applied：相同 callback 的业务事实已经存在，可以安全确认 Agent 作业。
- rejected：身份、序号或状态机前置条件不成立；Agent 不得把它当成成功。
- 200 只表示回执被正常返回；Agent 必须校验 disposition。
- 新 Agent 遇到旧 Core 的 204/空响应时按可恢复的 `CALLBACK_RECEIPT_MISSING` 处理。
- 旧 Agent 可以忽略新 Core 的 200 JSON，因此滚动发布必须先升级 Core，再升级 Agent。

## Outbox 事件范围

Outbox 只承载能够结束当前观察或转入用户动作的持久业务边界：

- completed；
- error；
- artifact_awaiting_user_approval。

agent_chunk、工具进度和普通状态事件继续直接进入 Redis。普通 checkpoint 的 SSE 摘要也保持直接
发布；即使该摘要丢失，PostgreSQL 快照和 outcome 仍能恢复业务状态。等待用户的 checkpoint 是
例外：Agent 不再先直发 waiting 事件，Core 在保存等待态 checkpoint 的同一事务内创建对应 Outbox。

## `WritingEventOutbox` 结构

```text
id
taskId                  FK WritingTask，级联删除
commandId               FK WritingRunCommand，可空以兼容历史任务
sourceEventId           Agent callback 的稳定来源标识
sourceSequence
durableBaseline         持有任务行锁后、修改本次业务事实前读取的 PostgreSQL 快照序号
dedupeKey               同一业务边界唯一
eventType
payloadJson             只保存引用、错误码和展示摘要，不复制完整正文

deliveryState           pending | delivering | published | blocked | superseded
attemptCount
nextAttemptAt
leaseToken
leaseExpiresAt
lastErrorCode
redisEventId

createdAt
updatedAt
publishedAt
```

约束与索引：

- `sourceEventId` 唯一；`dedupeKey` 唯一；`taskId + sourceSequence` 唯一。
- complete 与 fail 为同一 command 竞争同一个 terminal dedupe key，不能各自产生终态。
- sequence 为正数，durableBaseline 非负且小于 sequence，attemptCount 非负。
- due 索引覆盖 pending 和过期 delivering；task/sequence 索引保证同任务顺序。
- blocked、pending 和 delivering 行禁止清理；published/superseded 默认保留 7 天。
- 正文、候选全文和完整 Diff 不复制到 Outbox，也不得截断 payloadJson。

## 事务与幂等

有效边界 callback 在一次数据库事务内：

1. 按 taskId/jobId 锁定任务和精确命令。
2. 校验 callback 身份、持久序号、任务状态和终态竞争。
3. 创建候选、保存报告或消息。
4. 收敛任务和命令。
5. 插入唯一 Outbox 行。
6. 一次提交后返回 applied 回执。

任何一步失败都整体回滚。重复 callback 命中相同业务事实和 Outbox 时返回 already_applied；相同
来源标识、序号或终态幂等键对应不同事件类型、payload 或完成结果时返回明确 rejected 冲突，不能
静默沿用第一次结果，也不能变成可重试的 500。`durableBaseline` 只能由持有任务行锁的仓储使用
事务修改前快照生成；回调服务不得用 `sequence - 1` 猜测。数据库提交后 Redis 是否可用，不再影响回执。

普通过程事件也必须按来源标识精确比较 sequence、event type 和规范化 data；只有三者完全一致才是
安全重复，否则返回 `WRITING_EVENT_SOURCE_CONFLICT`。该来源核验必须先于“命令已终态”或“序号已被
持久快照覆盖”等短路判断，避免把篡改后的重复来源误报为无副作用。终态回调首次应用时把 Agent 原始 result 作为
内部幂等指纹随命令保存，后续重复必须与该原始 result 完全一致；该内部字段不会出现在公开命令结果中。
completed Outbox 另外保存规范化 result 的 SHA-256，使同一来源在 Redis 侧也能识别内容冲突。

迁移前没有 `WritingRunCommand` 的历史终态无法重建完整原始 result：只允许核验可从任务恢复的
finalContent/finalResponse 和 agentOutputs；出现其他字段，或两个 final 字段彼此不一致时 fail-closed，
不能把“无法证明不同”当成“已经证明相同”。

长篇图稳定结束为 completed/error 时，checkpoint 只把内部终态保存在 `graphStateJson`，供 Agent
重试直接重放终态回调；`WritingTask.phase` 与命令在该 checkpoint 后仍保持非终态。只有随后
complete/fail 事务可以同时设置任务、命令终态并创建 Outbox，避免两个 HTTP 请求之间投影出假的
`inconsistent`。等待用户的 checkpoint 仍原子收敛为 awaiting_user_review 与命令 succeeded。

迁移前已经形成的分裂状态不会批量伪造 Outbox。它们由 outcome 暴露为 inconsistent，再通过明确
运维动作处理。为兼容已存在且从未创建命令的长篇 completed/error 历史任务，投影器保留只读的
legacy succeeded/failed 解释；中短篇缺少命令时仍为 inconsistent，不能借该兼容规则伪造候选或报告。

## Publisher

Core 新增受现有 `BackgroundTaskRegistry` 监督的 Outbox publisher：

1. 短事务使用 `FOR UPDATE SKIP LOCKED` 领取到期 pending 或租约过期行。
2. 同一任务只领取最小 sequence，领取时写入随机 leaseToken 和 leaseExpiresAt。
3. 释放 PostgreSQL 锁后调用现有 Redis Lua 幂等追加。
4. 只有持有当前 leaseToken 的 worker 可以标记 published。
5. 可恢复 Redis 错误回到 pending，并按 1 到 60 秒指数退避。
6. 确定性 payload/契约错误标记 blocked，使 readiness 失败但不阻塞其他任务。

Redis Lua 继续使用 taskId + sourceEventId 去重。XADD 成功而 Core 在标记 published 前崩溃时，
租约到期后的重试返回原 Redis event id，不产生新的业务事件。

Publisher 不跳过同任务更早的未发布行。创建 resume/artifact_decision 新命令的事务会先把同任务
尚未发布的 waiting 行标为 superseded；Publisher 发布前仍会核对一次，若 XADD 时发生序号竞争，
还会在把 waiting 标为 blocked 前再次核对后续命令。已被取代的 waiting 最终只能是 superseded，
不能迟到发布或制造永久 blocked。

Outbox 的 `deliveryState` 同时充当 Redis 边界事件的 SSE 可见性栅栏：published 才允许按 legacy
事件重放，superseded 直接跳过，pending/delivering/blocked 停在原游标等待。这样即使 XADD 已成功、
但 PostgreSQL 的 published CAS 尚未完成，浏览器也不会先看到一个尚未确认归属的边界事件。该栅栏
只影响边界通知的可见性，不参与业务 outcome 投影。

## SSE 与客户端

SSE 保留 Redis Stream 的过程事件和 legacy 边界事件，同时增加不写入 Redis、没有事件游标的
`run_outcome` 控制帧：

- 建连立即发送；
- outcome 改变时发送；
- 心跳周期重新核对；
- 关闭前发送最终 outcome；
- 只按 `streamShouldClose` 结束流，不能再按 completed/error 等事件名关闭。

没有 id 的控制帧不会覆盖浏览器保存的 Last-Event-ID。Redis 被清空或 Outbox 尚未发布时，客户端
仍能从 PostgreSQL outcome 得到最终结论。

终态连接如需兼容重放已 published 的 legacy 边界事件，必须先发 outcome、再发 legacy 展示帧、最后
再发同一权威 outcome，确保最终控制帧居后。legacy completed/error/artifact 事件不得完成前端操作、
updates_saved/updates_declined 和 legacy completed/error 阶段也不得改变终态或触发成功回调；它们只
刷新展示和缓存。前端不得把 legacy 草案事件携带的对象直接恢复成可操作草案，只能重新查询 Core；
非 waiting_user 的权威终态必须按任务清理活动草案、消息挂载、审核弹窗和旧确认提示，同时保留其他
任务的待确认草案。终态清理和会话切换还必须推进草案状态代际，所有列表与单草案读取在 await 后
校验代际，禁止清理前发出的晚到响应重新恢复旧入口。相同任务、命令与结果的 succeeded outcome
即使在流末重申，也只能领取一次完成副作用。
连接建立或 reader 中断后，客户端都先 GET 一次 outcome；仍为 queued/running 时沿用原 cursor 退避
重连，取消统一以 `AbortError` 结束。

Web 长篇、中短篇和无 UI 操作工具统一遵循：

- 生命周期只读 outcome；legacy SSE 事件只用于展示兼容；
- stream 结束后再 GET 一次 outcome；
- queued/running 时携带原 cursor 重连；
- waiting_user 正常释放当前发送锁并刷新草案；
- inconsistent 明确显示对账异常，不能显示成功；
- 中短篇只有 `result.ready=true` 才打开候选或报告。

## 迁移与发布

数据库迁移是 additive，不包含运行时自动 DDL：

1. 新增版本化 SQL `scripts/migrations/20260801_writing_event_outbox.sql`。
2. 在隔离数据库演练迁移并导出新 schema contract。
3. 对共享远程数据库执行 pg_dump 完整备份并做可读取/可恢复验证。
4. 执行事务迁移，随后运行 schema guard 和只读数据核验。
5. 部署支持 Outbox 的 Core，再部署强制回执的 Agent 和 outcome 客户端。

项目三个环境文件当前指向同一远程数据库。不能把 `.env.local` 当成隔离克隆。没有成功备份时
禁止执行正式 DDL。

旧镜像持有旧精确 schema contract，新增表后会因多表而 readiness 失败。因此回滚不删除新表，
也不能盲目切回旧镜像：

- 开放新写入前失败：恢复已验证备份并使用旧镜像；
- 开放新写入后失败：保留表并回滚到理解新 schema、但可关闭 publisher 的兼容版本；
- 回滚前先停止新边界 callback，并尽量排空 pending/delivering Outbox。

## 验收标准

- 候选、报告、消息、task、command 或 Outbox 任一写入失败时整笔事务回滚。
- Core 业务事务成功而 Redis 不可用时，callback 仍返回 applied，Outbox 保持 pending。
- 重复 complete、complete/fail 并发只形成一个命令终态和一个 terminal Outbox。
- XADD 后进程崩溃、租约过期和双 publisher 均不会产生重复来源事件或乱序。
- Redis Stream 为空但 PostgreSQL 已成功、失败或等待用户时，SSE 仍发送正确 run_outcome 并结束。
- task completed 但候选缺失时，GET/SSE/客户端均显示 inconsistent，不能显示成功。
- 长篇和中短篇业务终点保持各自语义，没有借本次改造互相套用。
- 结构迁移、schema contract、Core/Agent/Web 测试、Ruff、Mypy、TypeScript、Lint 和 API 生成检查通过。
