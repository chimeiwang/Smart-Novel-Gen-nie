# 剧集制作重构实施规格

日期：2026-09-10

状态：P0～P4 的仓内实现和本地隔离验收已经完成。新 Episode 生产链、关键帧、simulated MP4、基础后期、唯一前端／公共 API／普通 CLI 均已落地；旧章节视频运行入口、Catalog 定义和后台装配已经退出。A／B／C 组合 E2E 与完整 `mvnw verify` 已通过。真实 Seedance 调用、服务器退役迁移和生产发布继续关闭。

产品依据：[视频业务重做设计](2026-09-09-video-production-redesign.md)。实施结果与剩余收口见 [分批实施计划](../plans/2026-09-10-video-episode-production-rebuild.md)。用户已允许重新设计视频相关功能及结构，并说明相关视频没有历史数据；已落地能力均以当前代码、契约和测试为准，不从早期暂停补丁推断完成。

计划补充：用户要求具体修改计划。分批计划进一步给出任务编号、模块范围、依赖、验收和初步工时；本规格同时明确初始基线与生成的先后关系，以及镜头结构重构和所有消费者适配必须同批完成的约束。

## 1. 交付边界

第一批完整交付：作者按独立分集选择多个小说来源，起草、编辑并确认单集剧本，再设计分镜；修改第一集后可以处理本集和后续集的影响，明确沿用适用成果。现有生成、素材和基础后期能力接到新的分集身份，最终只有一条新建制作主链。

保留 Core 唯一持久化所有者、Agent 单 Step 执行、公共 API、人工确认、不可变来源和素材的边界。视频 AI 工作流直接使用现有 V2 执行内核，不保留 `VideoAdaptationTask` 作为新工作流的第二份执行权威。

本轮设计不扩展为多镜自动视频编辑、完整声音生产引擎、商业预算结算或生产开放。真实 Seedance 调用继续独立封装并保持关闭；受控模拟只能证明制作业务与恢复链，不能证明画质或音色一致性。

## 2. 实施现场与结构结果

- P0 已完成旧实现、共享引用、公共契约、Agent 输出和三项具名迁移边界盘点；整个实施保留工作树中的其他任务改动，没有整体 reset。
- P1/P2 结构已经进入当前开发 schema-contract 与 jOOQ：独立 Episode、来源快照、剧本／分镜版本、稳定 Shot、影响复核、TakeAdoption、ProductionBaseline 和后期新作用域均有明确约束。
- ReviewArtifact、WorkflowRun／Evidence／Event、计费和素材仍是共享事实；P4 retirement 不删除这些表，也不使用 DROP CASCADE。
- 旧公共／内部视频路由、旧后台装配、普通 CLI 和旧 UI 已退出。旧 Java/Python 仓储源码及旧 jOOQ 类型作为未装配死代码暂留，实际服务器物理退役时与 schema-contract/jOOQ 同步处理。
- `20260910_video_legacy_domain_retirement.sql` 只在具名隔离 PostgreSQL 完成正向、幂等、两类旧行 guard 和中途失败整事务回滚验证；没有应用到服务器数据库。

## 3. 对象与持久化设计

优先重构视频专属关系，强类型小文档可以保存为带 `schemaVersion` 的 JSON。不能把所有生产事实塞进一个任意 JSON，也不为每句台词机械增加一套版本表。

