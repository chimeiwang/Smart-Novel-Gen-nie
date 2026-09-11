# 剧集制作 P4 旧链退场审计

日期：2026-09-10

状态：旧章节改编、旧逐镜生成／选片和旧后期的公共读写、内部回调及后台任务装配已退出运行时；Project、Asset、VisualCanon、provider-asset 与新 Episode 媒体链继续开放。用户确认当前没有视频历史数据。物理退役只允许在专用隔离库演练，本审计不授权连接或修改服务器数据库。

依据：[实施规格](../specs/2026-09-10-video-episode-production-implementation.md)、[分批计划](../plans/2026-09-10-video-episode-production-rebuild.md)、[数据变更授权清单](../DATA_CHANGE_AUTHORIZATIONS.md)。

## 1. 唯一公共语义

Python FastAPI 公共契约源已删除全部 chapter-adaptation、旧 render/take 和旧 post-production 路径。对应 Java VideoController 只保留 11 个 Project、Asset、VisualCanon 和 provider-asset 映射；新生成、Take、剪辑、混音与导出统一通过 Episode + ProductionBaseline 路径访问。

旧写路径和旧 GET 不再保留 410 或历史只读公共契约，统一重导后直接返回 404。普通 CLI 注册表当前也只保留 Project／Asset／VisualCanon 和 Episode 主链命令。公共 OpenAPI、Java/TypeScript 生成产物由整合负责人统一刷新，本子任务没有运行 api:generate。

## 2. 运行时与后台退场

Java 不再装配 VideoAdaptationRepository/Service/TaskStore、LegacyVideoPlanStore/Service、旧 VideoRenderRepository/Service、旧 VideoPostProductionRepository/Service，也不再创建旧 adaptation/legacy-plan dispatcher 或旧 render/post reconciler。四个旧 Operations starter 已删除。provider-asset 已迁移到 VideoEpisodeRenderService/Repository，只查询已确认且锁定的共享 VideoAsset。

Python 历史 Core 同步卸载旧 public GET、旧 internal scene/adaptation routers，并且不再实例化或启动旧 adaptation、render、post 仓储／服务／worker。VisualCanon 和 provider-asset 各自使用仅依赖共享表的服务。旧实现源码可以暂时作为未装配死代码保留，但没有公共／内部路由、Bean 或后台循环能够调用它们。

Java 仍保留生成的旧 jOOQ 类和旧应用源码，Python 的共享 VideoRepository 仍包含已退场 Scene 方法；当前运行装配只调用其中 Project/Asset 方法。物理迁移晋升前必须同步删除这些死代码引用并刷新 schema contract/jOOQ，不能拿隔离演练替代运行时结构切换。

## 3. 物理表分组

退役脚本只 DROP 25 张真正 legacy-only 的表：章节改编根及 head、旧 Scene/Beat/Shot、旧 ShotPlan/EpisodePlan、旧任务、旧决策命令、旧视觉引用集合和旧阶段 head。

以下 12 张表已经由新 Episode 链写入，原表保留且绝不进入 DROP 清单：

- VideoShotPromptVersion、VideoShotKeyframeVersion；
- VideoShotRenderTask、VideoShotTake、VideoTakeFrameExtraction；
- VideoEpisodeEditVersion、VideoEpisodeEditClip；
- VideoEpisodeMixVersion、VideoEpisodeAudioClip、VideoEpisodeSubtitleCue；
- VideoEpisodeExportTask、VideoEpisodeExport。

脚本用 adaptationId、shotId、shotPlanVersionId 或旧 episodePlanVersionId/episodeNo 逐表识别这 12 张表的旧分支。旧分支为零后，只具名删除服务旧父表、自引用和旧复合身份的约束／索引，并把 scope CHECK 收紧为 Episode/Baseline 新分支。旧可空列保留为墓碑，当前新仓储显式写入的 NULL 仍兼容。

