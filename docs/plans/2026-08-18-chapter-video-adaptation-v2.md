# 长篇章节影视化工作台 v2 实施计划

**目标：** 在 InkForge 当前长篇章节、选区、设定、ReviewArtifact、耐久任务和生成客户端能力上，建立一个真正可用的
“小说章节 → 场景 → 戏剧节拍 → 电影化镜头 → 分集 → 即梦提示词”工作台；本期不调用视频生成 API。

**架构：** 新增独立章节改编域，不再把整章、场景、镜头和提示词塞入 `VideoScene.planJson`。AI 候选进入
ReviewArtifact，用户批准后物化为不可变关系化 ShotPlanVersion；分集和逐镜提示词各自版本化。Agent 使用可恢复的
场景/节拍分析、镜头设计、电影语法复审和最多一次完整返工。旧视频预览域保留只读兼容。

**规划评审门：** 任务 1 之后必须先取得用户确认，才能开始任务 2 及任何实现、DDL 执行或真实数据写入。

---

## 任务 1：冻结架构与清理方向

**文件：**

- 更新：`docs/specs/2026-08-18-chapter-shot-adaptation-workbench.md`
- 新增：`docs/plans/2026-08-18-chapter-video-adaptation-v2.md`

- [x] 记录当前 `VideoScene`、`planJson`、Scene-bound task、单次拆镜和前端单体化问题。
- [x] 定义章节改编根、ShotPlanVersion、Scene、Beat、Shot、来源锚点、EpisodePlan、PromptVersion 和 AdaptationTask。
- [x] 定义 Web/Core/Agent 模块边界、公共接口和 dev-only 迁移边界。
- [x] 定义电影感质量门禁和真实章节新旧对照验收。
- [x] 用户确认先完成规划再按该架构实施；开发库迁移范围限定为 `novelwriterdev`。

## 任务 2：撤销探索性补丁并锁定失败测试

**原则：** 只清理由本轮探索产生、且已被新架构取代的代码；保留此前已经验证的通用视频项目、鉴权、队列、
ReviewArtifact 和长篇选择能力。

**文件：**

- 删除：旧 `apps/agent-service/src/inkforge_agents/jobs/video_chapter.py`
- 删除：旧 `apps/web/src/features/video/chapter-shot-workspace.tsx`
- 删除：旧 `apps/web/src/features/video/chapter-shot-workspace-state.ts`
- 删除：对应旧测试
- 修改：`video.py`、Core video router/service/repository、共享契约中旧 chapter-shot 分支

- [x] 用 `git diff` 逐块确认探索性代码归属，不覆盖用户无关改动。
- [x] 写架构测试：新页面和新 API 不得引用 `VideoScene.planJson`、旧 chapter-shot endpoint 或旧任务 workflow。
- [x] 写 schema/ORM 失败测试，固定计划中新表、外键、唯一约束和 ReviewArtifact 新目标列。
- [x] 删除被替代代码，保证旧通用视频预览仍能导入和通过既有测试。

## 任务 3：共享契约与嵌套读模型

**文件：**

- 新增：`packages/service-contracts/src/inkforge_contracts/video_adaptation.py`
- 修改：`packages/service-contracts/src/inkforge_contracts/__init__.py`
- 修改：`packages/service-contracts/src/inkforge_contracts/jobs.py`
- 新增/修改：`packages/service-contracts/tests/*video_adaptation*`

- [x] 定义 `ChapterAdaptationCandidateV2` 的 Scene → Beat → Shot 嵌套结构。
- [x] 定义来源锚点、镜头目的、景别、机位、运镜、声音、切镜理由和 500ms 时长契约。
- [x] 定义任务 payload、dramatic checkpoint、review、completion/failure callback。
- [x] 定义正式工作台读模型、EpisodePlan 和 PromptVersion DTO。
- [x] 用契约测试覆盖多句对白同镜、一句多镜、首个补充建立镜头、非法父子归属和机械切镜理由。

## 任务 4：开发库迁移设计、ORM 与 schema contract

**文件：**

