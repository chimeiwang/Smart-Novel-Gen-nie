# 模型调用按任务归集与日志关联规格

## 背景

当前 Agent Service 在每次真实模型调用完成后，已经向 Core 上报 `requestId`、`taskId`、`runId`、
`novelId` 以及 `promptTokens`、`cachedTokens`、`completionTokens`、`totalTokens`。Core 会用模型授权
令牌校验这些身份，但进入计费仓储后只保留用户、小说、模型、Agent 和四项 token，最终写入的
`TokenUsage` 无法关联具体任务、运行或单次请求。

人工工作流日志保存完整模型 messages、模型正文和完成原因，但每个模型调用区块没有计费用量和
计费 `requestId`。因此当前既不能稳定查询某一写作任务的逐调用 token，也不能把数据库用量与完整
模型输入输出一一对账。

用户已于 2026-08-21 明确授权本次 PostgreSQL Schema 修改和受控迁移。本规格构成当前“禁止修改
PostgreSQL Schema”规则的一次有界例外，仅允许修改 `TokenUsage` 归集字段及其必要索引，不授权其他
表结构调整。

## 目标

- 每个成功返回规范化 usage、并被 Core 接受的真实计费模型调用，都形成一条可按任务查询的
  `TokenUsage`。
- 使用 `requestId` 将 `TokenUsage` 与人工模型调用日志一一关联；金额大于零时，再与同一
  `requestId` 的 `CreditLedger` 计费流水关联。
- 支持按 `taskId` 查询调用明细和汇总，回答某一章节任务实际调用次数及四项 token 消耗。
- 保持余额扣减、计费幂等、服务身份和正式写作流程不变。

## 非目标

- 不保存工具 schema、模型 tool calls、工具参数、工具结果或供应商 reasoning。
- 不在数据库保存完整 prompt 或模型正文；这些内容继续只存在于受保护的人工工作流日志。
- 不用时间、模型或 token 数量猜测历史记录的任务归属。
- 不统计 Provider 抛异常且未返回可靠 usage 的调用，也不声称覆盖 SDK 内部不可见的 HTTP 重试。
- 不修改其他 PostgreSQL 表，不把迁移改成应用启动时自动 DDL。

## 数据模型

在现有 `TokenUsage` 增加三个可空 `TEXT` 字段：

| 字段 | 语义 | 新记录要求 |
| --- | --- | --- |
| `requestId` | Core 模型授权返回、用于计费回调以及金额大于零时与 `CreditLedger` 对账的请求标识 | 真实计费调用必填 |
| `taskId` | 模型调用所属业务任务标识 | 真实计费调用必填 |
| `runId` | 同一任务的一次启动、恢复或继续运行标识 | 真实计费调用必填 |

字段在数据库层保持可空，只用于兼容迁移前历史记录。应用对迁移后的新增真实计费记录强制非空。
`taskId` 不建立 `WritingTask` 外键，因为质量检查和文风画像等模型任务使用不同任务实体；它是跨任务
类型的统一关联标识。

新增索引：

- `TokenUsage_requestId_key`：`requestId` 唯一索引；PostgreSQL 允许多条历史 `NULL`。
- `TokenUsage_userId_taskId_createdAt_idx`：按当前用户和任务顺序查询。
- `TokenUsage_runId_createdAt_idx`：按一次运行顺序查询。

保留现有用户、小说和 Agent 索引。迁移为 additive，不删除、不重写历史 `TokenUsage`。

## 数据流与计费幂等

1. Agent Service 使用现有模型授权流程取得 Core 生成的计费 `requestId`。
2. Provider 返回 `ModelTurnResult` 后，Agent 按现有协议上报四项规范化 usage，以及已经存在的
   `taskId`、`runId`、`novelId`。
3. Core 校验 usage 与授权 claims 完全一致，把 claims 中的 `requestId/taskId/runId` 传入
   `ChargeUsage`。
4. 计费仓储在同一短事务中写入 `TokenUsage`；金额大于零时才扣减余额并写入
   `CreditLedger.ai_charge`。
5. 金额大于零时，`TokenUsage.requestId` 与 `CreditLedger.requestId` 使用同一值。重复回调不新增
   `TokenUsage`、不重复扣费；载荷或任务身份不一致则返回冲突。金额大于零的重放返回原计费流水
   余额，金额为零的重放查询并返回重放时的当前余额。

对于四项 token 全为零、因而金额为零的真实 billable usage，仍写入一条 `TokenUsage`，以免“没有记录”
与“Provider 返回零 usage”无法区分；不写 `CreditLedger`、不扣余额。重复零 usage 通过 `requestId`
幂等返回且不产生任何写副作用。非 billable Fake Provider 不写正式 `TokenUsage`。

部署切换期间，迁移前已经成功扣费的正金额请求可能只有 `CreditLedger.ai_charge`，而对应历史
`TokenUsage.requestId` 仍为 `NULL` 或不存在。此时 Core 只使用流水中能够证明的用户、小说、Agent、
模型、四项 token 和金额判断重放：同一 `requestId` 恰好存在一条且全部一致时返回该流水保存的金额和
扣费后余额，不再次扣费，也不新增或回填 `TokenUsage`；字段不一致或存在多条同请求扣费流水时返回
冲突。历史流水没有 task/run，不能声称比较或恢复这两个身份。

