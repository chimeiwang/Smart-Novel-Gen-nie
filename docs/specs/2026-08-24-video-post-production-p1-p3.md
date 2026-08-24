# 小说视频后期制作 P1–P3

状态：已完成并通过最终验收（仅开发环境）
日期：2026-08-24
适用范围：长篇小说章节影视化工作台、Core API、CLI、开发库与本地/开发部署

## 1. 背景与产品判断

P0 已经完成“正式镜头 + 正式提示词 + 冻结视觉参考 -> Seedance 任务 -> 不可变 Take -> 人工选片”。
但单镜头候选仍然不是一条可交付视频。P1–P3 必须补齐三个彼此连续、又不覆盖上游事实的制作层：

```text
正式镜头与视觉设定
  -> P1 关键帧/视觉锚点（可选但可进入下一次渲染清单）
  -> 已确认 Take
  -> P2 分集粗剪版本（顺序、入出点、占位、转场）
  -> P3 声音/字幕版本（多轨、校时、替换）
  -> 冻结清单 -> 耐久导出任务 -> 不可变整集成片
```

核心产品原则如下：

1. 关键帧不是另一个“导演方案”，而是正式镜头下可确认、可替换的画面锚点。
2. 粗剪只引用 Take，不修改或覆盖 Take 文件；每次保存产生不可变编辑版本。
3. 声音和字幕绑定一个明确粗剪版本，粗剪变化后必须显式创建新的声音版本，不能静默错位。
4. 导出任务冻结粗剪、声音、字幕、素材哈希和输出参数；历史成片始终能追溯到输入版本。
5. 图片生成模型和 TTS 供应商不属于本轮已存在的系统能力。本轮允许使用已上传或外部模型生成并已锁定的图片/音频，并支持从 Take 抽取关键帧；未来接入图片模型或 TTS 时，只新增素材生产器，不改动关键帧、时间线或混音领域模型。

## 2. 完成范围

### 2.1 P1：关键帧与连续性

- 一个正式镜头可分别确认 `initial_state`、`transition_anchor`、`end_state` 三类关键帧；每类只存在一个当前 head，历史版本不可变。
- 关键帧可来自：
  - 已上传且权利为 `confirmed`、已锁定的 `keyframe`/`storyboard` 图片素材；
  - 从本项目已归档 Take 的合法时间点抽帧后生成的受控图片素材。
- 保存和清除关键帧都携带 `clientRequestId + expectedRevision`，使用 CAS，重复请求返回同一版本。
- 工作台展示每个关键帧角色的完整版本历史；恢复历史图片或清除状态会创建新版本，不覆盖原记录。
- 创建新 Seedance 任务时冻结当前关键帧。Core 生成明确的图片序号指令；Agent 仍只执行供应商短调用，不自行解释业务角色。
- Ark Seedance 当前公开接口只使用有序 `reference_image`，没有可依赖的独立首帧/尾帧 role。本实现按有序图片和明确文本指令表达首帧、过渡锚点和尾帧，不伪造供应商参数。
- 连续性检查返回可解释问题，不给虚假“AI 评分”：
  - 关键帧素材未锁定、已丢失或模态/职责不正确；
  - 同一镜头的首尾帧冲突或重复；
  - 提示词冻结的角色身份、服装、场景、道具参考在关键帧生成时是否仍齐全；
  - 相邻镜头存在同类视觉设定但采用了不同素材版本时提示人工复核。

### 2.2 P2：分集非破坏性粗剪

- 以当前正式 `VideoEpisodePlanVersion` 的集号为边界；Core 根据边界确定每集合法镜头集合。
- 首次进入时提供默认时间线：按正式镜头顺序排列，已确认 Take 自动放入，未确认镜头成为等长占位。
- 用户可调整镜头顺序、选择同镜头任一已归档 Take、设置毫秒级入点/出点、保留占位，以及选择 `cut` 或 `fade_black` 基础转场。
- 一条保存请求必须完整提交该集所有镜头且每个镜头恰好一次；不能把别集或旧正式方案镜头混入。
- 入出点不得超出素材已知时长；素材时长未知时只能使用完整素材，避免静默裁错。
- 每次保存创建 `VideoEpisodeEditVersion` 和有序 `VideoEpisodeEditClip`，并用 `VideoEpisodeEditHead.revision` 做 CAS。旧版本、原始 Take 和原始文件不被改写。
- 用户可把任一历史粗剪加载到工作区，并以显式 `basedOnVersionId` 创建分支版本；head 仍通过当前 revision CAS，不能覆盖其他页面刚保存的结果。
- Web 预览按编辑决定顺序播放真实 Take/占位，并显示时间线总长；无需先导出即可审片。

