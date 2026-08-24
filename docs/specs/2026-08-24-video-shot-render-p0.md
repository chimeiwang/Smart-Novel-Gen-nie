# 逐镜视频生成与候选 Take P0

状态：已完成（开发环境）
日期：2026-08-24
适用范围：当前长篇小说章节影视化工作台、Core API、Agent Service、CLI 与开发库

## 1. 背景与产品判断

当前主链已经能把章节转换为正式镜头方案，并为每个正式镜头保存即梦提示词和视觉参考快照，但到此为止仍然只是“生成前准备”。用户无法提交真实视频任务、查看供应商状态、比较多次生成结果，也无法确认某一条结果作为该镜头当前采用的素材。

P0 的产品对象不是“整章成片”，而是正式镜头下的候选 Take：

```text
正式镜头 + 正式提示词版本 + 该提示词冻结的视觉参考
  -> 一次显式、可能计费的即梦任务
  -> 一个不可变候选 Take
  -> 人工播放比较
  -> 确认某个 Take 为该镜头当前采用版本
```

这个边界保持“小说 -> 分集 -> 镜头 -> 提示词 -> 候选视频”的可追溯关系，并为后续时间线、声音和局部重做保留稳定输入。

## 2. P0 目标

1. 用户可从一个正式镜头的当前正式提示词创建一次即梦任务。
2. 任务跨刷新、Core/Agent 重启后仍可恢复；供应商提交和查询都是短调用，不占用 Agent 队列 worker 长时间轮询。
3. 每次可能再次计费的生成或重试都创建新任务，不暗中复用旧任务。
4. 提交前冻结镜头方案版本、提示词版本及文本、视觉参考版本及强度、画幅、供应商模型和输出参数，并计算输入哈希。
5. 供应商成功结果必须先归档到 InkForge 受控存储，之后才创建不可变 Take；浏览器不直接依赖供应商临时 URL。
6. 用户可播放并并排比较同一镜头的多个 Take，查看各自输入版本、状态和失败原因。
7. 用户确认 Take 时只原子切换该镜头的 Take head；使用 expected revision 做 CAS，旧 Take 和旧确认历史不被覆盖。
8. 新增公共能力全部提供 CLI 命令；公共接口通过 OpenAPI 生成客户端。

## 3. P0 非目标

- 不做整集或整章批量付费生成。
- 不做关键帧生成或首尾帧编辑。
- 不做多轨粗剪时间线、镜头裁切、转场或整集导出。
- 不做配音、音乐、音效、字幕和口型同步。
- 不做基于已有视频的局部 Retake、扩画或视频编辑。
- 不做自动质量评分，也不以机器评分替代人工选片。
- 不改写正式镜头方案、正式提示词版本或视觉设定历史。
- 不重新启用旧 `VideoScene` 公共接口，也不复用旧 `VideoGenerationTask`。
- 本规格不授权生产数据库迁移、生产视频开关或真实生产付费调用。

## 4. 产品流程

### 4.1 生成前门禁

只有同时满足以下条件才允许创建任务：

1. 章节改编、项目、镜头归当前用户所有；
2. 镜头属于当前正式 `VideoShotPlanVersion`；
3. 镜头已有 `VideoShotPromptHead.currentVersionId`，且请求的 expected prompt revision 匹配；
4. 正式提示词非空；
5. 提示词版本冻结的所有视觉参考素材仍存在、权利为 `confirmed` 且已锁定；
6. Core 显示供应商 `configured=true` 且 `enabled=true`；
7. 有视觉参考时，供应商可访问的短时素材传输地址已经配置；
8. 输出时长是用户显式选择的供应商时长，不从镜头时间线静默截断。界面默认使用最接近镜头时长的支持值，并同时展示两者。

### 4.2 任务与状态

`VideoShotRenderTask` 是 Core/PostgreSQL 的权威事实，状态机为：

```text
pending -> submitting -> queued/running -> archiving -> succeeded
                  \-> submission_unknown
queued/running ---------------------------> failed/expired/cancelled
archiving --------------------------------> failed
```

- `pending`：等待 Core 后台领取。
- `submitting`：正在执行一次供应商创建短调用。
- `submission_unknown`：创建调用结果不确定；不得自动重提，以免重复计费。用户只能显式创建新任务。
- `queued/running`：已有稳定 providerTaskId，按 nextAttemptAt 短轮询。
- `archiving`：供应商成功，正在下载并写入受控存储。
- `succeeded`：受控文件、`VideoAsset` 和 `VideoShotTake` 已在同一完成流程中登记。
- `failed/expired/cancelled`：明确终态，保留供应商错误代码和可读说明。

Redis 不保存渲染业务状态。Core 后台 reconciler 只领取到期行；Agent Service 只执行即梦 `submit/query` 短请求，且没有数据库访问。

### 4.3 重试语义

