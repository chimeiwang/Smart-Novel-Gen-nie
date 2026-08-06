# 长篇创作资料 CLI 安全写入规格

## 状态

- 日期：2026-08-06
- 状态：方案已确认，待实施
- 适用范围：`long_serial` 长篇小说、公共 Core API、`inkforge-cli` 与生产操作 Skill
- 用户确认：采用“完整补齐安全写契约”方案

## 背景

生产长篇 CLI 当前只能读取规划、设定和资源。Core API 已经存在大部分创作资料写接口，但除大纲正文
外普遍缺少版本前置条件；创建接口没有稳定幂等身份。直接把现有接口加入 CLI 会产生三类风险：

1. 浏览器、CLI 或其他任务并发修改时，旧内容能够静默覆盖新内容。
2. 创建请求在网络结果不确定后重试，可能产生重复实体。
3. 多项清理部分成功后，调用方无法仅凭本地状态判断权威结果。

此外，故事背景、世界设定、作品圣经和剧情进度等单例资源使用冲突更新时，没有显式推进
`updatedAt`；在修复前不能把该字段作为有效 CAS 版本。

## 目标

1. 为长篇创作资料提供完整、无状态、可恢复的 CLI 写能力。
2. 更新和删除使用服务端 CAS，创建使用稳定请求身份防止重复实体。
3. 继续只访问 `/api/v1/**`，由 Core 负责认证、归属、引用、事务和删除影响。
4. 保持长文本、结构化字段和错误详情完整，不引入截断或本地业务镜像。
5. 生产 Skill 使用精确白名单、写前完整 Diff、明确确认和写后权威回拉。
6. 不修改 PostgreSQL schema，不增加迁移或自动建表行为。

## 明确范围

### 单例资料

- 故事背景
- 世界设定
- 作品圣经
- 故事进展
- 剧情进度

### 设定实体

- 角色
- 地点
- 势力
- 物品
- 术语
- 人物关系
- 人物经历

### 写作素材

- 参考资料的创建、更新、删除和重新索引
- 为小说应用或清除已有文风

## 非目标

- 大纲正文和大纲节点
- 伏笔
- 章节、章节进展、章节状态和章节排序
- 用户级文风库的创建、删除、文件上传、画像生成和分节编辑
- 跨小说批量复制、全量覆盖、导入导出或自动 ID 重映射
- Agent Service 工具、内部接口和数据库直连
- PostgreSQL schema、迁移 SQL 和 `schema-contract.json`

## 命令面

所有命令均为 `inputMode=json`、`outputMode=json`、`mutation=true`、`requiresIdentity=true`，不接受
`outputFile`。八条创建命令要求调用方提供稳定 `clientRequestId`；CLI 不临时生成该值。重新索引使用
`referenceId + expectedContentHash` 作为现有确定性任务身份。

### 单例资料命令

```text
long.lore.story-background.save
long.lore.world-setting.save
long.lore.writing-bible.save
long.lore.story-progress.save
long.plot-progress.save
```

### 实体命令

```text
long.lore.character.create
long.lore.character.update
long.lore.character.delete
long.lore.location.create
long.lore.location.update
long.lore.location.delete
long.lore.faction.create
long.lore.faction.update
long.lore.faction.delete
long.lore.item.create
long.lore.item.update
long.lore.item.delete
long.lore.glossary.create
long.lore.glossary.update
long.lore.glossary.delete
long.lore.relation.create
long.lore.relation.update
long.lore.relation.delete
long.lore.experience.create
long.lore.experience.update
long.lore.experience.delete
```

### 素材命令

```text
long.reference.create
long.reference.update
long.reference.delete
long.reference.reindex
long.style.apply
long.style.clear
```

本规格合计新增 32 条长篇写命令。生产 policy 必须逐条列出，禁止 `long.*`、`long.lore.*` 或其他
通配授权。

## Core 公共契约

### 版本字段

1. 单例保存请求必须携带 `expectedUpdatedAt`。资源尚不存在时显式传 `null`；已存在时传完整 UTC
   时间戳。
2. 实体、关系、经历和参考资料更新、删除必须携带非空 `expectedUpdatedAt`。
3. Core 在事务内锁定目标、比较版本并执行写入。版本不匹配返回 HTTP 409 和稳定业务码，不修改数据。
4. 实际内容相同视为幂等成功，不推进 `updatedAt`；实际内容变化必须显式把 `updatedAt` 推进到当前时间。
5. `story-progress` 当前存放在 `Novel`，其 CAS 暂时使用 `Novel.updatedAt`；因此其他小说元数据变化可能导致
   保守冲突。CLI 遇到冲突重新读取，不自动换版本覆盖。
6. 文风应用不使用时间戳，而使用 `expectedStyleId` 与当前应用值比较；目标值已经相同视为幂等成功。