### 2.3 P3：声音、字幕与整集输出

- 一个声音版本固定引用一个粗剪版本，并保存：
  - 音频片段：`dialogue | narration | ambience | sfx | music`；
  - 素材、可选镜头、时间线起点、源入点/出点、增益、淡入淡出；
  - 字幕 cue：可选镜头、起止时间、说话人和完整文本。
- Seedance Take 自带音频作为粗剪底声保留；附加音轨与底声混合。用户可替换单个音频片段而不改粗剪。
- 首次创建声音草稿时，可从正式镜头的 `speechMode/spokenText` 确定性生成字幕建议；它只是可编辑草稿，不生成或篡改对白。
- 每次保存创建不可变 `VideoEpisodeMixVersion`、`VideoEpisodeAudioClip` 和 `VideoEpisodeSubtitleCue`，使用独立 head revision 做 CAS。
- 声音字幕历史同样可加载并分支；目标粗剪版本与声音版本父链分别保存，不能把“复制历史轨道到新粗剪”伪装成原版本未变化。
- 用户上传的音频和视频必须由 Core 使用 ffprobe 读取真实时长后再固化素材；不能信任调用方声明。探测失败时删除本次临时文件并明确失败，不能留下时长未知却可进入时间线的新素材。
- 导出是 Core 拥有的耐久任务，不在浏览器请求中长时间阻塞。导出冻结编辑版本、声音版本、全部素材 SHA-256、字幕和输出参数。
- 媒体执行器在导出前拒绝残留占位，并使用 FFmpeg 统一画幅/帧率、裁切并串联视频、应用淡黑转场、混合底声和附加音轨、烧录字幕，输出 H.264/AAC MP4 并启用 faststart。
- 成功结果先写入受控 `VideoAsset`，再创建不可变 `VideoEpisodeExport`；浏览器不依赖临时路径。
- 导出失败保留明确错误；显式重试创建新任务并精确复用旧冻结清单，不在未知状态下自动重复产出。

## 3. 非目标

- 不在本轮接入新的图片生成供应商、TTS/声音克隆供应商或自动配乐供应商。
- 不做口型同步、说话人分离、自动降噪、响度母带或多语言配音。
- 不做溶解叠化、光流补帧、变速、画中画、调色、特效合成或局部 Retake；这些进入后续专业编辑阶段。
- 不把静态规则包装成“AI 连续性评分”，也不以机器结论替代用户确认。
- 不重新启用旧 `VideoScene`、`VideoGenerationTask` 或旧视频接口。
- 不授权生产数据库迁移、生产开关、生产部署或真实付费调用。

## 4. 领域模型

开发库具名迁移 `scripts/migrations/20260824_video_post_production_p1_p3.sql` 新增以下表，并把现有
`VideoAsset.duty` 的开发库约束扩展为 `sfx` 与 `episode_export`，避免把音效冒充环境声、把整集成片
冒充逐镜 motion 素材。

### 4.1 VideoTakeFrameExtraction / VideoShotKeyframeVersion / VideoShotKeyframeHead

抽帧事实以输出 assetId 为主键，保存来源 Take、镜头、改编、项目、小说、毫秒时间点、幂等请求和创建人；
`(assetId, takeId, timestampMs)` 唯一。关键帧版本声称 `sourceKind=take_frame` 时，数据库复合外键必须命中
这条来源事实，调用方不能把任意图片伪装成 Take 抽帧。

关键帧版本保存 adaptation/project/novel/shot/plan 归属、role、versionNo、basedOnVersionId、可空 assetId、来源种类、可空 sourceTakeId/sourceTimeMs、内容哈希、请求哈希、创建人和时间。`assetId=NULL` 表示一个显式清除版本。

head 以 `(shotId, role)` 为主键，保存当前版本和 revision。当前版本必须属于同一镜头与角色。

### 4.2 VideoEpisodeEditVersion / VideoEpisodeEditClip / VideoEpisodeEditHead

编辑版本固定引用 adaptation、当前 episode plan、shot plan 和 episodeNo；保存 basedOnVersionId、versionNo、总时长、内容哈希、请求哈希、创建人和时间。

编辑片段以 `(editVersionId, ordinal)` 排序，保存 shot、可空 Take、源入出点、输出时长和后置转场。每个版本内 shot 唯一。

head 以 `(episodePlanVersionId, episodeNo)` 为主键，保存当前编辑版本与 revision。

### 4.3 VideoEpisodeMixVersion / VideoEpisodeAudioClip / VideoEpisodeSubtitleCue / VideoEpisodeMixHead

