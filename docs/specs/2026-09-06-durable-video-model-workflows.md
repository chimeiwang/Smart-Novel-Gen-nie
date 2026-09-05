# 开发视频模型工作流耐久迁移

状态：仓内接线、隔离跨进程与全仓验收完成。基线 `65ebacf` 为 19/21，本项两操作闭环后为 **21/21**。
该数字仅指仓内业务操作迁移验收，不代表真实供应商、固定 CLI 安装包或生产配置已更新。

## 目标与非目标

只迁移已有 `video.chapter_cinematic_adaptation_v2`、`video.chapter_shot_prompt_v2` 的模型调用，
保留拆镜、逐镜提示词、候选审核和作者确认语义。一次真实 HTTP 调用对应一个耐久 Step，Core 决定接续，
Agent 只执行本次冻结阶段；复用现有 journal、预算、计费、取消和恢复，不建立另一套队列或执行状态机。

不新增视频功能、公共接口、CLI 命令、取消入口、数据库列或迁移；不删除历史任务或外键。不迁移 Seedance
渲染、关键帧和整集导出，不启用生产视频，不访问真实供应商或真实数据库。本批不改变发布流程、固定 JAR
或活动 Skills。平均镜长、慢镜比例、空镜及语义建议继续是非阻断发现，不升级成作者确认门禁。

## 原业务任务与 V2 执行绑定

`VideoAdaptationTask` 同时承载原候选、冻结来源与外键，不能直接照画像任务删除：拆镜 Artifact、确认命令
以及提示词版本都引用它。保留 Task 作为原业务记录，V2 Run 是唯一执行权威，Task 的状态、检查点和结果
仅由 Core 在 Run 收敛事务中投影；Agent 不对 V2 Task 调用旧写回接口，也不建立双重调度。

- 新 Task、原完整 requestJson、Run/Evidence/首 Step 同一 `CoreDatabase.transactionResult` 提交。
  原 clientRequestId 重放先返回同一 Task，不因新路由或 Head 变化换引擎；跨两种 Task 的单活动互斥不变。
- Run.sourceType=video_adaptation_task_v2、sourceId=taskId；内部 key 为 `video-model.<taskId>`，
  不复用可能超过 128 字符的原 Task.idempotencyKey。Task 无 runId 列，不新增列，按以上绑定查找。
- Run.novelId 为真实小说，chapterId/sessionId=null，targetId=adaptationId；targetType 分别为
  video_adaptation、video_shot_prompt，提示词目标镜头集合保存于完整冻结 payload，不制造新实体。
- 改编已冻结 sourceText/hash；当前 Chapter 后续编辑或删除不使该快照失效。不能为了匹配 scopeKinds
  把 Run 绑定到实时 Chapter。提示词任务完成也不新增当前 Head 比较：旧基线候选可历史完成，仍由原
  readModel 过滤和 savePrompt 的基线检查决定能否保存。
- 失败拆镜任务的合法 dramatic checkpoint 继续按原参数匹配继承；V2 将继承事实冻结到新 Run 来源，
  不重新调用已复用的分析步骤，也不把旧执行状态作为新 Run 权威。
- 无 V2 绑定的历史 Task 仍走 V1；旧 dispatcher、旧 progress/checkpoint/complete/fail 明确排除 V2
  绑定，不能按现在的 allowlist 升级已受理任务。Task.jobId 仅保留原兼容锚，不冒充 V2 的逐 Step job/fence。
- 继续保留 VIDEO_PREVIEW_ENABLED、VIDEO_DISPATCH_ENABLED 与原命名空间。预览开启而 dispatch 关闭
  时可以登记任务但不能调用模型；通用 V2 dispatcher 的新领取和恢复必须尊重该视频门禁，其他工作流不受影响。
  生产仍在配置、Catalog developmentOnly 和部署授权层拒绝视频执行；关闭调度不阻止已有结果收敛。
  V2 领取与恢复也按原 Task.jobId 的 `video-adaptation-<namespace>-` 精确前缀过滤，不能跨开发命名空间领取。

