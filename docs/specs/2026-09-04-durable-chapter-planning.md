# Durable Agent V2 章节规划纵切

日期：2026-09-04。状态：仓内实现、全仓测试、章节规划专项及额外问答恢复回归已完成；未部署生产。

## 完整目标与本阶段

本阶段继续 `2026-08-31-core-owned-durable-agent-execution.md` 的完整重构目标，不取代其全部 Operation、
恢复、资源、开发环境、生产迁移和真实账号验收要求。本阶段开始时，代码的 21 项 Catalog 中仅问答、章节选区改写有完整
V2 handler；其他项的占位声明不能算实现。`plan_chapter` 是下一条必须完成的创作主链，完成它仍不表示整个重构完成。

已验证的 CLI 切换以本地提交 `cc7ffc6` 保存。2026-09-04 已使用新版生产 Skill 和现有 Keychain 会话成功执行
指定账号的 `auth.whoami`，未导出令牌或使用密码脚本；此证据只证明真实身份和 Java CLI 接线，不证明新 Agent 已上线。
本阶段不推送 main、不触发部署、不执行远程数据库迁移或真实写作。

## 行为

- 沿用公共 `long_serial.plan_chapter`、章节 target/scope、稳定 clientRequestId 和可选写作会话，不新增 CLI 命令。
  V2 使用 WorkflowRun/Step，不创建 WritingTask、WritingRunCommand 或 LangGraph 状态。
- Core 冻结章节目标、大纲及路径、剧情进展、相关权威设定/伏笔和已有批准计划的最小充分 Evidence；显式记录缺失
  来源，不从模型回传来源 ID/hash，不读取完整 workspace 作为提示，不静默裁掉上下文。
- 生成、编辑 Reviewer、自动返工和用户显式 revise 使用同一个不可变 Evidence bundle。输入只含当前用户指令和
  明确的目标字数；返工另带原指令、精确上一候选/revision 和本次要求，不让模型读可变业务状态。
- 新输出是严格语义对象：title、summary、chapterGoal、sceneBeats；可选 mainPlotConnection、
  chapterAcceptanceCriteria、totalEstimatedWords。每个 sceneBeat 有 goal，可选 conflict、characters、
  foreshadowingRefs、estimatedWords、acceptanceCriteria。字段类型/长度沿用现有 Beat Plan 产品约束；
  beatCount、连续 order、Artifact ID、来源和完整性哈希由程序派生，不要求模型计算。
- 使用版本化 `plot.chapter_plan.v1` 生成 Profile，并为章节规划提供专用编辑 Reviewer Profile/Prompt，不能把
  选区 Reviewer 的 replacement 指令套到计划。Profile、Prompt、Deployment、Schema、Step Budget、review policy
  与 manifest 成套引用；每个模型 Step 独立预算和结算，保留最多三个全局模型槽。
- 规划生成与复审每 Step 最多 30,000 input tokens，未命中缓存额度同为 30,000，不假定供应商已经缓存作品资料；
  两轮共最多四次调用，Run input/cache-miss 上限均为 120,000。completion/reasoning/visible、每 Step 与 Run
  的费用上限、时间上限不随此修正放宽。首次隔离验收证明旧 10,000 cache-miss 配置会拒绝合法的 10,377 输入，
  因此修正的是新 Operation 的冷缓存预算配对，不修改 Fake 计量、不隐藏超限失败，也不允许超过 30,000 的完整输入。
- 复审成功保存独立 Evaluation。按冻结 policy 最多一次自动完整返工，然后再次复审；Reviewer 不可用、分歧、
  结构性阻断或第二轮仍不通过时保留候选交给作者，不把基础设施错误当内容不通过。自动返工必须是新耐久 Step，
  不允许隐藏工具循环、无限重试或覆写已存在 revision。

## 草案与应用

- Core 确定性创建 `kind=beat_plan` 的 V2 ReviewArtifact，每个 revision 只保留一个规范语义计划及
  Evidence/Step/result 身份与哈希，不在 payload/diff 中再复制完整 before/after。既有 head 投影保留；generation
  Step.output 保存候选引用。Reviewer/返工所需的冻结执行 input 可携带该 revision 的完整候选，但必须核对相同哈希。
  精确详情重建规范 payload/sourceBindings/diff；列表仍只有有界 summary，不把计划伪装成选区 replacement。
- 生成和复审期间不写正式 ChapterBeatPlan/SceneBeat。作者 approve 时，Core 在 Run → Artifact/revision → 来源的
  同一事务内核对来源和 revision，复用正式 Beat Plan 应用器：旧批准计划 supersede、新计划和逐场景记录一次创建，
  历史保留，正文不变，Run/决定 Step/Event 同事务完成。
