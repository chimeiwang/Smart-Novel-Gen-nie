# 退役旧 VideoScene 公共接口

状态：已完成
日期：2026-08-23

## 1. 背景

当前长篇视频工作台已经只挂载章节级 `VideoChapterAdaptation`，由完整章节生成按时间线排列的
Scene、DramaticBeat 和 Shot，再进行人工结构编辑、分集、视觉设定与逐镜提示词生产。旧
`VideoScene` 则以浏览器手工选区为入口，形成一个孤立的 4～15 秒规划任务；Web 和 CLI 均不再调用。

继续保留旧公共路由会让 OpenAPI 同时宣称两套互相冲突的小说影视化产品路径，也使“Core 当前视频
公共能力全部可由 CLI 操作”无法成立。本规格退役旧公共入口，不删除历史数据库事实。

## 2. 目标

- 从 `/api/v1/video/**` 删除全部六个旧 `VideoScene` 公共路由；
- 从项目公共读模型移除旧 `scenes` 集合和 `sceneCount`；
- 从 OpenAPI 和生成 TypeScript 客户端移除只属于旧入口的请求、响应和 operation；
- 保持当前 ChapterAdaptation、视频项目、素材和视觉设定接口不变；
- 为仍在使用的素材预览公共接口补充 CLI 命令，使剩余视频公共路由全部可由 CLI 调用；
- 保留历史任务的内部回调、耐久收敛和数据库结构兼容，不再允许创建新的旧任务。

## 3. 删除的公共接口

以下路由直接从 FastAPI 注册表删除，不提供别名或 `410` 兼容层；调用方得到标准 `404`：

```text
POST /api/v1/video/projects/{project_id}/scenes
GET  /api/v1/video/scenes/{scene_id}
POST /api/v1/video/scenes/{scene_id}/retry
POST /api/v1/video/scenes/{scene_id}/revise
POST /api/v1/video/scenes/{scene_id}/approve
POST /api/v1/video/scenes/{scene_id}/prompt-preview
```

`VideoProjectResponse.sceneCount` 和 `VideoProjectDetailResponse.scenes` 同时删除。项目列表不再连接
`VideoScene` 统计，项目详情只返回项目、素材与能力状态。

## 4. 保留的边界

### 4.1 当前公共产品链

删除后保留 20 个视频公共路由：

- 视频项目 3 个：创建、列表、详情；
- 素材 4 个：上传、权利确认、下载、浏览器内联预览；
- 章节改编 13 个：改编创建/列表/详情、拆镜、候选确认/丢弃、分集、提示词、视觉设定和逐镜参考。

CLI 为这 20 个路由提供具名命令，并额外提供一个只轮询改编聚合的本地 watcher。素材预览命令必须
把完整原始字节写入显式 `outputFile`，不得把二进制放入 stdout。

### 4.2 历史兼容

本轮不删除以下历史事实：

- `VideoScene`、`VideoGenerationTask`、`VideoAssetBinding`、`VideoReviewDecisionCommand` 数据表与 ORM；
- `/internal/v1/video/scenes/**` 签名回调；
- Core 对历史任务的 dispatcher、checkpoint、完成/失败和计费对账逻辑；
- Agent Service 的旧视频 job handler 与共享历史契约解析。

这些能力只用于已经存在的历史任务收敛和结构契约兼容。公共路由删除后没有新的 `VideoScene` 任务
准入路径。完整删除历史表、内部回调和 Agent handler 需要单独的数据盘点、终态证明、版本化数据库迁移
和生产授权，不在本次范围内。

## 5. 代码与文档变更

- 删除 Core 公共 router 中六个 scene handler；
- 删除 `VideoService` 中只被这些 handler 调用的公开编排方法和 route-only 编译依赖；
- 收窄项目公共 schema 与 repository 查询；旧 repository 事务代码暂时保留为历史兼容实现，不注册入口；
- 更新 03、04 号当前需求与 Agent 架构文档，把旧导演规划标为历史收敛链；
- 运行 `npm run api:generate`，禁止手工修改生成客户端；
- 更新 CLI 规格、README、注册表和测试，增加 `long.video.asset.preview`。

## 6. 数据库与部署

- 不执行开发库或正式库 DDL/DML；
- 不修改 `schema-contract.json`；
- 不删除历史数据或素材文件；
- 不改变 `VIDEO_PREVIEW_ENABLED`、Seedance 配置或生产部署状态。

## 7. 验收标准

1. FastAPI/OpenAPI 中不存在六个 `/video/**/scenes` 旧公共路由和对应 operations。
2. OpenAPI 不再暴露 `Create/Revise/ApproveVideoScene`、`VideoSceneResponse`、旧 PromptPreview DTO。
3. 项目公共响应不含 `scenes` 或 `sceneCount`，项目列表查询不再连接 `VideoScene`。
4. 当前 Web 的 ChapterAdaptation 工作台、视觉素材缩略图和全部 v2 路由保持可用。
5. CLI 精确注册 21 个 `long.video.*` 命令；20 个剩余公共路由均有调用入口。
6. 旧公共路径请求返回 404，而素材、项目和 ChapterAdaptation 路由仍通过认证与业务校验。
7. 内部历史任务回调、dispatcher、数据库 schema guard 和生产迁移守卫保持通过。
8. OpenAPI 一致性、相关 Pytest、CLI 全量测试、Web 测试、TypeScript、ESLint、Ruff、Mypy、
   架构测试与 `git diff --check` 通过。

## 8. 实施验证

- 六个旧 `VideoScene` 公共 operation 已从 FastAPI 和生成客户端删除；OpenAPI 现在精确保留 20 个
  视频公共 operation，不再包含 `/api/v1/video/**/scenes`。
- `VideoProjectResponse.sceneCount` 与 `VideoProjectDetailResponse.scenes` 已删除，项目列表不再连接
  `VideoScene`，项目详情只查询项目与素材。
- CLI 已注册 21 个 `long.video.*` 命令；新增 `long.video.asset.preview` 后，20 个剩余视频公共
  operation 均有具名调用入口，额外 watcher 只复用改编详情轮询。
- 历史 ORM、数据库表、内部签名回调、dispatcher 和 Agent handler 保留；本轮没有执行数据库读写、
  迁移或结构契约变更。
- 全仓 Python 3151 项通过、2 项按数据库环境跳过；视频 Core 80 项通过、2 项跳过，视频 Agent
  150 项、CLI 518 项、架构 114 项通过。
- Web 289 项与 API Client 3 项通过；OpenAPI 一致性、TypeScript、ESLint、生产构建、全仓 Ruff、
  287 个源文件 Mypy 和 `git diff --check` 通过。
