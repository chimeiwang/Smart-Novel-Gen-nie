# 小说级多模态视频制作系统重构规格

## 文档状态

- 初始日期：2026-08-07
- 状态：历史研究背景；产品范围、领域模型和实施边界已由
  `2026-08-08-novel-to-video-product-architecture.md` 与
  `2026-08-08-novel-to-video-detailed-design.md` 取代
- 当前适用作品：仅 `long_serial`；本文中关于 `short_medium` 接入、篇幅中立和旧纵向切片的描述均不再是需求
- 替代对象：已撤销的中短篇纯文本 Seedance 提示词预览原型
- 数据库状态：该日的对话授权仅作为历史记录；当前是否允许 DDL 以仓库 `AGENTS.md`、`DOCS.md` 和
  2026-08-08 详细设计的实施门为准，本研究稿不再提供迁移授权

## 结论先行

旧原型不应继续修补。当前产品决策是建立长篇专用多模态视频制作域，永久不开发中短篇视频入口、
适配器或兼容工作流；本文其余内容只保留供应商能力、提示词和旧原型问题的研究价值。

同时，旧的固定 schema 不能安全承载正式版：现有 `ReviewArtifact` 强制绑定 `WritingTask`，现有
持久命令只服务写作任务，现有上传只接受 UTF-8 文本。把视频项目、审核、任务和计费事实放进对象存储，
会绕开 PostgreSQL 事务、正式审核链和崩溃恢复。因此本规格明确分成两个交付边界：

1. **制作包验证版**：先验证小说改编、视觉规范、素材需求、分镜、引用打包和提示词编译；只导出用户
   下载的不可执行制作包，不创建正式视频项目、不扣费、不提交供应商。
2. **正式生产版（历史设想）**：本稿不再是 schema、ReviewArtifact、计费、队列、迁移或实施依据；这些
   边界完全以 2026-08-08 两份长篇专用设计为准。本文仅保留供应商能力、提示词研究和旧原型问题分析价值。

## 背景与事实边界

此前原型把视频化建模为“中短篇正文生成若干纯文本镜头提示词”，并把入口、任务、结果和
Seedance 配置直接绑定到 `short_medium`。该模型不能表达真实参考素材、人物与场景锁定、跨镜状态、
长篇分集、素材版本或生成后质量检查，继续扩展会把错误边界固化，因此代码已经全部撤销。

截至 2026-08-07，火山方舟已公开 Seedance 2.5 API，模型 ID 为
`doubao-seedance-2-5-260628`。官方教程、提示词指南、任务接口和授权人像资料为：

- <https://www.volcengine.com/docs/82379/2607688?lang=zh>
- <https://www.volcengine.com/docs/82379/2607689?lang=zh>
- <https://www.volcengine.com/docs/82379/1520757?lang=zh>
- <https://www.volcengine.com/docs/82379/2315856?lang=zh>

已确认的方舟 API 基线：

- 异步创建接口为 `POST https://ark.cn-beijing.volces.com/api/v3/contents/generations/tasks`，创建后按
  task ID 查询；`content[]` 承载文本和媒体，参考图示例使用 `image_url` 与
  `role: "reference_image"`；
- `resolution` 只支持 `480p`、`720p`，明确暂不支持 `1080p` 和 `4K`；
- `duration` 支持 4～30 秒或 `-1` 自适配；编辑任务只能使用 `-1`，被编辑视频须为 4～30 秒；
- `ratio` 支持 `16:9`、`4:3`、`1:1`、`3:4`、`9:16`、`21:9`、`adaptive`，编辑、延长、首帧和
  首尾帧任务存在只允许 `adaptive` 的限制；
- 单次多模态参考素材总上限为 50 个，可自由组合图片、视频和音频；其中参考图为 1～30 张，参考
  视频最多 10 段且总时长不超过 30 秒，参考音频最多 10 段且总时长不超过 30 秒；
- 单图小于 30 MB，单段参考视频为 2～30 秒且不超过 200 MB，单段音频为 2～30 秒且不超过
  15 MB；图片/音频 Base64 请求还受 64 MB 请求体限制；
- 输出格式为 `mp4` 或 `mov`，`watermark` 默认 `false`；生成记录保留 7 天，结果 URL 只保留
  24 小时且最多下载 100 次，必须自动、及时转存；
- 2.5 不能把包含真人人脸的普通图片/视频直接作为参考；只有官方当前列明、当前账号可验证的指定
  模型原始产物、预置虚拟人像或 `asset://<asset_id>` 形式的已授权真人素材才能走对应人像路径；
- 官方提示词规则为“主体 + 动作/事件 + 场景环境 + 视觉风格 + 运镜/切镜 + 声音”，并支持通过
  `@图片1`、`@视频1`、`@音频1` 明确素材职责。

Dreamina C 端产品页还描述了 4K、180 秒 Beta、R2V 绿幕/白模和局部编辑等产品能力：

- <https://dreamina.capcut.com/seedance>
- <https://dreamina.capcut.com/pt-br/seedance/seedance-2-5-prompt>

即梦当前创作页也公开展示通过 `@图片1`、`@视频1`、`@音频1` 指定素材用途的交互方式：

- <https://jimeng.jianying.com/ai-tool/home?type=video>

Dreamina/即梦 C 端页面不是火山方舟 API 契约，不能把其中的 4K、180 秒、60fps、局部区域 mask 或
绿幕/白模直接映射为 API 参数。`seed`、`fps`、提示词最大长度、局部编辑字段、账户权限、地域配额和
价格仍须以控制台及真实调用验证为准；未确认能力默认关闭。

## 目标

1. 把视频化提升为小说级独立生产域，不依附中短篇写作操作。
2. 以真实、已审核、版本化的图片、视频和音频素材作为生成前提，而不是依赖人物形容词锁定身份。
3. 中短篇与长篇共用素材、分镜、生成和审片底座；长篇增加分集和跨场连续性。
4. 把一次供应商生成建模为 4 到 30 秒的 `GenerationSegment`；普通叙事段优先规划 15～30 秒，
   高风险动作可以更短。一个生成段可包含多个镜头节拍，而不是固定拆成三个独立的 5 秒任务。
5. 让模型只生成结构化影视化方案，最终供应商提示词和素材局部编号由确定性程序编译。
6. 在没有完成素材锁定、能力校验和用户确认时阻止付费渲染。
7. 支持掉线恢复、幂等任务、费用预检、生成结果审片、局部修复或重新生成。
8. 保持 Core、Agent、Web 的现有信任边界；视频持久化只能通过 Core 访问新增 schema，Agent 仍不得
   连接 PostgreSQL，Web 仍只能访问 `/api/v1/**`。

## 非目标

- 第一阶段不承诺把整部长篇自动生成完整影视剧。
- 不承诺仅靠文字提示词保持人物、场景或道具一致。
- 不假定所有 Seedance 产品界面能力都已开放给火山方舟 API。
- 不让 Agent 自动采用影视化方案、锁定素材或发起付费渲染。
- 不让视频产物反向修改小说正文、大纲、设定或章节版本。
- 不在 Web 中运行模型、保存供应商密钥、访问数据库或实现业务 API。
- 不修改生产数据库；开发迁移必须显式读取 `.env.local`、确认 `current_database()` 为
  `novelwriterdev`，并具有幂等校验、回滚脚本和更新后的 schema contract。
- 不在第一阶段实现批量整季渲染、自动发行或复杂非线性剪辑器。

## 核心决策

### 从视频域重新实现，而不是重写 InkForge

保留认证、小说归属、正文版本、Core 与 Agent 服务身份、OpenAPI 客户端、Ed25519 内部鉴权以及
“PostgreSQL 为事实、Redis 仅做可重建投递”的架构原则。现有写作队列、模型 token 计费和文本上传
只能复用实现模式，不能直接复用数据语义。新视频域使用独立契约、任务与页面，不能复用
`short_medium` 的文档操作或伪装成 `WritingTask`。

### 素材锁定是业务事实，不是提示词描述