声音版本固定引用某一编辑版本，并沿用相同 adaptation/episode/plan 归属。音频片段与字幕 cue 都是版本的不可变子项；文本不静默截断。

head 以 `(episodePlanVersionId, episodeNo)` 为主键，保存当前声音版本与 revision。当前声音版本引用的编辑版本不要求等于后来切换的编辑 head；界面必须明确显示“声音基于旧粗剪”，并要求用户显式迁移或重建。

### 4.4 VideoEpisodeExportTask / VideoEpisodeExport

任务保存请求用户、完整归属链、editVersionId、mixVersionId、retryOfTaskId、输出参数、冻结清单、输入哈希、状态、尝试次数、到期时间、错误与时间戳。状态为：

```text
pending -> rendering -> succeeded
                  \-> failed
```

`VideoEpisodeExport` 保存任务、输出素材、集内版本号、输入哈希和创建时间。一个任务至多产生一个 export；历史导出不可覆盖。

## 5. API

| 方法与路径 | 作用 |
| --- | --- |
| `GET /api/v1/video/chapter-adaptations/{adaptationId}/post-production` | 读取关键帧、连续性、分集粗剪、声音和导出聚合 |
| `POST /api/v1/video/chapter-adaptations/{adaptationId}/shots/{shotId}/keyframe-versions` | CAS 保存/清除一个关键帧角色 |
| `POST /api/v1/video/takes/{takeId}/frames` | 从 Take 的合法时间点抽取受控关键帧素材 |
| `POST /api/v1/video/chapter-adaptations/{adaptationId}/episodes/{episodeNo}/edit-versions` | CAS 保存完整粗剪版本 |
| `GET /api/v1/video/episode-edit-versions/{editVersionId}` | 读取一个不可变粗剪版本及完整片段 |
| `POST /api/v1/video/chapter-adaptations/{adaptationId}/episodes/{episodeNo}/mix-versions` | CAS 保存完整声音/字幕版本 |
| `GET /api/v1/video/episode-mix-versions/{mixVersionId}` | 读取一个不可变声音字幕版本及完整轨道 |
| `POST /api/v1/video/chapter-adaptations/{adaptationId}/episodes/{episodeNo}/export-tasks` | 创建一次整集导出任务 |
| `GET /api/v1/video/export-tasks/{taskId}` | 查询导出任务 |
| `POST /api/v1/video/export-tasks/{taskId}/retry` | 按旧冻结清单显式重试 |
| `GET /api/v1/video/exports/{exportId}/content` | 归属校验后播放/下载整集成片 |

公共 Pydantic 契约先于前端实现，并通过 OpenAPI 生成 TypeScript 客户端。所有写接口归属校验到用户、小说、项目、章节改编和当前正式方案。

## 6. Web 产品结构

章节影视化工作台扩展为：

```text
镜头确认 -> 分集 -> 视觉设定 -> 提示词 -> 关键帧 -> 生成与选片 -> 粗剪 -> 声音与输出
```

- “关键帧”仍以镜头为维度，显示首帧/过渡/尾帧和连续性待办；不新增 AI 导演人格。
- “粗剪”以集为维度：左侧集选择，中间播放器与时间线，右侧当前 clip 的 Take、入出点和转场。
- “声音与输出”继续以同一集为上下文：音轨和字幕编辑在上，冻结版本与导出历史在下；导出按钮只在粗剪、声音和 FFmpeg readiness 都满足时可用。
- 页面明确区分“当前工作版本”“历史版本”“尚未确认 Take 的占位”，不把未完成集伪装成成片。
- 导出面板允许明确选择 720p/1080p、24/25/30 fps 和是否烧录字幕，历史任务回显冻结参数。

## 7. CLI

Core 新增的每一个公共操作都提供 CLI：

- `long.video.post.show`
- `long.video.keyframe.set`
- `long.video.keyframe.clear`
- `long.video.keyframe.extract`
- `long.video.edit.save`
- `long.video.edit.get`
- `long.video.mix.save`
- `long.video.mix.get`
- `long.video.export.start`
- `long.video.export.get`
- `long.video.export.retry`
- `long.video.export.watch`
- `long.video.export.download`

复杂时间线和混音请求从 JSON 文件读取，避免在命令行参数中丢字段；watch 输出 JSONL，download 必须显式指定输出路径。

## 8. 运行与安全

