# Beat Plan 骨架职责与复审事实一致性规格

状态：已实现

日期：2026-08-12

## 背景

当前 `plan_chapter` 同时要求章节级验收和逐场景验收，并要求额外写明转折、代价、结果与余波。模型容易把作品设定、禁止事项和写作约束复制进每个节拍，使 Beat Plan 退化为冗长检查表。

主剧情 Agent 生成计划时可以读取大纲、剧情进度和当前章节组，但复审与返工只读取 Artifact 草案。若用户指令仅要求“与权威设定一致”，复审 Agent 无法核对剧情进度中的准确数值，可能把信息缺失误判为合理克制。

## 目标

1. 将 Beat Plan 收敛为正文写作前的简洁剧情骨架。
2. 让每个节拍的验收标准只表达一句可观察结果，不复制全局限制。
3. 让 `plan_chapter` 的复审与返工使用主 Agent 生成时的同一份冻结作品事实。
4. 保持 ReviewArtifact、用户确认和正式应用流程不变。

## 非目标

- 不修改 PostgreSQL schema。
- 不删除 `ChapterBeatPlan.chapterAcceptanceCriteria` 或 `SceneBeat.acceptanceCriteria`。
- 不改变正文、大纲、设定等其他 Operation 的复审上下文。
- 不给 reviewer 增加读取工具。
- 不由 Beat Plan 承载完整专业操作规程、文风要求或所有世界设定。

## 设计

### Beat Plan 职责

- 章节计划只描述章节目标、主线连接和按顺序排列的剧情节拍。
- 每拍保留目标、阻力或变化、参与角色、伏笔引用、预估字数和落点。
- `acceptanceCriteria` 如填写，只允许一句可观察的节拍结果。
- `chapterAcceptanceCriteria` 可省略；需要时最多写三条章节级结果。
- 转折、代价、结果与余波融入相应节拍，不再要求逐项重复列举。
- 只读上下文中已有的名称、时间和数值必须原样使用，不得降格为“存在固定奖励”等模糊表达。

### 复审事实

- `plan_chapter` primary 继续使用 `outline` 最小投影。
- reviewer 除 Core 权威草案外，同时读取当前 GraphState 中生成草案时使用的 `contextMessages`。
- reviser 同样读取该冻结上下文、Core 权威草案和合并后的修改要求。
- 冻结上下文仍作为只读作品资料注入，不改变工具权限，也不能触发重新查询。
- 其他 Operation 继续只向 reviewer/reviser 注入现有草案上下文。

## 文档同步

同步更新 Agent 架构文档以及 03、04 号需求文档，明确 `plan_chapter` 是冻结事实随审的特例。

## 验收标准

1. `plan_chapter` 执行提示明确 Beat Plan 是剧情骨架，并禁止逐拍复制全局规则。
2. 执行提示不再强制逐项列出转折、代价、结果与余波。
3. `plan_chapter` reviewer/reviser 能同时看到冻结作品事实与权威草案。
4. 非 `plan_chapter` reviewer/reviser 的上下文保持原行为。
5. reviewer 仍无读取工具，正式变更仍需 ReviewArtifact 和用户批准。
6. 相关 Agent Service pytest、Ruff 和 Mypy 通过。