- approve 不接受选区 editedReplacement、全文 editedContent 或 selectedUpdateRefs；规划的编辑继续通过明确的
  revise 产生新候选，不扩展公开 DTO。discard 保留审计并完成；revise 使用同一 Evidence 创建新 generation Step。
- 同 requestId 幂等、source/revision 冲突、cancel/approve 竞争、迟到 callback、失败结算和跨重启恢复必须沿用
  现有 V2 语义；不可退回 V1 收尾，也不在批准后再调用模型。

## 验证

1. 先写输出/Registry、Evidence、草案与决定的失败测试，再实施；Python/Java 使用相同输出 Schema。
2. Agent 单 Step 测试覆盖有效计划、空白/额外字段/数值越界、一次供应商调用、复审/返工、取消和完整 usage。
3. PostgreSQL Testcontainers 覆盖公共 start 到 Step/Evidence、结果到候选、详情重建、批准/丢弃/返工、来源与幂等
   冲突、无 V1 旁路和唯一计费；增加独立的章节规划跨进程场景，不借用问答通过报告。
4. CLI 命令数量与 45 命令 Skill 范围不变；补充规划 V2 输入、观察与决定说明并验证现有入口/输出兼容。
5. 运行相关 pytest/Ruff/Mypy/JUnit 和全仓门禁，再记录实际完成证据；其余未迁移 Operation、系统 Step、全量路由、
   V1 排空删除与生产验收仍保留为原始目标的剩余工作。

## CLI 与 Skill 更新说明

命令总数仍为 125，两份 macOS Operator Skill 的允许集合仍为 45；`plan_chapter` 原本就在允许集合内。
Agent 没有新增对 CLI 的直接入口，公共调用链仍是 `scripts/run.sh → Java CLI → Core /api/v1/**`。
本阶段不修改已安装 Skill 的允许范围，也不能凭本分支实现提前宣称生产规划已经使用 V2。

`long.agent.start` 的输入格式不变，下面是字段示例，ID 必须替换为目标环境中已读取的真实资源：

```json
{
  "clientRequestId": "chapter-plan-20260904-0001",
  "novelId": "novel-id",
  "chapterId": "chapter-id",
  "operation": "plan_chapter",
  "target": {"type": "chapter", "id": "chapter-id"},
  "scope": {"kind": "chapter", "chapterId": "chapter-id"},
  "userInstruction": "依据已有目标和大纲规划本章，突出主角的主动选择。"
}
```

- 202 只表示受理。保留返回的 `runId`，用既有 `long.task.get` / `long.task.watch` 观察同一 ID；即使命令字段
  仍叫 `taskId`，V2 传入的也必须是该 `runId`，不能猜造 WritingTask。按返回的 `engineVersion` 区分 V1/V2。
- V2 `waiting_user` 表示候选等待作者，不是已写入正式计划。读取 `artifact.artifactId` 对应的完整详情，确认
  `kind=beat_plan`、`payload.beatPlan`、当前 `revision` 和 `sourceBindingStatus=verified`；不读取选区 replacement。
- 详情命令 `long.artifact.get` 必须传 `{"artifactId":"artifact-id","revision":1}`；revision 取自 Run 的
  `artifact.artifactRevision`。V2 不允许省略 revision 后读取可变 head，也不能把 `expectedRevision` 当详情参数。
- 批准使用 `long.artifact.approve`，输入如下；Core 才会创建正式 ChapterBeatPlan/SceneBeat，正文不变：

```json
{
  "artifactId": "artifact-id",
  "engineVersion": 2,
  "expectedRevision": 1,
  "clientRequestId": "chapter-plan-approve-20260904-0001"
}
```

- 规划不接受 `editedContent[File]`、`editedReplacement[File]`、`selectedUpdateRefs`。要修改方案，用
  `long.artifact.revise` 和同样的身份字段，另加非空 `userMessage`；观察同一 Run 的新候选，再读新的 revision。
- 放弃使用 `long.artifact.discard`，保留相同四个身份字段但使用独立、稳定的决定 requestId；V2 保留审计记录。
- 网络结果不确定时重发完全相同的请求，不能换 requestId。来源或 revision 冲突时重新读取完整详情，不能自动
  覆盖新来源或把旧决定套到新 revision。`completed` 仍须结合最终决定和正式计划回读，不能把 discard 当成已批准。
- 既有生产 `auth.whoami` 已通过，只证明身份接线；此章节规划 V2 链仍须单独完成部署与真实业务验收。

## 跨进程负面证据

以下失败报告保留，不覆盖或改写成通过：

