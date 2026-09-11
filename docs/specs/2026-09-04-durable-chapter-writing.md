# Durable Agent V2 正文写作纵切

日期：2026-09-04。状态：显式正文写作纵切本地验收完成；总重构仍在实施。

本文的首版输入预算已由 [2026-09-11 正文写作输入预算调整](2026-09-11-chapter-writing-input-budget.md)
更新；下文 30,000/180,000 保留为 v1 设计与当时验收事实。

## 目标与范围

继续 `2026-08-31-core-owned-durable-agent-execution.md` 的完整重构目标，不以本纵切替代其余 Operation、
系统用途、V1 退役、开发/生产迁移及真实账号验收。开始时 HEAD 为 `a0b6a98`，工作区干净、无残留测试进程；
上一阶段章节规划及全仓门禁已完成，属于真实进展。Catalog 当前 3/21 项 V2 启用，仍有 18 项待迁移。

本阶段完成 `long_serial.write_chapter` 的完整正文生成、同 Evidence 双复审、一次自动修改、作者返工、
普通/编辑批准、丢弃、取消及恢复；继续当前分支，不推送 main、不部署、不访问远程数据库或真实模型。
普通显式写作入口仍绑定现有章节，不借正式应用器已有的 `new_next_chapter` 分支扩大成自动新建章节。

## 公共输入与 Evidence

- 保持现有公共 `write_chapter`、同章 target/scope、完整 userInstruction、targetWordCount、可选会话和
  稳定 clientRequestId；拒绝选区输入。V2 只创建 WorkflowRun/Step/Evidence，不创建 V1 Task/Command/Graph。
- 新增组合式 `ChapterWritingEvidenceReader`，由 reviews.application 端口和 reviews.infrastructure SQL 实现，
  供 writing starter 与批准来源复验共同调用，不形成 reviews → writing 反向模块依赖。
- 复用规划 Reader 的章节目标、批准计划/全部节拍、大纲及路径、当前/之前章节进展、剧情、相关设定与伏笔。
  给相关性选择提供独立的额外文本参数以纳入目标章已出现实体，不能把完整正文拼进真正的 userInstruction，
  默认入口必须保持现有规划快照与哈希不变。
- 写作另冻结完整目标章正文及身份/版本，小说 summary/storyProgress/appliedStyleId，前后各一章的标题、顺序、
  状态、时间与程序字数，以及当前已选文风画像。相邻章按现有顺序选择而非 order±1；不把截断的邻章正文冒充摘要，
  不把完整相邻章节自动注入提示。正文为空表示来源存在且为空，不是 absence。
- 已选文风仅来自 Novel.appliedStyleId → 同作者 WritingStyle 的完整 portraitMarkdown 与相关版本字段；
  未选择、未生成画像明确记录，不读取 StyleReference 文件路径或原始文件。不存在现成 styleMode，不伪造该输入。
- 唯一 `chapter_writing_context` JSON Evidence 包含完整投影和 sourceBindings；所有选择/缺失都参与哈希。
  批准以同一 capture 重新选择并核对内容/版本，检测新增、删除、重排、文风切换及相同时间戳下的内容变化。
- 生成、复审、完整返工与局部 patch 使用同一不可变 bundle。Agent 校验唯一 JSON context、存在/无 range、
  schemaVersion、小说与章节身份，不回读可变 workspace；需要扩展的通用系统用途仍属原总目标后续工作。

## 严格输出与预算

Provider 只返回 `summary` 与 `content`：summary 为 1～1000 个 Unicode 码点且非空白的完整说明，content
为完整非空白正文，不设任意字符硬上限，不允许混入 ID、target、hash、字数、reviewerAgent、工具或业务控制字段。
不引入旧 ARTIFACT_OUTPUT 标记回退。正文按原始 UTF-8 派生 contentSha256，wordCount 复用 Web/Core 明确的
Unicode 空白和 BOM 排除规则，不能用裸 len 或 Python 的宽泛空白集合。Core 独立复验两项派生值。
Core 将现有章节纯计数提取至 platform.text.TextLength，旧章节入口委托该实现，避免工作流反向依赖章节模块。

初始 Step input 仅 userInstruction/targetWordCount；返工另加成对的 originalUserInstruction 和精确
previousArtifact{artifactId,artifactRevision,payload:完整结果}，与章节规划使用相同身份字段。
复审 input 为 task/candidate，保留原始要求 A 与本轮修改 B。
targetWordCount 是创作目标而非截断指令或篇幅承诺；不新增无依据的硬比例门禁。length/content_filter 等不完整
输出明确失败，不保存半截成功，不自动续写；大上下文超过冻结预算也必须完整拒绝而非裁切。

