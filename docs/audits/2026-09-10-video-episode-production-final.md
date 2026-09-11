# Episode 视频生产链最终验收记录

日期：2026-09-10

状态：P0～P4 的仓内实现与本地隔离验收完成。真实 Seedance、服务器数据库迁移和生产视频开放均未执行。

## 1. 验收结论

视频产品已经从章节附属的八步改编流程切换为独立 Episode 生产链：多章取材、单集剧本、稳定分镜、影响复核、
视觉定妆与关键帧、不可变制作基线、逐镜 Take、采用、基础粗剪、声音字幕和确切版本交付均可独立回读与返工。
旧章节视频公共／内部路由、普通 CLI、Web 工作区、Catalog 定义和后台装配已经退出活动运行路径。

当前验收只覆盖 `simulated` 模式。模拟产物明确标记为 `simulated_placeholder`，不能用于推断 Seedance 真实画质、
音色、用量或费用。生产继续保持视频关闭。

## 2. 产品场景 E2E

组合证据目录：[`output/video-local-e2e/20260910T093753Z/`](../../output/video-local-e2e/20260910T093753Z/)。
权威结构化回执为 [`evidence.json`](../../output/video-local-e2e/20260910T093753Z/evidence.json)，结果为
`status=passed`、`simulationOnly=true`、`seedanceApiKeyPresent=false`、`productionDatabaseTouched=false`。

### 场景 A：第一集从取材到交付

- 冻结 2 个章节来源，确认正式剧本和正式分镜；分镜包含 2 个稳定镜头身份。
- 创建 B0 后完成 2 个 Episode RenderTask，归档 2 个 `simulated_placeholder` Take；作者记录 2 次采用并确认 B1。
- 粗剪保存 3 个独立 clip，覆盖同素材重复使用、裁切以及 `keep`／`mute` 两种原声决定。
- 混音和字幕绑定稳定台词 ID；导出创建不可变交付 `cmtvc46qymle7mqel88ogy6tw`。
- Episode 聚合精确返回该 `latestDeliveryVersionId`，`deliveryRevision=2`；浏览器显示“当前交付 已有”。
- 浏览器证据：[`browser-a.png`](../../output/video-local-e2e/20260910T093753Z/browser-a.png)。

### 场景 B：跨集承接与独立回忆

- 第二集与第一集可以共享第 13 章来源，但各自保留独立 SourceSet 和剧本版本。
- 承接关系冻结第一集正式剧本 v1、消费场次、状态 key 与哈希；“三日前”的回忆场拥有独立叙事时间，
  不会覆盖当前时间线状态。
- 浏览器证据：[`browser-b.png`](../../output/video-local-e2e/20260910T093753Z/browser-b.png)。

### 场景 C：上游返工不清空既有成果

- 第一集确认剧本 v2 后精确产生 1 个待处理 impact；无直接依赖的回忆场没有被错误列入。
- 旧 B0／B1、粗剪、混音和交付继续可读，没有随剧本 head 更新而被删除或重写。
- 浏览器证据：[`browser-c.png`](../../output/video-local-e2e/20260910T093753Z/browser-c.png)。

隔离数据库最终事实为：2 个 Episode、3 个正式剧本版本、1 个正式分镜版本、2 个制作基线、2 个渲染任务、
2 个 Take、2 个 Adoption、1 个粗剪版本、1 个混音版本、1 个交付、1 个待处理影响项、0 个 legacy adaptation。

## 3. 媒体证据

模拟成片：[`scenario-a-delivery.mp4`](../../output/video-local-e2e/20260910T093753Z/scenario-a-delivery.mp4)。

| 项目 | 实测值 |
| --- | --- |
| SHA-256 | `37aff09c460682e06761bdbe677b13cf57b4fcdf5451c7610830bbb1ae0a8b1c` |
| 视频 | H.264，720×1280，24 fps |
| 音频 | AAC |
| 时长 | 8.000 秒 |
| 文件大小 | 24,380 字节 |

这些参数由 ffprobe 读取归档文件得到，不使用输入期望值冒充媒体事实。

## 4. 契约与执行边界

- 视频公共 OpenAPI 为 56 个路径、67 个操作；Java `VideoApi` 保留 11 个 Project／Asset／VisualCanon／
  provider-asset 共享操作。
- 普通 CLI 共 152 个命令，其中视频 67 个；Operator Skill 白名单没有扩大。
- Durable Agent V2 Catalog 共 23 项，其中视频只保留
  `episode_script_generate`、`episode_script_revise`、`episode_storyboard_generate`、
  `episode_storyboard_revise` 4 项。旧章节视频操作、dispatcher 和 handler 不再可达。