| 对象 | 关键身份与内容 | 写入方式 |
| --- | --- | --- |
| `VideoProject` | 小说归属、系列名、画幅及默认创作说明 | 复用项目；默认值变化不改旧制作版本 |
| `VideoEpisode` | 稳定 episodeId、projectId、novelId、标题、展示顺序、各业务 head 与 revision | 创建幂等，改名／排序 CAS；集号不参与身份 |
| `VideoEpisodeSourceSetVersion` | 本集一次明确选择的来源集合、顺序、内容哈希 | 不可变版本 |
| `VideoEpisodeSourceSnapshot` | 来源集合、章节身份、原文快照、哈希、Unicode 范围 | Core 从权威章节冻结；多章分别保存 |
| `VideoEpisodeScriptDraft` | episodeId、revision、基础正式版、来源集合、完整结构化工作稿 | 自动保存只更新工作稿，CAS 防止覆盖 |
| `VideoEpisodeScriptVersion` | 完整剧本、来源、承接依据、作者确认的状态、内容哈希和审核来源 | 人工确认后创建不可变版本 |
| 稳定 Shot 与 ShotVersion | 独立镜头身份，以及某版方案中的具体内容、剧本场次／台词绑定 | 现 `VideoShot` 内容行改造为版本；另设稳定身份 |
| `VideoShotPlanVersion` | episodeId、scriptVersionId、已确认镜头版本与顺序 | 复用版本机制，退出章节改编归属 |
| `VideoProductionBaseline` | 本次选定的剧本、分镜、参考、声音及素材采用关系 | 不可变清单；单独 CAS 切换当前制作基线 |
| `VideoTakeAdoption` | 原 Take、目标镜头版本、核对依据及作者采用决定 | 不改原 Take 的生成清单；同集显式采用 |
| `VideoEpisodeDependency` | 消费场次／台词、来源集的正式版本、状态 key、时间关系和哈希 | 与正式剧本同事务冻结 |
| `VideoImpactReview` | 前后版本、基线 revision、直接差异、待复核对象、逐项决定 | 决定幂等并校验被审依据；不能成为第二份工作流状态 |
| `VideoEpisodeCommand` | projectId／novelId、可空 episodeId、命令类型、actor、clientRequestId、requestHash、完整结果 | 只保存已完成领域命令回执；不承担任务执行或草稿内容 |

实际 SQL 合并／拆分以约束和查询为依据，不将以上概念数量作为新增表数量目标。退役旧章节根、章节 head、断点分集及不再承担业务事实的 Beat／来源关系时，必须同步处理关联仓储、契约和测试。

### 3.1 稳定场次与台词身份

场次、台词与行动节点先放在版本化剧本文档内，具有稳定 ID、顺序、类型和明确引用。Core 在保存事务校验唯一性、归属、来源范围、说话人和版本对应关系；跨集依赖锚定到不可变剧本版本内的确切节点。

新节点由 Core 分配身份。前端／模型可以提交临时 key，Core 返回映射；修订只能使用冻结的已有 ID 或明确声明新建节点。标题、镜号和台词相似度不能用来自动认定同一对象。删除节点在新版中明确记录，不修改旧版本。

移动和修改保留逻辑身份；复制产生新身份；删除后不得把旧 ID 分配给别的内容；拆分／合并记录明确来源关系。JSON 内节点存在性由 Core 事务校验及 PostgreSQL 集成测试保证，不宣称数据库外键已经逐节点验证。

### 3.2 生成依据与采用关系

Take 保留生成时的镜头版本、提示词、参考、声音意图、参数与媒体哈希。新制作采用旧 Take 时，创建独立 Adoption，检查同项目、同集及实际关联依据。

采用决定先绑定 episodeId、目标 shotVersionId、比较依据和必要的原制作基线；可以逐项形成，但不会立即替换当前制作。新的 ProductionBaseline 明确引用经过校验的 Adoption ID 集合，确认基线时才生效。这样不需要让采用记录和新基线互相依赖，也不重建全局唯一的“当前 Take”。

初始基线 B0 允许镜头处于“待生产”，不要求已经有 Take，但必须冻结本次生成所需的剧本、分镜、参考和声音意图。渲染读取 B0 的明确输入；生成成功只登记候选；作者采用后确认 B1，B0 保持不变。粗剪与混音是引用制作基线的下游版本，基线创建不反向要求已有粗剪／混音；导出一次性冻结基线、粗剪和混音的确切组合。

首批不自动跨版本复用。直接输入未变只是沿用候选条件；角色知情程度或前后语境改变仍可能需要人工复核。作者明确确认后记录核对结果和目标制作上下文。只有存在有效采用关系的素材才可进入新基线，不通过删除现有归属检查实现复用。

### 3.3 后期关系

粗剪、声音、导出统一以 episodeId 和明确版本为根，不再依赖 `adaptationId + episodePlanVersionId + episodeNo`。剪辑片段有独立 clipId，引用采用关系与实际媒体入出点；不能用 shotId 充当每个时间线片段的唯一身份。

