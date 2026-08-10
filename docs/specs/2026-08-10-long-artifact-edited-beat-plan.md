# 长篇 Beat Plan 草案批准时人工编辑

## 背景

长篇 `plan_chapter` 会生成 `kind=beat_plan` 的 ReviewArtifact。当前用户只能批准原计划、要求 Agent
完整返工或丢弃；`long.artifact.approve` 虽支持正文 `editedContent`，却不能把人工修订后的结构化
Beat Plan 作为本次批准的有效内容。

这会让几处已经明确、可机械核对的计划调整也必须重新调用 Agent。另一方面，新增绕过 ReviewArtifact
的正式 Beat Plan 保存接口会破坏“Agent 产物先审核、后应用”的边界。

## 当前事实

- `ReviewArtifactDecisionRequest` 已包含 `clientRequestId`、`expectedRevision`、`decision`、
  `editedContent`、`selectedUpdateRefs` 和 `userMessage`。
- Artifact 决定在一个 Core 事务中完成正式写入、Artifact 状态变化和持久命令创建。
- Beat Plan 批准时会锁定目标章节，将旧 approved 计划标记为 `superseded`，再新建 approved
  `ChapterBeatPlan` 及其完整 `SceneBeat` 集合。
- `expectedRevision` 保护 Artifact revision；Beat Plan 来源绑定使用父计划和全部 SceneBeat 的规范化聚合
  哈希，能够发现正式计划或场景节拍漂移。
- CLI 在批准前会 GET Artifact，并要求 `sourceBindingStatus=verified`。

## 目标

扩展现有 `long.artifact.approve`，允许用户在批准一个等待审核的结构化 Beat Plan Artifact 时提交完整
`editedBeatPlan`，由 Core 严格校验后作为本次批准的有效计划原子应用。

该能力必须：

- 保留 `awaiting_user -> applying -> applied` 状态机；
- 保留 Artifact revision、来源绑定、幂等和事务边界；
- 保存本次实际应用的完整人工编辑计划作为命令审计事实；
- 不修改 PostgreSQL schema；
- 不新增绕过 Artifact 的正式 Beat Plan 直写接口。

## 非目标

- 不支持直接修改已经 approved 的 Beat Plan。
- 不支持局部 patch、JSON Patch 或按 SceneBeat 单项增删改。
- 不允许 `revise` 或 `discard` 携带 `editedBeatPlan`。
- 不支持 `beat_plan_draft`、正文、大纲或 `agent_updates` 使用该字段。
- 不改变 Agent 自动复审结论，也不重新触发一次 Agent 复审。
- 不要求本期增加前端 Beat Plan 结构化编辑器。

## 方案选择

采用专用结构化字段 `editedBeatPlan`，不复用 `editedContent`，也不引入通用 `editedPayload`。

原因：

- Beat Plan 是结构化数据，文本反解析无法可靠保留字段和类型；
- 通用结构化编辑会同时扩大其他 Artifact 的权限面，不符合本次最小目标；
- 专用字段能通过 OpenAPI、Pydantic 和 CLI 前置校验明确表达边界。

## 公共 API 契约

为 `ReviewArtifactDecisionRequest` 增加：

```python
editedBeatPlan: EditedBeatPlanRequest | None = None
```

`EditedBeatPlanRequest` 只描述正式落库字段，不接受 Artifact 展示字段：

```text
chapterGoal: 非空字符串
mainPlotConnection: 字符串或 null
chapterAcceptanceCriteria: 字符串或 null
totalEstimatedWords: 大于等于 0 的整数
sceneBeats: 1 到 50 个 EditedSceneBeatRequest
```

`EditedSceneBeatRequest`：

```text
order: 大于等于 1 的整数
goal: 非空字符串
conflict: 字符串或 null
characters: 字符串数组
foreshadowingRefs: 字符串数组或 null
estimatedWords: 大于等于 0 的整数
acceptanceCriteria: 非空字符串
```

