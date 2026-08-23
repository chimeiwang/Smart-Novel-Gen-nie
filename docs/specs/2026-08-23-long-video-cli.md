# 长篇章节影视化 CLI

状态：已完成
日期：2026-08-23

## 1. 背景

当前长篇章节影视化已经形成完整公共 API：视频项目、章节改编根、镜头方案任务、候选确认、分集、
逐镜提示词、视觉设定版本、逐镜参考图和素材权利确认。Web 已能操作该主链，但仓库 CLI 只覆盖长篇
写作、资料、审核和质量检查，自动化操作者仍只能回到浏览器。

本规格把当前产品主链 CLI 化，不把早期“选区创建 `VideoScene`”开发预览重新包装成新流程。CLI
继续是 Core 公共 API 的受约束客户端，不是数据库管理器，也不是 Agent Service 客户端。

## 2. 产品流程

```text
创建/选择视频项目
  → 按章节创建改编根
  → 启动拆镜任务并观察
  → 导出完整候选，人工删除/合并/编辑镜头
  → 携带完整编辑后候选和双 revision 确认正式镜头方案
  → 保存分集边界
  → 上传图片、确认权利、建立并批准视觉设定版本
  → 按正式镜头保存参考版本与强度
  → 启动逐镜提示词任务并观察
  → 人工编辑并逐镜保存正式提示词
```

候选确认、视觉版本批准和正式提示词保存都保持显式命令，不提供“一键从章节自动写入全部正式结果”
命令。CLI 不替作者自动批准 ReviewArtifact、视觉图片或提示词。

## 3. 命令面

新增 21 个具名命令：

```text
long.video.project.list
long.video.project.get
long.video.project.create
long.video.asset.upload
long.video.asset.rights
long.video.asset.download
long.video.asset.preview
long.video.adaptation.list
long.video.adaptation.get
long.video.adaptation.create
long.video.adaptation.watch
long.video.plan.start
long.video.plan.confirm
long.video.plan.discard
long.video.episode.save
long.video.prompt.start
long.video.prompt.save
long.video.canon.list
long.video.canon.candidate.set
long.video.canon.approve
long.video.reference.save
```

命令全部使用现有 `/api/v1/video/**`。不注册旧 `VideoScene` 的 `create/retry/revise/approve` 和
`prompt-preview` 命令，避免形成两套互相冲突的“小说转视频”产品路径。

## 4. 输入与输出

除 `auth.login` 外继续统一使用 stdin UTF-8 JSON，stdout 返回 JSON；
`long.video.adaptation.watch` 返回 JSONL。

### 4.1 完整读取

- 项目、改编、视觉设定查询默认完整内联返回；
- 查询可显式提供 `outputFile`，把完整 JSON 原子写入文件；
- `long.video.asset.download` 强制提供 `outputFile`，按原始字节原子写入，不把二进制放入 stdout；
- `long.video.asset.preview` 同样强制提供 `outputFile`，只把公共内联预览响应转换为本地完整文件；
- 不按大小自动截断候选、章节来源、提示词、审镜发现或参考图元数据。

### 4.2 文件输入

- `long.video.plan.confirm` 接受 `plan` 或 `planFile`，必须且只能提供一个；
- `long.video.prompt.save` 接受 `currentPrompt` 或 `currentPromptFile`，必须且只能提供一个；
- `long.video.asset.upload` 只接受 `filePath`，以 multipart 上传原始文件，不做转码、压缩或内容改写；
- JSON 文件必须是单个完整 UTF-8 JSON 对象，提示词文件按完整 UTF-8 文本读取。

### 4.3 路径与字段

所有资源 ID 都做 URL path segment 编码。每个命令拒绝未声明字段，`profile` 和读取命令的
`outputFile` 是唯一通用本地字段。CLI 只做类型、枚举、长度、唯一性和跨字段一致性预检，不复制
FastAPI/Pydantic 的完整业务 DTO；Core 仍是最终契约权威。

## 5. 幂等、CAS 与人工确认

需要稳定 `clientRequestId` 的命令：

```text
long.video.adaptation.create
long.video.plan.start
long.video.plan.confirm
long.video.plan.discard
long.video.episode.save
long.video.prompt.start
long.video.canon.candidate.set
long.video.canon.approve
```

`long.video.plan.confirm` 和 `long.video.plan.discard` 在写入前必须 GET 当前改编，核对候选存在、
`reviewArtifact.revision` 和 `headRevision` 与调用方提交值一致，然后才调用正式接口。该 preflight 不能
替代 Core 事务内锁和 CAS。