一个素材只有同时满足以下条件才算“锁定”：

- 存在真实文件；
- 有稳定 `assetId` 和不可变版本；
- 有 SHA-256 内容哈希；
- 已声明素材类型、绑定实体和引用职责；
- 已通过用户审核；
- 未被替代或废弃；
- 当前用户对其有使用权限，并确认来源或版权。

“二十余岁、清瘦、灰蓝布衫”只能作为生成素材的需求，不能作为人物锁定结果。

### 供应商中立的规范层与供应商专用编译层分离

规范层只引用稳定业务 ID，例如 `character-langjun@3`。引用打包器根据当前生成段、素材状态和
供应商能力选择相关子集，再在单次请求中分配 `@图片1`、`@视频1`、`@音频1` 等局部编号。
局部编号不得写回规范层或跨任务复用。

### 结构化计划与最终提示词分离

DeepSeek 或其他语言模型通过严格工具调用提交结构化 `AdaptationProposal`、
`VisualDirectionProposal`、`AssetRequirementPlan`、`VisualCanonFinalization`、`ScenePlan` 和
`GenerationSegmentPlan`。所有结果仍经过共享 Pydantic 契约、来源绑定和跨字段校验。模型不得直接
提交可执行供应商请求，也不得编造素材 URL 或 `@素材` 编号。

`ProviderPromptCompiler` 是确定性代码，只根据已校验的生成段、已锁定素材和供应商能力生成：

- 完整提示词；
- 参考素材请求数组；
- 时间线与运镜指令；
- 负向约束；
- 分辨率、画幅、时长和音频参数；
- 本次素材局部编号映射；
- 可审计输入摘要和内容哈希。

### 正式控制面必须进入 PostgreSQL

`WritingTask`、`WorkflowRun`、`ReviewArtifact` 和 `ReferenceMaterial` 都有已定义语义，不能为了绕过
schema 约束将视频生产域塞入这些表。对象存储只承载二进制、完整来源快照和不可变大清单，不能承担
项目 head、审核状态、待执行命令、轮询时间、余额预占或渲染状态等事务事实。

正式版需要单独的 schema 扩展设计，至少覆盖：

- 视频项目、来源快照元数据、版本 head 和对象哈希；
- 素材、素材版本、锁定状态与权利声明；
- 生成段、渲染意图、供应商任务和结果版本；
- 有索引的耐久命令、`nextAttemptAt`、租约、幂等键和 outbox；
- 视频费用预占、结算、释放和供应商对账；
- 能绑定视频生产任务的 ReviewArtifact 审核主体，以及批准后在同一事务中应用候选版本的能力。

该 schema 扩展已获得仅限本地服务所连接的服务器端 `novelwriterdev` 开发库的实施许可。不得用 JSON 文件、Redis、浏览器状态或虚构
`WritingTask` 绕过正式控制面，也不得把本次许可解释为生产迁移或真实付费渲染许可。

## 领域层级

```text
VideoProject
├── SourceSnapshot
├── AdaptationVersion
│   ├── SeriesPlan（系列项目）
│   ├── SeasonPlan（多季项目）
│   ├── VolumePlan（来源卷映射）
│   ├── EpisodePlan（中短篇可省略）
│   └── ScenePlan
├── VisualDirectionProposal
├── VisualCanonVersion
├── ContinuityLedgerVersion
├── AssetManifestVersion
│   └── AssetVersion
├── GenerationSegment
│   └── CameraBeat
├── VideoCommand
├── RenderJob
├── QualityReport
└── FinalAssembly
```

### VideoProject

一个小说可以有多个视频项目，例如概念片、预告片、终章片段、单集或系列改编。核心字段：

- `projectId`、`novelId`、`schemaVersion`、`revision`；
- `mode`：`concept`、`trailer`、`highlight`、`short_film`、`episode`、`series`；
- `storyLengthProfile`；
- `title`、`targetAudience`、`targetAspectRatio`、`targetLanguage`；
- 当前来源、改编、视觉规范、连续性账本和素材清单版本；
- 当前提供商档案；
- 项目状态和创建、更新时间；
- 当前正式版本 revision，用于数据库条件更新与并发控制。

### SourceSnapshot

任何影视化计划必须绑定不可变小说来源：

- 小说 ID 与篇幅类型；
- 中短篇的蓝图/正文版本 ID、内容 SHA-256；
- 长篇所选章节的章节 ID、更新时间、正文 SHA-256；
- 用户选择范围与每段原文锚点；
- 生成快照时的标题、大纲路径和必要设定版本摘要；
- 整个来源包的规范化哈希。

Agent 每次只接收当前工作所需的最小来源投影。长篇不能把全书正文无条件塞入一次模型请求；应先按
卷、集、场景分层规划，再按需通过 Core 内部读取工具获取原文。

长篇章节正文会被后续编辑覆盖，因此仅保存章节 ID 和哈希不足以恢复历史来源。Core 必须把本次选中的
完整原文按 `sources/{snapshotId}/{sha256}.json` 保存为不可变对象，不能截断；短中篇即使已有 Revision，
也使用同一 SourceSnapshot 契约。后续计划、审片和争议对账均读取该快照，不读取已经变化的当前正文。

### AdaptationVersion

影视化改编版本回答“保留什么、删掉什么、以什么形式呈现”，但不直接包含供应商提示词：

- 核心命题、受众与形式；
- 分集、场景和动作因果链；
- 旁白、对白、环境叙事策略；
- 原文依据；
- 信息披露约束；
- 人物和场景需求；
- 预计时长、生成段数量和成本范围；
- 用户审核状态。

长篇层级的职责不能含混：`SeriesPlan` 固化全系列形式、受众和总命题；`SeasonPlan` 固化一季的主冲突、
人物弧与信息揭示边界；`VolumePlan` 只记录小说来源卷与影视季/集的映射，不默认一卷等于一季；
`EpisodePlan` 选择本集来源、开场钩子、场景顺序和结尾悬念。下层只继承已批准上层版本，任何上层改版
都必须标记受影响的下层版本待重新校验，不能静默覆盖。

### VisualDirectionProposal

视觉方向提案发生在素材制作之前，只定义美术目标、实体需求、摄影/声音方向、允许变化和禁止项，不得
声称人物、场景或道具已经锁定。它经过一次用户确认后，才允许生成 `AssetRequirementPlan`。

### VisualCanonVersion

视觉规范记录跨镜不可漂移的规则：

- 人物骨相、年龄、身高关系、发型、基础服装；
- 服装、伤势、污渍和饰品允许变化的版本；
- 地点空间布局、方位轴线、时间、天气和主光方向；
- 道具形状、材质、磨损和状态；
- 画幅、安全构图、摄影格式、色彩、材质和声音基调；
- 禁止出现的元素；
- 对应已锁定素材版本。

VisualCanon 不能只保存自然语言，也必须把规则绑定到实体 ID 和素材版本。

正式 VisualCanon 只能在素材候选通过技术校验和用户锁定后生成：它把已批准的视觉方向逐项绑定到
具体 `assetId@version`，再经过 ReviewArtifact 复审与用户确认。更换任一身份、场景或关键道具素材
都会创建新的 Canon 版本，并使引用旧版本的 ScenePlan/GenerationSegment 进入待复核状态。

### ContinuityLedgerVersion

连续性账本按叙事时间和场景记录状态：

- 人物是否在场、服装版本、伤势、污渍、情绪和姿态；
- 道具归属、位置、完整/损坏状态；
- 场景时间、天气、光线、破坏和人群状态；
- 信息披露状态、身份称呼和字幕限制；
- 上一场输出状态与下一场输入状态；
- 状态变化对应的原文依据。

生成段完成后不能由视频模型自行改写账本；只有已批准的 `ScenePlan` 能确定账本预期输出，渲染结果
只产生质量报告。

### AssetVersion

素材类型至少包括：

