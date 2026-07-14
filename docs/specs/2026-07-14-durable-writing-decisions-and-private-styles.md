# 持久化写作命令与用户私有文风修复设计

## 背景

2026-07-14 的本地三服务全面验收确认了以下硬故障：

- 用户批准或丢弃 `ReviewArtifact` 后，正式数据已经变化，但 `WritingTask` 仍停留在 `awaiting_user_review`，重启对账会把它再次提交。
- 前端恢复 SSE 时没有延续 `Last-Event-ID`，可能重放旧的待审批事件并在新终态到达前结束处理。
- Core 在持久化 Agent 消息和任务终态之前发布 `completed/error`，浏览器收到终态后立即刷新可能看不到最终数据。
- 文风、参考资料和画像任务没有用户归属，任何已登录用户都可以读写同一批文风。
- “单节重新生成”实际触发整套画像生成，与当前需求不符。
- 外部用户查询其他用户任务的草案时得到 `200 null`，未明确区分“本人的任务没有草案”和“任务不属于当前用户”。
- `packages/service-auth` 的安全测试可以运行，但未通过 Mypy；写作界面还存在 React 列表 key 警告。

用户决定采用方案 B：由 Core API 通过 PostgreSQL 持久化写作命令，统一编排初次运行、普通恢复和草案决定，不再让浏览器负责“先决定、再恢复”的两步协调。用户同时确认文风必须归属于单一用户，并批准清理现有文风相关数据、为本次修复执行受控数据库结构变更。

## 目标

1. 任意已接受的写作启动或恢复意图都先进入 PostgreSQL，再投递 Redis；Redis、Core 或 Agent 短暂重启不能丢失该意图。
2. 草案批准、丢弃或返工只需要一次浏览器请求；正式写入与恢复命令在同一事务边界内形成可恢复结果。
3. 重复请求、投递重试和服务重启不得重复应用草案、重复创建章节、重复写入消息或重复扣费。
4. SSE 终态只能在对应数据库状态和可见消息已经持久化后发布。
5. 文风、文风参考资料和画像任务全部通过 `WritingStyle.userId` 归属当前用户。
6. 单节重新生成只更新目标分节，并重新计算画像 Markdown 汇总。
7. 清除本轮验收发现的授权语义、Mypy 和 React key 问题，并恢复全部自动化门禁。

## 非目标

- 不改变 Next.js 页面视觉体系或写作产品交互布局。
- 不让 Agent Service 连接 PostgreSQL，也不允许 Agent 直接写正式小说数据。
- 不引入 Celery、Kafka、RabbitMQ 或新的常驻服务。
- 不在本次修复中启用真实 embedding、评判真实模型文学质量或配置公网 HTTPS。
- 不把持久化命令机制扩展到 RAG 和质量检查任务；文风画像仍使用现有 `StylePortraitTask` 作为持久化任务事实。

## 数据库变更例外与执行边界

根级规范原本禁止修改 PostgreSQL schema。用户已经针对本设计明确批准一次例外。例外只覆盖：

- 新建 `WritingRunCommand` 表及其索引、约束和外键；
- 为 `WritingStyle` 新增非空 `userId` 外键和索引；
- 为 `StylePortraitTask` 新增可空 `section` 字段和取值约束；
- 清理现有 `StylePortraitTask`、`StyleReference`、`WritingStyle` 数据，并解除 `Novel.appliedStyleId` 引用。

应用启动代码仍不得执行 DDL、`create_all()` 或自动迁移。结构变更由版本化的一次性 SQL 脚本完成，先在克隆数据库演练并导出新的 `schema-contract.json`，再在完整备份后对生产数据库执行。

## 一、持久化写作命令

### 数据模型

新增 `WritingRunCommand`：