所有模型继续使用 `extra=forbid` 和严格类型。`sceneBeats.order` 必须唯一，并从 1 开始连续排列。
字符串数组不得包含空字符串。

### 请求组合约束

`editedBeatPlan` 仅在以下条件同时成立时可用：

- `decision=approve`；
- Artifact 状态为 `awaiting_user`；
- Artifact `payload.kind=beat_plan`；
- Artifact `sourceBindingStatus=verified`；
- `expectedRevision` 等于当前 revision。

`editedBeatPlan` 与 `editedContent`、`selectedUpdateRefs` 互斥。CLI 的 `editedBeatPlanFile` 只是本地输入
便利字段，不进入公共 API。

## Core 数据流

1. 决策入口按现有流程锁定 Artifact、任务及来源绑定，并校验 `expectedRevision`。
2. 如果请求包含 `editedBeatPlan`，Core 校验 Artifact kind 和请求组合，再把完整结构化对象传给
   `ReviewService` 与 `FormalArtifactApplier`。
3. `FormalArtifactApplier` 计算本次有效计划：有 `editedBeatPlan` 时使用它，否则保持使用
   `artifact.payload.beatPlan`。
4. 有效计划继续调用同一条正式 Beat Plan 应用路径，不另写一套数据库逻辑。
5. 正式写入锁定章节，将旧 approved 计划设为 `superseded`，创建新的 approved 计划和完整 SceneBeat。
   旧计划及其 SceneBeat 保留为历史。
6. 正式写入、Artifact 变为 `applied`、持久决定命令和结果仍在同一事务中提交。
7. Agent 只恢复既有任务状态，不再次应用正式数据。

应用失败时沿现有流程把 Artifact 从 `applying` 恢复为 `awaiting_user`。

## 幂等与审计

完整 `editedBeatPlan` 必须进入决定请求的规范化正文、请求指纹和 `WritingRunCommand.payload`：

- 同一 `clientRequestId` 与同一完整计划安全返回原结果；
- 同一 `clientRequestId` 携带不同计划返回幂等键复用冲突；
- Artifact 原 payload 和 revision 不被改写；
- 命令审计记录保存最终由用户提交并实际应用的计划。

新增字段未提供时不得改变旧请求的规范化指纹。实现时只在 `editedBeatPlan` 非空时把该新字段加入
规范化正文；现有字段的 null 处理保持原样，避免部署前已经受理的 `clientRequestId` 无法重放。

## CLI 契约

不新增命令，扩展 `long.artifact.approve` 的允许字段：

- `editedBeatPlan`：内联 JSON 对象；
- `editedBeatPlanFile`：指向 UTF-8 JSON 文件，文件根节点必须是对象。

若提供人工编辑计划，二者必须且只能选择一个；也允许二者都省略，以批准 Artifact 原计划。CLI 把文件
完整解析成对象后，只向 Core 发送 `editedBeatPlan`，不得发送本地路径。`editedBeatPlan`、
`editedBeatPlanFile`、`editedContent`、`editedContentFile` 和 `selectedUpdateRefs` 按编辑类型互斥，不能在
同一次 approve 中混用。

示例：

```json
{
  "artifactId": "artifact-id",
  "clientRequestId": "stable-request-id",
  "expectedRevision": 3,
  "editedBeatPlanFile": "C:\\work\\chapter-1-beat-plan.json"
}
```

CLI 在 POST 前继续 GET Artifact，并额外校验当前 Artifact 为 `awaiting_user`、`kind=beat_plan`、
`sourceBindingStatus=verified`。Core 必须再次执行权威校验，不能信任 CLI 预检。

## 操作员闭环

生产 Skill 对人工 Beat Plan 编辑采用以下闭环：

1. GET 当前 Artifact，完整读取 revision、来源状态和原 Beat Plan。
2. 展示完整旧计划、完整新计划和完整 Diff，取得一次针对该 Diff 的明确批准。
3. 使用稳定 `clientRequestId`、当前 `expectedRevision` 和完整 `editedBeatPlan` 执行一次
   `long.artifact.approve`。