原“每个正式镜头恰好出现一次”的规则退出。基础粗剪可明确省略镜头或重复采用同一素材区间，记录创作决定；完整性检查针对未处理占位、无权访问、无效采用、时长越界和缺失文件。首批不因此增加复杂转场、变速或调色。

对白、旁白与字幕保留稳定台词关联。附加声音不能默认为替换原声；需要明确的片段原声保留／静音选择。完整音色管理和重配音引擎留后续，原生音视频不能承诺改声必然不影响画面。

### 3.4 P2 分镜与首个制作基线的精确结构

P2 使用 `VideoEpisodeShot` 保存不随文案、镜号和顺序变化的镜头身份；镜头在某次正式分镜中的具体内容保存为
`VideoShotVersion`。工作稿 `VideoStoryboardDraft` 只保留当前可编辑文档和 revision；正式确认创建不可变的
`VideoStoryboardVersion` 及其完整 `VideoShotVersion` 清单。修改现有镜头沿用 shotId；复制、替换、拆分或合并
必须提交 `tempKey` 及类型化 `lineage`，由 Core 在同一事务分配新的 shotId、保存一个或多个来源 shotId 并返回
映射。替换和复制各有一个来源，拆分允许一个来源产生多个新身份，合并必须有至少两个有序来源；不能用单个
`replacesShotId` 冒充全部沿袭语义。已从工作稿删除的 shotId 不能凭相似标题重新使用；旧分镜中的镜头与镜头
版本保持只读。

分镜文档固定使用 `video-episode-storyboard/1.0`，每个镜头必须绑定该正式剧本中的稳定 sceneId，可选绑定同一
场次内的 lineId；同时保存镜头标题、画面动作、景别、机位运动、预计毫秒数和类型化制作意图。Core 校验身份、
顺序、剧本归属与行级范围，不能依赖模型声称其只修改了选区。P2 的手工保存和确认可独立工作；分镜 Agent Run、候选预览和采用已经通过独立 V2 操作接通，正式确认仍是作者的另一项操作。

`VideoProductionBaseline` 是整集不可变制作输入。确认 B0 时，调用方只选择同集的正式剧本版本、与之精确绑定的
正式分镜版本、可空的当前基线和 `productionRevision`；Core 从该分镜派生全部镜头版本及顺序，逐镜冻结
`VideoProductionBaselineShot`，不接受调用方省略或重排镜头。B0 的镜头状态均为 `pending`，可以没有 Take，
但会冻结镜头版本内容和完整的试制输入：`provider=seedance`、模型、`generationMode=reference`、
`executionMode`、`feeConfirmed`、提示词、画幅、4～12 秒、`resolution=720p`、`generateAudio`、水印、
`outputFormat=mp4`，以及最多 20 份有序参考版本、素材身份和哈希。当前输入 schema 为
`video-production-shot-input/1.2`；每份 Canon 参考和关键帧同时冻结 `rightsStatus=confirmed` 与规范 UTC
`lockedAt`，渲染前再和当前数据库中的版本、素材哈希、MIME、职责、权利与锁定时刻逐项核对。`1.0`／`1.1`
只兼容历史 simulated 读取；live 创建、重试和 worker 解析均要求 1.2，否则关闭失败并要求新建基线。模拟模式不得确认费用；live 模式必须确认费用。
参考素材必须是同项目、权利已核验的 JPEG／PNG／WebP。后续素材采用由 `VideoTakeAdoption` 和新的基线版本表达；
`VideoProductionBaselineShot.adoptionId` 显式引用适用于该目标 shotVersion 的采用事实，P2 不修改旧 Take head，
也不把“生成成功”当成“已经采用”。

`VideoEpisode.currentStoryboardVersionId` 与 `currentProductionBaselineId` 是两个独立 head；
`productionRevision` 只保护制作基线切换。确认新版分镜只更新分镜 head，既有制作基线继续指向原剧本和原分镜。
确认新基线在单事务创建不可变基线、完整镜头清单、领域命令回执，并以 CAS 更新制作 head。相同
clientRequestId／请求体重放返回原结果，不同请求体复用同一 key 返回冲突。