稳定冲突码如下：

```text
LORE_CONTENT_VERSION_CONFLICT
LORE_ENTITY_VERSION_CONFLICT
LORE_RELATION_VERSION_CONFLICT
LORE_EXPERIENCE_VERSION_CONFLICT
PLOT_PROGRESS_VERSION_CONFLICT
REFERENCE_VERSION_CONFLICT
APPLIED_STYLE_VERSION_CONFLICT
RESOURCE_CREATE_CONFLICT
```

### 创建幂等

创建请求携带 `clientRequestId`。Core 使用 `userId + novelId + resourceKind + clientRequestId` 生成稳定资源
ID，并在小说级事务锁内处理：

1. 目标 ID 不存在：验证归属和引用后创建。
2. 目标 ID 已存在且当前创建字段与请求一致：返回现有资源和 `effective=false`，不重复创建。
3. 目标 ID 已存在但字段不一致：返回 `409 RESOURCE_CREATE_CONFLICT`。
4. 同一 `clientRequestId` 被用于不同小说或不同资源类型时，各命名空间互不冲突；同一命名空间内不得
   更换请求内容重放。

该设计以正式资源行承担稳定身份，不新增命令账本或数据库字段。资源后来被更新时，旧创建请求重放会
安全冲突而不是覆盖当前内容；资源明确删除后，同一创建身份再次调用具有重新创建该资源的 PUT 语义。

### 单例资料

- 修复故事背景、世界设定、作品圣经和剧情进度冲突更新不推进 `updatedAt` 的问题。
- 作品圣经继续允许字段级更新，但请求至少包含一个业务字段。
- `long.lore.writing-bible.save` 不允许把目标作品的 `storyLengthProfile` 改为 `short_medium`；若请求包含
  该字段，只接受 `long_serial`。
- 故事背景和世界设定不允许 `content=null`；故事进展沿用现有可空语义。
- 剧情进度对应 `PlotProgress` 的四个结构化字段，不等同于故事进展长文本。

### 删除影响

CLI 删除不是级联清理入口。Core 在事务中检查引用，并按以下规则处理：

- 角色仍有人物关系、人物经历或物品持有引用时拒绝删除。
- 地点仍有子地点或被势力作为驻地引用时拒绝删除。
- 势力仍被角色引用时拒绝删除。
- 人物关系和人物经历只删除目标记录。
- 参考资料删除目标资料、对应 RAG 文档与分块；响应明确报告这些影响。
- 物品和术语没有下游引用时只删除目标记录。

删除冲突返回 HTTP 409 和具体引用计数。生产 Skill 必须在用户确认前展示完整目标和服务端报告的删除
影响，不能以数据库外键的隐式行为代替说明。

### 参考资料

- `create` 和 `update` 支持 `content`/`contentFile` 二选一，按完整 UTF-8 读取。
- 更新和删除使用 `expectedUpdatedAt`。
- `reindex` 要求 `expectedContentHash`；内容 hash 不匹配时拒绝启动。
- Core 复用现有 `referenceId + expectedContentHash` 确定性索引任务身份；完全相同的请求返回同一任务，
  不重复入队。资料内容变化后必须先取得新的 `contentHash`，不能用旧 hash 启动索引。
- 资料事务提交成功只表示正式资料已保存，不代表 RAG 已 ready。CLI 返回 `ragStatus`，生产流程继续通过
  `long.resources.get` 观察到 `ready` 或 `failed`；pending 状态不得表述为索引成功。

### 文风应用

- `long.style.apply` 请求包含 `novelId`、`styleId` 与 `expectedStyleId`。
- `long.style.clear` 请求包含 `novelId` 与 `expectedStyleId`，目标值固定为 `null`。
- Core 继续校验文风属于当前用户且画像完整。
- 本规格不允许创建、修改或删除用户级文风资产。

## CLI 输入规则

1. 每条命令精确拒绝未知字段；`profile` 是唯一通用本地字段，不发送给 Core。
2. 所有 ID 进入 URL 前编码，只允许调用 `/api/v1/**`。
3. 故事背景、世界设定和故事进展使用 `content`/`contentFile` 严格二选一。
4. 作品圣经、剧情进度和实体字段放在 `data` 对象中；CLI 按资源类型验证字段白名单。
5. 实体创建要求 `novelId + clientRequestId + data`；更新要求
   `novelId + <resourceId> + expectedUpdatedAt + data`；删除要求
   `novelId + <resourceId> + expectedUpdatedAt`。
