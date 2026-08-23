# 正式库视频章节改编域结构晋升

状态：已完成；兼容版本已先行发布，正式库结构已晋升并通过验收
日期：2026-08-23

## 1. 背景与现状

章节影视化、视觉设定版本和逐镜提示词链路已在服务器端 `novelwriterdev` 开发库完成真实验收，
迁移前正式库 `novelwriter` 仍保持旧结构。应用以关闭视频预览开关的 schema profile 运行，因此正式
服务不依赖这些表；2026-08-23 已按本规格把验证结构受控晋升到正式库，视频功能仍保持关闭。

2026-08-23 对两库进行只读导出和规范化比对，结果如下：

| 项目 | 开发库 `novelwriterdev` | 正式库 `novelwriter` |
| --- | --- | --- |
| 表数量 | 69 | 44 |
| 枚举类型数量 | 22 | 22 |
| 规范化结构指纹 | `36904c220803175dbb65dc38329f29b8d41f1386cac46f4992d8f77ad6653f40` | `ecd541a96eba65d43fba66f59834f53987818b03ea10298f981a3ab965002fbe` |
| `TokenUsage` 任务/运行归集结构 | 已有 | 已有 |

正式库相对开发库缺少 25 张视频域表：

```text
VideoAdaptationDecisionCommand
VideoAdaptationTask
VideoAsset
VideoAssetBinding
VideoChapterAdaptation
VideoChapterAdaptationHead
VideoCinematicScene
VideoDramaticBeat
VideoDramaticBeatSourceAnchor
VideoEpisodeBoundary
VideoEpisodePlanVersion
VideoGenerationTask
VideoProject
VideoReviewDecisionCommand
VideoScene
VideoShot
VideoShotPlanVersion
VideoShotPromptHead
VideoShotPromptVersion
VideoShotPromptVisualReference
VideoShotSourceAnchor
VideoShotVisualReferenceBinding
VideoShotVisualReferenceSet
VideoVisualCanon
VideoVisualCanonVersion
```

共同表中只有以下结构差异：

- `Novel` 增加 `(id, userId)` 唯一约束；
- `Chapter` 增加 `(id, novelId)` 唯一约束；
- `ReviewArtifact` 增加 `videoSceneId`、`videoAdaptationId`、`videoAdaptationTaskId`，以及相应外键、
  唯一约束、检查约束和查询索引；
- `ReviewArtifactKind` 增加 `video_scene_plan`、`video_adaptation_plan`。

正式库不存在开发库没有的表；本次不需要处理反向漂移。上述比对只比较结构，不读取或复制正文、
提示词、账号等业务内容。

## 2. 目标

1. 用一个正式库专用、具名、可重复执行的 SQL，把上述结构差异补齐。
2. 保留正式库全部现有业务数据，不从开发库迁移测试数据。
3. 在生产结构克隆库完成首次执行、重复执行、反向脚本和最终结构比对。
4. 执行前生成可恢复的正式库完整备份及 SHA-256 校验文件。
5. 正式执行后重新只读导出，要求规范化结构与当前开发 contract 精确一致。
6. 迁移保持与功能启用解耦；先发布结构兼容镜像，本次不打开视频预览开关。

## 3. 非目标

- 不迁移 `novelwriterdev` 中的项目、镜头、视觉设定、图片或提示词数据；
- 不启用 `VIDEO_PREVIEW_ENABLED`；
- 不调用即梦 API，不创建正式视频任务；
- 不实现 `production_v2` 目标架构中尚未落地的表或兼容迁移；
- 不重复执行已经存在于正式库的 `20260821_token_usage_task_run.sql`；
- 不让 Core API、部署脚本或应用启动过程自动执行 DDL。

## 4. 迁移设计

新增正式库专用脚本：

```text
scripts/migrations/20260823_production_video_adaptation_domain.sql
scripts/migrations/20260823_production_video_adaptation_domain.rollback.sql
```

前向脚本只允许在数据库名精确为 `novelwriter` 时运行，并要求运维显式传入版本绑定的确认值。脚本
按已经在开发库验证过的四个阶段执行：

1. 旧视频控制面；
2. 视频 Review 决定命令；
3. 视频域归属链；
4. 章节改编、分集、提示词、视觉设定版本和逐镜参考绑定。

每个阶段都使用事务、事务级 advisory lock 和幂等 DDL。分阶段事务是必要的：PostgreSQL 14 对同一
事务中新加入的枚举值有使用限制。某一阶段失败时该阶段整体回滚，已经完成的前序阶段可由同一脚本
安全重放，不以人工补 SQL 继续。

前向脚本开始前检查基线表、枚举和 `TokenUsage` 已批准结构；结束时检查 25 张表、三个
`ReviewArtifact` 字段和两个枚举值均存在。

## 5. 数据与兼容性

本次全部是 additive DDL：创建表、列、索引、唯一约束、检查约束和外键。正式库迁移前没有视频域表，
因此没有发生视频行回填。共同表上的新列均可空；现有 `ReviewArtifact` 行继续合法。`Novel` 与
`Chapter` 的复合唯一约束由现有主键蕴含，不改变数据语义，只为跨域复合外键提供数据库级归属链。

迁移后视频功能仍由现有开关关闭。只有包含“无视频预览” schema profile 的 Core 版本会忽略具名
视频域；2026-08-23 实际核验发现现网镜像 `c6d6960edcaf4e86df3385d9792ac6cd6925d7c0` 仍持有 44 表
contract，且没有 profile 能力。因此兼容 Core 镜像必须先于正式 DDL 发布并在迁移前基线结构上保持
ready；不能再次让旧镜像直接面对迁移后结构。正式执行后还必须用当前仓库的 full schema guard 对
迁移后结构做只读校验。