- PostgreSQL 保存业务权威状态；Redis 不保存关键帧、编辑、混音或导出事实。
- 媒体处理位于 Core，因为它需要在归属校验后读取受控素材并写回 `VideoAsset`；Agent Service 继续禁止数据库和文件域访问。
- FFmpeg/ffprobe 必须从固定可执行文件名启动，使用参数数组而非 shell；临时目录使用独立随机目录，超时后终止进程并清理。
- Core 容器安装版本化发行版提供的 FFmpeg；readiness 同时检查 ffmpeg 和 ffprobe。缺失时只阻断抽帧和导出，不阻断历史读取与编辑保存。
- 浏览器上传职责不包含 `episode_export`；整集成片只能由 Core 导出流程创建，不能通过普通素材上传冒充。
- 文件路径只由 `VideoAssetStorage.resolve()` 从已校验 storageKey 解析；请求不能传服务器路径。
- 本迁移只允许 `novelwriterdev`，脚本必须在其他数据库主动失败。

## 9. 验收标准

1. 关键帧保存、清除、重复请求和旧 revision 冲突均符合 CAS；旧版本仍可读取。
2. 新渲染清单包含已确认关键帧的 assetId/SHA/role 和最终 providerPromptText；旧 P0 清单仍可解析。
3. 非法图片、未锁定素材、跨项目素材和越界抽帧均被拒绝。
4. 默认粗剪精确覆盖一集全部镜头；无 Take 显示占位；保存后修改不影响旧编辑版本或 Take。
5. 跨集镜头、旧方案镜头、跨镜头 Take、重复/遗漏镜头、非法入出点均被拒绝。
6. 声音版本只能引用同项目已确认锁定音频，时间范围不得越过粗剪总长，字幕时间与文本合法。
7. 切换粗剪后旧声音版本明确显示 stale，不被静默套到新时间线。
8. 同一导出请求只产生一个任务；成功后供应商或临时文件不存在仍可播放受控成片。
9. FFmpeg 失败不创建 export；显式重试创建新任务并复用旧 manifest。
10. Web 可完成关键帧、粗剪、音轨/字幕、导出全流程；所有公共操作可由 CLI 调用。
11. 开发库迁移前备份、隔离库双跑、开发库执行、schema contract 导出与 0 差异校验全部留痕；正式库仅只读校验。
12. Python/Web/CLI/OpenAPI/架构测试、Ruff、Mypy、TypeScript、ESLint 和生产构建通过。

## 10. 实施与验收记录

本节记录 2026-08-24 的最终验收事实，不把开发环境结果表述为生产部署结果。

- 迁移前备份位于 `.data/backups/inkforge-20260824T030508Z`；校验了 SHA-256 和 `pg_restore --list` 可读性。
- `scripts/migrations/20260824_video_post_production_p1_p3.sql` 已在隔离的 pgvector 数据库完成恢复、首次迁移和重复迁移；随后只对服务器端 `novelwriterdev` 开发库执行并再次验证幂等。脚本会主动拒绝其他数据库。
- 开发库完整结构契约包含 85 张 public 表、22 个枚举，指纹为 `8aaa4d25c3cd3114bc8659330700a2eecdbcdefc7f3d83473c93c1baee576629`；最终只读校验 `ready=true`、差异 0。
- `novelwriter` 正式库没有执行本迁移或任何写操作；只读 `without_video_preview` 投影校验 `ready=true`、差异 0，指纹为 `ecd541a96eba65d43fba66f59834f53987818b03ea10298f981a3ab965002fbe`。
- 服务器开发库真实事务测试覆盖关键帧 CAS/重放/历史、27 个占位片段、粗剪和声音版本分支、字幕持久化及占位导出门禁；外层事务最终回滚，独立连接确认本迁移新增的 12 张表均为 0 行。
- 容器内真实 FFmpeg/ffprobe 烟测成功：从视频抽出 PNG，合成 720×1280 H.264/AAC MP4，包含音轨和已烧录字幕；输出时长约 1.833 秒，上传 WAV 探测时长为 2000 毫秒。
- 浏览器使用现有开发实例“雾港守灯人·视频闭环测试”验收正式 v1：27 镜可进入关键帧、分集粗剪、声音与输出；首帧/过渡/尾帧、27 个默认占位、四类附加音轨入口、字幕、历史分支和导出参数均可见，浏览器日志无运行错误。裸机缺少 FFmpeg/ffprobe 时页面会明确展示门禁；最终容器具备并通过上述媒体烟测。
- 最终回归：Python `3213 passed, 3 skipped`；Web `289 passed`；生成客户端 `3 passed`；Compose 安全测试 `17 passed`；Ruff、Mypy（305 个源文件）、TypeScript、ESLint、OpenAPI 漂移检查、`git diff --check` 和 Next.js 生产构建均通过。
- 本轮没有发起真实付费 Seedance 调用，没有接入图片生成或 TTS，也没有迁移正式库、开启正式环境视频功能或执行生产部署。
