# 视觉设定版本与逐镜参考图绑定

状态：开发库实现完成；真实 Core 链路与 Chrome 可视闭环已验收，交互收敛见 2026-08-23 验收加固 spec
日期：2026-08-22

## 1. 背景

章节影视化已经形成“章节原文 → 场景/节拍/镜头 → 人工确认 → 分集 → 逐镜提示词”的主链路，
但角色、服装、场景和关键道具仍主要依赖文字设定。只给角色或地点表增加一个 `imageUrl` 会产生四个问题：

- 无法区分角色身份、服装变体、地点时段和道具等不同职责；
- 换图后旧提示词和未来视频任务无法说明当时采用了哪一版；
- 未确认的候选图会被误当成正式视觉事实；
- 多角色镜头只能携带一张模糊参考图，容易串脸、串服装或污染场景。

现有 `VideoAsset` 已经提供项目级文件、哈希、权利确认和受保护读取能力，应继续作为媒体文件仓库；
旧 `VideoAssetBinding` 固定绑定旧 `VideoScene`，不能用于新的章节改编域。

## 2. 产品结论

新增“视觉设定（Visual Canon）”层，而不是在小说设定实体上保存一张图片：

```text
小说文字设定
  → 项目内视觉设定槽（角色身份 / 服装 / 场景 / 道具）
  → 上传候选图片
  → 用户确认权利与视觉内容
  → 生成不可变视觉设定版本
  → 正式镜头绑定具体版本与参考强度
  → 提示词任务冻结绑定快照
  → 正式提示词保存同一组参考版本
  → 后续即梦请求复用同一组图片和强度
```

图片负责稳定“它是谁、穿什么、空间长什么样、道具长什么样”；逐镜提示词继续负责当前动作、表情、
视线、摄影和声音。绑定参考图后，Agent 不再机械复述参考图已经负责的完整静态外观，但仍保留主体名称、
构图中可见的必要锚点和当前状态。

## 3. 目标

1. 角色、地点和道具可以拥有项目级、分职责、分变体的视觉设定槽。
2. 上传图片先成为候选，只有用户明确确认后才产生不可变正式版本。
3. 一个镜头可以同时绑定多个人物身份、人物服装、场景和道具版本，并分别设置参考强度。
4. 逐镜提示词任务固定到精确视觉版本；换图不改变既有候选或正式提示词的来源。
5. 章节影视化页面能预览候选/正式图片、批准版本、按镜头编辑绑定，并提示缺少角色或场景参考。
6. 为后续即梦图片参考参数提供稳定的 `assetId + canonVersionId + strength` 输入，但本阶段不调用视频生成 API。

## 4. 非目标

- 不让 AI 自动决定哪张图片成为正式视觉设定；
- 不从单张图片自动生成三视图、表情集或服装变体；
- 不实现即梦视频生成、首尾帧生成或供应商上传；
- 不把视觉设定写进 `Character/Location/Item` 表；
- 不复用旧 `VideoAssetBinding` 或旧 `VideoScene`；
- 不修改生产数据库。

## 5. 产品流程

### 5.1 视觉设定槽

首版支持：

| 文字设定 | 视觉职责 | 典型变体 |
| --- | --- | --- |
| 角色 | `identity` 身份 | `default`，中性三分之四脸为主 |
| 角色 | `costume` 服装 | 常服、制服、战损、特定阶段 |
| 地点 | `scene` 场景 | 默认、日/夜、天气或剧情阶段 |
| 道具 | `prop` 道具 | 默认、损坏前/后等静态版本 |

`variantKey` 是同一设定与职责下的稳定槽标识，不把“夜景”“战损”混进文件名猜测。角色身份默认只保留
一个当前批准版本；服装、场景和道具允许多个变体槽并存。

### 5.2 候选与批准

1. 用户选择文字设定、职责、变体和图片，并明确确认拥有使用权；
2. 图片保存为 `VideoAsset`，必须是 `image`，职责必须与视觉设定槽一致；
3. 图片先进入该槽的候选位置，不影响当前正式版本；
4. 用户查看图片、包含特征、排除特征和默认参考强度后点击“确认为视觉设定”；
5. Core 创建新的不可变 `VideoVisualCanonVersion`，切换槽的当前版本并清空候选；
6. 旧版本继续保留，已绑定镜头和既有提示词仍可追溯。

上传图片建议在界面内明确：避免强表情、强动作、极端透视和戏剧性彩光；身份图优先中性三分之四脸，
场景图优先能读清空间关系的主视图。建议不是硬门禁。

