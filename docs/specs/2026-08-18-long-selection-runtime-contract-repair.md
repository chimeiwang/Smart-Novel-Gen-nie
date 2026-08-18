# 长篇选区改写运行契约修复

## 背景

生产 `rewrite_chapter_selection` 暴露出两处独立契约缺口：

1. 模型已在 `begin_artifact_output.replacement` 提交完整选区替换文本，但真实工具调用可能没有可见正文。Agent 校验器仍要求 `replacement` 与空 `visibleContent` 完全相同，导致合法工具调用被判为 `ARTIFACT_CONTRACT_MISMATCH`。
2. Agent 已创建并复审选区 Artifact 后，会保存包含 `currentOperation.kind=rewrite_chapter_selection` 的等待态快照。Core 快照恢复白名单没有这两个选区 Operation，因而拒绝 checkpoint；Agent job 失败后，Core 在十分钟对账时只能写入兜底错误 `AGENT_JOB_TERMINAL_FAILED`。

任务查询投影也维护了独立 Operation 集合，当前把选区任务显示为 `operation=null`，并且不能按选区 Operation 过滤。

## 目标

- 选区 Artifact 以结构化 `replacement` 为唯一权威正文。
- 允许模型工具调用的 `visibleContent` 为空；如果模型同时返回非空可见正文，仍要求它与 `replacement` 逐字一致。
- Core 能验证并保存所有共享公共长篇 Operation 的稳定快照。
- 任务查询从共享公共长篇 Operation 契约派生允许集合和 Artifact 类型，不再漏掉选区改写。
- 为真实工具调用形态、选区快照恢复和任务投影补回归测试。

## 非目标

- 不修改 PostgreSQL schema，不新增迁移。
- 不改变 ReviewArtifact 的用户确认状态机，也不绕过来源绑定校验。
- 不在本次提交中直接修改生产孤儿 Artifact 或失败任务数据。
- 不扩大生产 CLI 的命令授权范围。

## 设计

### Agent 选区产物

`_validate_selection_submission()` 继续拒绝空白 `replacement`、完整 `content`、未知字段和冻结身份漂移。仅调整可见正文规则：

- `visibleContent == ""`：接受，返回 `replacement`；
- `visibleContent != ""` 且等于 `replacement`：接受；
- `visibleContent != ""` 且不等于 `replacement`：拒绝。

Artifact 持久化和候选物化继续只读取结构化 `replacement`。

### Core 快照恢复

Core 的历史 Operation 集合保留旧 Operation，并并入 `PUBLIC_LONG_SERIAL_OPERATIONS` 的全部键。这样共享契约新增公共长篇 Operation 时，checkpoint 校验不会再次因手工白名单遗漏而失败。

### 任务查询投影

任务查询允许集合由短篇固定 Operation 与 `PUBLIC_LONG_SERIAL_OPERATIONS` 合并。需要 Artifact 的长篇 Operation 及其 Artifact kind 从共享定义的 `artifactKind` 派生。公共响应枚举显式补齐 `rewrite_scene`、`rewrite_chapter_selection` 和 `rewrite_outline_selection`，保证 OpenAPI 与运行投影一致。

## 错误边界

- 选区来源更新时间、全文哈希、Unicode 码点范围或选区哈希冲突仍由 Core 在启动前拒绝。
- 模型返回非空但与 `replacement` 不一致的可见正文仍以 `ARTIFACT_CONTRACT_MISMATCH` 失败。
- 非公共或历史未知 Operation 仍不能通过稳定快照校验和公共任务过滤。
- 已存在的失败任务与孤儿 Artifact 不自动提升、删除或应用，避免未经用户确认修补生产数据。

## 验收标准

- 空 `visibleContent` 加合法选区 `replacement` 能通过 Agent 产物校验。
- 非空且不一致的可见正文仍被拒绝。
- 两个选区 Operation 的稳定快照均能通过 Core 恢复校验。
- 选区任务查询返回真实 Operation，并按正确 Artifact kind 投影等待态结果。
- 相关 Agent/Core 测试、Ruff 和 Mypy 通过。