| 字段 | 含义 |
| --- | --- |
| `id` | 命令标识，也是稳定队列作业标识的输入 |
| `taskId` | 关联 `WritingTask`，删除任务时级联删除命令 |
| `kind` | `start`、`resume` 或 `artifact_decision` |
| `artifactId` | 草案决定对应的草案标识；不设置外键，允许物理丢弃草案后保留审计信息 |
| `decision` | `approve`、`discard`、`revise` 或空 |
| `payloadJson` | 版本化命令负载，保存恢复输入、会话绑定和用户选择 |
| `idempotencyKey` | 当前用户与客户端请求标识组合后的唯一键，防止重复受理同一动作 |
| `resultJson` | 已受理结果的版本化摘要，用于重复请求返回原结果 |
| `status` | `pending`、`submitted`、`processing`、`succeeded`、`failed` |
| `attemptCount` | 投递尝试次数 |
| `nextAttemptAt` | 下次允许投递的时间 |
| `lastError` | 最后一次投递失败的内部摘要，不返回浏览器 |
| 时间字段 | 创建、更新、提交、完成时间 |

数据库使用部分唯一索引保证同一个 `WritingTask` 同一时间最多只有一个 `pending/submitted/processing` 命令。第二个并发决定返回 409，而不是覆盖第一个命令。

启动、普通恢复和草案决定请求都增加必填 `clientRequestId`。浏览器在用户动作开始时用 `crypto.randomUUID()` 生成一次，并在该动作的自动重试中复用。Core 先按当前用户和 `clientRequestId` 查询已有命令：若已存在则直接返回保存的受理结果，再执行资源状态校验。这样即使第一次响应在网络中丢失，物理删除草案后的重试也不会被误判为草案不存在，更不会创建第二个命令。

### 事务边界

Core 新增写作编排用例层。它负责打开一个 SQLAlchemy 事务，并让领域仓储在同一事务中完成操作；路由不得直接拼接 SQL。

- 初次运行：创建 `WritingTask`、保存首条用户消息并创建 `start` 命令。
- 普通恢复：锁定并校验任务与会话、幂等保存用户消息并创建 `resume` 命令。
- 批准草案：锁定任务和草案，在同一事务内执行正式写入、把草案标记为 `applied` 并创建 `artifact_decision` 命令。
- 丢弃草案：在同一事务内物理删除草案并创建保留草案标识的 `artifact_decision` 命令。
- 返工草案：在同一事务内把草案恢复到 `draft` 并创建 `artifact_decision` 命令。

批准涉及的正文、大纲、Beat Plan 和 `agent_updates` 正式写入必须改为共享同一个事务会话。任何正式写入失败都会回滚草案状态和命令创建，不允许出现“数据已经应用但没有恢复命令”。

### 单一草案决定入口

保留公共路径 `POST /api/v1/review-artifacts/{artifactId}/decision`，但成功语义改为 202 Accepted，返回：

- `artifactId`
- `taskId`
- `commandId`
- `decision`
- `status`
- `savedCount` 或 `deleted`（适用时）

`approve`、`discard` 和 `revise` 都使用这一入口。浏览器不再随后调用 `/writing/runs/{taskId}/resume`。普通聊天和章节目标确认仍调用 resume API，但该 API 也只负责持久化命令并返回 202。

### 投递与对账

Core 生命周期内运行 `WritingRunCommandDispatcher`：

1. 使用 `FOR UPDATE SKIP LOCKED` 领取到期的 `pending` 命令。
2. 使用命令 ID 构造稳定 Agent job ID；重复提交只能得到 queued 或 duplicate。
3. Agent 接受后把命令标记为 `submitted`；首次检查点或事件把它标记为 `processing`。
4. 终态回调，或返工后再次进入 `awaiting_user_review` 的稳定检查点，把命令标记为 `succeeded`。
5. Agent 明确失败时把命令标记为 `failed`，同时按现有规则把任务标记为 error；只对投递故障自动退避重试，不自动重跑已经执行失败的模型调用。

