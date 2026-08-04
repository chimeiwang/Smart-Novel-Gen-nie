# 中短篇正文来源大纲显式重绑定规格

## 目标

允许作者通过现有中短篇版本预览与人工提交接口，显式声明“当前正文已经按当前大纲完成校订”，并在正文内容不变时创建一个更高版本号的新正文版本，将 `sourceOutlineVersionId` 绑定到当前已应用的大纲版本。

该能力首先用于把《无年之灾》当前正文 v8 的来源大纲从 v2 修正为当前大纲 v4，同时保留 v8 及更早版本的原始审计记录。

## 非目标

- 不原地修改任何既有版本的 payload、内容、Diff、版本号或来源字段。
- 不因大纲版本变化而自动重绑定正文；未显式请求时，人工正文版本继续继承基础正文版本的来源大纲。
- 不推断正文是否真正落实了新大纲，也不让 Agent 自动完成溯源声明。
- 不修改 PostgreSQL schema，不新增表、字段、迁移或自动建表逻辑。
- 不新增独立的重绑定路由，不修改 Agent Service、LangGraph 或 ReviewArtifact 状态机。
- 本次不增加 Web 操作入口；先由现有 CLI 通过公共 Core API 执行显式重绑定。

## 当前事实与根因

- 中短篇版本内容和来源字段保存在不可变 ReviewArtifact payload 中，已创建版本不能原地改写。
- 当前人工正文提交始终继承基础正文版本的 `sourceOutlineVersionId`。
- 当前正文工作稿与当前正文版本内容相同时，人工提交直接返回当前版本，不创建新版本。
- 当前预览的 `confirmationHash` 只绑定文档、章节、基础版本、工作稿内容 hash、目标版本和文本 Diff，不绑定目标来源大纲。
- 因此，正文内容不变时无法通过现有正式流程修正来源大纲；直接改数据库会破坏不可变版本和确认审计边界。

本规格只为显式溯源修正增加一个受确认保护的例外，不改变“默认人工编辑不能冒充基于新大纲”的既有规则。

## 设计

### 1. 复用现有预览与提交接口

继续使用：

```text
POST /api/v1/novels/{novelId}/versions/preview
POST /api/v1/novels/{novelId}/versions
```

`VersionPreviewRequest` 和 `ManualVersionRequest` 增加可选字段：

```text
sourceOutlineVersionId: string | null
```

字段语义：

- 大纲请求不允许携带该字段的非空值。
- 正文请求省略或传 `null` 时，保持现有行为：首个正文版本绑定当前已应用大纲，后续正文版本继承基础正文版本的来源大纲。
- 正文请求传入非空值时，表示作者显式要求把新正文版本绑定到该大纲。
- 首轮只允许该值等于同一作品当前已应用大纲版本 ID；目标不是当前大纲、不是已应用版本或不属于当前作品时返回 409。

不新增专用重绑定接口，避免把人工版本创建、版本号分配、工作稿校验、幂等和确认逻辑复制到第二条写路径。

### 2. 预览同时表达内容变化和溯源变化

`VersionPreviewResponse` 增加：

```text
currentSourceOutlineVersionId: string | null
targetSourceOutlineVersionId: string | null
sourceOutlineChanged: boolean
contentChanged: boolean
```

兼容规则：

- `contentChanged` 只表示正文或大纲文本是否变化。
- `sourceOutlineChanged` 只表示正文来源大纲是否变化；大纲文档固定为 `false`。
- 现有 `dirty` 改为“存在可提交变化”，即 `contentChanged || sourceOutlineChanged`，字段继续保留。
- 仅溯源变化时，文本 Diff 的 `blocks` 为空、字数变化为 0，但确认摘要必须明确显示来源大纲 ID 的变化，不能显示“没有可提交的变化”。
- 内容和溯源同时变化时，确认摘要同时说明字数变化与来源大纲变化。

版本详情和版本列表已经返回 `sourceOutlineVersionId`，无需新增第二套展示字段。

### 3. 确认哈希覆盖目标来源大纲

人工版本预览和提交重新计算确认哈希时，把解析后的 `targetSourceOutlineVersionId` 加入规范化确认上下文。

确认上下文至少绑定：

```text
documentType
chapterId
baseVersionId
currentDraftHash
targetVersionId
targetSourceOutlineVersionId
diff
```

提交事务内重新读取当前正文版本、工作稿和当前已应用大纲并解析目标绑定。以下任一事实变化都使旧确认失效并返回冲突：

- 当前正文基础版本变化；
- 工作稿更新时间或内容 hash 变化；
- 当前已应用大纲版本变化；
- 请求中的目标来源大纲与预览不一致；
- 文本 Diff 变化。

候选采用和历史恢复已经由不可变目标版本 ID 绑定完整 payload，不开放来源大纲覆盖，保持现有语义。

### 4. 内容不变但溯源变化时创建新版本

人工提交在事务内分别判断 `contentChanged` 与 `sourceOutlineChanged`：