P2 公共资源具体为：分镜工作稿读取／CAS 保存，分镜确认准备／读取／批准，正式分镜列表／单版读取，以及制作
基线确认／列表／单版读取。正式确认继续使用 `ReviewArtifact(kind=video_episode_storyboard)`；共享审核引用为
RESTRICT。公共 Python 路由只提供 OpenAPI 权威，运行实现仍由 Java Core 独占。

素材采用前必须通过 `GET /api/v1/video/episodes/{episodeId}/takes` 按必填 `targetShotVersionId` 获取有界候选，
不得要求作者手填 Take ID。Core 先验证目标镜头版本属于同用户、同项目、同集，再只返回该集已归档并锁定的
新域 Take；按 `createdAt,id` 倒序，用 `beforeTakeId` 和 `limit` 做稳定游标分页。每项摘要包含源基线、源稳定镜头、
源镜头版本、提示词版本、素材 ID、时长、文件字节数、MIME、可得的画面宽高、模型、输入哈希，以及针对目标
镜头版本的最近采用记录。宽高缺少可信归档元数据时返回空值，不能用输入期望值冒充实测媒体尺寸。
成功 Take 可通过 `lastFrameAssetId` 以同项目复合外键冻结已归档尾帧；供应商临时 URL 只存在查询过程，不能写入
不可变 Take 或候选摘要。

### 3.5 P3 基础后期与交付的精确结构

基础后期公共资源全部位于
`/api/v1/video/episodes/{episodeId}/production-baselines/{baselineId}`。粗剪、声音字幕和交付历史均以调用方明确
指定的基线为根，不读取或拼装其他基线的最新 head。粗剪和声音分别使用
`VideoProductionEditHead(episodeId,productionBaselineId)` 与
`VideoProductionMixHead(episodeId,productionBaselineId)` 做 revision CAS；历史列表只返回有界摘要，完整 clip、声音和
字幕仅由精确版本 GET 返回。

粗剪保存请求使用有序 clip 临时键，Core 为每一项分配全局独立 `clipId`。每个正式 clip 必须同时引用属于目标
基线镜头的 adoptionId 和它采用的 takeId，提供真实 sourceInMs/sourceOutMs，且出点不能超过锁定视频素材的实测
durationMs；时间线起点和输出时长由 Core 按顺序派生。同一个 adoption 可以在一版中出现多次并形成不同 clipId。
每项明确选择 `sourceAudioMode=keep|mute`。基线中的每个镜头版本必须由至少一个 clip 或一条带原因的 omission
处理；省略只写 `omissionsJson`，不能生成无 Take 的占位 clip。

声音字幕版本必须引用同一基线下确切的 editVersion。附加音频只接受同项目、权利已确认并锁定的受控 audio
素材，入出点不得越过实测时长；可选 shotVersionId 必须属于该基线。字幕必须同时绑定该基线的正式
shotVersionId 和其正式剧本中的 scriptLineId，开始、结束时间位于粗剪总时长内。字幕文案可以做展示调整，但稳定
台词身份不能由自然语言猜测。

导出任务明确冻结 baselineId、editVersionId、mixVersionId、三者内容哈希、每个 clip 的 clipId／adoptionId／
takeId／原声决定、所有媒体 storageKey 与 SHA-256、字幕台词身份，以及固定画幅、分辨率、帧率、字幕烧录和 FFmpeg
编码参数。worker 只能读取该不可变 manifest，不回读当前 head。旧基线可在没有活动导出任务时明确创建新任务；
失败重试复制原任务 manifest，不能换成新 head。成片文件、`VideoAsset`、不可变 `VideoEpisodeExport` 和任务成功
状态同事务闭合；内容接口只按精确交付 ID 读取受控文件。

## 4. 四种版本与事务边界