- 修改：`AGENTS.md`
- 修改：`DOCS.md`
- 新增：`scripts/migrations/20260818_video_chapter_adaptation_domain.sql`
- 修改：`apps/core-api/src/inkforge_core/db/models.py`
- 修改：`apps/core-api/src/inkforge_core/db/schema_guard.py`
- 修改：`apps/core-api/src/inkforge_core/db/schema-contract.json`（只能从迁移后的 dev 库只读导出）
- 修改：`apps/core-api/tests/db/test_model_metadata.py`
- 修改：`apps/core-api/tests/db/test_schema_guard.py`

- [x] 根级文档增加这一条具名 `novelwriterdev` 例外，明确不授权生产迁移。
- [x] SQL 自带数据库名断言、事务、advisory lock、幂等建表和完整注释。
- [x] 新增 Adaptation、Head、Task、PlanVersion、Scene、Beat、Shot、Anchor、EpisodePlan、PromptVersion、DecisionCommand。
- [x] ReviewArtifact 增加新 kind、adaptation/task 目标外键和互斥约束。
- [x] ORM 与迁移 SQL 逐字段对齐；`without_video_preview` 投影排除全部新表和新列。
- [x] 在迁移执行前只运行元数据与静态 SQL 测试，不连接生产。

## 任务 5：Core 章节改编域

**文件：**

- 新增：`apps/core-api/src/inkforge_core/video/adaptation/schemas.py`
- 新增：`apps/core-api/src/inkforge_core/video/adaptation/repository.py`
- 新增：`apps/core-api/src/inkforge_core/video/adaptation/service.py`
- 新增：`apps/core-api/src/inkforge_core/video/adaptation/router.py`
- 新增：`apps/core-api/src/inkforge_core/video/adaptation/internal_router.py`
- 新增：`apps/core-api/src/inkforge_core/video/adaptation/read_model.py`
- 新增：`apps/core-api/src/inkforge_core/video/adaptation/validation.py`
- 修改：Core app 和视频 dispatcher wiring
- 新增：`apps/core-api/tests/video/adaptation/`

- [x] 创建/读取不可变章节改编根，严格校验 long_serial、章节归属和 updatedAt。
- [x] 单独受理 ShotPlan 任务并耐久投递；同一来源和 clientRequestId 幂等。
- [x] 保存/读取 dramatic checkpoint，拒绝旧 job 和错绑回调。
- [x] 完整候选回调原子创建 `video_adaptation_plan` ReviewArtifact，不写正式关系表。
- [x] 批准事务关系化物化 Scene/Beat/Shot/Anchor、创建 PromptHead 并切换 AdaptationHead。
- [x] EpisodePlan 新版本和 PromptVersion 保存使用独立 CAS 与内容哈希。
- [x] 所有读模型都从关系行重建，测试中禁止依赖正式 planJson。

## 任务 6：Agent 电影化工作流

**文件：**

- 新增：`apps/agent-service/src/inkforge_agents/jobs/video_adaptation.py`
- 新增：`apps/agent-service/src/inkforge_agents/jobs/video_adaptation_quality.py`
- 新增：`apps/agent-service/src/inkforge_agents/jobs/video_dispatch.py`
- 修改：视频任务分发和 Core 签名客户端
- 新增：`apps/agent-service/tests/video_adaptation/`

- [x] Scene/Beat Analyst 只输出戏剧结构，不输出镜头。
- [x] 成功后先把 checkpoint 回调 Core；重试读取 checkpoint 后直接继续。
- [x] Shot Designer 围绕冻结 Beat 设计有动机镜头，不按句子或说话人拆分。
- [x] 纯代码门禁验证父子关系、来源归属、连续性、时长和切镜理由。
- [x] Cinematic Reviewer 返回 pass/revise；revise 时完整重写一次，不做局部 patch。
- [x] 失败只回传稳定错误，不记录正文、模型草案或提示词。
- [x] Prompt workflow 生成结构化 ShotPromptSpec，由确定性编译器生成即梦文本。

## 任务 7：前端三栏工作台

**文件：**

