# 删除同步设定流程规格

## 目标

删除“同步设定”在写作工作台中的用户入口和新任务执行路径，避免继续触发尚未稳定的设定同步工作流。

## 非目标

- 不修改 PostgreSQL schema 或现有数据。
- 不删除已经生成的 ReviewArtifact、WritingTask 或工作流日志。
- 不硬删旧快照中的 `sync_lore` 类型标识，避免历史任务反序列化失败。
- 不删除通用的设定创建、设定修改和更新构建器能力。

## 设计

- 从写作快捷动作、章节完成后的下一步建议和会话内快捷按钮中删除“同步设定”。
- 显式关键词路由不再识别 `sync_lore`。
- Operation 权威定义中删除 `sync_lore`，新分类结果即使返回该兼容类型，也必须回退为普通问答，不能进入设定同步图。
- `CreativeOperationKind` 和旧输出类型暂时保留 `sync_lore` / `sync_proposal`，仅用于读取历史快照，不作为当前可执行能力。
- 删除只服务于 `sync_lore` 初次执行的上下文和工具过滤分支；通用 ReviewArtifact 复审上下文能力不受影响。
- 当前需求和 Agent 架构文档不再把同步设定列为可用流程。

## 影响范围

- `apps/web/src/features/writing/**`
- `apps/agent-service/src/inkforge_agents/operations/**`
- `apps/agent-service/src/inkforge_agents/jobs/adapters.py`
- Agent 与写作流程相关测试和当前需求文档

## 验收标准

- 写作工作台不再显示“同步设定”按钮或推荐动作。
- `WRITING_SHORTCUT_ACTIONS` 和 `getWritingNextActions()` 不再返回 `sync_lore`。
- 带 `@设定` 的旧同步提示不会路由为 `sync_lore`。
- 分类器返回 `sync_lore` 时回退为 `answer_question`。
- `OPERATION_DEFINITIONS` 不包含 `sync_lore`。
- 旧 `CreativeOperation` 快照仍可解析 `sync_lore` 标识。
- 不修改数据库结构和现有数据。
