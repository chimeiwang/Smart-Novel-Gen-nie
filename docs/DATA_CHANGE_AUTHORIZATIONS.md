# 数据变更授权清单

整理日期：2026-09-10

用途：承接根 `AGENTS.md`、`DOCS.md` 中具名数据变更的授权索引，供数据库、迁移、旧执行清理和生产开关任务按需读取。
本清单记录已有授权的范围，不是新的授权、实施指令或当前环境验收报告；不能由“列在清单中”推断尚需执行。
目标环境、脚本与业务范围必须同时匹配，具体门禁以链接的具名规格和运维手册为准。

## 使用规则

- PostgreSQL schema 默认冻结，应用启动不得自动 DDL；未获批准只能只读核对结构。
- 已有授权在原范围内沿用，不因迁出根文件而失效或要求重新批准。新增或改变范围时，先在对应 spec
  记录用户明确授权、目标环境、允许及排除项，再更新本索引；不再把逐次授权追加到根 `AGENTS.md`。
- 受控迁移须有具名脚本、可恢复备份、隔离 PostgreSQL 验证和目标库 contract 导出复验；不得用开发迁移
  覆盖生产授权，也不得修改脚本的数据库名保护来跨环境执行。
- 当前正式库已有 V2 Run，永久禁止 DDL rollback；历史规格中的 rollback 示例不赋予当前正式库回退结构的权限。
  应用回滚必须保留 V2 查询及收敛能力，不得使用 V1-only Python Core 或不兼容的旧 Agent 镜像。
- 生产视频保持关闭；表存在、开发验收或结构晋升均不授权生产视频开放、调度或真实 Seedance。
- 执行次数、数据库指纹、部署版本与 canary 结果留在原规格、运维手册及审计中；执行前核对实际环境，不能把历史记录当作当前检查结果。

## 具名结构变更

以下是本次从根文件承接的范围索引，不将仓库中其他历史迁移自动加入授权。

### 视频控制面与章节改编域

- 开发目标仅为服务器端 `novelwriterdev`，对应四个脚本：
  [控制面](../scripts/migrations/20260807_video_production_control_plane.sql)、
  [审核命令](../scripts/migrations/20260817_video_review_decision_command.sql)、
  [归属链](../scripts/migrations/20260817_video_domain_ownership_chain.sql)、
  [章节改编域](../scripts/migrations/20260818_video_chapter_adaptation_domain.sql)。
  范围含该域内视觉设定版本与逐镜参考绑定，不含生产迁移或完整 `production_v2` schema。
- 2026-08-23 单独批准[生产晋升脚本](../scripts/migrations/20260823_production_video_adaptation_domain.sql)
  向服务器端 `novelwriter` 晋升上述已验证结构；不迁开发数据、不启用视频，也不授权其他生产 DDL。
- 原始规格与证据：[控制面设计](specs/2026-08-07-novel-multimodal-video-production-system.md)、
  [预览加固](specs/2026-08-17-video-preview-hardening.md)、[章节改编](specs/2026-08-18-chapter-shot-adaptation-workbench.md)、
  [生产晋升规格](specs/2026-08-23-production-video-adaptation-schema-promotion.md)、[晋升审计](audits/2026-08-23-production-video-schema-promotion.md)。

### TokenUsage 任务归集与诊断明细

- 2026-08-21 批准[任务归集迁移](../scripts/migrations/20260821_token_usage_task_run.sql)，仅涉及
  `TokenUsage` 归集字段及具名约束、索引；范围与执行门禁见[任务归集规格](specs/2026-08-21-task-model-usage-attribution.md)。
- 2026-08-23 批准[诊断明细迁移](../scripts/migrations/20260823_token_usage_details.sql)及固定生产
  forward/rollback。仅增加可空 `INTEGER` `promptCacheMissTokens`、`reasoningTokens` 和三个 CHECK；
  无默认值、无回填、无索引，旧行保持 `NULL`。
- 明细脚本只用于服务器端 `novelwriterdev`；`novelwriter` 使用独立固定生产脚本及已审核部署门禁，
  不接受任意 SQL。详见[生产迁移规格](specs/2026-08-23-token-usage-production-migration-release.md)；
  历史 rollback 流程仍受本文已有 V2 正式库禁令约束。

### 视频逐镜生成与后期

- 2026-08-24 批准[逐镜 P0](../scripts/migrations/20260824_video_shot_render_p0.sql)和
  [后期 P1-P3](../scripts/migrations/20260824_video_post_production_p1_p3.sql)，仅对服务器端 `novelwriterdev` 执行。
- 范围分别为逐镜耐久任务、不可变 Take、head 与确认命令，以及受控 Take 抽帧来源、关键帧版本、
  非破坏性粗剪、声音／字幕版本和耐久整集导出；允许该开发库 `VideoAsset.duty` 增加 `sfx`、`episode_export`。
- 两个脚本不得对 `novelwriter` 执行，不迁开发数据、不启用生产视频，不授权图片生成、TTS 或旧
  `VideoScene`／`VideoGenerationTask` 公共语义复活。