- 新增：`apps/web/src/features/video/adaptation/chapter-adaptation-workspace.tsx`
- 新增：`source-panel.tsx`
- 新增：`shot-timeline.tsx`
- 新增：`shot-inspector.tsx`
- 新增：`episode-editor.tsx`
- 新增：`prompt-editor.tsx`
- 新增：`adaptation-state.ts`
- 新增：对应 Node 测试
- 修改：`apps/web/src/app/globals.css`
- 修改：长篇 workspace video 入口

- [x] 复用当前章节、ChapterList 和选区身份桥。
- [x] 拆镜页显示 Source → Scene → Beat → Shot，不在镜头卡中展开大表单。
- [x] 删除/恢复/合并/新增/重绑保持 Beat 和 Scene 关系合法。
- [x] “拆分”改为选择来源和镜头目的，不再对半切文字。
- [x] 分集页展示每集时长、平均镜头时长和分布预警。
- [x] 提示词页展示前后镜、结构字段、AI 候选和正式保存版本。
- [x] PC 宽度下无溢出、遮挡或嵌套卡片堆叠。

## 任务 8：接口生成、全量验证与开发库迁移

- [x] `npm run api:generate && npm run api:check`。
- [x] Web 相关测试、typecheck、lint、build。
- [x] service-contracts/Core/Agent 全量 pytest、Ruff、Mypy。
- [x] schema guard、ORM metadata、architecture 和 migration SQL 测试。
- [x] 核对目标连接数据库名但不输出连接串或凭据。
- [x] 只在 `novelwriterdev` 执行具名迁移；数据库名断言不是 `novelwriterdev` 时必须整体失败。
- [x] 从迁移后的开发库只读导出 schema contract，并以 live guard 确认零差异。

## 任务 9：真实章节产品验收

- [x] 使用账号 `nie` 的真实长篇章节创建新 ChapterAdaptation。
- [x] 走完 Scene/Beat 分析、镜头设计、Reviewer 和 ReviewArtifact 候选。
- [x] 浏览器完成场景合并、方案确认、分集、提示词生成/手改/正式保存；删除、恢复、新增和选区重绑由前端纯状态测试覆盖。
- [x] 对照旧失败基线 `1160 字 → 49 镜 → 253 秒`，记录新方案的 Scene、Beat、Shot、时长分布。
- [x] 通过真实候选与契约测试抽查多句对白同镜、一句多镜和无原句补充镜头；确认没有按说话人机械拆镜。
- [x] 服务热重启、浏览器刷新、终态回调和任务幂等重放后结果一致。

## 最终验收记录

- 真实章节：`第一章 雾钟之前`，1160 字。
- AI 原始候选：6 场、12 节拍、27 镜、72.5 秒；用户合并连续空间后正式版本为 5 场、12 节拍、27 镜。
- 平均镜头时长 2.7 秒，原文覆盖率 97%；相较旧基线减少 22 镜和 180.5 秒，不再按对白或句末机械拆分。
- 正式 EpisodePlan v1 为一集；S01 即梦 2.5 提示词已由 AI 生成、人工补充屏幕方向连续性并保存为 PromptVersion v1。
- 开发库 live schema guard：`ready=true`、`diffs=0`；Scene/Beat、Head/EpisodePlan、Prompt/Task 三类关系错绑查询均为 0。
- 验证结果：Python 全量 `3037 passed, 2 skipped`；Web/API Client `279 passed`；API 生成校验、TypeScript、ESLint、Next.js build、Ruff、Mypy 全部通过。

## 完成定义

只有以下证据全部成立，才能认为目标完成：

1. 新页面真实使用 chapter-adaptations API，且新流程不写旧 `VideoScene.planJson`。
2. 开发库存在受完整外键保护的正式 Scene/Beat/Shot/Anchor 关系和不可变版本。
3. 同一真实章节在浏览器完整跑通并产生可编辑、可保存的即梦提示词。
4. 电影化质量抽查和短视频节奏指标通过，不以测试通过代替产品质量。
5. 所有约定测试、类型检查、静态检查、构建、schema guard 和 API 客户端校验通过。
6. 没有连接或修改生产数据库，没有残留新功能使用的伪 Scene、扁平 planJson 或机械按句拆分代码。