- `character_identity`：人物身份和骨相；
- `character_costume`：服装与阶段状态；
- `character_expression`：表情范围；
- `location_layout`：场景空间；
- `prop`：关键道具；
- `style_frame`：色彩和材质；
- `storyboard_frame`：首帧、尾帧或关键构图；
- `motion_reference`：动作、多人调度或绿幕/R2V；
- `camera_reference`：运镜；
- `voice_reference`：音色和表演；
- `ambience_reference`：环境声；
- `music_reference`：音乐和节奏。

核心字段：

```text
assetId
version
entityId
type
mediaType
objectKey
contentHash
byteSize
width / height / duration
role
sourceKind
rightsDeclaration
status
approvedAt
supersedes
createdAt
```

状态为：

```text
draft -> uploading/generating -> ready -> locked -> retired
                       \-> failed
```

素材版本一旦 `locked` 不再原位覆盖；替换必须创建新版本并显式迁移引用。

### 素材生产与锁定流程

视频计划不能直接跳到 Seedance。每个 `AssetRequirement` 先定义实体、用途、必须看见的角度/状态、
来源锚点、权利要求和验收规则，再进入以下流程：

```text
requirement
  -> upload 或 static_asset_generation
  -> candidate versions
  -> 技术校验与重复检测
  -> 用户比较/退回
  -> ReviewArtifact 批准
  -> locked version
```

人物至少区分“不会随剧情变化的身份层”和“会变化的状态层”：

- 身份层：清晰正脸、三分之二侧脸、侧脸、全身比例、发型和稳定骨相；
- 状态层：本场服装、伤势、污渍、年龄阶段、表情和手持道具；
- 声音层：音色、说话速度、情绪范围、口音和用户权利声明；
- 禁止把一张模糊氛围图同时当作身份、服装、表情和动作的全部锁定依据。

场景至少有建立镜头视角和空间布局，关键道具至少有可识别外形、尺度、材质和剧情状态。动作/运镜
参考只负责动作或摄影职责，不能覆盖人物身份。ReferencePacker 可以为供应商预算选择最小集合，但
任何关键职责没有真实 `locked` 文件时必须报缺失，不能用文本描述自动补位。

静态图片或声音的 AI 生成也属于正式候选内容，必须经过相同审核链。具体提供商保持可替换；在确认
图片/声音模型、价格、版权和真人规则之前，MVP 只允许用户上传有权使用的真实素材和项目自有测试素材。

### GenerationSegment 与 CameraBeat

`GenerationSegment` 是一次供应商生成的原子单元，时长由能力接口决定。一个生成段可以包含多个
`CameraBeat`，每个节拍具有明确时间范围：

- 原文依据；
- 起止秒数；
- 出现人物及当前状态；
- 场景和道具状态；
- 动作、调度、镜头、光线和声音；
- 首帧、尾帧和转场目标；
- 需要的素材职责；
- 负向约束；
- 输入与输出连续性状态。

生成段之间通过已锁定素材和明确状态衔接，不能仅靠重复粘贴人物描述维持一致。

## 镜头设计与切分规则

### 三层单位不能混用

- `Scene`：叙事单位；地点、时间和主要行动连续。
- `GenerationSegment`：一次方舟任务的输出单位；允许 4～30 秒，普通叙事段优先 15～30 秒，高风险
  动作、局部衔接或低成本试片可以是 4～14 秒。
- `CameraBeat`：生成段内部的镜头/切镜节拍；可以是单镜到底的一段运镜，也可以是明确切换的若干镜头。

不能把“小说段落”“一个镜头”和“一次 API 任务”视为同一概念。小说段落可能跨多个场景，一个
GenerationSegment 也可能根据官方提示词能力包含多个 CameraBeat。

### 从原文到镜头的确定性流水线

1. **来源锚定**：把用户选择的完整原文保存为 SourceSnapshot，句段只保存可回溯锚点，不改写来源。
2. **戏剧节拍提取**：识别目标、阻力、动作、反应、信息揭示和结果；区分可见动作、内心信息、对白、
   旁白和需要改编的抽象叙述。
3. **场景归并**：按地点、叙事时间、人物组合和主要行动连续性形成 Scene；换地点或明显跳时必开新场。
4. **时长预算**：先由成片目标给场景分配时长，再给动作、对白、反应和揭示分配可观看时间，不能按
   字数平均切段。
5. **镜头意图图**：先确定每个 CameraBeat 要让观众看见什么、知道什么、感受什么，再选择景别、机位、
   镜头运动和声音，不从随机“电影感”词汇开始。
6. **生成段打包**：在 30 秒、参考素材预算和动作复杂度范围内，把连续 CameraBeat 装入
   GenerationSegment；ReferencePacker 超限时回退重分段。
7. **连续性校验**：校验轴线、视线、运动方向、人物/道具状态、光线、服装、声音桥和首尾帧。
8. **提示词编译**：模型输出结构化意图，确定性编译器生成带时间码的完整提示词和素材数组。

### 强制切分条件

出现以下任一条件必须创建新的 Scene 或 GenerationSegment：

- 地点、叙事时间或主光环境发生不可连续的变化；
- 当前段超过方舟 30 秒上限，或单项/组合参考素材超过已验证能力；
- 前一段输出状态不能作为后一段可验证输入，例如人物服装、伤势或道具归属发生关键变化；
- 同一段要求互相冲突的画幅、首尾帧模式、编辑模式或声音策略；
- 多人复杂调度、快速形变、精细手部动作等高风险事件需要隔离重试；
- 需要把一个可接受结果锁定，避免因后续局部问题整段重新付费。

以下是优先切分点，但可以由导演意图覆盖：

- 动作完成后的反应；
- 新人物或关键信息首次揭示；
- 对白轮次、视点或情绪目标改变；
- 音乐重拍、声音桥或自然遮挡转场；
- 从全景建立空间转入人物关系，或从关系镜头转入关键细节。

不得为了凑固定秒数在一句对白中间、一个身份关键动作中间或因果结果出现前硬切。超时应重新分配
场景时长、改写为可见动作或拆成有首尾锚点的两个生成段。

### CameraBeat 最小契约

每个 CameraBeat 至少包含：

```text
beatId / sourceAnchors / startSecond / endSecond
dramaticPurpose / visibleAction / reaction / informationReveal
subjects / blocking / screenDirection / eyeline / axisRule
shotSize / cameraHeight / cameraAngle / lensIntent / cameraMovement
focusTarget / depthPlan / lightingState / environmentMotion
dialogue / narration / ambience / soundEffects / musicCue
entryFrame / exitFrame / transition / continuityInput / continuityOutput
requiredAssetRoles / negativeConstraints / riskFlags
```

时长估算使用可调整的导演启发式，不写死为供应商参数：建立空间通常需要 2～4 秒，单一动作或反应
通常需要 1.5～4 秒，关键揭示通常需要 2～5 秒；对白必须按真实试读时长加呼吸和反应余量。任何估算
都要在生成段总时长内显式闭合，不能让多个节拍时间重叠或留下无定义空洞。

### 镜头语法门禁

- 每个镜头只保留一个主要观看目标和一个主要镜头运动；复杂调度拆成连续节拍。
- 同一场先建立空间和轴线，再切关系、反应和细节；越轴必须有中性镜头、可见运动或明确意图。
- 人物进出方向、视线和动作方向必须与连续性账本一致。
- 景别变化应服务信息层级；禁止无目的地“大全景—特写—大全景”跳变。
- 推、拉、摇、移、跟、手持或静止都必须说明动机、速度、起止构图和焦点，不堆砌运镜词。
- 对白段优先保证表演、口型和声音可读性；需要隐藏身份时不让字幕、称呼或构图提前泄露。
- J-cut、L-cut、环境声延续和音乐重拍属于声音/剪辑契约，不只写在自由文本里。
- 首帧和尾帧必须描述可验证构图与状态，用于下一生成段衔接和失败定位。

### 中短篇与长篇的切分差异