如果 Core 在 Agent 接受任务后、写回 `submitted` 前崩溃，下一次投递仍使用相同 job ID，因此不会产生第二次执行。

现有 `WritingRunReconciler` 调整为：

- 优先恢复数据库中尚未完成的命令；
- 只对没有活动命令的 `active/waiting_call` 任务使用旧检查点对账；
- 永远不对没有决定命令的 `awaiting_user_review` 任务强制恢复。

## 二、SSE 与终态持久化

前端以 `taskId -> lastEventId` 映射保存每个任务最后处理的 SSE 事件 ID：

- 创建新任务时从空游标开始；
- 普通恢复、章节目标确认和草案决定后重新连接时发送对应 `Last-Event-ID`；
- `processStream` 每解析一个合法帧就更新该任务游标；
- 重放事件继续使用现有序号去重，不重复渲染草案或 Agent 消息。

Core 回调顺序改为：

1. 在数据库事务中幂等保存可见 Agent 消息、更新 `WritingTask` 终态并结束活动命令；
2. 事务提交成功后向 Redis 事件流追加 `completed` 或 `error`；
3. 如果事件追加失败，Agent 重试回调时数据库写入保持幂等，事件仍可补发。

因此浏览器一旦收到终态事件，立即读取会话也必须看到最终消息和终态任务。

## 三、文风用户归属

### 清理顺序

迁移前记录三张表的行数和全部 `StyleReference.filepath`，并完成数据库与 uploads 备份。事务内按以下顺序处理：

1. 将所有 `Novel.appliedStyleId` 设置为空；
2. 删除 `StylePortraitTask`；
3. 删除 `StyleReference`；
4. 删除 `WritingStyle`；
5. 增加新的字段、外键、索引和约束。

数据库事务成功后，只删除迁移前记录且位于受控 `uploads/styles` 根目录内的旧参考文件。路径越界或符号链接必须拒绝，不能扩大删除范围。

### 授权规则

- 创建文风时必须写入当前用户 ID。
- 列表只返回当前用户的文风。
- 读取、删除、上传/删除参考资料、整套生成、单节生成、编辑分节和画像任务查询都通过文风所有者过滤。
- 应用文风时同时校验小说和文风属于同一用户。
- 他人的资源和不存在的资源统一返回 404，避免泄露资源存在性。
- `StyleReference` 和 `StylePortraitTask` 不重复保存用户 ID，所有权通过 `WritingStyle.userId` 推导。
- 内部画像回调继续校验服务令牌、任务、运行和文风绑定；公开用户身份不能替代服务身份。

## 四、真正的单节画像生成

`StylePortraitTask.section` 为空表示整套画像，非空时只能是五个画像分节之一。

新增公共入口：

`POST /api/v1/styles/{styleId}/sections/{section}/portrait`

处理流程：

1. Core 校验当前用户拥有文风和可用参考资料，创建带目标分节的画像任务。
2. Agent job payload 携带可空 `section`。
3. 整套任务使用现有五节生成提示；单节任务只要求返回一个目标分节。
4. Core 成功回调锁定任务和文风，校验回调模式与任务目标一致。
5. 单节任务只更新目标列，保留另外四节，再调用统一的 `build_portrait_markdown()` 重建汇总。

前端整套按钮继续展示全部分节为生成中；单节按钮只锁定和更新目标分节。两类任务仍共享“同一文风同时只能有一个 pending/processing 画像任务”的规则。

## 五、剩余授权与静态问题

### 任务草案查询

`GET /api/v1/writing/tasks/{taskId}/artifact` 先查询当前用户拥有的任务：

- 任务不存在或不属于当前用户：404；
- 任务属于当前用户但没有活动草案：`200 null`；
- 存在活动草案：返回草案。

### Mypy

安全测试中故意传入非法构造参数的用例使用精确行级 `type: ignore`，动态覆盖参数改为显式 `TypedDict` 或分支调用。不得扩大 ignore 范围，也不得修改生产鉴权语义。

