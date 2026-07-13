# 写作运行计费与 SSE 恢复修正规格

## 目标

修复真实模型调用完成后因用量上报标识不匹配而终止写作任务的问题，确保浏览器携带 Redis Stream 事件 ID 重连 SSE 时能继续接收后续事件，并避免 Python 写作任务向旧 `WorkflowRun` 外键写入不存在的任务 ID。

## 非目标

- 不修改 PostgreSQL schema 或已有业务数据。
- 不改变积分价格、授权额度、Agent 编排或 ReviewArtifact 状态机。
- 不新增 Redis 初始化步骤或依赖特定 Redis 新版本。

## 当前事实

- Core 模型授权响应中的 `requestId` 是 grant 内用量上报标识。
- Agent 生成的确定性模型请求 ID 只用于授权接口的服务请求幂等。
- 当前 Redis 服务不接受 `XRANGE` 的 `(<id>` 独占起点语法。
- Python 写作运行以 `WritingTask.id` 为权威运行标识，不创建旧 `WorkflowRun` 记录。

## 设计

Agent 在授权成功后校验并保存授权响应中的 `requestId`，用它构造用量载荷和用量接口幂等键。SSE 重放使用包含式起点读取 Redis Stream，再过滤与 `Last-Event-ID` 完全相同的记录，从而保持“只返回光标之后事件”的契约。新建 ReviewArtifact 只绑定 `taskId`，`workflowRunId` 保持空值，除非未来存在真实的旧运行记录。

## 影响范围

- Agent Service 模型计费运行时及其测试。
- Core API Redis SSE 事件存储及其测试。

## 验收标准

- 授权请求幂等 ID 与授权返回 ID 不同时，用量上报使用授权返回 ID。
- Redis SSE 使用合法的包含式起点，并且不会重复返回光标事件。
- Python 写作任务创建草案时不伪造 `workflowRunId`。
- 写作失败回调产生的 `error` 事件可在 `agent_start` 后通过 SSE 重放。
- 不修改数据库结构。