## 4. 数据与证据门禁

任一 DDL 前必须同时证明：25 张 legacy-only 表全部为零；12 张共享媒体表的旧分支全部为零；ReviewArtifact 三个旧归属与两个旧 kind 为零；旧 WorkflowRun、video_task_context Evidence、关联 TokenUsage 为零。ReviewArtifact Revision/Evaluation、Workflow Run/Step/Evidence/Event/Evaluation/BillingReservation、TokenUsage、VideoAsset 及受控文件均保留。

脚本不搬迁、清空或猜测数据，不含 DELETE、TRUNCATE、DROP CASCADE。所有旧专属表使用具名顺序和 DROP TABLE ... RESTRICT；漏盘依赖或部分结构使整个事务失败回滚。

## 5. 隔离执行边界

脚本只允许 inkforge_video_legacy_retirement_test 和 inkforge_video_legacy_retirement_codegen，并要求显式确认令牌 P4_WRITES_REMOVED_HISTORY_EMPTY_READ_RUNTIME_REMOVED_FILES_PRESERVED_SHARED_MEDIA_PRESERVED。令牌表达 SQL 无法观察的应用切换、文件清单和生成投影事实；普通启动或部署不得自动设置。

本轮隔离验收必须覆盖空结构正向执行、幂等重放、legacy-only 行拒绝、共享表旧分支行拒绝，以及失败后事务没有留下半退役结构。服务器数据库不在允许清单，演练不会同步或执行到服务器。

## 6. 定向验证

- Python OpenAPI 当前为 56 条视频路径、67 个 operation；不存在 chapter-adaptation、旧 render/take/post 或旧 internal 视频路径。
- 架构测试锁定公共／内部旧 handler、旧 Bean、旧 worker 和四个 starter 均不存在；共享接口和新 Episode worker 仍存在。
- 静态迁移测试锁定 25 张 legacy-only DROP 集合、12 张共享媒体保留集合、旧分支与共享证据门禁、RESTRICT 及无清空／级联。
- 已运行 Python 路由、健康和 P4 架构定向测试；Java 编译和生成契约由整合负责人串行执行。

## 7. 2026-09-10 隔离 PostgreSQL 演练结果

使用临时 pgvector/pgvector:0.8.0-pg14 容器，先导入当前 novelwriterdev schema，再执行 20260831 Durable Agent 迁移补齐共享证据表，并从该模板创建两个脚本允许的具名数据库。最终结果如下：

- inkforge_video_legacy_retirement_test 正向执行成功：legacy-only 表剩余 0，12 张共享媒体表全部存在，12 个新 scope CHECK 全部存在。
- 在同一已退役库重放成功；所有具名 IF EXISTS 操作只产生预期 NOTICE，没有重复对象或部分状态。
- 在 codegen 库给 VideoChapterAdaptationHead 布置 1 条旧专属行后，脚本在首个 DDL 前以“发现需要保全的旧视频数据”拒绝；表、行和 ReviewArtifact 三个旧列保持不变。
- 重置 codegen 库并给 VideoShotPromptVersion 布置 1 条旧作用域行后，脚本以 VideoShotPromptVersion[legacy]=1 拒绝；25 张旧专属表、旧作用域行和 ReviewArtifact 旧列保持不变。
- 再次重置后增加一条未盘点的外键依赖，脚本在末段 DROP VideoChapterAdaptation 时被 RESTRICT 拒绝。回读证明此前已执行的 DDL 全部回滚：25 张旧专属表仍在、ReviewArtifact 三个旧列仍在、VideoShotPromptVersion_shot_plan_fkey 仍在。

首次演练还发现并修正了 PL/pgSQL 局部变量 table_name 与 information_schema.columns.table_name 的歧义，以及 ExportTask 旧唯一约束早于其依赖外键拆除的顺序问题。两次失败均发生在事务内并完整回滚，修正后才取得上述正向和幂等证据。
