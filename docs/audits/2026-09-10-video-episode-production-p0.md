# 剧集制作重构 P0 现场与取舍清单

日期：2026-09-10

状态：进行中。本文记录实施开始时的直接事实与逐模块取舍；不把文件存在、旧测试结果或暂停补丁记作新流程完成。

依据：[实施规格](../specs/2026-09-10-video-episode-production-implementation.md)、[修改计划](../plans/2026-09-10-video-episode-production-rebuild.md)。本轮用户已经要求按计划执行；生产发布和真实 Seedance 调用仍排除。

## 1. 开工现场

- Git HEAD：`0a7e7017e7ef18cfc4c1baa2543a03c0440eace8`，提交说明为“构建：重试主分支生产部署”。
- 开工时工作树包含此前暂停的视频补丁、产品设计文档，以及另一项文档治理／Java 注释任务的大量未提交修改。不得整体 reset、checkout 或覆盖这些文件。
- 开工只读检查没有发现 InkForge Core、Agent、Web、Maven 或 pytest 进程，也没有运行中的 Docker 容器。本事实只说明本地现场，不代表远端服务状态。
- 冻结 `schema-contract.json` 当前记录 86 张表，包含 41 个 `Video*` 表，指纹为 `4f8cbf58820c7e601026012249f1896e4f8ad0231cfa6b9bd2fdad1c83c3d195`。当前 V2 结构还要叠加 `20260831_durable_agent_execution.sql` 和运行时 guard 核对，不能将这份文件冒充实时数据库全貌。

## 2. 其他任务修改：保留且不归本视频重构所有

以下改动在本次恢复实施前已经存在，且明显属于文档治理或 Java 注释／可读性任务：

- 根 `AGENTS.md`、`DOCS.md`、`CLAUDE.md`、`docs/DATA_CHANGE_AUTHORIZATIONS.md` 与 `docs/specs/2026-09-10-agents-document-governance.md` 的治理重构；本任务只在授权清单和视频专题文档追加必要状态，不改写其治理结构。
- Java Core 的 identity、billing、chapters、outlines、quality、reviews、shortmedium、writing、platform、service-auth、CLI 基础命令等大量注释或小型重构；本任务只在新视频调用确实需要时做窄适配，保留已有语义与注释。
- `docs/specs/2026-09-09-java-comment-guidelines.md` 及相关必要注释规则；本视频新增 Java 代码遵循它，不把该文档算作视频产物。

同一文件若同时包含旧视频补丁和其他任务修改，实施时使用小范围 patch，不能用 HEAD 整文件覆盖。

## 3. 此前暂停的视频补丁取舍

| 模块 | 当前取舍 | 纳入阶段与重新验收条件 |
| --- | --- | --- |
| Agent `seedance.py`、router、executionMode 契约与测试 | 保留待吸收 | P3；真实调用继续独立，默认模拟必须证明无外呼、可恢复且不虚构用量 |
| Java Render Reconciler、归档器、ffprobe、FFmpeg 模拟器及测试 | 保留待吸收 | P3；先改成 episode／productionBaseline／shotVersion 归属，再验归档恢复和唯一 Take |
| VisualCanon 候选 revision、Lore 删除引用保护与 PostgreSQL 竞态测试 | 原则保留 | P2／P3；改接 Episode 制作输入，重新验证跨项目归属和旧版本不漂移 |
| 设定卡视觉编辑器、项目上下文和离开保护 | 组件级复用 | P3；移入新剧集工作台并使用新 API，不能继续依赖章节适配对象 |
| `chapter-adaptation-workspace.tsx` 的轮询、模式提示与局部修复 | 拆分复用 | 轮询辅助可复用；旧八步调度、currentChapter 根和章节内分集退出新入口 |
| `take-workspace.tsx` 的未知提交状态和模拟标记 | 交互规则保留 | P3；使用 ProductionBaseline／Adoption 新语义后重写数据入口 |
| 旧 V0.1／V0.2 requirements 与客户端生成产物 | 不作为当前事实 | 新契约每批重新生成；需求只在新业务实际验收后更新为已实现 |
| `tests/video_local_e2e/` 隔离环境和固定媒体 | 检查后复用 fixture | P1～P3；重建为 Episode A／B／C 场景，旧成功结果不算新验收 |

## 4. 当前必须替换的业务入口

- Web `VideoWorkspace` 直接加载 `ChapterAdaptationWorkspace`，workspace 又把 `currentChapter` 传入视频入口。
- 公共新建入口集中在 `/projects/{project_id}/chapter-adaptations`，后续写入围绕 `/chapter-adaptations/{adaptation_id}/...`。
- `VideoChapterAdaptation` 只冻结完整单章；`VideoEpisodePlanVersion + episodeNo` 才间接表示一集。
- 正式镜头新版本会创建新的 Scene／Beat／Shot 身份；确认方案会清空当前分集 head。
- 粗剪要求本集每个正式镜头恰好出现一次；旧 Take 必须属于同一个 Shot 和方案。

这些语义在新入口开放时逐步关闭，不能通过把 episodeId 塞进 adaptationId 继续运行。旧读取或执行收敛是否保留，以共享引用和真实数据清单为准。

## 5. 共享依赖保护

- `ReviewArtifact` 当前以 CASCADE 外键关联 `VideoChapterAdaptation`、`VideoAdaptationTask` 和 `VideoScene`；ArtifactRevision／Evaluation 再依赖 Artifact。
- 旧 V2 Run、Evidence、Event 和 BillingReservation 可能引用旧视频 task 身份；不得改写 sourceId 伪装成新 Episode，也不得按 workflow 批量删除。
- 旧视频物理退役只通过第三份具名迁移，在精确检查共享引用后进行。发现任何应保全数据时，迁移终止相应物理删除并保留只读来源。
- 新 Episode 及 Artifact 使用明确归属和 RESTRICT／软归档；应用启动不执行 DDL。

## 6. P0 决策

- 新视频 AI 只使用 Core-owned V2 Run；不再创建 `VideoAdaptationTask` 作为第二执行权威。
- Run 完成、候选采用到工作稿、确认正式版本、确认制作基线是四个不同事实。
- 第一阶段结构包含 Episode、SourceSet／Snapshot、ScriptDraft／Version、Dependency、ImpactReview、领域命令回执和 ReviewArtifact Episode 归属。
- 稳定 Shot、ShotVersion、ProductionBaseline 和 Adoption 在第二阶段引入；修改镜头关系时同批修正 Prompt、Keyframe、Render、Take 和后期的底层编译依赖。
- 初始 B0 基线允许镜头待生产；候选采用后另行确认 B1，避免基线与素材互相等待。

## 7. 待补直接证据

- 第一阶段最终公共字段、错误码与 OpenAPI 生成结果。
- 第一份具名迁移在隔离 PostgreSQL 的正向、幂等、失败回滚和最小权限结果。
- 真实仓内结构叠加 V2 migration 后的新 schema 指纹与 jOOQ 生成结果。
- P1 受控 V2 剧本候选从 Run 到工作稿采用和正式确认的纵向结果。
- 浏览器 A／B 场景、自动保存与两窗口冲突结果。

上述证据到位后再将相应 P0／P1 项标为完成。