首次回滚后的真实基线比对还发现，本地 profile 漏掉了后续增加的 5 张视觉稳定性表：
`VideoVisualCanon`、`VideoVisualCanonVersion`、`VideoShotVisualReferenceSet`、
`VideoShotVisualReferenceBinding` 和 `VideoShotPromptVisualReference`。本规格内补齐该名单，并新增
“当前 69 表 contract 投影后必须恰为 44 表且不得残留任何 `Video*` 表”的回归测试。修正后的 profile
与正式库迁移前实际结构为 0 项差异；只有包含该修正的镜像才是允许先行发布的兼容版本。

## 6. 备份、演练与执行

1. 只读记录正式库迁移前指纹、数据库大小、目标对象缺失情况和活动长事务；
2. 使用生产服务器 PostgreSQL 工具生成完整 custom-format 备份及 SHA-256；
3. 从正式库结构导出创建一次性隔离数据库，不复制业务数据；
4. 在隔离库把数据库名守卫替换为该一次性精确库名，执行前向脚本两次；
5. 导出隔离库结构，与开发库规范化结构逐项比较；
6. 在空视频域的隔离库执行反向脚本，确认只删除本次视频对象；反向脚本通过替换仅由
   `ReviewArtifact.kind` 使用的枚举类型精确移除两个新增值，随后再次执行前向脚本证明可恢复；
7. 先发布同时兼容迁移前基线与迁移后视频域的 Core 镜像，确认功能开关关闭且 readiness 正常；
8. 在维护窗口内对正式库执行前向脚本；
9. 重新导出正式库结构并运行 schema guard；所有结果写入具名审计文档。

一次性隔离数据库和临时 SQL 在验收结束后按精确名称删除。备份不随临时环境清理。

## 7. 回滚策略

在功能尚未启用、25 张视频表全部为空时，允许使用具名反向脚本移除本次增加的表、字段和约束。
反向脚本必须先验证所有视频表为空；任何一张表存在行时立即拒绝执行，禁止自动丢弃正式数据。

PostgreSQL 14 没有安全的原地删除枚举值操作，因此反向脚本只在视频域和视频审核关联全部为空、
`ReviewArtifactKind` 仍仅由 `ReviewArtifact.kind` 使用时，创建迁移前值集合的新枚举、事务内转换该列、
删除旧类型并把新类型重命名回原名。依赖范围或值集合不符合已核验基线时必须拒绝执行。若迁移后已经
开放视频写入，回滚方案改为关闭功能开关、保留 additive schema 并恢复兼容镜像，不能执行
destructive rollback。

## 8. 验收标准

1. 正式库迁移前有可恢复备份和校验和，文件路径与校验结果进入审计记录，但不记录密钥。
2. 隔离库首次迁移、重复迁移和空域回滚均成功；回滚后可再次前向迁移。
3. 隔离库与正式库迁移后的规范化结构指纹均为
   `36904c220803175dbb65dc38329f29b8d41f1386cac46f4992d8f77ad6653f40`。
4. 正式库原有表行数抽样和 `ReviewArtifact` 总行数迁移前后不变；开发数据未进入正式库。
5. 25 张视频表存在且为空，三个新 `ReviewArtifact` 字段对历史行均为 `NULL`。
6. 当前仓库 schema guard、迁移架构测试、相关 Pytest、Ruff、Mypy 和 `git diff --check` 通过。
7. 兼容镜像先于 DDL 发布；正式环境视频开关保持关闭，DDL 执行后不重启应用。

## 9. 2026-08-23 正式执行结论

- 前向脚本在完整备份和隔离演练后成功执行，迁移后正式库为 69 表，full contract 指纹为
  `36904c220803175dbb65dc38329f29b8d41f1386cac46f4992d8f77ad6653f40`；
- 原有小说、章节和审核记录计数未变，25 张视频表均为空，历史审核记录三个视频关联字段均为
  `NULL`；
- 数据库结构本身通过当前代码的 full schema guard，但现网旧 Core 镜像没有 schema profile，因多出
  视频表而把 `check_database_schema` 判为失败；
- 在未启用功能、视频域和视频审核关联全空的前提下，先在结构克隆库证明精确反向指纹，再对正式库
  执行反向脚本；正式库恢复为 44 表和迁移前指纹
  `ecd541a96eba65d43fba66f59834f53987818b03ea10298f981a3ab965002fbe`，readiness 全项恢复；
- 修正 profile 后，提交 `ecfc1e968539c64bfc685d2528c8083d210f3022` 已通过 CI 并完成生产发布；
  镜像内 69 表 contract 在功能关闭时精确投影为正式库迁移前的 44 表结构，readiness 全项正常；
- 新的迁移前完整备份完成校验和完整恢复演练后，同一前向脚本再次执行成功；正式库最终为 69 表，
  25 张视频表均为空，full contract 指纹为
  `36904c220803175dbb65dc38329f29b8d41f1386cac46f4992d8f77ad6653f40`；
- 小说 192、章节 221、审核记录 215 与迁移前一致，历史审核视频关联为 0；无效索引、未验证视频约束
  和长事务均为 0；运行中容器健康且 readiness 全项为 `ok`；
- `VIDEO_PREVIEW_ENABLED` 保持关闭，开发库数据没有进入正式库。完整证据见
  `docs/audits/2026-08-23-production-video-schema-promotion.md`。