## 冻结来源与阶段计划

唯一原始来源 `video_task_context`，resourceId=taskId，保存 taskId 和原完整版本化 VideoAdaptationJobPayload；
所有来源、设定、视觉参考、参数与历史基线按原 Task 创建事务冻结，不由 Agent 读取当前数据库、文件或 URL。
逐镜提示词实际发给模型的内容继续用原投影规则：只有每个目标自己的 Scene/Beat/Shot、来源和必要设定，
不能因完整来源已冻结就向模型额外发送整章或邻镜完整事件。图片只提供原已批准的视觉元数据，不新增读图。

现有冻结计划只有一个 generator、通用 Artifact reviewers 和全局 quality 纠正，不能准确表达电影化阶段。
增加只供这两项使用的可选 `stageSteps` 和版本化 `videoStagePolicy`：

- 每个 stageKey 绑定独立 Profile、静态 Prompt、Output Schema、lane、预算与最大调用次数；不做通用 DAG。
- Catalog 的可选 `stageSteps` 每项为 `stageKey/modelProfile/outputSchema/stepBudgetProfile/maxInvocations`，
  包含首阶段；冻结计划的同名数组每项为 `stageKey/step/maxInvocations`，其中 step 是现有完整 Step 快照。
  `videoStagePolicy` 只允许 `video.cinematic-stages.v1` 或 `video.shot-prompt-stages.v1`，程序严格核对
  对应四阶段或单阶段集合与次数，不允许新增任意节点。generator 必须等于首阶段；查找阶段不重复计算 generator。
- 现有 19 项及历史无 stageSteps 计划的字段、解析和 canonical 序列化保持原样，不向旧快照补空字段，
  不重算历史 hash；新阶段引用必须纳入同一个冻结 planSha256。
- 阶段均为 generation Step，即生成领域结构、候选或审镜结论，不是通用 ReviewArtifact 的 reviewer。
  cinematic_review 有独立明确命名的 Profile/Schema，不取消原审镜，也不要求提前伪造 Artifact。
  原未启用的通用 cinematic reviewPolicy 占位改为 none，真实审镜由冻结视频阶段策略明确保存。
- requireStep 必须按 purpose、Profile、版本、Schema、预算完整身份选择阶段，不能只看 purpose，
  也不能接受 Agent 自选任意 Profile 或自报下一节点。阶段输入与前序产物在 Core 内校验后冻结。
- 不同阶段的结构纠正和审镜返工是领域阶段次数，不冒充全局 `protocol_correction`；Run 的通用纠正额度
  不扩大。每次领域纠正有明确前序 Step、原因和阶段次数，仍逐次占用总调用、token、费用与墙钟预算。

## 原拆镜阶段与有限接续

实际 V1 正常调用为分析、设计、审镜三次；有一次审镜返工时通常五次。原合法结构纠正和补槽都算入后，
一次执行最多十次：分析最多两次、完整设计最多三次、补漏槽最多三次、审镜最多两次。Catalog 旧值 5 是
未启用占位，不是原业务已有的任务调用硬限制，不能直接启用它来削减原能力。

1. dramatic_structure：按原完整来源单元和动态 sourceUnitIds Schema 分析并物化稳定 Scene/Beat/Goal
   与范围。首次协议或结构错误可按原固定安全要求完整重做一次；再次失败终止。正常结果由 Core 保存
   耐久 Step，并投影原 dramatic checkpoint 后进入设计。
2. shot_design：消费完整冻结 checkpoint、原文单元和原正式基线。保持原 Beat 槽归位、完整设计与结构
   校验规则；首次完整设计可有一次结构重做，审镜返工的设计不再取得额外结构重做。
