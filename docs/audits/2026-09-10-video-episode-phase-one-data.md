# 独立剧集第一阶段数据与 Java 实施审计

日期：2026-09-10

状态：实施中；仅使用本机隔离 PostgreSQL，没有连接服务器开发库或正式库，没有供应商调用。

范围：P0-2、P1-1、P1-2 的来源、草稿、手工确认及候选应用底座。P2 的稳定镜头、制作基线和后期结构不在此迁移内。

## 精确结构范围

第一阶段具名脚本：`scripts/migrations/20260910_video_episode_script_domain.sql`。
只允许 `inkforge_video_episode_test` 与 `inkforge_video_episode_codegen` 两个隔离数据库名；服务器库被主动拒绝。

新增 8 表：`VideoEpisode`, `VideoEpisodeCommand`, `VideoEpisodeDependency`, `VideoEpisodeScriptDraft`, `VideoEpisodeScriptVersion`, `VideoEpisodeSourceSetVersion`, `VideoEpisodeSourceSnapshot`, `VideoImpactReview`。

命令表只记录已完成领域写入的完整幂等回执，不承担模型或工作流状态。新版本、审核来源和跨集依赖均使用 RESTRICT，旧表不 DROP，现有共享证据不回填或删除。

旧视频专属表精确清单（41 张，保留）：

- `VideoAdaptationDecisionCommand`
- `VideoAdaptationTask`
- `VideoAsset`
- `VideoAssetBinding`
- `VideoChapterAdaptation`
- `VideoChapterAdaptationHead`
- `VideoCinematicScene`
- `VideoDramaticBeat`
- `VideoDramaticBeatSourceAnchor`
- `VideoEpisodeAudioClip`
- `VideoEpisodeBoundary`
- `VideoEpisodeEditClip`
- `VideoEpisodeEditHead`
- `VideoEpisodeEditVersion`
- `VideoEpisodeExport`
- `VideoEpisodeExportTask`
- `VideoEpisodeMixHead`
- `VideoEpisodeMixVersion`
- `VideoEpisodePlanVersion`
- `VideoEpisodeSubtitleCue`
- `VideoGenerationTask`
- `VideoProject`
- `VideoReviewDecisionCommand`
- `VideoScene`
- `VideoShot`
- `VideoShotKeyframeHead`
- `VideoShotKeyframeVersion`
- `VideoShotPlanVersion`
- `VideoShotPromptHead`
- `VideoShotPromptVersion`
- `VideoShotPromptVisualReference`
- `VideoShotRenderTask`
- `VideoShotSourceAnchor`
- `VideoShotTake`
- `VideoShotTakeDecisionCommand`
- `VideoShotTakeHead`
- `VideoShotVisualReferenceBinding`
- `VideoShotVisualReferenceSet`
- `VideoTakeFrameExtraction`
- `VideoVisualCanon`
- `VideoVisualCanonVersion`

## 共享表指向旧视频域的外键

| 来源 | 列 | 目标 | 删除行为 |
| --- | --- | --- | --- |
| `ReviewArtifact` | `videoAdaptationId` | `VideoChapterAdaptation` | CASCADE |
| `ReviewArtifact` | `videoSceneId` | `VideoScene` | CASCADE |
| `ReviewArtifact` | `videoAdaptationId, novelId` | `VideoChapterAdaptation` | CASCADE |
| `ReviewArtifact` | `videoAdaptationTaskId, videoAdaptationId` | `VideoAdaptationTask` | CASCADE |
| `ReviewArtifact` | `videoSceneId, novelId` | `VideoScene` | CASCADE |

`ReviewArtifactRevision` 与 `ReviewArtifactEvaluation` 又指向共享 `ReviewArtifact`，旧视频根的级联删除会影响审核证据。新 `videoEpisodeId` 使用复合 `(videoEpisodeId, novelId)` 归属和排他 CHECK，不复用旧 `videoAdaptationId`。

V2 Run 的视频绑定还有逻辑依赖：`sourceType=video_adaptation_task_v2`、`sourceId=taskId`、Evidence 内的 task 与 adaptation。不能仅因没有数据库外键就删除旧 Task。生成/导出还经素材 storageKey 和不可变 requestManifestJson 引用文件；本批没有删除任何文件。

主结构文件为隔离库导出的 94 表、22 枚举，指纹 `36fa5b65e22d940851ac8435eb2042ae3307579634e6fcae0722b468b0931596`。它是原冻结基线叠加本次结构，不是服务器实时指纹；共享 V2 使用独立后迁移契约继续验证。

## 事务与接口事实

- 项目排序与创建通过 Project revision 协调；分集修改、工作稿、来源和确认使用各自 revision。
- 命令以 `(actorUserId, clientRequestId)` 去重，原始结果与领域变更同事务提交；同键不同请求拒绝。
- 来源从 Core 的真实章节冻结完整原文，选区以 Unicode 码点解释。后续章节改动/删除只改变只读提示，不改变旧快照。
- 首次取材仅自动绑定从未编辑的系统空稿；已有工作稿必须显式 CAS 保存来源选择。
- 手工确认先建立作者来源 Artifact，再按审核、草稿和分集三个 revision 批准；批准推进正式版本和草稿基础版本，不覆盖小说正文。
- AI 候选与确认使用不同 applyTarget；候选应用只更新工作稿，不把同一已 applied Artifact 当作正式确认重复应用。
- 跨集承接冻结正式版本和状态 key；前集新版本只新增待复核事实，后集旧版本保持不变。
- 第一批只退出旧章节根新建、拆镜起跑及提示词起跑，返回 `VIDEO_CHAPTER_CREATION_RETIRED`；旧 GET 与已存在任务的回调/收敛保持可读。旧渲染与后期写入口按后续批次接通新归属后退出。

## 验证记录

- 隔离 PostgreSQL 首次手动执行具名迁移成功，真实导出契约与 jOOQ 生成成功。
- Python ORM metadata：42 项通过；对应 Ruff 通过。
- 2026-09-10 11:05 定向 Java：迁移 1 项、剧集仓储 PostgreSQL 11 项、剧本状态流转 5 项，共 17 项通过，无跳过。日志 `/tmp/inkforge-episode-pg.log`。
- 后续组合轮新增控制器 3 项通过；共享工作流测试受两条并行 Maven 重写同一 target 目录影响，出现 `NoClassDefFoundError`。已停止并行构建，这轮失败不能作为业务通过或业务失败结论；根任务进行独占复核。日志 `/tmp/inkforge-episode-combined.log`。
- 完整审核报告保存、三个旧入口退役和历史 HTTP fixture 已追加，需随下一次独占 Maven 复验。
- 整体 Maven verify、V2 组合验收和前端浏览器由主任务整合；未完成前不宣称 P1 交付。