- 详细范围：[逐镜 P0 规格](specs/2026-08-24-video-shot-render-p0.md)、[后期 P1-P3 规格](specs/2026-08-24-video-post-production-p1-p3.md)。

### 手机号身份

- 2026-08-27 分阶段批准[手机号迁移](../scripts/migrations/20260827_user_phone_identity.sql)：
  先隔离验证，再服务器端 `novelwriterdev`，同日另行批准备份后对 `novelwriter` 执行并开启手机号登录和真实短信发送。
- 保留数据库名校验，正式执行须精确确认令牌；同一事务内将 `UserPhoneIdentity` 所有者对齐现有 `User`
  表所有者。保留老账号密码登录；不包含其他生产 DDL、手机号数据删除、老账号绑定或账号合并。
- 完整授权、开发／正式执行记录、历史指纹与浏览器验收边界见[手机号认证规格](specs/2026-08-27-aliyun-phone-auth.md)。

### Core 权威耐久 Agent 执行

- 2026-08-31 批准[耐久执行迁移](../scripts/migrations/20260831_durable_agent_execution.sql)，完成隔离
  PostgreSQL、开发库、备份、契约、回滚预案和全量测试门禁后依次用于 `novelwriterdev` 与 `novelwriter`。
- 仅允许演进 `WorkflowRun/WorkflowStep`、支持 V2 非章节 Run、增加 Workflow Evidence/Event/Evaluation
  与逐 Step BillingReservation 表及规格列、约束和索引。BillingReservation 仅用于模型调用前积分预留、
  幂等结算和未知用量对账，不得成为第二份作品或工作流状态。
- 不授权修改正式作品、回填历史 Graph、删除旧任务表、启用生产视频或跳过生产 canary；已有 V2 正式库
  永久禁止 DDL rollback。
- 详细范围：[耐久执行规格](specs/2026-08-31-core-owned-durable-agent-execution.md)、
  [V2 运维手册](DURABLE_AGENT_V2_ROLLOUT.md)、[发布审计](audits/2026-09-06-durable-agent-release-preflight.md)。

## 有界数据操作与后续设计

- **2026-09-13 LangGraph 兼容回退**：用户要求生产恢复 8 月 29 日写作流程，并明确正文和大纲不受影响、
  对话历史允许删除。按[兼容回退规格](specs/2026-09-13-langgraph-aug29-compatible-rollback.md)保留现有
  PostgreSQL 和 V2-aware 后台，关闭 V2 fresh 路由并重新开放 V1 fresh；恢复旧 LangGraph 新任务。
  本次默认零数据删除，不执行 DDL rollback，不把对话授权扩大成 Task、Command、候选、账务或作品来源删除。
  原有生产视频关闭要求不变；本条授权不代表已经部署。

- **2026-09-07 旧执行退出与成果保全**：按[具名规格](specs/2026-09-07-durable-release-preserve-novel-assets.md)
  退出精确旧执行历史并完成服务器配置。聊天／旧执行恢复可不兼容，设定、大纲、正文和版本成果必须保全；
  不得物理删除会断开成果来源的 Task／Command 或候选。先备份、锁定精确清单，只退出旧执行状态，
  复验全部非执行业务表不变；不包含其他 schema 调整、成果修改或生产视频开放。
- **2026-09-09 视频 V0.1／V0.2 原范围**：用户允许修改本次定妆、单镜试制与恢复所需相关字段，
  不必为假设的旧视频数据增加兼容负担；仍须具名迁移、隔离验证与契约同步，不涉及无关小说成果、账号、
  账务历史、生产部署或视频开放。真实供应商调用已延期，原验收限定模拟与传输替身，不能声称真实画质或计费通过。
  [旧实施规格](specs/2026-09-09-video-v01-v02-implementation.md)已标记暂停；
  [视频重做设计](specs/2026-09-09-video-production-redesign.md)随后取代旧方案。保留原授权记录不构成恢复旧实施的指令。
- **2026-09-10 剧集制作重构执行**：用户认可[视频业务重做设计](specs/2026-09-09-video-production-redesign.md)，
  随后要求按[剧集制作重构修改计划](plans/2026-09-10-video-episode-production-rebuild.md)执行。授权视频专属
  业务结构、公共／内部契约、Java Core、Python Agent、Web 与普通 CLI 按
  [实施规格](specs/2026-09-10-video-episode-production-implementation.md)重构，并允许起草和验证规格中三份具名
  迁移：[Episode 剧本域](../scripts/migrations/20260910_video_episode_script_domain.sql)、
  [制作基线域](../scripts/migrations/20260910_video_production_baseline_domain.sql)和
  [旧域退役](../scripts/migrations/20260910_video_legacy_domain_retirement.sql)。迁移须先用于明确命名的隔离
  PostgreSQL，完成结构、幂等、权限、契约和完整测试门禁后才可用于服务器端
  `novelwriterdev`；禁止用于 `novelwriter` 正式库。授权不包含生产部署、生产视频开放、真实 Seedance 调用、
  共享小说成果删除或按 `workflow=video` 清空审核、V2 Evidence／Event／BillingReservation。旧视频表只有在精确
  证明没有需保全引用时才能由第三份具名退役脚本处理；禁止 `DROP ... CASCADE`。