- “重试”是用户显式发起的新任务，并通过 `retryOfTaskId` 指向旧任务。
- 重试精确复制旧任务冻结的输入 manifest，不自动采用后来修改的提示词或视觉参考。
- 原任务若已不属于当前正式镜头方案，则拒绝付费重试；用户必须从当前正式镜头重新生成。
- 若用户希望采用最新提示词或参考图，应从镜头再次“生成候选”，创建另一条新任务。
- `clientRequestId` 保证同一用户操作重放时返回原任务，不重复计费。

### 4.4 Take 与确认

- 一个成功任务至多产生一个 `VideoShotTake`。
- Take 保存 task、shot、plan、prompt、asset、providerTaskId、模型、输入哈希和脱敏供应商元数据；成功后不可修改。
- `VideoShotTakeHead` 保存镜头当前采用的 Take 和 revision。
- 确认命令携带 `clientRequestId + expectedTakeRevision`。命令成功、重复、冲突结果均持久化，重复请求返回同一结果。
- 切换当前 Take 不删除旧 Take；P2 时间线只能引用已经确认的 Take head 或其明确版本。

## 5. 数据模型

开发库具名迁移 `scripts/migrations/20260824_video_shot_render_p0.sql` 新增：

### 5.1 VideoShotRenderTask

核心字段：id、adaptationId、projectId、novelId、shotId、shotPlanVersionId、promptVersionId、retryOfTaskId、provider、model、status、clientRequestId、inputHash、requestManifestJson、providerTaskId、pollCount、attemptCount、nextAttemptAt、错误、createdAt/updatedAt/submittedAt/completedAt。

关键不变量：

- shot、plan、adaptation、project、novel 必须属于同一条所有权链；
- promptVersion 必须属于该 shot 和 plan；
- retryOfTask 必须属于同一 shot；
- `(shotId, clientRequestId)` 唯一；
- `(provider, providerTaskId)` 在 providerTaskId 非空时唯一；
- 同一镜头同时至多存在一个 pending/submitting/queued/running/archiving 任务；
- 活跃任务有 due partial index；
- `requestManifestJson` 创建后不改写。

### 5.2 VideoShotTake

核心字段：id、taskId、adaptationId、projectId、shotId、shotPlanVersionId、promptVersionId、assetId、takeNo、provider、model、providerTaskId、inputHash、providerMetadataJson、createdAt。

关键不变量：taskId 和 assetId 均唯一；同一 shot 的 takeNo 唯一；所有冗余归属字段由组合外键约束。

### 5.3 VideoShotTakeHead

核心字段：shotId、shotPlanVersionId、currentTakeId、revision、updatedAt。currentTakeId 必须属于同一 shot；revision 是确认 CAS 的唯一权威。

### 5.4 VideoShotTakeDecisionCommand

核心字段：id、adaptationId、projectId、shotId、takeId、clientRequestId、expectedRevision、status、resultingRevision、errorCode、requestedByUserId、createdAt。`(requestedByUserId, clientRequestId)` 唯一。

## 6. 请求 manifest 与敏感信息

持久化 manifest 只包含：

- schemaVersion；
- shot/plan/prompt 的 ID、内容哈希及冻结提示词；
- 有序视觉参考的 canonVersionId、assetId、sha256、duty、strength；
- model、ratio、durationSeconds、resolution、generateAudio、watermark；
- sourceTimelineDurationMs 和整体 inputHash。

不持久化 API Key、Authorization header、供应商临时视频 URL、素材短时签名 URL。短时素材 URL 只在 Core reconciler 领取任务后物化并通过受签名的 Core -> Agent 内部请求传递。

## 7. 公共 API

| 方法与路径 | 作用 |
| --- | --- |
| `GET /api/v1/video/chapter-adaptations/{adaptationId}/renders` | 读取当前正式方案的任务、Take、head 与供应商 readiness |
| `POST /api/v1/video/chapter-adaptations/{adaptationId}/shots/{shotId}/render-tasks` | 从当前正式提示词创建一次新任务 |
| `POST /api/v1/video/render-tasks/{taskId}/retry` | 按旧 manifest 显式创建新任务 |
| `GET /api/v1/video/render-tasks/{taskId}` | 查询一条耐久任务 |
| `POST /api/v1/video/chapter-adaptations/{adaptationId}/shots/{shotId}/takes/{takeId}/confirm` | CAS 确认当前 Take |
| `GET /api/v1/video/takes/{takeId}/content` | 归属校验后播放/下载受控视频 |

章节规划聚合保持原有稳定契约；同级 render workspace 聚合返回供应商 readiness、逐镜任务、Take 和 Take head。渲染事实不塞入 `latestTask` 的规划任务语义。

## 8. Agent 与供应商边界

- Agent 新增受 Ed25519 和直接对端网段保护的内部 Seedance 短调用路由。
- submit 输入是 Core 已冻结 manifest 的运行时投影；Agent 不重写提示词、不重排参考图、不读取数据库。
- query 只返回规范化状态、成功时的临时 video URL、必要输出元数据或失败错误；Core 负责归档和业务状态。
- 当前官方查询状态按 `queued/running/succeeded/failed/expired/cancelled` 规范化；未知状态进入可恢复错误，不猜测成功。
- 供应商关闭和未配置是两个不同 blocker。

## 9. Web 原型落点