- 制作基线输入使用 `video-production-shot-input/1.2`。Canon 与关键帧冻结 `rightsStatus=confirmed` 和规范 UTC
  `lockedAt`，渲染时重新对照当前数据库权利、锁定时刻、素材身份、MIME 和哈希。`1.0`／`1.1` 只允许历史
  simulated 读取；live 关闭失败并返回 `VIDEO_RENDER_RIGHTS_SNAPSHOT_REQUIRED`。
- Seedance 真实 POST／GET 分别集中在 `SeedanceProvider._create_live_task()` 和 `_query_live_task()`；默认
  `SEEDANCE_EXECUTION_MODE=simulated` 不访问供应商。提交开始后的未知结果进入 `submission_unknown`，普通重试和
  同镜新任务绕过均被禁止。
- Episode 交付 head 与交付记录使用复合外键；成片归档、Asset、Export、任务完成和
  `latestDeliveryVersionId/deliveryRevision` 在同一闭合事务中推进。

实现按火山引擎官方 Seedance 2.5 的[视频生成接口说明](https://docs.volcengine.com/docs/82379/1520757?lang=zh)、
[创建任务](https://docs.volcengine.com/docs/82379/1521309?lang=zh)和
[查询任务](https://docs.volcengine.com/docs/82379/1521720?lang=zh)规划供应商适配；本轮没有发送真实请求。

## 5. 数据库与退役验证

三项具名迁移已经落盘：

1. `scripts/migrations/20260910_video_episode_script_domain.sql`；
2. `scripts/migrations/20260910_video_production_baseline_domain.sql`；
3. `scripts/migrations/20260910_video_legacy_domain_retirement.sql`。

retirement 脚本只在隔离 PostgreSQL 验证：正向成功、幂等重放成功、legacy-only 行和共享表旧分支分别阻断，
额外外键导致中途失败时整事务回滚；脚本不使用 `DROP CASCADE`、`DELETE` 或 `TRUNCATE`。

常规 jOOQ 源码从 104 表 pre-Durable 契约生成，`WorkflowRun` 不包含只属于 post-Durable 动态 SQL 的字段；Episode
交付 head、复合外键和 revision 约束均存在。pre-Durable 规范指纹为
`0b8da839b6a759aaa1063c0cb8395e98feff184a4b7e94ee0bf3aae4f252a7ce`，109 表 post-Durable 投影规范指纹为
`3a51237c2d642c3b08247adbb6468615ab9b7f651216c74b877d7ca38d8d5e32`。

没有连接或修改服务器 `novelwriterdev`／`novelwriter`，没有执行生产部署。隔离容器、匿名卷、临时服务和任务专用
目录在验收后清理，最终核对为 `ZERO_RESIDUALS`。

## 6. 最终门禁

| 命令／检查 | 结果 |
| --- | --- |
| `./mvnw verify`（JDK 21） | 通过；服务鉴权 11、服务契约 5、Core 1,248（3 跳过）、Java CLI 145 |
| `.venv/bin/pytest -q` | 5,864 通过、3 跳过、1 个第三方弃用警告 |
| `.venv/bin/ruff check .` | 通过 |
| `.venv/bin/mypy apps/core-api/src apps/agent-service/src packages/service-contracts/src packages/service-auth/src` | 310 个源文件通过 |
| `npm run test:web` | Web 371、生成客户端 3，全部通过 |
| `npm run typecheck`、`npm run lint`、`npm run api:check` | 全部通过 |
| A／B／C 浏览器与媒体组合 E2E | 通过 |

全量收口中曾发现两项环境／契约问题并已解决：默认 JDK 17 被 Maven Enforcer 在测试前拒绝，改用项目要求的
JDK 21 后通过；Python ORM 曾只映射 `VideoEpisode` 六条数据库 CHECK 中的一条，形成不对称元数据，删除该孤立
映射后元数据定向 42 项和全量测试均通过。jOOQ 也已明确从 104 表 pre-Durable 隔离库重新生成，避免把 109 表
post-Durable 投影误写入常规生成源码。

## 7. 上线前剩余门槛

1. **真实调用与商业计费**：live 前必须补齐 Core `BillingReservation`、价格快照、调用前预留、幂等结算和未知
   用量对账；`feeConfirmed` 目前只表示试制确认。缺少 provider task ID 的 `submission_unknown` 还需要具名人工
   处置流程。在这些能力完成前，生产视频和 live Seedance 必须保持关闭。
2. **服务器物理退役**：需要用户对具名迁移另行授权，并在备份后核对目标库零旧行、零旧 Run／Artifact 引用；
   随后删除仍依赖旧 jOOQ 类型的未装配源码、执行迁移、重新导出 contract、重生成 jOOQ，并运行非视频 V2 回归。
3. **真实效果验收**：使用明确预算完成 Seedance 真实画质、声音、延迟、失败恢复和供应商用量验收后，才可讨论生产
   开关或公开商业能力。