- 两者都为 `false`：返回当前版本，不增加版本号。
- 任一为 `true`：创建新的 `source=manual`、`status=applied` 版本。
- 仅溯源变化：新版本内容、内容 hash 和字数与基础正文完全一致，`baseVersionId` 指向当前正文版本，`sourceOutlineVersionId` 使用显式目标大纲；默认文本 Diff 为空。
- 内容和溯源同时变化：同一个新版本同时记录新内容与显式目标大纲。

旧正文版本保持不变。新版本成为当前正文版本，但正文工作稿内容不需要发生写入变化。

### 5. 幂等与并发

- `clientRequestId` 继续作为人工提交的幂等键；首次仅溯源提交成功后，原请求重放返回同一个新版本。
- 同一基础正文并发提交时，只允许第一个成功；后续请求因基础版本过期返回 409。
- 显式目标大纲在预览后被新的大纲版本取代时，提交返回 409，不能静默改绑到更新的大纲。
- 显式目标已经等于基础正文来源且内容不变时，不创建重复版本。
- 任何失败都不能部分修改工作稿、历史版本或当前版本判定。

### 6. CLI 操作流程

现有 CLI 会把非本地字段透传给公共 API，不增加新命令。操作顺序保持：

1. `auth.whoami` 确认身份。
2. `short.pull` 获取干净快照和当前版本。
3. `short.version.preview` 携带当前正文 `baseVersionId`、`chapterId` 和目标 `sourceOutlineVersionId`。
4. 向用户展示文本 Diff、字数变化、当前/目标来源大纲及 `confirmationHash`。
5. 用户确认同一哈希后，`short.version.submit` 使用相同目标来源大纲和摘要提交。
6. 重新拉取并核对新版本、内容 hash 和 `sourceOutlineVersionId`。

CLI 的本地 manifest 门禁、完整文件 hash 校验和网络不确定时的稳定 `clientRequestId` 规则保持不变。

## 错误语义

- 大纲请求携带非空 `sourceOutlineVersionId`：422，请求契约错误。
- 正文显式目标不存在、不属于当前作品、不是已应用版本或不是当前大纲：409，来源大纲冲突。
- 预览后当前大纲变化：409，要求重新拉取和重新预览。
- 正文基础版本、工作稿时间或工作稿 hash 变化：沿用现有 409 错误。
- 确认哈希未覆盖当前目标来源大纲：409，确认摘要过期。

## 影响范围

### Core API

- 扩展中短篇版本预览和人工提交请求、响应契约。
- 在版本服务中集中解析并校验目标来源大纲。
- 扩展人工提交的确认哈希上下文和“是否存在可提交变化”判断。
- 不修改数据库仓储结构，只复用当前大纲版本查询和既有文档事务。

### 生成客户端与 CLI

- 重新生成 TypeScript API 客户端并执行契约一致性检查。
- CLI 不增加命令，只补充请求透传与响应字段的测试。

### 文档

- 实现完成后同步更新 `docs/requirements/04-review-quality-and-workflow.md` 中的中短篇不可变版本规则。
- 更新原中短篇工作流规格的人工版本例外：只有显式、已确认的重绑定请求可以创建内容不变的新版本。

## 测试要求

- 预览仅溯源变化时，`dirty=true`、`contentChanged=false`、`sourceOutlineChanged=true`、文本 Diff 为空且确认摘要明确。
- 使用同一确认哈希提交后，创建更高版本号的正文版本；内容 hash 不变，来源大纲更新，基础版本和历史版本不变。
- 未携带目标来源大纲且内容不变时，仍返回当前版本，不增加版本号。
- 显式目标与基础正文来源相同且内容不变时，不增加版本号。
- 内容变化但未显式重绑定时，仍继承基础正文来源大纲。
- 内容变化并显式重绑定时，新版本同时保存新内容和目标大纲。
- 大纲文档携带非空目标来源字段时被拒绝。
- 非当前、未应用、跨作品或不存在的目标大纲被拒绝。
- 预览后当前大纲变化会使提交失败，旧确认哈希不能复用。
- 仅改变目标来源大纲会改变 `confirmationHash`。
- 相同 `clientRequestId` 重放返回第一次创建的版本，不重复增加版本号。
- 相关 Core API/service pytest、CLI pytest、Ruff、Mypy、`npm run api:generate` 和 `npm run api:check` 通过。

## 《无年之灾》数据修正验收

- 大纲当前版本保持 v4：`cmsdbw40s6n2royakxqpmd2jq`。
- 正文 v8：`cmsdbxfqk6n2toyaknu4awreg` 保持不可变，仍记录原来源大纲 v2。
- 用户确认仅溯源预览哈希后，创建正文 v9，`baseVersionId` 指向 v8，`sourceOutlineVersionId` 指向大纲 v4。
- v9 正文内容 hash 仍为 `6bfb53700b06849deb5ecd8b9cf3fe7030fcb636c81fa032f1e3bbcc7a0c8b0f`，字数仍为 17831。
- 最终重新拉取时，当前正文文件与 v9 内容逐字节一致，结尾咒语和四句正文不变。