现有章节影视化步骤后新增“生成与选片”，沿用安静工作区和三栏信息层级：

- 左栏：按集、场、节拍组织正式镜头，显示未生成/生成中/有候选/已确认状态；
- 主区：当前镜头的候选 Take 网格，可播放，并可选择最多两个并排比较；
- 右侧/主区详情：冻结的提示词版本、参考图、模型、时长、任务错误和重试；
- 主操作只有“生成新候选”“重试该输入”“确认为当前 Take”；不把整章生成伪装成 P0 能力。

实现继续遵守 `DESIGN.md`：PC 优先、原生 CSS、复用现有按钮/状态/notice 语义，不引入独立设计体系，也不把每一行做成悬浮卡片。

## 10. CLI

新增并复用同一公共接口：

- `long.video.render.start`
- `long.video.render.list`
- `long.video.render.get`
- `long.video.render.retry`
- `long.video.render.watch`
- `long.video.take.confirm`
- `long.video.take.download`

watch 输出 JSONL；download 必须显式给出输出文件，不把二进制写到终端。

## 11. 后续路线图

### P1：关键帧与视觉锚点

- 为高风险镜头先生成/确认首帧、尾帧或关键帧；
- 关键帧本身版本化，并进入渲染 manifest；
- 提供角色脸、服装、场景空间和道具连续性检查。

状态：已进入 `2026-08-24-video-post-production-p1-p3.md` 实施范围。

### P2：粗剪时间线

- 以分集为单位把已确认 Take 放入非破坏性时间线；
- 支持入点/出点、镜头顺序、空缺占位、基础转场和预览；
- 原始 Take 不被裁切覆盖，编辑决定单独版本化。

状态：已进入 `2026-08-24-video-post-production-p1-p3.md` 实施范围。

### P3：声音、字幕与整集输出

- 对白/旁白配音、环境声、音效、音乐、字幕和混音轨；
- 对齐镜头时间线，支持人工校时和单轨替换；
- 导出可追溯的整集版本。

状态：已进入 `2026-08-24-video-post-production-p1-p3.md` 实施范围。

### P4：局部 Retake 与视频编辑

- 基于已生成 Take 做局部重绘、表情/动作修正、扩画、续写和首尾帧约束；
- 每次局部修改仍创建新派生版本，不覆盖原 Take；
- 比较修改前后，并保留派生关系和供应商输入。

## 12. 验收

1. 同一创建请求重放只产生一个任务；显式重试产生新任务并指向原任务。
2. 任务提交后刷新页面，仍能继续看到 queued/running 和最终结果。
3. 模拟 Core 在 submit 响应前断线时进入 `submission_unknown`，不会自动重复提交。
4. 供应商成功但归档失败时不创建 Take，任务保留明确错误且可显式重试。
5. 成功归档后供应商 URL 失效，Take 仍可从 InkForge 播放。
6. 修改提示词或参考图不会改变旧任务 manifest 和旧 Take。
7. 两个页面用同一 expected revision 确认不同 Take，只有一个成功，另一条得到稳定 409 命令回执。
8. Web 能并排播放两个候选，清楚显示当前已确认 Take。
9. 所有新增公共操作都有 CLI 命令，OpenAPI 客户端与 Core 契约一致。
10. 开关关闭时绝不调用供应商；开发迁移不触碰生产库。

## 13. 实施与验证记录

- 已在服务器端 `novelwriterdev` 执行具名迁移；迁移前备份位于
  `.data/backups/inkforge-20260824T013702Z`，已通过 SHA-256 与 `pg_restore --list`
  校验。迁移先在隔离恢复库执行两次，再在开发库执行并验证幂等。
- 开发库完整 schema guard：`ready=true`、0 项差异，指纹为
  `bbb5615534446d2031e6abdc6b807e4692fd6a5072efe0a2b31530d07dd604d1`；四张
  P0 表当前均为 0 行，验收数据已精确清理。
- 正式库 `novelwriter` 仅做只读 `without_video_preview` 校验：`ready=true`、0 项差异；
  正式库不存在 `VideoShotRenderTask`，未执行 P0 DDL、未开启视频或 Seedance 开关。
- Python 全量回归 3179 通过、2 跳过；Web 289 项、API Client 3 项通过；Ruff、
  Mypy、TypeScript、ESLint、OpenAPI 漂移检查与 Next.js 生产构建均通过。
- PostgreSQL 事务验收覆盖创建、领取、供应商受理、归档 Take、确认 head、旧 revision
  冲突持久化和按原 manifest 重试；测试结束后相关数据均已清理。该验收使用本地假供应商，
  未向外部发起付费调用。
- Chrome 本地实例验收覆盖现有长篇章节入口、正式方案与待审候选隔离、
  “集 → 场 → 戏剧节拍 → 镜头”导航、按剪辑目标选择默认生成时长，以及 Seedance
  三项关闭门禁；控制台无错误或警告。
- 真实 Seedance 付费端到端调用不属于本次安全验收结果；只有配置密钥、素材公网短时传输
  和开发环境真实调用开关后，才允许另行执行。