### 5.3 镜头绑定

正式镜头方案确认后，每个镜头拥有一个带 CAS revision 的视觉参考集合。用户可以：

- 从项目当前已批准版本中选择多个参考；
- 为同一角色分别绑定身份与服装；
- 为多人镜头绑定多个人物身份，不能合并成一个“人物参考”文本；
- 调整每个参考的 `strength=1..100`；
- 使用按名称与当前镜头事实计算的非阻断推荐，一键采用后仍可手动调整。

集合保存必须替换完整集合并递增 revision；空集合合法，但界面提示角色/场景稳定性风险。

### 5.4 提示词与后续视频请求

创建 `chapter_shot_prompt_v2` 任务时，Core 在同一事务中冻结每个目标镜头的视觉参考：

- `canonVersionId`；
- `assetId` 与完整内容哈希；
- 设定类型、设定 ID、显示名称、职责和变体；
- 包含/排除特征与参考强度。

Agent 只读取这份结构化元数据，不读取 PostgreSQL，也不接收文件路径。绑定 `identity/costume/scene/prop` 后，
设定投影分别省略由图片负责的完整静态身份外观、完整服装、场景装饰或道具造型；本镜明确动作、状态和画面中
必须识别的锚点仍可进入提示词。

候选响应展示“本提示词需随附的参考图”。用户保存正式提示词时：

- 若从 AI 候选保存，复制该候选来源任务冻结的参考集合；
- 若没有候选而直接手写，复制保存时当前镜头参考集合；
- 正式提示词版本通过关系表引用精确视觉版本，不能只保存当前 Head 或图片 URL。

## 6. 数据模型

继续扩展已批准的开发迁移 `scripts/migrations/20260818_video_chapter_adaptation_domain.sql`，新增：

### 6.1 `VideoVisualCanon`

项目内逻辑视觉设定槽：

- `id/projectId/novelId`；
- `settingKind=character|location|item`、`settingId/settingName`；
- `duty=identity|costume|scene|prop`、`variantKey/label`；
- 可空 `candidateAssetId/currentVersionId`；
- `revision/createdAt/updatedAt`。

唯一键为 `(projectId, settingKind, settingId, duty, variantKey)`。Core 每次写入都校验文字设定仍属于同一小说；
多态设定引用不伪造数据库跨表外键。

### 6.2 `VideoVisualCanonVersion`

用户批准后生成的不可变版本：

- `id/canonId/projectId/novelId/versionNo/assetId`；
- 批准时冻结的 `settingName/label`，避免随后重命名候选改变历史提示词说明；
- `includeFeaturesJson/excludeFeaturesJson/defaultStrength`；
- `approvedByUserId/contentHash/createdAt`。

素材必须已确认权利、已锁定、模态为图片且职责匹配。版本行创建后不修改；Head 只在 `VideoVisualCanon` 上切换。

### 6.3 `VideoShotVisualReferenceSet` 与 `VideoShotVisualReferenceBinding`

参考集合保存 `shotId/planVersionId/adaptationId/projectId/novelId/revision/updatedAt`；子项保存有序
`canonVersionId/strength`。复合外键保证镜头属于当前方案、方案属于该改编、视觉版本属于同一项目和小说。

### 6.4 `VideoShotPromptVisualReference`

正式提示词版本与视觉设定版本之间的不可变有序关系，保存 `promptVersionId/shotId/ordinal/canonVersionId/strength`。
它让提示词版本不依赖随后变化的镜头参考集合。

## 7. 公共 API

新增：

```text
GET  /api/v1/video/projects/{projectId}/visual-canons
POST /api/v1/video/projects/{projectId}/visual-canons
POST /api/v1/video/visual-canons/{canonId}/approve
PUT  /api/v1/video/chapter-adaptations/{adaptationId}/shots/{shotId}/visual-references
GET  /api/v1/video/assets/{assetId}/preview
```

上传与权利确认继续复用：

```text
POST  /api/v1/video/projects/{projectId}/assets
PATCH /api/v1/video/assets/{assetId}/rights
```

公共 DTO 先由 Core Pydantic 定义，再重新生成 TypeScript 客户端。前端不得手写重复业务 DTO。

## 8. 前端原型

章节影视化步骤改为：

```text
拆镜与审镜 → 分集 → 视觉设定 → 逐镜提示词
```