成套启用 `writer.chapter_draft.v1`、专属 Prompt/Deployment/Output，并新增
`reviewer.chapter_draft_consistency.v1`、`reviewer.chapter_draft_editorial.v1`。校验核对事实，编辑核对整章
行动/叙事与阅读效果，不复用选区外衔接提示。Reviewer 关闭 thinking，正文使用受限高推理 Profile。

首版沿用 Catalog 六次调用及 Run 40,000 completion / 16,000 reasoning / 24,000 visible / 2,000,000
costMicros / 900 秒的上限：生成各 16,000 completion（8,000 reasoning、8,000 visible）、600,000 costMicros、
300 秒；两类复审各 2,000 completion/visible、零 reasoning、200,000 costMicros、75 秒。
每 Step input/cache-miss 均 30,000，Run 两者均 180,000，不能依赖冷缓存命中。部署 384,000 的能力上限不再
被当作每一步的统一预算，也不宣称此 Profile 可以完成公共目标字数参数允许的任意大请求。

## 双复审与确定性局部修改

- 两个并行 Reviewer 绑定同一候选 revision 和 Evidence，分别保存 Evaluation，Core 按新版本化 merge policy
  合并；不可用、无法判断、结构问题、职责结论分歧或第二轮仍有问题时保留候选交作者。
- 给共享 EvaluationFinding 新增可选 `candidatePatch`：严格 `{kind:"text_replace",find,replace}`。
  find 非空且原样保留，replace 可为空表示删除；不含资源 ID、revision、hash。suggestion 仍只是解释文字，
  绝不从其中解析可执行替换。使用写作专属 Reviewer Output Schema，旧选区和规划 Schema/Policy 不变。
- 新字段只在非空时进入终报哈希/持久映射；不能给旧 finding 无条件补 candidatePatch:null，使旧闭合 Schema
  失效或改变旧结果哈希。写作 Schema 将该字段设为可选。公共/internal 操作数不变，机械导出共享 Schema/Java DTO。
- 两个 Reviewer 都完成且明确指出局部问题，所有待处理 finding 的 confidence≥0.8，才允许一次自动修改：
  全部有结构化 patch 时走确定性 patch；全部没有 patch 时可创建一次完整返工 generation；混合提议交作者。
  每次自动修改后必须再做双复审。不能仅因 soft warning 直接应用正式正文。
- patch 基于同一个原候选定位，精确相同提议可去重，去重后最多 20 个；原文零命中、多命中、替换冲突或范围重叠
  时原子放弃自动修改并交作者，不能降级为完整 rewrite。如提供 candidateRange，必须与 Core 定位的 Unicode
  码点范围一致。全部定位成功后逆序应用并复验完整正文非空、hash 和字数，不部分提交。
- patch 是 Core 同一复审合并事务内的真实 `WorkflowStep(stepType=persistence,purpose=candidate_patch,
  lane=control)`：记录 policy、旧 revision、Evaluation/finding 引用及结果哈希，追加新 revision 并排入双复审。
  它不是模型 System Purpose，不伪造 Profile、Provider、usage 或 BillingReservation，不调用 Agent。
- 自动修订计数必须同时计入 generation 与 candidate_patch，不能在 patch 后因模型生成次数没增长而再自动修改。
  作者 revise 也受原 Run 剩余预算约束；不足以完整生成并双复审时明确拒绝，不隐式抬高冻结预算。

## 候选持久化与正式应用

- 以独立 `DurableChapterDraftArtifact` 语义保存完整正文一次、summary、hash/字数和 Evidence/来源/Step 身份。
  每个 revision 不在 payload/diff 再存完整 before/after，既有 head 投影保留；generation Step.output 只留引用。
  精确详情从冻结 Evidence 与 revision 重建完整 payload 和全文 Diff，不伪装成 selection/replacement。
- 复用 `chapter_draft` 公共 kind，规范 payload 标明 write_chapter 与当前章节目标；普通/编辑采用必须通过
  Run → Artifact/revision → Novel → Chapter/来源的一致锁顺序与 revision/source CAS。