6. 更新的 `data` 至少包含一个字段；需要清空的可空字段必须显式传 `null`。
7. 写命令不保存本地镜像，不接受服务端内容输出文件，也不根据本地文件 mtime 或 hash 判断权限。
8. 409 保留 Core 的 `code`、`message`、`details` 与 `requestId`，映射退出码 4；本地输入错误返回 2，
   文件错误返回 6，传输或远端失败返回 5。

## Web 兼容与生成客户端

公共请求契约增加 CAS 后，现有 Web 写入调用必须同步携带最后一次 GET 返回的版本；不能把 CAS 设计成
仅 CLI 使用的旁路参数。前端收到 409 时保留本地编辑值并提示刷新，不自动覆盖服务端内容。

公共 FastAPI/Pydantic 契约修改后重新运行：

```text
npm run api:generate
npm run api:check
```

禁止手写重复 TypeScript DTO。

## 生产 Skill 流程

1. 固定 `https://inkforge.cn`、`production` profile 和预期用户名；每个业务命令前继续执行
   `auth.whoami`。
2. 写前执行对应完整 GET，确认小说 ID、名称、资源 ID、当前版本和当前完整内容。
3. 展示完整旧值、新值、删除影响与 Diff；用户确认只授权本次具体变化。
4. 使用读取到的版本执行一次写命令。409 时停止并重新展示新 Diff，不自动换 `expectedUpdatedAt`。
5. 网络结果不确定时先回拉；创建只允许使用原 `clientRequestId` 与完全相同的请求重放，重新索引只
   允许使用原 `referenceId + expectedContentHash` 重放。
6. 写后通过 `long.planning.get`、`long.lore.get` 或 `long.resources.get` 完整回拉并逐字段核对。
7. Skill 不使用 SSH、数据库、内部接口、自制 HTTP 或浏览器 UI 绕过公共 CLI。

## 实施切片

按以下顺序实施，每个切片先写失败测试再写实现：

1. Core 公共 CAS 基础设施和单例资料。
2. 五类设定实体、人物关系和人物经历。
3. 参考资料与文风应用。
4. CLI handler、registry、README 与错误映射。
5. Web 调用方与生成客户端同步。
6. 生产 Skill、精确 allowlist、离线测试和生产只读冒烟。

不得只实现当前《遗产猎人（迁移）》需要的五条更新命令后宣称本规格完成。

## 测试要求

### Core API

- 单例首次创建、相同内容幂等、正确版本更新、过期版本 409、并发同版本只有一个有效写入。
- 创建请求首次成功、相同请求重放不重复、相同身份不同内容冲突。
- 五类实体、关系、经历和参考资料的更新/删除 CAS。
- 小说归属、跨小说引用、地点循环、长篇作品圣经篇幅守卫。
- 删除影响与引用计数，不发生未说明的级联删除。
- 参考资料正式保存与 RAG 异步状态严格区分。
- 文风 apply/clear 的 expectedStyleId、归属和画像完整性。
- PostgreSQL schema 指纹保持不变。

### CLI

- 32 条命令的精确 route、method、query/body 和注册元数据。
- 未知字段、缺失版本、空 patch、错误资源字段、ID 编码和本地字段不外发。
- `content`/`contentFile` 二选一；大 UTF-8、CRLF、组合字符、emoji 和尾部换行完整保留。
- 409/422/传输失败和文件失败的退出码及完整错误透传。
- registry、README、Core OpenAPI 和生产 allowlist 的命令集合一致。
- 明确断言大纲、伏笔、章节和用户级文风管理命令不因本规格被新增。

### Web 与静态检查

- 现有创作资料保存流程携带 CAS，冲突时不丢本地内容。
- 相关前端测试、`npm run typecheck`、`npm run lint`。
- Core 相关 pytest、CLI pytest、Ruff；公共契约和共享边界变化时运行 Mypy。
- `npm run api:generate` 后 `npm run api:check` 无漂移。

### 生产 Skill

- allowlist 无通配、无重复，只增加本规格的 32 条命令。
- 固定 HTTPS、production profile、预期用户名和逐命令身份预检。
- 未确认删除、过期版本、网络结果不确定和 RAG pending 的恢复路径。
- Skill 快速校验和 PowerShell 离线测试通过。

## 验收标准

1. 32 条命令全部注册并通过 CLI、Core、Web 和生产 Skill 契约测试。
2. 所有正式更新和删除都有服务端版本前置条件，不存在 CLI 静默覆盖路径。
3. 所有创建在相同稳定请求重放时不产生重复资源。
4. 删除不会产生未说明的级联影响。
5. CLI 不维护本地业务权威状态，不访问数据库、内部接口或非 `/api/v1/**` 路径。
6. 大纲、伏笔、章节和用户级文风库保持原有命令边界。
7. 数据库 schema 指纹保持不变。
8. 部署和生产验证必须分别报告；代码提交、CI 触发或部署开始都不等于线上能力已经可用。