3. missing_beat_shots：一次完整设计若缺 Beat 槽，只为冻结的遗漏槽调用一次补全；已完成槽保持原样，
   返回槽集合必须精确匹配。补槽自身不纠正。补槽成功后物化失败可沿初始设计的剩余结构重做额度处理，
   不能额外赠送调用。补槽后原建议集尾清空规则不变。
4. cinematic_review：读取完整候选和原确定性发现，返回原 CinematicReviewResult 并合并发现。首次
   revise 触发最多一次完整设计返工，再审一次；第二次仍 revise 时保留结论及发现交作者，不稳定失败，
   不据历史规格把软质量建议恢复成硬门禁。Reviewer 自身没有额外协议纠正。

## 原逐镜提示词与结果信封

提示词是一个目标批次一次模型调用，不改成逐镜循环。按原目标顺序完整返回，每批最多 120 镜，最多一次
完整纠正，随后硬错误失败，语义问题按原最多 12 条 warning 保存候选。动态目标 Schema、景别规范化、
视觉参考投影与 360/480/640 字编译预算全部复用原规则，不静默截断或自动保存 PromptHead。

每阶段输入使用精确判别类型，包含 stageKey、初始/审镜返工轮次、该阶段纠正标记，以及必要的完整
checkpoint、design、candidate 或纠正原因；这些材料必须来自同一 Run 的冻结来源或已完成 Step。
输出使用程序包装的阶段结果：可用规范化产物、明确需要补槽、或已解析但需要纠正的验证发现；不是模型
自报执行策略。Core 根据固定状态转移和次数决定接续，不接受通用 next-call 请求。

失败 callback 不新增 message/details：坏 JSON/协议失败用稳定错误码映射原固定安全纠正要求，不保存
坏参数原文；成功解析后发现的提示词质量问题保存类型化 validationFindings（镜号、稳定 code、受控参数、
blocking）和完整可解析批次，使 Core 能生成下一次原具体要求，不能把正文塞进错误码或伪造字符串诊断。
补槽供应商响应本身不完整、协议或 Schema 错误、返回槽集合不匹配时直接失败，不返回可重做的阶段结果；
只有合法补槽与原设计合并后的物化错误才可能使用初始设计尚未消耗的结构重做额度。

### 共享视频阶段契约

`VideoTaskContextV2` 精确包含 `taskId,payload,inheritedCheckpoint`，其中 `payload` 复用原完整
`VideoAdaptationJobPayload` 判别联合；`inheritedCheckpoint` 必填且可空，提示词任务必须为空。
Run.input 固定 `{taskId}`。首设计可使用来源中继承的 checkpoint，不伪造一个已完成分析 Step。

各输入固定共同字段 `stageKey,cycle,correction,dependencies`：`cycle` 为 0（初始）或 1（审镜返工），
`correction` 为布尔值；`dependencies` 是按原 ordinal 有序的 `{stepId,resultHash}` 数组，列出截至本
Step 的全部因果前驱，包含失败纠正依据，最多 9 项。Core 从原结果复制完整产物并核对哈希，首输入为空依赖。

| stageKey | 额外输入字段 | 输出字段（除 stageKey/outcome/validationFindings） |
| --- | --- | --- |
| dramatic_structure | correctionFindings | checkpoint（可空） |
| shot_design | checkpoint,requiredChanges,correctionFindings | design（可空）,candidate（可空）,missingBeatKeys |
| missing_beat_shots | checkpoint,design,missingBeatKeys | candidate（可空） |
| cinematic_review | candidate | review |
| shot_prompt | correctionFindings | promptBatch（可空） |

以上字段无隐式默认省略；普通阶段的 correctionFindings/requiredChanges 为完整空数组。dramatic 与 prompt
只允许 cycle=0；missing/review 的 correction 必须为 false；审镜返工 design 的 correction 必须为 false，
requiredChanges 必须精确来自首 review（允许保留历史空数组而不授予结构纠正）。初始 design 的 requiredChanges 为空；结构纠正使用专门
correctionFindings，不能混成语义返工。input 不含当前正文、网络地址、动态工具或下一次请求。