`long.video.prompt.save` 使用 `expectedPromptRevision`，`long.video.reference.save` 使用
`expectedRevision`。冲突时停止并重新 GET，不自动替换 revision 重试。

现有项目创建、素材上传、素材权利修改和逐镜 CAS 接口没有 `clientRequestId`。CLI 不伪造幂等能力：

- 项目创建或素材上传遇到网络结果不确定时，先 list/get 核对，不能盲目重试；
- prompt/reference 写入遇到网络结果不确定时，先回读 Head revision 和正式版本再决定；
- CLI 不增加本地任务账本或隐藏重试。

## 6. 异步任务观察

`long.video.adaptation.watch` 要求 `adaptationId + taskId`，轮询
`GET /api/v1/video/chapter-adaptations/{adaptationId}`：

- 首次返回完整 `snapshot`；
- `latestTask.status/checkpointStage/updatedAt` 变化时返回 `progress`；
- `completed` 返回 `terminal` 和退出码 0；
- `failed/cancelled` 返回 `terminal` 和退出码 5；
- 当前 `latestTask.id` 与目标不一致时明确返回被后续任务替代错误，不把其他任务当成本任务结果；
- Core 连续不可达超过 300 秒才停止观察，停止观察不取消服务端任务；
- Ctrl-C 返回 130，只停止 watcher。

当前章节影视化没有公共 SSE 或 task GET 接口，CLI 不访问 `/internal/v1/**`，也不把普通轮询伪装成
SSE。以后若增加公共事件接口，再以独立 spec 演进。

## 7. 视觉稳定性

CLI 覆盖完整视觉设定闭环：

1. 上传图片素材；
2. 显式把权利状态改为 `confirmed`；
3. 把素材设置为角色身份、角色服装、地点场景或道具候选；
4. 携带候选槽 revision 批准不可变版本；
5. 为正式镜头保存有序 `canonVersionId + strength` 集合。

职责与设定类型必须匹配：`identity/costume → character`、`scene → location`、`prop → item`。
同一镜头不能重复绑定同一视觉版本，同一候选的包含/排除特征不能重复。

## 8. 架构边界

- 只修改 `tools/inkforge-cli`、CLI 文档和测试；
- 不新增或修改公共 API、共享契约、OpenAPI 客户端和 PostgreSQL schema；
- 不导入 Core 实现、SQLAlchemy、asyncpg 或 Agent Service；
- 不读取 `DATABASE_URL`，不访问 `/internal/**`；
- 不改变 ReviewArtifact、VideoAdaptationTask、PromptVersion 或视觉版本状态机；
- 生产环境当前 `VIDEO_PREVIEW_ENABLED=false`，CLI 发布不等于功能启用。写命令会继续得到 Core 的
  `VIDEO_SERVICE_UNAVAILABLE` 或 `VIDEO_PREVIEW_DISABLED`，不能用 CLI 绕过开关。

## 9. 验收标准

1. 注册表与 README 精确列出全部 21 个新命令，无通配符或未实现占位。
2. 每个命令只调用对应 `/api/v1/video/**` 路径，ID 编码、HTTP method 和 body 精确。
3. plan/prompt 文件完整读取，asset 上传/下载保持原始字节；无静默截断。
4. plan confirm/discard 在 POST 前完成真实 GET revision preflight，冲突时不发写请求。
5. clientRequestId、CAS revision、枚举、列表唯一性和未知字段校验均有负向测试。
6. watcher 覆盖完成、失败、被替代、不可达超时和 Ctrl-C，不取消远端任务。
7. CLI API 客户端的二进制下载仍只允许 `/api/v1/**`，认证 Cookie 不进入输出或错误。
8. `tools/inkforge-cli` 全量测试、Ruff、Mypy、根级架构测试和 `git diff --check` 通过。

## 10. 实施验证

- 21 个 `long.video.*` 命令已注册，覆盖项目、素材、章节改编、镜头候选、分集、视觉设定、
  逐镜参考和提示词主链；README 命令清单与注册表精确一致。
- 完整 JSON/UTF-8 文件输入、原始二进制上传下载、路径编码、幂等字段、双 revision preflight、
  CAS、枚举和列表唯一性均有正向与负向测试。
- watcher 已验证成功、失败、任务被替代、Core 连续不可达和 Ctrl-C；只停止本地观察，不取消任务。
- CLI 与架构测试共 632 项通过；全仓 Ruff 通过，Core、Agent、共享包和 CLI 共 287 个 Mypy
  源文件通过，`git diff --check` 通过。
- 本轮没有修改公共 API、共享契约、生成客户端或数据库结构，也没有访问开发库或正式库。