`cachedTokens` 是 `promptTokens` 的子集；`totalTokens` 始终等于 `promptTokens + completionTokens`，查询
和日志不能把缓存 token 再次加到合计。

## 人工日志关联

每个 `Axx` 模型调用区块在现有完整 messages 和完整正文之外，增加：

```text
任务标识：<taskId>
运行标识：<runId>
计费请求标识：<requestId>
模型：<provider>/<model>
Token 消耗：输入 <promptTokens> | 缓存 <cachedTokens> | 输出 <completionTokens> | 合计 <totalTokens>
```

继续记录规范化完成原因和供应商原始完成原因。绝不记录 `grantToken`。Core 已接受 usage report 的
billable 调用，其 `TokenUsage` 和日志区块必须能通过同一 `requestId` 关联；金额大于零时还关联
`CreditLedger`。非计费调用显示“无计费请求标识”。

billable Provider 成功形成 `ModelTurnResult` 后，Agent 先向 Core 上报 usage；只有 Core 成功接受 report
且配置了 observer 时，才记录该次人工模型区块。report 失败时异常向上传播，不留下该次模型区块。
非 billable Provider 成功后直接调用 observer，但只有 observer 与运行 context 都存在时才写区块，计费
请求标识为“无”。Provider 在返回 usage 前失败时不能伪造 token。工具参数校验发生在 Provider 返回、
usage 上报和日志记录之后，因此 `MODEL_TOOL_ARGUMENTS_INVALID` 等后置失败仍应存在可归集的
`TokenUsage` 和模型区块。

## 按任务查询接口

新增公共接口：

```text
GET /api/v1/billing/usage/tasks/{task_id}
```

首版只允许查询属于当前用户的 `WritingTask`。不存在或不属于当前用户统一返回无权访问/不存在，不得
泄露其他用户任务是否存在。响应包含：

- `taskId`；
- `requestCount`；
- 四项 token 汇总；
- 按 `createdAt, id` 排序的逐调用明细：`requestId`、`runId`、`agentId`、`model`、四项 token、
  `createdAt`。

接口不返回完整 prompt、正文、余额或 `grantToken`。公共 Pydantic 契约修改后重新生成 TypeScript
客户端并执行 `npm run api:check`。

## 历史数据

- 迁移前记录的 `requestId/taskId/runId` 保持 `NULL`。
- `CreditLedger` 同样没有历史 task/run 信息，不能可靠回填。
- 新接口只返回部署后具有匹配 `taskId` 的记录；不得把历史未归集用量计入具体任务。
- 用户总计和当月 usage 仍包含全部历史 `TokenUsage`，现有统计语义不变。

## 迁移与发布

新增版本化事务 SQL：

```text
scripts/migrations/20260821_token_usage_task_run.sql
```

迁移脚本必须：

- 使用 PostgreSQL advisory transaction lock；
- 只增加三个可空列、非空值检查和三个索引；
- 可安全重跑，并在结束前核验列、约束和索引定义；
- 不修改或猜测任何历史行；
- 不读取或输出数据库密码、模型密钥或用户正文。

发布顺序：

1. 在隔离数据库执行迁移演练并导出、核对新 schema contract。
2. 完成 PostgreSQL 可恢复全量备份并验证备份可读取；没有成功备份不得执行正式 DDL。
3. 暂停接收新的模型任务，等待正在执行的计费回调收敛。
4. 在维护边界内执行事务迁移，并用目标版本 Core 镜像运行只读 schema guard。
5. 部署理解新 schema 的 Core 和 Agent，再执行计费、任务 usage 查询和日志关联冒烟。
6. 恢复模型任务入口。

旧镜像持有旧精确 schema contract，迁移后不能作为自动回滚目标。迁移发布前必须准备一个理解新 schema
且可关闭新增查询/日志功能的兼容 Core/Agent 镜像。开放新写入前失败可恢复备份并回到旧镜像；开放新
写入后失败保留新增列，回滚到兼容镜像，不删除列、不丢弃已归集用量。

应用启动和普通生产部署继续禁止自动执行 DDL。本次迁移只能通过明确的版本化脚本和维护步骤执行一次。

## 测试与验收

- 数据库模型与新 schema contract 精确一致。
- 迁移在隔离 PostgreSQL 上首次执行和重复执行均成功，且历史行三个新字段为 `NULL`。
- 一次金额大于零的真实计费 usage 同时写入同 `requestId` 的 `CreditLedger` 和 `TokenUsage`；金额为零
  时只写 `TokenUsage`。
- 相同 requestId、相同身份和 usage 重放不重复扣费、不重复写入；不同 task/run 或 usage 返回冲突。
- 零金额真实 usage 写一条 `TokenUsage`，重复回调保持幂等。
- 按任务接口只能读取当前用户的任务，并准确返回逐调用和汇总四项 token。
- Core 成功接受 report 的 billable 调用，其人工日志区块包含相同 taskId、runId、计费 requestId 和四项
  实际 token，完整输入输出不被截断；report 失败不留下该次模型区块。
- 现有用户总计、月度 usage、余额扣减和 ReviewArtifact 流程回归通过。
- Core 相关 pytest、Agent 相关 pytest、Ruff、Mypy、schema guard、迁移测试、API 生成与
  `npm run api:check` 全部通过。