`outcome` 只允许 `ready,needs_correction,needs_supplement` 的阶段适用子集；ready 必须有该阶段完整
规范化产物，needs_supplement 仅用于设计并携带完整可解析归位设计和精确遗漏槽，needs_correction 只携带
安全发现（提示词另保留已成功解析的完整批次）。review 只允许 ready。输入和输出均禁止额外字段。
`VideoStageValidationFinding` 固定 `code,shotKey,parameters,blocking`；code 为封闭枚举，shotKey 必填
可空，parameters 按 code 校验完整字段名、非负计数和有限的景别/效果/动作/字段名列表，禁止任意字符串。
渲染器据这些字段还原原具体纠正要求；供应商坏 JSON、未知字段名、异常正文不得进入这些字段。
协议失败使用 `VIDEO_STAGE_PROTOCOL_CORRECTION_REQUIRED` 和固定 `protocol_invalid` 发现；只有完整六项
token 明细可靠，且供应商已知结束（stop 或原视频允许的明确 length/content_filter incomplete）时，
分析、初始设计、提示词首轮才允许 Core 结算后创建独立完整纠正阶段。不续接半截正文；unknown finish、
未知用量、补槽、审镜、已纠正及审镜返工阶段均不获额外纠正。此兼容不改变其他 19 项完成原因规则。
合并审镜结果使用
`VideoCinematicReviewConclusion`（字段形状不变，中间 findings 最多 1203）；模型原始
`CinematicReviewResult` 仍最多 240，最终公开候选仍最多 480。中间保守上界按候选已有 480、
每 Beat 两类缺目标最多 240、每镜无目标最多 120、邻镜重复最多 120、全局提示 3、模型 240 合计；
每 Beat 至少一镜且方案总镜头最多 120。首轮 481 条发现仍可按原 revise 完整返工，不能在中间提前拒绝；
最终由 Core 按冻结 candidate Schema 的 480 上限复验，超限明确失败并保留所有已发生调用结果和用量，不截断。

独立 profile 为 `video.dramatic_structure.v2,video.shot_design.v2,video.missing_beat_shots.v2,
video.cinematic_review.v2,video.shot_prompt.v2`；静态 Prompt key 为对应 `prompt.` 前缀，Output key 为
`output.video_<stageKey>_stage.v2`，Step Budget key 为 `step_budget.video.<stageKey>.v2`，版本均为 2。
前四 profile 使用 `deployment.video.chapter_adaptation.v2`，提示词使用 `deployment.video.shot_prompt.v2`。
两项 Catalog 已完成接线与隔离链路验收；原空 `output.video_adaptation_plan.v2` 占位不作为模型输出 Schema。

每阶段 input/cacheMiss 资源预算各 240,000，墙钟 300 秒，providerRetries=2、本地规范化次数=1。
单次可见输出按阶段为 48,000/48,000/16,000/12,000/48,000，金额上限为
1,500,000/1,500,000/1,000,000/1,000,000/1,500,000 供应商成本微单位（costMicros，不是用户积分）。改编 Run 的十次调用总预算为
input/cacheMiss 各 2,400,000、可见输出 312,000、金额 13,000,000、墙钟 3,000 秒；提示词两次为
input/cacheMiss 各 480,000、输出 96,000、金额 3,000,000、墙钟 600 秒。全部关闭 reasoning。
这是本轮显式有界资源限制，不承诺任意长度请求与 V1 等价；完整消息和动态模型 Schema 在调用前估算，
超限明确失败，绝不截断输入或输出。视频每 Step 不做内部 HTTP 重发，重试参数不授权隐藏的第二次调用。
用户积分仍按 Core 原单 Step 最坏 token 预算预留，可靠用量返回后按实际 token 结算：以上 48,000 输出阶段
需可用 336 积分，补槽为 272，审镜为 264；不是一次扣除此金额，也不是预留整个十阶段总额。
缺少可靠用量时维持原待对账预留，不伪造零消耗。该资源限制和预留要求属于本轮 V2 的显式行为，
隔离测试使用独立测试账号，不能靠修改真实账号余额证明业务可用。