- V2 公共决定语法允许 approve 的 editedContent 或 editedReplacement 二选一，但具体类型由 Core 权威 Artifact
  决定：write_chapter 仅允许 editedContent，选区仅 editedReplacement，规划均不允许；selectedUpdateRefs
  继续禁止，revise/discard 不接受 edited 字段。先改 Python/Pydantic 契约，再对齐 Java/CLI/Web。
- editedContent 为完整非空白正文；先追加用户编辑 revision，再同事务复用 FormalArtifactWriter。普通批准同样
  复用现有全文应用器：覆盖当前章、回到 drafting、清 completedAt、创建或失效一致性检查、取消旧活动质量运行。
  保持目前即使采用相同正文也重置质量状态的既有语义，不借此做编辑器保存行为统一。
- 不自动送审/完成章节，不写 ChapterProgress、PlotProgress、StoryProgress、Beat Plan、设定或伏笔；不创建下一章。
  discard 保留审计并完成；用户 revise 产生新 generation/revision；幂等、取消竞争和迟到回调沿用 V2 规则。

## CLI、界面与验证

CLI 命令数 125、Skill 45 命令和三个允许 Operation 不变。正文草案 V2 允许既有
`long.artifact.approve` 的 editedContent/editedContentFile，精确读取对应 revision 后判类型；不能扩大规划和
选区的字段。Java/Python 对照及 Web 决定请求同步，写清 Skill 更新文档。若实际 Java CLI 行为变化，完成构建、
隔离入口验证后显式更新本机已安装包及来源记录，不把源码变更当已安装生效；生产开放仍另行验收。

先测试后实现，至少覆盖：

1. 全文 Unicode/空白/BOM/NEL、summary、额外字段、错误完成原因、字数/hash、冷缓存与不裁切的大输入输出。
2. Evidence 完整且最小、同 bundle、absence/同时间戳内容变化、文风归属与切换、相邻章选择和无 V1 旁路。
3. 双 Reviewer 职责/输入 A/B/精确 revision；完整返工与无模型 patch、新 revision 再审、冲突/分歧/不可用及限次。
4. 普通/编辑采用、唯一正式写入、质量失效和旧回调隔离；其他数据层前后不变；source/revision/取消/幂等竞争。
5. 专属跨进程 Fake 验收包含生成、双复审、重启、普通/编辑批准、手动/自动返工与 patch、取消、零重复计费；
   不借用规划或问答报告。CLI/JSONL 和前端相关测试、完整 pytest/Ruff/Mypy/JUnit/Maven/Web/契约门禁。

未完成上述全部范围前不标记正文写作迁移完成；本纵切完成仍不标记整个重构、生产迁移或真实模型验收完成。

## 实施验证记录

2026-09-04，本分支实现已完成以下本地集成验收，并显式更新本机固定 CLI 包；未部署服务器。

- 正文 Evidence/启动、严格输出、双复审、候选局部修改/完整返工、普通/编辑决定及 CLI/Web 接线已落盘。
- 先失败测试后修复了 BOM-only 编辑内容、Java/Python 广义空白与统一码点规则的差异。
- 独立复核发现作者返工原来只检查调用次数，可能在已耗 100,000 input、下一整轮需要 90,000、
  Run 上限 180,000 时错误受理。现复用既有 Run 保守预算核算，受理前预检完整生成与双复审；
  不提高预算，不接受只够生成却不够复审的返工。未知用量、各 token/费用/墙钟与原子拒绝测试已通过。
- Python 全仓：4,286 passed、3 skipped；仅既有 Starlette 弃用警告，日志
  `/tmp/inkforge-chapter-writing-python-final.log`。Ruff 全仓通过，Mypy 280 源码文件通过。
- Web 327 项与 API 客户端 3 项通过；typecheck、lint、api:check 和生产构建通过。
- Java 完整 `./mvnw verify` 五个 reactor 全通过：服务身份 11、共享契约 5、Core 692（3 skipped）、
  CLI 120；日志 `/tmp/inkforge-chapter-writing-maven-release.log`。Core 数据库测试使用 PostgreSQL。
- 两环境真实 JAR/shell 隔离验证通过：配置安装、无 Python/uv 启动、缺会话、命令白名单、端点绑定及包校验；
  日志 `/tmp/inkforge-chapter-writing-launchers-final.log`，未读取真实业务凭据或连接生产。
