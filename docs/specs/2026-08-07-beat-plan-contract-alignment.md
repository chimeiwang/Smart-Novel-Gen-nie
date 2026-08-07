# Beat Plan 场景字段契约修复

## 背景

生产环境 `plan_chapter` 已生成并复审通过结构化 `beat_plan` Artifact，但用户批准时返回
`ARTIFACT_APPLY_FAILED`。权威状态回拉确认事务已整体回滚：Artifact 仍为 `awaiting_user`，章节
`approvedBeatPlan` 仍为空。

根因是 Agent 的 `submit_beat_plan` 仅把 `sceneBeats` 声明为任意字典列表，模型因而生成了
`sceneName`、`sceneGoal`、字符串 `characters` 和 `foreshadowingReferences`；Core 正式写入只接受
`order`、`goal`、字符串数组 `characters`、字符串数组 `foreshadowingRefs`、`estimatedWords` 和
`acceptanceCriteria`。复审可以通过非标准结构，但正式应用必然失败。

## 目标

- 新生成的 Beat Plan 在 Agent 工具入口即满足正式写入契约。
- 当前已生成的非标准 Artifact 可以在不改变叙事内容的前提下批准。
- 非法或无法无歧义归一化的场景继续明确失败，不能静默丢失内容。
- 不修改 PostgreSQL schema、公共 API、前端或 Artifact 状态机。

## 非目标

- 不新增场景名称数据库字段。
- 本次不把 Beat Plan 契约迁入共享包；先完成最小热修，后续如有第二个 Python 消费方再统一抽取。
- 不改变章节计划的审核、返工和批准流程。
- 不修改当前 Artifact 的故事内容、场景顺序或字数安排。
- 不为任意历史字段建立无限兼容规则。

## 设计

### Agent 入口使用严格场景模型

在 `apps/agent-service/src/inkforge_agents/tools/control.py` 增加严格的 Beat Plan 场景参数模型，并让
`BeatPlanArgs.sceneBeats` 使用该模型。`chapterGoal` 与 `sceneBeats` 改为必填，消除 Agent 可生成、Core
必然拒绝的顶层空值。场景允许字段固定为：

- `order`：可选正整数；
- `goal`：必填非空字符串；
- `conflict`：可选字符串；
- `characters`：字符串数组，默认空数组；
- `foreshadowingRefs`：可选字符串数组；
- `estimatedWords`：可选非负整数；
- `acceptanceCriteria`：可选非空字符串。

这样模型工具 schema 会直接约束未来产物，不再允许 `sceneGoal` 等漂移字段进入新 Artifact。
`beatCount` 必须等于 `sceneBeats` 的实际数量，避免展示数量与正式计划不一致。

### Core 在正式应用边界兼容当前 Artifact

在 ReviewArtifact 的 Beat Plan 应用路径增加一个聚焦的归一化函数。规范字段原样保留；仅兼容当前生产
已经出现的旧字段：

- 缺少 `goal` 时，把 `sceneName` 与 `sceneGoal` 合并为 `“场景名：场景目标”`，保证两部分信息均不丢失；
- 字符串 `characters` 按 `、`、中文逗号或英文逗号拆成非空名称数组；
- 缺少 `foreshadowingRefs` 时，把非空 `foreshadowingReferences` 作为单个完整引用文本保存；
- 缺少 `order` 时按场景列表顺序生成，从 1 开始；
- 其余正式字段沿用原值。

归一化后仍缺少非空 `goal`、列表结构非法或字段类型无法安全转换时，继续拒绝应用。兼容层只位于正式
应用边界，不改变 Artifact 原始 payload 和 revision，便于审计。

### 错误处理

当前 `ReviewService` 对未知应用异常保持事务回滚并把 Artifact 恢复为 `awaiting_user`。本次不改变该状态
机。归一化校验错误继续使批准失败，不创建 approved Beat Plan，也不留下部分 SceneBeat。

## 测试

- Agent 单元测试证明严格场景模型接受规范字段，并拒绝 `sceneGoal`、字符串 `characters` 等漂移结构。
- Core 单元测试用当前生产 Artifact 的场景形态复现旧失败，并验证归一化后的 `goal`、角色、伏笔、顺序、
  字数和验收标准完整传给正式写入端口。
- Core 单元测试证明规范字段不会被兼容层改写。
- 运行相关 Agent/Core pytest、Ruff 和 Mypy；不涉及公共接口与数据库结构，因此不生成客户端、不执行迁移。

## 发布与生产验收

1. 将测试和实现提交到 `main` 并触发现有生产发布流程。
2. 确认对应 CI 与生产部署成功，而不是只确认 push 已触发工作流。
3. 重新读取生产 Artifact，确认仍为 `revision 4`、`awaiting_user`、`sourceBindingStatus=verified`。
4. 复用原批准请求标识重新批准同一 Artifact。
5. 观察同一任务收敛，并回拉第一章，确认 `approvedBeatPlan` 非空且五个 SceneBeat 顺序、内容与字数正确。

## 验收标准

- 当前 Artifact 可以正式批准，且没有叙事信息被静默丢弃。
- 新的 `submit_beat_plan` 工具调用只能生成可正式写入的场景结构。
- 应用失败仍保持原有全事务回滚语义。
- 所有相关测试、Ruff 和 Mypy 通过，生产回拉证明第一章已获得批准计划。