| 命令 | 前置条件 | 原子结果 |
| --- | --- | --- |
| 保存工作稿 | 工作稿 revision、完整有效文档 | 更新工作稿并递增 revision；不生成正式版 |
| 采用 AI 候选 | Artifact revision、目标工作稿 revision 与冻结基线匹配 | 候选应用到声明的工作稿目标，保存来源与决定回执 |
| 确认正式剧本／分镜 | 确切工作稿及审核依据、head revision | 新正式版本、确认命令与影响事实一起提交 |
| 确认新的制作基线 | 所选版本存在且同集、待处理事项已按规则复核 | 不可变制作清单及当前 head CAS 更新 |
| 导出／交付 | 指定制作／编辑／声音版本和完整受控素材 | 冻结任务；归档完成后新增交付版本 |

正式内容仍遵循 proposal／ReviewArtifact／作者确认／Core 应用边界。AI 候选采用到工作稿后，不能对同一 `applied` Artifact 再次执行正式应用；正式批准保存独立的工作稿快照、审核依据和幂等决定。纯手写内容可以形成作者来源的待确认审核记录，不伪造 AI 候选或模型 Run。具体人工确认入口沿用现有视频领域模式，界面不增加重复确认向导。

确认正式剧本 v2 后，制作基线可以继续引用 v1，成片 v1 继续可读。生成与导出请求必须绑定明确基线，不临时拼装各对象最新 head。历史基线允许有清楚版本标识的再次导出。

所有写命令校验归属、幂等请求和相关 revision。相同 clientRequestId／内容重放返回既有结果；相同 key 不同内容返回冲突。网络响应不确定时先查命令回执，不自动换新请求 ID 再写一次。

分集创建、改名／调序、来源保存、正式确认等需要耐久回读的领域命令统一使用视频专属 `VideoEpisodeCommand`。`(actorUserId, clientRequestId)` 唯一，requestHash 和 resultJson 不可变；创建分集时 episodeId 可以为空，其余命令按类型要求精确分集。它只记录已经提交成功的原子业务结果，不能成为新的 Run、队列或 Artifact 状态。

## 5. 影响复核与跨集承接

1. Core 以来源集合、场次／台词稳定 ID、角色／道具状态和制作采用关系计算直接差异。
2. 已有明确依赖的后续场次列为直接影响；涉及语境的对象列为可能影响，不冒充自动确认的事实。
3. 可选语义分析只生成绑定证据的报告。查不到直接引用不能判为无影响；发现差异也不要求全部重做。
4. 作者选择沿用、修订、明确不采用，或继续保留旧制作基线。每项决定保存报告版本、对象版本及依据。
5. 依据变化后旧决定不能静默继续有效，返回冲突并保留本地选择。确认新制作基线时再次校验。

前集结尾引用的是 producerEpisodeId、producerScriptVersionId、状态 key 和时间关系。消费者可以是后续集、回忆或并行场景，不按集序号自动继承。引用必须指向已确认版本；对草稿中的未决承接不能伪装成正式事实。

小说更新只显示“来源有新版”。作者选择同步后创建来源集合与新剧本草稿；旧锚点仍定位旧快照。系列默认定妆更新同样只提供可选新依据，不回写既有制作。

## 6. 公共接口现状

下面的资源分组已经由 Pydantic/OpenAPI、Java Core、生成客户端和普通 CLI 落地。浏览器与 CLI 只访问这些 Episode 主链资源，不再暴露旧 chapter-adaptation 语义。

| 资源／路径组 | 必须支持的操作与关键输入 |
| --- | --- |
| `/api/v1/video/projects/{project_id}/episodes` | 列表、幂等创建；排序命令带项目 revision |
| `/api/v1/video/episodes/{episode_id}` | 聚合回读、修改标题；独立返回草稿／正式／制作／交付状态 |
| `.../source-sets` | 创建／读取来源集合；每项带章节版本、范围和内容哈希 |
| `.../script/draft` | 回读与 CAS 保存工作稿；返回稳定节点 ID 映射 |
| `.../script/runs` | 起草／局部修订；冻结来源、工作稿 revision、修改范围及意图 |
| `.../script/confirmations`、`.../script/versions` | 准备确切确认内容、作者批准、读取历史；不能复用已应用的候选决定 |
| `.../storyboard/draft`、`.../storyboard/runs`、`.../storyboard/confirmations` | 从正式剧本起草／修订分镜、工作稿 CAS 与人工确认 |
| `.../impact-reviews` | 读取直接差异／语义报告，幂等记录逐项决定 |
| `.../production-baselines`、`.../take-adoptions` | 明确沿用或采用素材，确认版本组合；不修改原素材 |
| `.../render-tasks`、`.../edit-versions`、`.../mix-versions`、`.../export-tasks` | 按 Episode、ProductionBaseline 和精确资源 ID 创建、恢复及读取媒体结果 |