- 写作自己的 Compose 验收 8 个场景通过，报告为
  `output/durable-agent-v2-e2e/20260904T130910Z-d055e572/report.json`，不借用上轮规划或问答报告。
  Core 重启丢弃、普通批准、作者返工、自动全文返工、局部 patch 后双复审、patch 冲突丢弃、千段完整
  Unicode/CRLF 编辑批准、submit 前取消均通过。七个完成 Run 的模型 Step 数为 3/3/6/6/5/3/3，
  每个物理调用一次且计费记录精确匹配；patch 为独立零模型 Step，取消零模型调用/零预留。
  七个 Run 前后其他创作数据层哈希一致，批准后旧质量结果清空；无重复应用、版本或计费。
  清理后容器、网络、卷均零残留。

当前执行资产指纹为 `db01dc57f7d2e92dd55f814d714ff613584db500a8fce42d59860ef7e1fc3ce5`，
共享 Schema 226 个，Catalog 4/21 已启用。其余 17 项及系统用途、V1 退役、真实环境切换与账号验收仍属原目标，
不因本轮正文接线完成而视为已完成。
重新核对 route-inventory 与 CLI registry：公共 Core 151、内部 Core 34、供应商媒体入口 1、CLI 命令 125，
本轮均未新增操作；只演进现有决定语法和共享内部可选 finding 字段。

首轮完整 Maven 的三个失败为旧 Catalog 仍只列三项/把 write_chapter 当未启用，以及旧指纹断言。
已按真实资产更新，并保持 rewrite_scene、视频和未实现系统用途的拒绝测试；完整门禁重跑通过。

首轮写作 Compose 报告 `output/durable-agent-v2-e2e/20260904T130235Z-785a0d92/report.json` 为失败，
保留原报告：Core 重启丢弃、普通批准、千段完整 Unicode/CRLF 编辑批准已通过；后续手动返工继承了该大篇幅
正式正文，两次生成输入为 27,593/27,916，四个 Reviewer 都在模型调用前触发 STEP_INPUT_BUDGET_EXCEEDED，
只产生 cannot_assess 并保留候选，没有截断或重复计费。失败来自共用章的用例互相影响，不是完整编辑采用失败。
现将大篇幅编辑场景排到普通返工/patch 场景之后，保留完整千段输入、字节哈希和尾段验证；
不缩小正文、不抬高冻结预算，也不宣称任意大来源都可完成双复审。清理后的容器、网络、卷均零残留。

第二次报告 `output/durable-agent-v2-e2e/20260904T130708Z-ef954850/report.json` 在 Compose up 返回 1，
未进入业务场景；原 runner 只保留 stderr 字节数及哈希，现有证据不足以确定启动失败原因，不能归因于业务逻辑
或断言已经修复。清理后容器、网络、卷均零残留。完整 Java 测试结束后，以显式 infrastructureRetry=1、
相同已构建镜像单独重跑。

成功报告复用的 Core 镜像为 `sha256:7509f5999beab667b2bb1cb4e8b75ed3c504829b8186a6d4c781b18f41fef525`，
Agent 为 `sha256:f5108586d32cfb50d363a3eddef459379d5c146ff55025c078e43bd788e2b9d5`；
Agent 关键源码与镜像哈希一致。报告保留 infrastructureRetry=1，不将前两次失败伪装成首次全绿。

### 本机 CLI 生效记录

两份已有 Skill 的 configure.sh 已重新安装构建后的固定运行包；脚本及 Skill 说明文件未修改。
新 JAR SHA-256 均为 `4e6a74f70a7ec5137534e31f0d0c2745966052d98592f4fafd355d32b57e5ec0`，
来源 revision 为 `a0b6a98913066f3d66e8d06a4274ab4f21d949a5`、repositoryDirty=true，真实标记包含本轮未提交实现。
安装后校验与构建包哈希一致，实际两份 run.sh 的离线帮助成功；origin/profile/用户名/Java 路径和 schemaVersion
与更新前一致。旧包及原配置完整保存在 `/Users/boqiangnie/.codex/inkforge-cli-writing-backup.9hh3ty`，可恢复。
本轮没有读取/迁移 Keychain 凭据、没有登录生产，也没有修改 Skill 命令白名单。

### 仍未完成的原目标

普通 Web 聊天的无选区入口仍发送旧请求并走 V1；本次显式 write_chapter 验收不能证明自然语言聊天已迁移。
后续按原总 spec 实施 resolve_intent 与请求规范化、其余既定操作和需要的系统用途，再完成 V1 新入口退役、
在途任务收敛及真实开发/生产切换验收。生产视频继续关闭，protocol_correction 的预留状态不擅自扩大成本轮门禁。