## 真实 Responses 传输与用量

旧视频仅支持官方 DeepSeek `deepseek-v4-flash`，使用 `POST https://api.deepseek.com/responses`，
不是普通 Chat JSON 或 Beta strict。保留 model/input/max_output_tokens/text.format(type/name/schema)
和 reasoning.effort=none，无 tools、无 strict:true；完整本地 Schema 与原供应商子集投影分别校验。

新增窄的 V2 Responses adapter，并复用同一个 ModelRuntime 全局 limiter。不得全局切换 Provider 影响
前 19 项，也不让旧 V1 自动获得新行为。真实 deployment/endpoint/capability 必须明确区分 Responses；
测试替身只限 test 环境，不把 fake 冒充官方供应商能力。SDK/HTTP 不做隐式重试，未知已开始调用不盲目重发。

旧 `_usage_from_payload` 缺用量默认零的行为不能复用到 V2。新独立结果类型保留实际 providerResponseId
和可靠的 nullable 用量，不为满足 ModelUsage 必填字段补零，也不编造 cached/reasoning/cost。无可靠用量
不能通过有问题的响应取得新的纠正调用；已知结果和未知费用按现有 Core 审计规则收敛。真实账务仍收费，
不沿用 RAG 的免用户积分配置。单 Step 本地确定性 JSON 规范化沿原允许范围审计，不冒充额外 HTTP。

## Core 业务物化与 CLI

领域拥有 `WorkflowVideoAdaptationCompletion`，提供处理状态投影、dramatic checkpoint、最终拆镜候选、
最终提示词批次、失败/取消投影。根据冻结 Run→Task 查业务，不伪造旧 taskId/jobId/runId 回调身份。
全部失败路径都必须投影 Task 终态，不能留 pending 阻塞下一次作者请求。

- 拆镜完成仍只创建原 video_adaptation_plan ReviewArtifact，保留 videoAdaptationTaskId；作者按原
  confirmPlan 双 revision/CAS 批准后，才创建正式 Plan/Scene/Beat/Shot 和 Head。
- 提示词完整候选仍存 Task.resultJson，原 candidateTaskId→savePrompt 复制冻结视觉参考并保存正式版本；
  不直接修改 PromptHead，不借用长篇写作批准接口。
- `long.video.plan.start`、`long.video.prompt.start` 与原轮询 watcher、参数、响应及退出码保持不变。
  受理仍返回原 Task 聚合，停止 watch 不等于取消；不新增 SSE、long.agent.start 别名、Agent 直连或
  Operator 权限。CLI/Skills 维护文档须区分内部逐阶段恢复与外部原任务身份。

## 验收

1. 新阶段计划与历史计划黄金向量往返；每阶段精确 Profile/Prompt/Schema/预算、前序来源、次数和非法转移。
2. Agent 原提示词及动态 Schema、完整源投影、原确定性规范化与 warning 语义等价；真实 Responses HTTP
   body/状态/结构/未知用量、并发/取消/无隐式重试的隔离单元测试。
3. PostgreSQL 与原 HTTP 覆盖新旧任务隔离、原子绑定、单活动互斥、checkpoint 继承、完整候选与作者确认、
   提示词冻结参考和 Head CAS；实时 Chapter/Head 变化不新增拒绝；dispatch=false 不调模型。
4. 独立 Core/Agent/PostgreSQL/双 Redis 的受控模型验收，至少覆盖阶段结果 journal 后重启不重调、完整拆镜
   与作者确认、提示词一次纠正及原保存路径；不用真实供应商/真实库，不开启生产视频。