Run／Artifact 观察复用现有公开读取能力，视频专用归属与应用分派已经接通；文件访问仍走受控素材接口。旧章节改编、章节内分集、旧逐镜任务及按 episode_no 后期入口已经退出公共契约。当前视频 OpenAPI 为 56 个路径、67 个操作，Java VideoApi 只保留 11 个 Project／Asset／VisualCanon／provider-asset 共享操作，其余按独立 Episode tag 分组。

Python 公共契约、Java 实现、生成 TypeScript／Java 模型及普通 CLI 已同步到唯一新链；接口与命令数量按实际导出冻结。Operator Skill 白名单没有因普通 CLI 改造自动扩大。

当前 Durable Agent V2 Catalog 共 23 项，其中 19 项为既有业务操作，视频仅保留
`episode_script_generate`、`episode_script_revise`、`episode_storyboard_generate` 和
`episode_storyboard_revise` 4 项 Episode 候选操作。旧章节视频操作不再出现在 Catalog、运行分派或 Agent
执行入口中。

## 7. Core 与 Agent 执行接入

| 操作 | 冻结输入 | 结果 |
| --- | --- | --- |
| 剧本起草／修订 | Episode、来源集合、工作稿和正式版、承接状态、创作意图／修改范围 | 剧本工作稿候选 Artifact |
| 分镜起草／修订 | 正式剧本版本、稳定场次／台词、原分镜、必要设定及修改范围 | 分镜工作稿候选 Artifact |
| 可选语义影响分析 | 前后版本、制作基线、直接差异和依赖 | 只读报告，不创建可直接替换内容的候选 |

新工作流只使用 V2，novelId 保持真实小说，chapterId 和写作 session 不绑定实时章节。Evidence 保存类型化完整输入和哈希。Run 完成代表候选／报告已持久化，Artifact 仍可 awaiting_user；观察完成不能代表作者已采用。

新增视频专用 Operation、Profile、输出 Schema、阶段策略和物化器，不能借用 `chapter_draft`、`beat_plan` 或 `agent_updates`。已有 `VideoStagePolicy` 和 callback 的视频操作识别为封闭集合，必须一起更新；只加 Catalog 不足以完成接入。

一次真实模型 HTTP 仍对应一个 Step，沿用预算、取消、journal、签名回调和同小说互斥。内部有界审阅与返工沿用既有机制；完成后作者提出新修订建立新 Run，不重新打开已完成 Run。

模型仅返回可校验提案。未选修改范围由 Core 保留；不要求模型全量重写后相信其“未改其他部分”的声明。视频任务的生产关闭与调度门禁同样覆盖新 Operation。

## 8. 迁移与旧链路退出

三项具名迁移已经落盘：

1. `scripts/migrations/20260910_video_episode_script_domain.sql`：独立集、来源、剧本、承接、影响复核及共享审核中的 Episode 目标约束；
2. `scripts/migrations/20260910_video_production_baseline_domain.sql`：稳定镜头、分镜版本、采用关系、制作基线，以及渲染和后期的新作用域外键；
3. `scripts/migrations/20260910_video_legacy_domain_retirement.sql`：只在精确零旧行、零共享旧证据时退役 25 张 legacy-only 表。

P4 脚本明确保留新链复用的 PromptVersion、KeyframeVersion、RenderTask、Take、Extraction、Edit/Mix/Export 等 12 张双作用域表，只在旧分支为零时具名解除旧约束并收紧新 Episode scope。脚本保留 ReviewArtifact、Workflow Run/Step/Evidence/Event/Evaluation/BillingReservation、TokenUsage、VideoAsset 和受控文件；不执行 DELETE、TRUNCATE 或 CASCADE。