### React key

先用写作主流程稳定复现警告并定位具体列表，再为真实稳定实体选择 key。不得使用随机值或每次渲染变化的索引来掩盖警告。

## 六、错误处理和幂等

- 请求在数据库事务提交前失败：返回对应 4xx/5xx，不留下命令或部分正式写入。
- 数据库提交成功但 Redis 不可用：仍返回 202，命令保持 pending，由 dispatcher 重试；响应明确表示已受理而不是已完成。
- 重复 idempotency key：返回原命令结果，不重复写入。
- 同一任务已有活动命令：返回 409 `WRITING_COMMAND_ACTIVE`。
- 草案状态不允许当前决定：返回 409，且不创建命令。
- Dispatcher 日志只记录命令、任务和错误码，不记录完整草案、用户消息、Cookie 或令牌。
- 终端 SSE 丢失：刷新后的会话状态仍以 PostgreSQL 为准；重新连接可从游标重放补发事件。

## 七、验证策略

所有行为修改遵循测试驱动：先增加一个能够复现当前缺陷的失败测试，确认因缺少目标行为而失败，再写最小实现。

重点自动化场景：

- 草案批准、丢弃和返工都只发送一个浏览器决定请求。
- 决定事务成功而 Redis 暂时不可用时返回 202，恢复 Redis 后自动投递。
- Core 在 Agent 接受后、命令状态写回前重启，稳定 job ID 防止重复执行。
- 两个并发决定只有一个被接受。
- 批准失败时正式数据、草案状态和命令全部回滚。
- 批准或丢弃完成后刷新页面，`currentTask` 为空、`lastTask` 为 completed，重启不会再次提交。
- SSE 恢复携带游标，不重放旧待审批事件；收到 completed 后立即读取能看到 Agent 消息。
- 第二用户无法列出、读取、上传、编辑、生成、应用或删除第一用户的文风。
- 单节生成只改变目标字段，整套生成仍更新五个字段。
- 迁移脚本在数据库克隆上清理旧文风数据、保留其他业务数据并通过新结构指纹守卫。
- 外部用户查询他人任务草案得到 404，本人无草案得到 `200 null`。
- React 主流程控制台无 key 警告，Mypy 全量通过。

最终门禁：

```powershell
npx playwright test
npm run api:check
npm run test:web
npm run typecheck
npm run lint
npm run build
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m mypy apps/core-api/src apps/agent-service/src packages
```

本地使用克隆数据库和 Redis DB15 完成迁移、重启与回归；生产执行前必须有可恢复备份。公网 HTTPS 和真实模型/embedding 仍单独记录为部署环境限制。

## 八、实施顺序

1. 在数据库克隆上实现并验证版本化迁移脚本和新结构契约。
2. 实现 `WritingRunCommand` 仓储、事务用例、dispatcher 和对账规则。
3. 把启动、普通恢复和三种草案决定切换到持久化命令。
4. 修复回调持久化顺序和前端 SSE 游标。
5. 实现文风所有权和单节画像任务。
6. 修复任务草案授权、Mypy 和 React key。
7. 运行全量门禁、三服务重启恢复和双用户权限回归。
8. 备份生产数据库与 uploads，执行受控迁移，部署并完成线上感知验收。

## 九、回滚

生产迁移和新版本发布作为一个维护窗口执行。若数据库迁移、结构守卫或三服务健康检查失败：

1. 停止新版本服务，阻止新写入；
2. 恢复迁移前 PostgreSQL 备份和 uploads 备份；
3. 恢复上一版本镜像；
4. 运行只读结构守卫和登录、小说读取冒烟测试后再恢复流量。

由于文风旧数据按用户要求清理，不能只靠反向 DDL 恢复；数据库和 uploads 备份是唯一受支持的完整回滚方式。