4. 继续监控同一 task 到终态。
5. 执行 `long.chapter.get`，逐字段核对正式 `approvedBeatPlan` 与用户批准的新计划。

该授权只覆盖当前 Artifact revision 和展示过的完整 Diff，不能扩展到其他 Artifact 或正式计划。

## 错误处理

- 请求字段类型、空值、顺序、字数或互斥关系不合法：422。
- `editedBeatPlan` 用于非 approve 决定或非 `beat_plan` Artifact：400，返回稳定业务错误码。
- Artifact 不在 `awaiting_user`、revision 过期、来源已漂移或存在并发决定：409。
- 文件不存在、不是 UTF-8、JSON 非法或根节点不是对象：CLI 本地错误，不发送生产请求。
- 正式应用失败：事务回滚，Artifact 恢复 `awaiting_user`，不创建部分 Beat Plan。
- 网络结果不确定：复用原 `clientRequestId` 和完全相同的请求对账，不生成新 ID 重试。

## 代码影响

- Core ReviewArtifact 决策请求与严格 Beat Plan 编辑模型。
- 决策编排器、ReviewService 和 FormalArtifactApplier 的参数透传与有效计划选择。
- 生成的 OpenAPI TypeScript 客户端。
- InkForge CLI 的 `long.artifact.approve` 输入解析与文件读取。
- 生产 operator Skill 的长篇章节流程、CLI 契约和相关测试。
- 当前需求文档中“Beat Plan 只能通过 revise 修改”的表述，调整为：Agent 结构性返工仍使用 revise；
  用户提供并确认完整结构化计划时，可以在 approve 中原子应用人工编辑版本。

生产 wrapper 命令数量和 allowlist 不变。

## 测试

### Core

- 未提供 `editedBeatPlan` 时保持原批准行为和旧幂等指纹。
- 合法 `editedBeatPlan` 优先于 Artifact 原 payload 落库。
- 非 approve、非 beat_plan、冲突编辑字段和非法结构被拒绝。
- revision 过期、Beat Plan 或 SceneBeat 来源漂移返回 409。
- 同一请求幂等重放，不同计划复用同一 ID 返回冲突。
- 应用后旧计划为 `superseded`，旧 SceneBeat 保留；新计划为唯一 approved，SceneBeat 完整一致。
- 任一步失败时正式数据、Artifact 状态和命令创建整体回滚。

### CLI

- 内联对象和 UTF-8 JSON 文件都原样发送为 `editedBeatPlan`。
- 非法 UTF-8、非法 JSON、非对象根节点、字段互斥和不支持的决定在本地拒绝。
- approve 前 Artifact kind、状态和来源预检正确。
- 命令仍声明 mutation、身份校验和稳定 `clientRequestId`。

### 集成与文档

- 重新生成 API Client，并通过 `npm run api:check`。
- 运行 Core reviews/writing 相关 pytest、CLI 相关 pytest、Ruff 和 Mypy。
- 运行生产 Skill 的 allowlist 与长篇工作流测试，确认命令总数不变。

## 基线与交付顺序

当前工作树落后于已经集成长篇生产 CLI 的主线基线。实现不得在旧 CLI 上平行重造缺失能力；进入实现前
应先同步到包含当前生产 `long.artifact.approve`、来源绑定门禁和结构化写入能力的权威主线，再按本 Spec
修改。若同步会覆盖当前工作树中未提交的用户改动，必须先停止并处理工作树隔离问题。

## 验收标准

- 用户可以对一个 `awaiting_user`、来源已验证的 `beat_plan` Artifact 提交完整人工编辑计划并批准。
- 实际应用的 approved Beat Plan 与提交对象逐字段一致。
- 原 Artifact、人工编辑内容、决定 revision 和幂等请求均可追溯。
- 无法用该能力修改其他 Artifact、绕过用户批准或直接覆盖已批准计划。
- 旧客户端不提供新字段时行为与幂等结果保持兼容。
- 不修改 PostgreSQL schema，不增加生产 wrapper 命令数量。