视觉设定步骤保持 PC 三栏：

- 左栏：当前章节用到的角色、地点、道具设定卡与“缺图/候选/已批准”状态；
- 中栏：当前设定的身份、服装、场景或道具变体，展示候选图、当前版本和历史版本摘要；
- 右栏：正式镜头列表与当前镜头绑定，支持参考强度、移除和采用推荐。

提示词步骤在编辑器上方展示参考图片缩略图、职责、版本和强度；没有角色身份或场景参考时显示非阻断提示，
不伪装成已经解决稳定性。

界面继续遵循 `DESIGN.md`：hairline 边框、紧凑列表、原生 CSS、状态文字与颜色同时出现，不引入新 UI 框架。

## 9. 安全与一致性

- 所有文件读取继续经过浏览器认证与小说归属校验；不暴露本地存储路径；
- 上传继续使用魔数、大小、路径穿越和符号链接防护；
- 只有 `rightsStatus=confirmed` 且 `lockedAt` 非空的图片可以批准；
- 候选批准、版本号分配和 Head 切换在一个事务内完成；
- 镜头参考保存使用 revision CAS，禁止最后写入静默覆盖；
- Prompt 任务 `requestJson` 与正式 PromptVersion 均保存精确版本关系；
- Agent Service 不读取图片文件、不连接数据库；
- 开发迁移必须拒绝非 `novelwriterdev` 数据库，应用启动不得执行 DDL。

实施时只读导出发现 `novelwriterdev.TokenUsage` 已在本迁移前存在可空 `requestId/taskId/runId` 与对应索引，仓库旧
ORM 未映射。该漂移不是视觉迁移创建的，本次不新增、删除或回填这些计费列；只增加可空 ORM 映射以保持导出的开发库
结构契约与运行时元数据一致，现有计费写入行为不变。

## 10. 验收标准

1. 用户能为角色身份、角色服装、地点场景和道具上传候选图片并明确批准。
2. 批准新图产生递增不可变版本，旧版本仍能被既有镜头和提示词读取。
3. 一个多人镜头可以绑定多个人物身份和各自服装，不发生单引用覆盖。
4. 镜头参考集合使用 CAS；跨项目、跨小说、未批准或非图片素材均被拒绝。
5. Prompt 任务载荷冻结每个目标镜头的精确视觉参考，Agent 不从当前 Head 猜版本。
6. 有视觉参考时，提示词上下文不再复制该职责负责的完整静态设定；当前动作、状态和摄影信息仍完整。
7. Prompt 候选与正式 PromptVersion 都能展示各自使用的图片版本和强度。
8. 前端完成“上传 → 权利确认 → 批准 → 逐镜绑定 → 生成候选 → 保存正式提示词”闭环。
9. 相关 Core、Agent、共享契约和 Web 测试通过；OpenAPI 客户端重新生成；Ruff、Mypy、TypeScript 和 Lint 通过。
10. 迁移只在 `novelwriterdev` 执行并重新导出 schema 契约；生产数据库不发生任何变更。

## 11. 实施验证

- `novelwriterdev` 已执行具名迁移并通过完整 schema guard，最终指纹为
  `36904c220803175dbb65dc38329f29b8d41f1386cac46f4992d8f77ad6653f40`；
- 真实 Core 业务链已完成“图片流式上传 → 权利确认 → 候选槽 → 批准不可变版本 → 正式镜头 CAS 绑定
  → Prompt 任务冻结 → PromptVersion 关系复制”，测试数据和文件均按精确 ID 清理，残留为零；
- Web 288 项、API Client 3 项测试通过；视频/数据库相关 Python 180 项通过、2 项按环境条件跳过；
- Ruff、Mypy、TypeScript、ESLint、OpenAPI 一致性、生产构建和 `git diff --check` 通过；
- 2026-08-23 已在本地 Chrome 登录实例完成“上传 → 权利确认 → 批准 v1 → S01 强度 70 绑定 →
  重新生成候选 → 手动编辑 → 保存 PromptVersion v2”闭环；开发库关系和页面参考缩略图一致。
- 浏览器验收发现的候选/正式版本上下文、参考快照变化提示、设定卡加载假空态和新增视觉效果告警，
  已由 `docs/specs/2026-08-23-video-adaptation-browser-acceptance-hardening.md` 收敛；随后在本地 Chrome
  把 S01 当前参考调整为强度 71，验证旧快照保持 70、按当前参考重生成并保存后正式版本冻结 71。