- `output/durable-agent-v2-e2e/20260904T114948Z-cd22fa00/report.json`：首次规划生成完成，复审降级为
  `cannot_assess`。报告证明 Core 重启后候选详情不变、丢弃完成、每 Step 一次物理调用及零扣费，但复审 Step
  失败，整轮判失败；当版诊断没有具体 token 维度，不能仅靠该报告猜测原因。
- `output/durable-agent-v2-e2e/20260904T115349Z-c9c34479/report.json`：补充脱敏 Step 诊断后复现，生成
  input/cache-miss 为 9,261，复审为 10,377、completion 为 42，错误明确为 `STEP_BUDGET_EXCEEDED`。
  Core 正确拒绝超预算进度，并接受准确失败结算，候选保留在 `waiting_user`，正文及余额不变。

两轮都未访问生产、开发库或真实供应商；结束时容器、网络、卷残留均为零，临时密钥目录已清理。测试控制器还单独
修复了自动返工 finding 缺少 Schema 必填的空 range 字段，并改用真实 Registry Schema 验证；此修复属于隔离测试
适配器，不是上述普通 pass 复审超预算的根因。

## 已通过的章节规划专项验收

修复冷缓存配置后，全量重建本地 Core/Agent 镜像并执行：

```bash
uv run python -m tests.durable_agent_v2_e2e.run_e2e --phase chapter-planning
```

报告 `output/durable-agent-v2-e2e/20260904T115848Z-e21d37f9/report.json` 为 `passed`，五个场景全部完成：

- 生成和复审各一次，Core 重启后精确 revision 详情不变，丢弃直接完成且不写正式计划。
- 批准与相同请求重放只创建一份正式计划及两个 SceneBeat，不重复模型调用、事件或计费。
- 作者显式返工创建 revision 2，两个生成、两个复审 Step 分别只调用一次，再丢弃并保留候选审计。
- 首次复审真实返回 `issues_found`，Core 创建一次自动完整返工；第二次复审 `pass` 后由作者批准。
  共四个模型 Step、两个 revision、两个 Evaluation；旧正式计划变为 superseded，历史 SceneBeat 保留。
- 提交到 Agent 前取消：零 Provider 调用、零候选、零 reservation/TokenUsage/账本写入。

四个完成场景的正文 SHA 均不变，V1 Task/Command 为零，每个模型 Step 恰有一份已结算的零金额 reservation 和
一份对应 TokenUsage，余额差及 CreditLedger 都为零。同启动/决定 requestId 重放返回同一权威结果。
八个 Agent 关键源码与镜像逐一 SHA-256 相等；最终容器、网络、卷残留为零，临时密钥已清理。
执行资产指纹为 `bb2c55cee208d59bbf1310f7902629034f6733c9a4f392921ba25fb953bbead0`。

本报告仅证明本地隔离 Fake Provider 的章节规划链。没有真实供应商、开发/生产迁移、生产账号写作或真实 2 核 2 GB
整机验收；计划当前仍有其他 Operation、系统 Step、全量路由和 V1 退役待完成。

## 全仓验证与范围收口

- 冷缓存修正后的完整 `./mvnw --batch-mode --no-transfer-progress verify`：五个模块成功；服务身份 11 项、
  服务契约 5 项、Core 667 项（3 项外部条件跳过）、Java CLI 108 项，无失败。
- 最终根 `uv run pytest -q`：4,156 passed、3 skipped；Ruff 全仓通过，Mypy 280 个源码文件通过。
- Web 324 项、生成客户端 3 项通过；`typecheck`、`lint`、`api:check` 和生产构建通过。
- 真实 JAR/shell 隔离启动器检查再次通过：本地和生产固定入口均无 Python/uv 依赖，配置、会话缺失、允许集合、
  端点绑定及包校验行为保持。CLI 新增的是规划兼容测试，不新增命令，也未在本阶段替换已安装运行包。
- 派生 Schema/manifest 检查、严格规划输入/Evidence/output、大上下文冷缓存及 `git diff --check` 均通过。
  修复过程中的 Java 固定旧 hash/旧启用集合断言已同步到新明确基线，未删除行为测试。
- 额外问答完整 `minimum` 在相同新镜像上复验通过，报告为
  `output/durable-agent-v2-e2e/20260904T121154Z-c0d8dff9/report.json`，包括回执丢失、Agent/Core 重启、取消及
  AOF 恢复。途中发现并修复验收器固定 fence=1 的假设，旧失败报告保留，分支范围与证据见 Compose E2E spec。

当前 Catalog 共 21 项，完整 V2 handler 已启用问答、章节选区改写、章节规划三项；其余 18 项仍未迁完。
本阶段没有推送 main、发布服务器或执行远程数据库变更，不把一次纵切或本机 Java 入口切换当作整体上线。