隔离 PostgreSQL 已验证：空旧域正向成功；同库幂等重放成功；legacy-only 行和共享表旧分支行分别阻断；额外未盘点外键在 DDL 中段触发 RESTRICT 后，之前的表、列和约束全部随事务回滚。该证据只证明脚本的隔离行为，没有连接或修改服务器数据库。

旧公共／内部路由、旧 UI、普通 CLI 和旧 dispatcher/reconciler 装配已经移除。当前 schema-contract、生成 jOOQ 和未装配旧仓储源码仍保留旧表投影；实际服务器晋升时必须在单独授权、备份和目标库零数据审计后同步更新，不能直接复制隔离库结论。

生产环境继续拒绝开启视频预览、真实 Seedance 和相关调度。新增结构或模拟产物不构成生产开放，也不触发 Durable Agent DDL rollback。

## 9. 前端交付要求

- 保持现有小说工作台外壳，视频视图以 projectId／episodeId 恢复上下文，不再以 currentChapter 决定正在制作的集。
- 将新路由查询状态纳入页面解析，刷新、前进后退和深链接回到同一集及工作面；章节列表仅在取材面板出现。
- 两个主要工作面为剧本、分镜与制作，右侧显示所选对象依据与待处理影响。正式／制作版本可以不同，文案必须准确。
- 工作稿自动保存带明确状态，切换前等待在途保存；409 保留输入并显示冲突，不能用远端新稿覆盖本地未提交内容。
- 长任务使用可恢复观察，离开停止读取而非取消执行。取消是明确独立操作。
- 镜头制作工具就地复用已有视觉、提示词、关键帧与候选能力。没有素材或没有已确认制作时，不能显示“沿用成功”或虚构成片。
- 展示所用剧情时间和承接版本；回忆不自动继承上一集结尾。影响未处理不等于原交付版本失效。

## 10. 必须通过的验证

1. 用户认可的 A／B／C 三个场景用隔离 PostgreSQL 与浏览器走通，固定素材和受控 Agent 响应明确标记。
2. 一集跨章、一章多集、改名和调序；稳定身份不漂移，来源正文和其他小说成果不变。
3. 自动保存、候选采用、正式批准及基线确认的两窗口竞争；响应丢失重放不产生重复版本或重复模型任务。
4. 草稿修订不更改正式版；批准剧本 v2 不清空 v1 制作与交付；旧基线仍能明确读取与再次导出。
5. 改动范围之外不被模型覆盖；场次／台词／镜头同名不意味着同一身份。
6. 同集 Take 显式沿用可用，跨用户／项目／错误版本或缺少采用关系被拒绝；原始媒体与生成清单不变。
7. 第一集由交信改为收回信，第二集开信进入复核；三日前的回忆保留独立依据；旧决定不能应用到新报告。
8. 基础粗剪可明确删镜或重复素材，媒体区间正确；原声处理意图明确，预览与导出使用相同清单语义。
9. V2 候选完成与采用分离，重启不重复调用；新视频 Operation 不绕过视频门禁，不破坏现有小说工作流。
10. 相关前端测试、typecheck、lint、Python pytest／Ruff／Mypy、Java JUnit 与完整 Maven verify、契约生成检查及架构检查通过。

最终仓内证据：公共契约为 56 个视频路径／67 个操作，VideoApi 为 11 个共享操作；Durable Agent V2 Catalog
共 23 项，其中视频 4 项；完整 `./mvnw verify` 通过服务鉴权 11 项、服务契约 5 项、Core 1,248 项
（3 项按预期跳过）和 Java CLI 145 项；Python 全量 5,864 项通过、3 项跳过；Web 371 项、生成客户端 3 项、
Ruff、Mypy、typecheck、lint 和 `api:check` 均通过。P4 数据退役保护已完成上述隔离 PostgreSQL 验证。

A／B／C 组合 E2E 已在本地隔离环境通过，完整证据见
[最终验收记录](../audits/2026-09-10-video-episode-production-final.md)。真实 Seedance、供应商用量、服务器迁移与生产开放未执行。