中短篇先确定唯一叙事主线和成片时长，主动合并次要人物、地点和重复信息；长篇先做季/集级选择，
再只把本集选中的章节范围送入上述相同流水线。长篇增加的是层级、继承和连续性检查，不改变
GenerationSegment 的 4～30 秒供应商上限，也不把全书压缩成一个超长提示词。

## 中短篇与长篇编排

| 维度 | 中短篇 | 长篇连载 |
| --- | --- | --- |
| 层级 | 项目 → 场景 → 生成段 | 项目 → 卷/季 → 集 → 场景 → 生成段 |
| 来源 | 完整正文版本或选定高潮 | 分层选择章节和大纲路径 |
| 素材 | 项目内复用 | 系列级基础素材，按集继承 |
| 连续性 | 场景级状态 | 跨集状态与信息披露账本 |
| 生成 | 少量 4～30 秒生成段 | 大量相同 4～30 秒原子生成段 |
| 审核 | 逐场景审核 | 分集审核并检查跨集漂移 |

篇幅类型只决定编排层级，不决定是否需要素材锁定。一篇人物反复出场的中短篇仍必须使用同一套
素材；一部长篇也不能被当作一个超长提示词提交给供应商。

## 对象存储与版本清单

### 存储归属

Core API 是视频对象存储的唯一业务所有者：

- 浏览器先向 Core 申请有范围、短时、一次性的上传签名，再直传对象存储；
- Core 在完成回调中校验文件类型、魔数、媒体元数据、大小、声明哈希和小说归属后，才在 PostgreSQL
  事务中登记素材版本；
- Agent 只通过 Core 内部接口获取短时只读 URL 或由 Core 代理所需内容；
- Agent 和浏览器都不能获得对象存储主密钥；
- 供应商结果 URL 仅允许由 Seedance 适配器处理。Agent 使用 Core 签发的单对象、短时写入凭证完成
  “供应商下载 → 受控对象上传”，再回报对象键、字节数与哈希；Core 复核后登记结果。Core 不抓取
  浏览器或通用回调提交的任意 URL，避免 SSRF；
- 下载适配器只接受 HTTPS 和官方响应字段中的 URL，逐跳校验重定向；解析后的每个目标地址都必须
  命中 provider allowlist，拒绝环回、链路本地、私网、保留地址、非预期端口和 DNS 重绑定。禁止把
  allowlist 只做成字符串后缀匹配；
- 方舟结果 URL 只有 24 小时有效且最多下载 100 次，成功任务必须立即安排转存，转存完成前不能标为
  `archived`。

开发环境使用 `LocalVideoObjectStore`，只允许位于明确的视频数据目录；生产使用 TOS 或经批准的兼容
对象存储。两者实现相同的 `VideoObjectStore` 端口。现有 `StyleStorage` 只接受 UTF-8 `.txt`，不得
复用；本地媒体上传需要独立的流式端点、独立 Nginx 路径大小限制和媒体探测沙箱。

### 对象键

```text
video-projects/{userId}/{novelId}/{projectId}/
├── manifests/{revision}-{sha256}.json
├── sources/{snapshotId}/{sha256}.json
├── adaptations/{adaptationId}/{revision}-{sha256}.json
├── canons/{canonId}/{revision}-{sha256}.json
├── continuity/{ledgerId}/{revision}-{sha256}.json
├── assets/{assetId}/{version}/{sha256}.{ext}
├── segments/{segmentId}/{revision}-{sha256}.json
├── renders/{renderJobId}/source.{ext}
├── quality/{reportId}.json
└── assemblies/{assemblyId}/{revision}.{ext}
```

所有键由 Core 根据已校验 ID 构造，不能接受浏览器提交的任意完整键。禁止对用户目录、桶根目录或
未解析前缀执行递归删除。

### 并发与恢复

- 大型业务清单和来源包采用不可变对象；PostgreSQL 保存当前版本指针、对象键、内容哈希和 revision。
- 更新当前版本必须在 PostgreSQL 中使用行锁或 revision 条件更新，冲突返回 409；对象写入成功但事务
  未引用的文件进入孤儿清理窗口，不得立即删除。
- 每个 `VideoCommand` 先在 PostgreSQL 事务中创建，连同业务状态变化和 outbox 一起提交；提交成功后
  dispatcher 才把命令 ID/类型/输入哈希投递 Redis。
- PostgreSQL 按状态和 `nextAttemptAt` 建索引并公平领取到期命令；Redis 丢失后可从耐久命令重建。
  禁止扫描对象存储前缀充当 due 队列，也禁止把完整正文、清单或媒体放入 Redis payload。
- Agent 回调必须绑定 `commandId`、`jobId`、`projectId`、`novelId` 和输入哈希。
- Redis 只是可重建队列，不是视频项目或渲染结果的唯一事实来源。
- 同一 `novelId` 的视频计划、素材规划和渲染命令默认串行；不同小说可以受全局限制并行。
- 提交和查询拆成短任务。供应商 task ID、`nextPollAt` 和最后状态写入 PostgreSQL 后结束当前租约；
  到期后再投递一次查询，不能让 LangGraph 或 Redis lease 等待数分钟。
- 如果提交请求超时且没有拿到 provider task ID，只有供应商确认支持外部幂等键时才可自动重试；否则
  进入 `submission_unknown` 对账状态，禁止盲目重提造成双扣费。

### 跨存储 Saga

PostgreSQL 事务不能与对象存储、Redis或方舟 API 组成原子提交，正式版必须实现可恢复 Saga：

1. `prepare`：事务内创建候选版本、费用预占、耐久命令与 outbox；
2. `materialize`：将大清单或媒体写入临时对象键，校验哈希后登记不可变对象；
3. `submit`：短任务调用方舟并持久化 task ID；未知结果进入对账，不自动重提；
4. `poll`：每次查询完成后保存状态和下一查询时间，再释放任务；
5. `archive`：在 24 小时窗口内把结果转存，校验后切换正式结果引用；
6. `settle`：按已确认价格结算预占，失败或取消按规则释放；
7. `compensate`：对终态失败、孤儿对象、过期上传和永久无法对账的命令执行显式补偿。

每一步都要有稳定幂等键、合法状态迁移和重启恢复测试。只有 `prepare` 事务完成后才允许返回 202。

## 模型与 Agent 工作流

视频域使用独立的 `video_planning` 工作流，不加入中短篇四个文档操作，也不假装成普通
CreativeOperation。计划生成可沿用现有 LangGraph `StateGraph`、`Send`、`Command` 和 `interrupt()`
模式，并复用 `ModelRuntime`、全局模型并发门、模型授权和人工日志；但必须新增独立
`video_planning` job kind、持久命令和共享服务契约。

计划阶段可以拆成：

```text
source_selection
  -> adaptation_proposal
  -> await_adaptation_approval
  -> visual_direction_proposal
  -> await_visual_direction_approval
  -> asset_requirement_plan
  -> await_asset_requirement_approval
  -> await_asset_lock
  -> visual_canon_finalize
  -> await_visual_canon_approval
  -> scene_plan
  -> await_scene_plan_approval
  -> generation_segment_plan
  -> await_segment_approval
  -> planning_complete
```

每个 Agent 候选版本必须先形成 `ReviewArtifact`，经过复审/返工与用户批准后，由 Core 在同一数据库
事务中切换视频项目的正式版本指针。现有 `ReviewArtifact.taskId -> WritingTask` 关系和批准应用逻辑不
支持这一点，因此它是正式版 schema 扩展的 P0 前置项；不得退化成对象存储中的 `approved: true`。

规划图到 `planning_complete` 为止，Agent 绝不创建付费 `RenderIntent`。后续必须由用户在 Web 查看
Core 报价并显式确认，Core 才能在事务中执行业务门禁、预占费用和创建 RenderIntent/耐久命令：

```text
用户确认报价
  -> Core 创建 RenderIntent + 费用预占 + outbox
  -> provider submit 短任务
  -> provider poll 短任务（可重复调度）
  -> 结果转存与技术质检
  -> 独立 semantic_qc job（能力启用时）
  -> 用户接受 / 重生成 / 返回修改
```

