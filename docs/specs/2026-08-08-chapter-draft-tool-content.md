# 正文章节草案工具内容契约修复

## 背景

生产环境第一章 `write_chapter` 任务在生成候选前失败。本地使用相同已批准 Beat Plan、真实模型、正式写作 Agent 与工具集合复现后确认：模型正常调用 `begin_artifact_output`，但正文没有出现在普通可见文本的 `ARTIFACT_OUTPUT_START` / `ARTIFACT_OUTPUT_END` 标记之间。

当前契约要求模型在一次响应中同时完成两件事：

1. 在普通文本通道输出完整正文和边界标记；
2. 调用 `begin_artifact_output` 提交摘要与审核参数。

真实模型可能只完成工具调用并在普通文本中留下说明，导致产物校验无法取得正文。Fake Provider 会主动拼出标记，因此现有测试没有覆盖真实模型行为。

## 目标

- `begin_artifact_output` 必须直接携带完整、非空的 `content`。
- 正文内容与产物提交在同一个终止工具调用中原子完成。
- 不截断正文，不设置正文最大长度。
- 旧任务或旧模型产生的标记格式继续可以读取。
- 使用真实模型在本地完成一次正文工具调用与产物校验后，才允许提交和部署。

## 非目标

- 不修改 PostgreSQL schema。
- 不修改公共 HTTP API、Web UI 或 ReviewArtifact 状态机。
- 不调整 Beat Plan、作品设定、模型供应商或输出预算。
- 不在本次顺带增加新的日志或调试接口。

## 设计

### 工具契约

`BeginArtifactArgs` 新增必填 `content: str`。字段只校验内容非空，不设置最大长度，也不修改原文。

模型执行说明改为：完整正文只放入 `begin_artifact_output.content`，普通可见文本只用于必要说明，不再要求模型同时生成正文标记块。

### 产物校验

`validate_artifact_submission()` 对 `begin_artifact_output` 按以下顺序解析正文：

1. 如果事件存在非空字符串 `content`，直接把它作为权威正文；
2. 如果事件没有 `content`，使用现有 `ARTIFACT_OUTPUT_START` / `ARTIFACT_OUTPUT_END` 解析逻辑兼容历史产物；
3. `content` 类型错误或空白内容明确拒绝，不静默回退。

产物类型、稳定 `artifactKey`、审核参数和用户确认边界保持不变。

### Fake Provider

Fake Provider 的 `begin_artifact_output` 调用改为在参数中提交正文，以确保默认测试路径与生产契约一致。历史标记兼容由专门的产物契约测试覆盖。

## 验证

- RED：新增测试证明当前工具 schema 缺少必填 `content`，且无标记的工具正文无法形成产物。
- GREEN：工具、Runtime、产物契约、Operation Graph、Writing Job 相关测试通过。
- 运行 Agent Service 全量 pytest、Ruff 和 Mypy。
- 使用本机真实模型、生产第一章只读快照和已批准 Beat Plan 运行完整 `AgentRunner`，断言：
  - 终态为 `terminal_control_tool`；
  - 恰有一个 `begin_artifact_output`；
  - `content` 非空并达到章节草案所需规模；
  - `validate_artifact_submission()` 成功返回完整正文。
- 上述本地验证全部通过后，才提交和推送。

## 影响与回滚

变更只位于 Agent Service 的模型工具与内部产物校验层。若真实模型仍不能稳定提交正文，可回滚本次提交；旧标记读取路径未删除，不影响已有历史任务恢复。