5. 全仓 Java/Python/Web、静态/类型/构建、契约与 manifest 导出门禁；只有通过后才分别计入 20/21、21/21。
   整体重构、固定 CLI/活动 Skills、真实环境与上线状态仍分开报告。

## 最终验收记录

- 2026-09-06：当前 manifest 为 `920ca5f4a4b98e078bdf620dcc4f1b2e943d2290029718aa3aa749277ad15b75`；
  316 个共享 Schema 可机械重现，原 19 个 Operation JSON 与基线 `65ebacf` 逐值不变。
- Java 定向检查 187 项、零失败，1 项既有跳过；随后最终候选包络复验增加测试，完整回调组 65 项全绿。
  日志分别为 `/tmp/inkforge-video-v2-targeted-4.log`、`/tmp/inkforge-video-v2-final-candidate-1.log`。
- 独立 Core/Agent/PostgreSQL/双 Redis 使用本轮新构建镜像，运行
  `uv run python tests/durable_agent_v2_e2e/run_e2e.py --phase video --evidence-dir output/durable-agent-v2-e2e/20260906-video-1`
  成功。证据 `output/durable-agent-v2-e2e/20260906-video-1/report.json`：拆镜三个阶段各一次物理调用，
  首结果已 journal、终报尚未送达时重启 Agent，恢复后首阶段不重调；原作者确认创建正式方案成功。
  提示词首批产生明确 `prompt_budget` 原因，第二 Step 完整纠正，原 candidateTaskId 保存正式提示词成功。
- 两场景分别 3/2 个完成 Step、对应 3/2 条结算与 TokenUsage、各唯一终态事件，零通用 Evaluation；
  保留原业务 Task，无 V1 队列回退。Fake 仅 test 授权且免收费，所以余额变化为零，不能据此声称真实视频免费。
  Core 镜像为 `sha256:2f67ca8aae172b1372087eac1d251bea91944054514dead18e06cbabae205429`，
  Agent 镜像为 `sha256:4124e516019f0aaded8debff25fc7c6933234f9521e896c5eda914ba3696d53e`。
  容器、网络和 volume 残留均为零，临时密钥目录已清理；2 核 2 GiB 主机容量仍为 `not_proven`。
- Web 类型、lint、构建、公共 API 客户端检查通过；Web 347、API 客户端 3 项全绿。机器核对公共/内部
  Core 操作仍 152/34、普通 CLI 125、Operator 45，名称与路由集合均未变；固定 JAR 与活动 Skills 未更新。
- `./mvnw verify` 全量成功，身份 11、共享契约 5、Core 1205（3 项既有跳过）、Java CLI 135；日志
  `/tmp/inkforge-video-v2-maven-all-2.log`。首轮仅因测试编译时仍保留视频“尚未启用”的旧断言失败，
  已改为验证开发专用门禁并完整重跑，不修改业务门禁来迁就测试。
- 全量 pytest 5523 通过、3 跳过、1 项既有 Starlette 警告，日志
  `/tmp/inkforge-video-v2-pytest-all-2.log`。三个跳过都是未显式提供服务器 dev 库地址的旧视频库测试，
  不是使用真实库证明本次迁移。首轮测试仍断言 HTTP 超时 120 秒，已同步为保持原 SDK 的 600 秒默认值，
  随后全量重跑通过；实际 V2 单 Step 仍受 300 秒 Runtime 墙钟预算约束。
- 全仓 Ruff、Mypy（294 个源文件）、manifest、316 个共享 Schema、Core 19 文件与 Agent 契约导出检查全绿。
  本次原公开接口和 CLI 名称、参数及退出码未变，CLI/Skills 维护说明已更新到
  `docs/specs/2026-09-01-durable-agent-v2-operator-skill-update.md`。
- 未进行远程写、生产部署、真实数据库变更、真实模型调用或活动 Skill/固定 JAR 更新；Fake、单机开发
  验收及仓内门禁不能冒充这些仓外结果。发布流程保持个人项目原入口，没有重建额外发布控制面。