渲染提交、查询、归档和质量检查都不是长驻规划图节点。Agent Service 不保存正式素材清单，不直接修改
数据库，也不在模型正文中解析控制 JSON。

现有 Agent ID 继续固定为设定、剧情、写作、校验和编辑，不为视频随意增加第六个 Agent。建议职责为：
剧情负责改编/场景/生成段主稿，设定负责视觉方向/素材需求/Canon，写作负责对白与旁白，编辑负责复审，
校验负责质量报告；最终映射仍须在独立 Operation 契约中显式声明。每个新读取或提交工具都必须注册到
`inkforge_agents/tools/registry.py`，同时声明 Agent/Operation/执行模式权限及只读并发属性；未注册或
未授权工具必须拒绝执行。

### strict 结构化输出

DeepSeek 只负责调用版本化工具，不在聊天正文中吐一大段待修复 JSON。每一步使用较小、职责单一的
Pydantic 输入模型生成 JSON Schema，并按当前
[DeepSeek 工具调用契约](https://api-docs.deepseek.com/zh-cn/guides/tool_calls)启用 `strict: true`：

- 所有业务字段显式 required 或显式 nullable，`additionalProperties: false`；
- ID、状态、景别、运镜和素材职责尽量使用 enum/Literal，时间统一整数毫秒或确定精度的小数；
- `sourceAnchors`、实体 ID 和上一步版本哈希必须由工具上下文提供或逐项验证，模型不能自造；
- 工具参数先做 JSON 解析、Pydantic 校验、跨字段校验和来源绑定，再形成候选版本；
- 不使用正则截取、补括号、静默删字段或截断内容来“修好 JSON”；
- 校验失败只允许把结构化错误反馈给模型做有次数上限的重试，仍失败则保留完整错误并结束命令；
- 复杂方案拆为 adaptation、canon、asset requirements、scene 和 segment 等多个工具调用，避免一个
  超大 schema 同时承担整部小说和全部镜头。

### 生产出网

当前 `agent-service` 只连接 `internal: true` 的 `agent_net`，生产环境无法访问 DeepSeek 或火山方舟。
正式实现前必须增加受控出网路径，例如只允许 Agent 使用、按域名和端口限制的 egress proxy；不能简单
把 Agent 接入 Web 所在的 `public_net`。架构测试必须验证：

- 浏览器和 Nginx 仍不能访问 Agent 内部接口；
- Agent 只能访问批准的模型、方舟和对象存储端点；
- Core/Agent 内部请求仍校验直接对端网段与 Ed25519 服务令牌；
- provider 密钥只进入需要它的服务，日志和回调不泄露密钥或签名 URL。

## 引用打包器

一次生成不能把长篇全部素材都提交给供应商。`ReferencePacker` 按以下顺序构造最小相关子集：

1. 从 CameraBeat 汇总必须出现的实体和素材职责；
2. 从连续性账本解析每个实体在当前场景的版本；
3. 只选择状态为 `locked` 的素材；
4. 优先人物身份、当前服装、场景布局、关键道具和首尾帧；
5. 再加入动作、运镜、声音和风格参考；
6. 根据供应商总上限、各模态上限、文件限制和任务类型做预算；方舟 2.5 当前总上限为 50 个，可自由
   组合，但仍受 30 张图、10 段视频（合计不超过 30 秒）、10 段音频（合计不超过 30 秒）分别限制；
7. 预算不足时阻止渲染并要求拆分生成段或减少非必要引用，禁止静默丢弃关键素材；
8. 为本次请求分配局部编号并生成可审计映射。

`@图片1` 等名称首先是制作包中的局部可读别名。只有官方 API 契约明确要求在提示词中使用相同语法时，
Provider 才按原样发送；若 API 使用结构化素材数组、文件 ID 或其他引用字段，适配器必须把同一别名映射
到真实请求结构，不能把 C 端输入框语法硬编码成 API 事实。

示例：

```text
character-langjun@3  -> @图片1，身份
costume-langjun-ch4@2 -> @图片2，第四章服装
location-yard@4       -> @图片3，场景空间
prop-overturned-pot@2 -> @图片4，道具
motion-rise-and-press@1 -> @视频1，人物动作
camera-medium-to-hand@1 -> @视频2，镜头运动
voice-langjun@1       -> @音频1，音色
ambience-riot@2       -> @音频2，环境声
```

## 提示词编译

完整导演制作单与最终方舟文本提示词是两个不同产物：制作单可以完整保存素材职责、来源锚点、镜头
设计和连续性；方舟 API 文档建议中文提示词不超过 500 字、英文不超过 1000 词，过长会分散模型注意
力。因此编译器输出的是高密度执行文本，不把完整小说原文或导演制作单原样塞入 API。

编译顺序固定为：

1. 任务和输出规格；
2. 全局视觉与声音规范；
3. 素材引用及每项职责；
4. 带时间码的 CameraBeat；
5. 人物、场景、道具连续性；
6. 镜头、动作、物理和声音细节；
7. 首帧、尾帧与转场；
8. 负向约束；
9. 供应商专用参数。

提示词长度不是质量指标。编译器必须完整表达素材职责和时间线，但同时遵守能力接口返回的长度政策；
中文 500 字是官方建议值，超过时给出明确警告而不是冒充 API 硬限制；产品仍以 2000 字作为本地安全
包络。超过安全包络时明确失败并要求删除已由精准素材承载的重复描述或拆分生成段，不能静默截断
提示词、删除关键引用或把超限文本伪装成可执行请求。

## 提供商能力适配

Core 的公开能力接口只返回 Agent Service 已确认的真实能力。档案不能是一个扁平布尔列表，因为
文生视频、多模态参考、首帧、首尾帧、编辑和延长对 ratio、duration 与素材角色的约束不同：

```text
ProviderCapabilityProfile
├── provider / model / availability / documentationVersion / verifiedAt
├── commonReferenceLimits
│   ├── maxTotalReferences = 50
│   ├── maxImageReferences = 30
│   ├── maxVideoReferences = 10 / maxTotalVideoSeconds = 30
│   └── maxAudioReferences = 10 / maxTotalAudioSeconds = 30
├── uploadLimits / promptLimit / pricingDescriptor / portraitPolicy
└── taskCapabilities[taskKind]
    ├── enabled / verificationState
    ├── durationRange / allowsAdaptiveDuration
    ├── supportedAspectRatios / supportedResolutions
    ├── supportedOutputFormats / generateAudioModes / watermarkModes
    ├── allowedReferenceRoles / requiredReferenceRoles
    └── editOrExtensionConstraints
```

Seedance 2.5 方舟档案以 `doubao-seedance-2-5-260628` 为模型 ID，初始只开放文档确认的 4～30 秒、
480p/720p、上述画幅、mp4/mov、50 个总素材上限及各模态限制。编辑、延长、首帧和首尾帧任务按
官方契约使用各自 profile，例如它们可能只允许 `adaptive` ratio 或 `duration = -1`。`1080p`、`4K`、
180 秒、60fps、局部 mask、绿幕/白模、`seed` 和 `fps` 均为关闭/未知，而不是前端可选项。

能力来源必须是官方 API 契约、资料更新时间、服务端配置和当前账户实调结果。界面不能根据环境变量
名称自行推断模型版本，也不能把“文档支持”误显示为“当前账号已配置”。至少区分：

- `documented`：官方契约已确认；
- `configured`：服务端密钥和必要存储已配置；
- `verified`：当前账号、地域与模型已完成最小实调；
- `disabled`：未配置、权限不足、价格未知或运维主动关闭。

提供商端口至少包括：

```text
get_capabilities()
submit_task(validated_request)
query_task(task_id)
cancel_generation(task_id)  # 仅官方接口支持时暴露
```

## 渲染前门禁

门禁分为两个不同责任层，不能做成跨服务读取一切的单体 `ProviderPreflight`。

Core 的 `RenderBusinessPreflight` 必须检查：

- 当前用户仍拥有小说；
- 来源快照未损坏且原文依据可以定位；
- 改编、视觉规范和生成段已由用户确认；
- 所有必需素材均已锁定且哈希匹配；
- 连续性输入状态与上一场输出一致；
- 没有引用临时、失败、已退休或越权素材；
- 当前 revision 与用户看到的报价、制作包完全一致；
- 本次费用报价已展示，用户已显式确认且余额预占成功；
- 幂等请求尚未提交或可以安全返回原任务。

Provider 侧纯函数 `ProviderRequestPreflight` 必须检查：

- task kind 对应的时长、画幅、分辨率、`generate_audio`、输出格式和 watermark 参数；
- 该任务类型允许的首帧、首尾帧、参考图/视频/音频组合及数量；
- 提示词长度和媒体格式、编码、时长、尺寸、字节数、请求体大小；
- 临时局部编号与结构化 `content[]` 顺序一一对应；
- 请求只包含 Core 授权的稳定对象哈希和短时 URL，没有任意外部 URL。

阶段 1 只能运行不依赖数据库的 `ProviderRequestPreflight`，并用 fixture 模拟供应商档案；
`RenderBusinessPreflight` 必须等治理门 A 后实现。真正提交前 Agent 还要对已编译请求再执行一次
Provider 校验，防止能力档案或对象在排队期间变化。任一门禁失败都不得调用供应商。

## 计费

视频生成仍由 Core 独占余额和账务。现有计费服务只覆盖 DeepSeek/fake 的 token 口径，单独增加
`CreditLedger.type = video_charge` 仍不能表达并发预占、未知提交和退款，因此正式版需要视频用量与
费用预占契约，不能伪装成 `ai_charge` 或伪造 token usage。

一次渲染采用以下账务状态：

```text
quoted -> reserved -> submitted -> settled
                    \-> submission_unknown -> reconciled -> settled/released
                    \-> failed/cancelled -> released
```

- 用户确认后，Core 在数据库事务和余额行锁内按最高可能费用预占，防止并发超卖；
- `renderIntentId`、`requestId` 和命令幂等键稳定绑定，重复请求返回原预占和原任务；
- 获得 provider task ID 后记录供应商计费依据；成功、失败、取消和未知提交分别按规则结算或释放；
- 如果供应商实际费用只能事后获得，预占上限、差额释放、超额策略和舍入方式必须写入计费契约；
- 供应商任务提交后即使前端断线也继续对账，重复回调不得重复扣费或重复退款。

在控制台价格、币种、计费单位和账户额度实调前，能力状态只能显示“价格未验证”，真实渲染不可用。

## 生成后质量检查

供应商返回成功不等于镜头通过。阶段 4A 先实现确定性的 `TechnicalQualityReport`：对象哈希、容器、
编码、时长、画幅、分辨率、音轨、可解码性、黑帧/静帧和归档完整性。未通过技术质检的结果不能进入
用户审片。

阶段 5 再增加模型辅助的 `SemanticQualityReport`，至少检查：

- 人物身份、服装和数量是否匹配锁定素材；
- 场景空间、道具和光线是否连续；
- 动作顺序、方向和物理结果是否符合 CameraBeat；
- 是否出现多余肢体、人物复制、换脸、随机文字或禁用元素；
- 声音、对白、口型和环境声是否符合要求；
- 首尾帧和连续性状态是否与下一生成段可衔接。

两类报告都只能给出 `pass`、`revise` 或 `block` 建议，不能自动采纳成片。首轮受控付费验收允许
“技术质检 + 用户人工语义审片”，但批量渲染必须等语义质检和失败抽检策略完成。用户选择：

- 接受当前版本；
- 局部编辑（提供商支持时）；
- 基于同一输入重新生成；
- 返回修改素材或生成段；
- 丢弃结果。

任何选择都不修改正式小说内容。

## 前端信息架构

入口提升到小说级工作台，例如 `/workspace/{novelId}?view=video`。界面遵循 `DESIGN.md` 的桌面工作台
结构，不使用巨大营销卡片或把完整制作流程塞进抽屉。

主视图分为：

1. **改编策划**：选择概念片、预告片、高潮片段、短片、单集或系列，并审核来源和改编版本；
2. **视觉圣经**：人物、场景、道具、服装、色彩、摄影和禁止项；
3. **素材库**：生成、上传、比较、声明版权、锁定和替换素材版本；
4. **分镜时间线**：场景、GenerationSegment、CameraBeat、原文依据和连续性状态；
5. **引用检查**：展示本段将提交的 `@素材` 映射、引用预算和缺失项；
6. **渲染任务**：费用确认、任务状态、结果版本、技术报告、语义报告（启用时）和用户决定；
7. **成片**：片段排序、基础声音和最终导出，后续阶段实现。

长篇增加卷/集导航和连续性账本；中短篇隐藏不需要的层级，但不能跳过素材锁定和渲染前门禁。

## 公共与内部接口草案

以下接口只在治理门 A 通过后实现。浏览器只访问：

```text
GET    /api/v1/video/capabilities
POST   /api/v1/video-projects
GET    /api/v1/video-projects?novelId=...
GET    /api/v1/video-projects/{projectId}
POST   /api/v1/video-projects/{projectId}/commands
GET    /api/v1/video-projects/{projectId}/commands/{commandId}
POST   /api/v1/video-projects/{projectId}/assets/uploads
POST   /api/v1/video-projects/{projectId}/assets/{assetId}/complete
POST   /api/v1/video-projects/{projectId}/assets/{assetId}/lock
POST   /api/v1/video-projects/{projectId}/segments/{segmentId}/render-quote
POST   /api/v1/video-projects/{projectId}/segments/{segmentId}/render-intents
GET    /api/v1/video-projects/{projectId}/renders/{renderJobId}
POST   /api/v1/video-projects/{projectId}/renders/{renderJobId}/decision
```

Agent Service 只通过 `/internal/v1/video/**` 获取来源、锁定素材的短时引用、保存检查点和回写命令结果。
所有写接口继续使用 Ed25519 请求绑定与 Redis 防重放，不能信任转发头判断内部身份。

新增或修改公共接口时先实现 Core Pydantic 契约，再运行 `npm run api:generate`，前端不得手写重复 DTO。

## 《无年之灾》第一条验收场景

第一条端到端验收只制作终章 15 到 30 秒场景，不做整篇自动成片。必须先具备：

- 郎君、满仓、长生和差役的锁定人物素材；
- 第四章服装/伤势状态；
- 院落土灶空间、缺沿铁锅、粗陶空碗和风格帧；
- 掀锅、传碗、起身按锅动作或可接受的分镜首尾帧；
- 环境声与郎君气声策略；
- “拘票前不得出现姓名、称号或字幕”的信息披露规则。

一个 GenerationSegment 内按时间线表达：

```text
0～5 秒：差役挑锅、踹开灶石，铁锅按真实重力翻倒，热汤泼入泥地；
5～10 秒：空碗继续按固定方向回传，长生护住孩子；
10～15 秒：郎君从泥里站起，按住锅沿，镜头推进到颤抖的手和气声余韵。
```

制作包中的导演制作单不能退化成几句形容词。以下长文本展示完整结构和密度，它不是直接发送给方舟
的 API 文案（中文目标尽量不超过官方建议的 500 字）；真正执行时，编译器从中选择当前生成段的必要信息，每个 `@素材` 必须由
ReferencePacker 映射到已经锁定的文件版本，编号顺序与方舟 `content[]` 保持一致：

```text
任务：生成 15 秒、16:9、720p、写实历史剧情片段，原生环境声与人物气声。保持真实重力、泥水和
铁器质感。叙事目标是“官差毁掉最后一口锅后，郎君第一次用身体阻止”，不是动作展示片。

视觉规范：阴冷灾年午后，低饱和灰褐色，潮湿泥地，漫射天光从院落左后方进入，人物肤色和布料保留
自然细节；镜头克制、贴近人物，不使用玄幻光效、商业广告光、过度浅景深或无动机旋转运镜。

素材职责：
@图片1 只锁定郎君的脸型、五官比例、发型、年龄与体态，任何镜头不得换脸或变年轻。
@图片2 锁定郎君本场灰蓝旧布衫、泥污位置、左肩破口和手腕擦伤，不替换服装。
@图片3 锁定满仓、长生与孩子的身份和身高关系，不增加、合并或复制人物。
@图片4 锁定差役身份、黑旧公服、腰带与靴子，不把他改成披甲士兵。
@图片5 锁定院落、土灶、门口和墙面的空间方位；土灶始终在画面右侧，人物运动轴保持一致。
@图片6 锁定缺沿铁锅、灶石和粗陶空碗的形状、大小、材质与磨损。
@视频1 只参考挑锅、锅沿失衡、热汤泼落的动作节奏和真实重量，不复制其中人物身份或场景。
@音频1 只参考郎君低哑、缺气、压住愤怒的音色，不复制原音频台词。
@音频2 只参考空旷院落的寒风、远处骚动、泥水和铁锅碰石声，不加入现代机械声。

0.0～3.2 秒：24mm 中低机位中全景建立空间，土灶在画面右侧，差役从左向右用木杆挑住锅沿。镜头
缓慢前移，不摇晃。满仓与长生护住孩子退在画面左后方。先听见木杆刮铁，再听见灶石松动。

3.2～6.0 秒：切 50mm 关系中景，保持同一轴线。差役向外发力并踹开灶石，铁锅因重量先倾斜、再翻落，
不是漂浮或突然弹飞；热汤沿缺口泼入泥地，蒸汽短暂遮挡下半身。铁碰石的尖响后接泥水闷响。

6.0～9.4 秒：借蒸汽消散切到 35mm 侧向中景。粗陶空碗沿既定方向继续回传，手与碗数量准确；长生
弯身护住孩子，满仓回头看郎君。镜头小幅横移维持三人关系，不越轴，不新增围观者。

9.4～12.2 秒：切 65mm 郎君近景。郎君先用手撑泥地，再因疼痛停顿半拍，抬眼看向画外右侧铁锅；
呼吸急促但不喊叫。脸、发型、衣服、泥污和伤势严格保持 @图片1、@图片2。

12.2～15.0 秒：跟随郎君起身切到 50mm 手部与上身近景。他从左向右迈半步，一只颤抖的手按住锅沿，
锅仍有余震但停止移动。焦点从手背伤口缓慢移到他的眼睛。他用 @音频1 的气声说“住手”，末尾保留
0.4 秒寒风和铁锅余响，尾帧固定郎君手压锅沿、差役在右侧回头的可衔接构图。

连续性与禁止项：保持人物数量、身份、衣着、伤势、道具缺口、土灶方位、运动方向和左后方主光；
不得换脸、复制人物、增加手指或碗、改变锅的材质和尺寸、让热汤逆重力运动、出现现代物件、文字、
字幕、姓名、称号、水印、慢动作、夸张武打、玄幻粒子、随机推拉或无动机环绕。
```

验收条件：

- 页面明确展示每个素材的真实缩略图、版本、哈希摘要和锁定状态；
- 生成前展示完整 `@素材` 映射，不存在未解析占位符；
- 人物、场景、道具、动作和声音引用均来自已锁定素材；
- 提示词包含时间码、动作方向、物理结果、镜头、声音、首尾帧和禁止项；
- 任一关键素材未锁定时渲染按钮不可用，并明确指出缺失项；
- 方舟 API 虽已有公开契约，但当前账号、价格、出网、存储或计费任一项未验证时只能导出制作包，
  不能伪装成已经可以渲染；
- 生成后经过自动质量报告和用户确认，不能自动加入成片。

## 分阶段实施

### 阶段 0：撤销旧原型与锁定事实（已完成）

- 撤销中短篇纯文本提示词原型及其 API、任务和界面耦合；
- 固化方舟 Seedance 2.5 的模型 ID、异步接口、720p 上限、4～30 秒、50 个总素材上限及分类限制；
- 明确 Dreamina C 端宣传能力与方舟 API 的边界；
- 输出本规格，并完成旧原型清理。

### 阶段 1：无持久化制作包技术验证（已完成）

- 在独立领域包中定义 provider-neutral Pydantic 契约和严格 JSON Schema；
- 实现确定性的 ReferencePacker、ProviderPromptCompiler、ProviderRequestPreflight 和 golden tests；
- 以《无年之灾》固定来源与本地测试素材生成完整 JSON/Markdown 制作包；
- 第一个可运行切片只接收一个 4～30 秒 ScenePromptSpec，校验素材编号、连续整数秒时间轴和必需镜头
  字段，编译出完整 SeedancePromptPackage；方舟中文 500 字是建议值，超过时给出警告，产品安全上限
  为 2000 字且禁止静默截断；测试素材必须标明为 fixture，不能伪装成已锁定文件；
- 该切片只验证契约和格式，不调用语言模型做镜头质量判断，也不构造可付费提交的方舟请求；
- 不增加公共 API、不创建正式项目、不扣费、不调用 Seedance、不提供会让用户误以为已保存的前端；
- 评审通过标准是：结构、镜头、素材职责和最终提示词符合预期，而不是“接口返回了 JSON”。

### 治理门 A：正式控制面许可（仅服务器 dev 开发环境已通过）

进入产品开发前必须先完成并批准独立规格：

- PostgreSQL 视频域表、ReviewArtifact 泛化方案和迁移/回滚策略；
- 耐久命令、outbox、due 索引、Saga 和孤儿清理；
- 视频费用预占、结算、释放与供应商对账；
- TOS/本地媒体存储、上传限制、生命周期和删除恢复；
- Agent 受控出网与架构安全测试。

本次许可只覆盖 `.env.local` 指向并经查询确认为 `novelwriterdev` 的数据库。迁移命令必须在执行前再次
校验数据库名，使用事务与 advisory lock，并附带只删除本次新增对象的回滚脚本；生产治理规则不变。

### 阶段 2：小说级控制面、制作台与素材闭环

首个纵向切片已于 2026-08-07 在 `novelwriterdev` 完成并实跑：项目、场景、素材、素材绑定、视频规划
任务与视频 ReviewArtifact 已持久化；当前章节原文可提交 DeepSeek strict 工具；候选提示词经用户批准
后才进入正式场景；真实 PNG 已完成魔数识别、哈希、权利确认、锁定和场景绑定。更完整的 Canon、素材
版本替换、孤儿清理与长篇卷/集导航仍属于后续增量，不能因纵向切片成功而宣称已完成阶段 4B。

- 依照已批准 schema 建立 VideoProject、SourceSnapshot、VisualDirection、VisualCanon、AssetManifest
  和正式版本指针；
- 建立视频专用 ReviewArtifact 绑定与批准应用事务；
- 建立独立媒体上传、探测、锁定、替换、版权声明和孤儿清理；
- 建立小说级视频制作台，中短篇隐藏卷/集层级，长篇显示分层导航；
- 先支持完整制作包导出，渲染按钮保持关闭。

首个完整纵向交付必须同时具备以下可操作能力，不能再用硬编码 fixture 冒充产品功能：

- 从当前小说建立视频项目，并持久化项目、场景、素材和生成任务；
- 从当前章节或用户选择的原文创建来源快照，提交独立 `video` Agent 任务；
- DeepSeek 通过 strict 工具调用返回 `ScenePromptSpec`，确定性编译器再生成 Seedance 提示词；
- Core 将候选保存为视频专用 ReviewArtifact，用户批准后才切换场景正式版本；
- 工作台展示任务状态、素材职责、连续镜头时间线、最终提示词和 Seedance 请求预览；
- 素材上传、哈希、类型校验、权利声明与锁定均为真实持久状态；未锁定时真实渲染按钮禁用；
- 火山 API Key 只留在 Agent/供应商网关环境变量中，未配置或未通过启用门 B 时只能导出请求预览。

### 2026-08-08 实跑纠偏与本轮验收

首个纵向切片证明了任务、审核和素材上传链路能够运行，但实跑也暴露出“方案批准”和“可提交渲染”
之间仍缺少正式编译闭环。本轮必须完成以下修复，不能只在界面上改状态文字：

- 每个方案素材需求保留稳定的逻辑 `assetId`；真实 `VideoAssetBinding` 必须通过
  `requirementAssetId` 明确解析其中一个需求，禁止依靠自由文本实体名称猜测对应关系；
- 一个场景的同一素材需求最多绑定一个当前真实素材。绑定素材必须属于同项目、已经锁定、模态一致且
  职责一致；替换时通过 revision 与唯一约束防止并发覆盖；
- `ReferencePacker` 保留镜头使用的逻辑素材 ID，同时写入真实素材 ID 与内容哈希。任一需求未解析时，
  制作包必须保持 `submissionReady=false`，并列出缺少的需求；
- 用户批准方案时持久化当时的正式提示词包。之后每次绑定或替换素材，Core 都从已批准方案和全部当前
  绑定确定性重新打包、重新编译并保存；禁止继续展示批准前的 fixture 包；
- 镜头声画信息拆为对白、环境声、动作音效和音乐。编译器分别输出 `{台词}`、`<声音>` 和
  `（音乐）`，并保留旧 `sound` 字段的只读兼容，不能再依赖模型在自由文本里自造标记；
- 镜头补充入画状态、出画状态、调度和屏幕方向，用于相邻 CameraBeat 的连续性检查；单镜头只允许
  一个主运镜，过密镜头或对白时长不足给出可见警告；
- 单场景默认由用户选择明确原文区间，界面显示选区字数并建议 300～2000 字；章节全文仍可手动使用，
  但不能让一个偶然从句中间开始的宽泛切片伪装成精确来源锚点；
- 界面分层展示“方案待审核/方案已批准”“素材已解析 X/Y”“提示词已重新编译”和“可渲染/不可渲染”。
  `approved` 只代表方案批准，不等于素材齐备或供应商已启用；
- 验收必须在 `novelwriterdev` 重新生成一个场景，批准方案，绑定至少一个真实锁定素材，并证明返回的
  正式制作包引用真实素材 ID/哈希且就绪状态随缺失素材数量正确变化。

### 阶段 3：改编、连续性与提示词编译

- 建立独立 `video_planning` Agent 工作流和耐久命令；
- 使用 strict 工具调用依次生成改编、视觉方向、素材需求、正式 Canon、场景和生成段候选；
- 所有候选走 ReviewArtifact 复审、返工、用户确认和 Core 正式应用；
- 建立长篇连续性账本和中短篇精简层级；
- 在《无年之灾》输出带真实锁定素材的可审核制作包。

### 阶段 4A：真实渲染禁用态实现

- 实现按 task kind 分组的 Seedance 能力档案、请求编译、提交和查询适配器；
- 建立耐久 VideoCommand、Redis 投递、签名回调、due 轮询和重启恢复；
- 实现费用预占/结算/释放、未知提交对账、结果及时归档和临时 URL 回收；
- 实现 TechnicalQualityReport、用户审片与接受/丢弃，语义检查先由用户完成；
- 使用 fake provider 和录制的脱敏响应完成故障注入；生产开关保持 `disabled`，不能真实付费提交。

### 启用门 B：最小真实调用

- 配置并验证方舟账号、`doubao-seedance-2-5-260628` 权限、配额和价格；
- 确认 TOS、结果转存、受控出网和 provider 密钥管理；
- 用非真人或已授权人像执行最小 4 秒、480p 测试，验证请求、查询、归档和计费对账；
- 实调任务类型边界、错误码、超时、未知提交和结果 URL 行为；
- 未通过时能力状态保持 `documented`/`disabled`，不能进入 `verified`。

### 阶段 4B：受控真实渲染

- 首版只开放 480p/720p、4～30 秒及实调通过的素材组合，不展示 1080p/4K/180 秒；
- 先限制单项目、单生成段和显式费用确认，不开放批量按钮；
- 完成《无年之灾》一个 15～30 秒片段的“技术质检 + 用户人工语义审片”付费验收。

### 阶段 5：质量检查与长篇批量生产

- 实现人物、场景、动作、声音和连续性自动报告；
- 支持局部编辑或同输入重生成；
- 增加分集模板、素材继承、跨集状态检查和基础成片组装；
- 在成本、2 核 2 GB 资源和失败恢复验证后再开放批量生产。

## 安全与删除

- 火山方舟、TOS 和其他供应商密钥只存在于对应服务端；
- 上传 URL 短时、一次性、限制对象键、类型和大小；
- 下载 URL 短时且必须先校验小说归属；
- 文件名、MIME 和扩展名都不能单独作为可信类型依据；
- 记录内容哈希，供应商请求日志不得输出密钥或完整签名 URL；
- 用户删除项目时先列出精确项目键并进入可恢复软删除窗口，不能递归删除用户根目录或桶；
- 清理供应商临时 URL 前先确保结果已复制到受控存储；
- 真人脸、声音和第三方素材必须记录用户权利声明，不能自动推定可商用。

## 验证要求

- 共享契约：Pydantic、生成客户端、跨语言样例和 extra-forbid 测试；
- Core：归属、ReviewArtifact 应用事务、revision 冲突、上传签名、媒体探测、哈希、命令恢复、
  Saga 补偿、费用预占/结算/释放和删除边界测试；
- Agent：严格结构化结果、来源绑定、最小上下文、引用打包、提示词编译、能力降级和非法工具调用测试；
- Web：素材锁定门禁、引用缺失、长篇/中短篇层级、任务恢复和完整提示词展示测试；
- 架构：Agent 不连接数据库、浏览器不访问内部接口、Nginx 阻断、受控出网 allowlist、Compose 密钥、
  Redis 小载荷和只读根文件系统测试；
- 数据库：只对已确认的 `novelwriterdev` 执行本规格迁移；迁移后导出并审查 schema contract，运行模型
  元数据对账、归属测试、回滚脚本静态测试和实时 schema 指纹校验；
- 真实验收：先离线导出《无年之灾》完整制作包，再在治理门 A 与启用门 B 均通过后执行一次受控
  付费渲染。

## 实施前阻断项

官方模型 ID、创建接口、480p/720p、4～30 秒、50 个总素材上限、分类限制和结果 URL 生命周期已经
确认，不再列为未知。以下任一项未解决时，不得启用真实 Seedance 2.5 调用：

1. `novelwriterdev` 的基础视频控制面、视频 ReviewArtifact 绑定和批准事务已实施并验证；生产迁移仍未
   获得许可；
2. 视频规划任务已有 PostgreSQL 耐久事实与 Redis 投递，但真实渲染的 submit/poll/archive Saga、
   due 调度和崩溃恢复尚未落地；
3. 视频计费单位、价格、预占/结算/释放和未知提交对账依据未确认；
4. 当前方舟账号/地域的模型权限、配额和最小实调未通过；
5. Agent 已有独立 provider 出网网络和服务端密钥占位，但域名级 egress allowlist、账号密钥配置和
   供应商请求日志脱敏实调未完成；
6. 本地素材上传验证已完成；TOS 或替代对象存储、24 小时内结果转存和完整数据生命周期未完成；
7. 首尾帧、R2V、原生音频、各任务类型素材边界、错误码及取消能力中准备开放的部分尚未实调；
8. 普通上传已有权利确认与锁定状态；真人授权素材、声音权利以及静态素材自动生成流程仍未完成。

治理门 A 已对本地服务所连接的服务器 dev 数据库通过，因此开始实施阶段 2、3 和 4A。其余真实调用阻断项与启用门 B
未通过前，不得进入阶段 4B，也不得打开真实供应商调用；开发界面必须如实显示“请求预览”或“供应商
未启用”，不能把 fixture、占位素材或 fake provider 标成可提交状态。
