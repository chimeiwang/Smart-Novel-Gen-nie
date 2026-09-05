# InkForge CLI

这个 CLI 给本机 Codex 和作者提供中短篇工作室与长篇服务端控制台的公开接口。它绕过 Web UI，
但不绕过 Core API 登录、作品归属、并发控制、ReviewArtifact、Diff 确认或版本状态机。

## 当前入口与本地启动

本文件保留完整 125 命令的共享契约。macOS 本地与生产两份 Operator Skill 已完成实际入口切换及离线验收，
执行链为 `scripts/run.sh → Java Operator → Java CLI → Core 公共 API`；新版 Skill 不再运行
Python 或 uv。构建、安装及真实 Skill 入口见 `tools/inkforge-cli-java/README.md`，本次切换规格见
`docs/specs/2026-09-04-java-cli-operator-cutover.md`。

Java CLI 实现同一注册表中的 125 个命令。它从冻结公共 OpenAPI 生成并编译客户端契约，但发行包只携带独立
CLI 运行时，不依赖 Spring Core、数据库驱动或 Agent。直接 CLI 的构建和本地运行方式如下：

```bash
export JAVA_HOME=/opt/homebrew/opt/openjdk@21/libexec/openjdk.jdk/Contents/Home
export PATH="$JAVA_HOME/bin:$PATH"
./mvnw -pl tools/inkforge-cli-java clean package
java -jar tools/inkforge-cli-java/target/inkforge-cli.jar auth.login \
  --origin http://127.0.0.1:8000 \
  --username <用户名>
printf '{}\n' | java -jar tools/inkforge-cli-java/target/inkforge-cli.jar auth.whoami
```

`auth.login` 是唯一交互命令。密码只从真实 TTY 隐藏读取；Java CLI 在 macOS 只使用 Keychain，在 Windows
只使用 Credential Manager；其他系统明确失败，不会把 Cookie 降级写入普通文件，也不把凭据写入仓库、
stdout 或日志。配置路径与旧 CLI 相同，迁移沿用原 profile/origin 对应的凭据，不要求重新登录。
系统若要求 Java 访问旧 Keychain 项，由用户确认；本次未读取真实 token，未宣称真实会话验收完成。
远程 Core 默认只允许 HTTPS，本地 HTTP 只允许回环地址。

Python CLI 源码与测试继续保留为契约对照，不作为新版 macOS Skill 的业务入口。尚未覆盖的逐命令成功分支、
真实账号端到端和 Windows 实机验收不能用本次 macOS 入口切换代替。新增 Operation 仍须通过 Python/Java
同契约与跨语言差异测试；Skill 的允许集合必须单独维护，不能自动开放底层 CLI 的全部能力。

除登录外，命令都从 stdin 读取一个 UTF-8 JSON 对象，stdout 返回 JSON；`short.agent.watch`、
`long.task.watch` 和 `long.video.adaptation.watch` 返回 JSONL。例如：

```bash
printf '{}\n' | java -jar tools/inkforge-cli-java/target/inkforge-cli.jar auth.whoami
printf '{}\n' | java -jar tools/inkforge-cli-java/target/inkforge-cli.jar short.list
printf '{}\n' | java -jar tools/inkforge-cli-java/target/inkforge-cli.jar long.novel.list
```

## 中短篇写作边界

- `short.pull` 导出完整 `outline.md`、`manuscript.txt` 和 manifest。
- `short.draft.save` 只保存可编辑工作稿，不创建版本。
- `short.version.submit`、`short.version.adopt`、`short.version.restore` 必须先取得完整 Diff，并
  提交用户确认过的同一 `confirmationHash`。
- Agent 只接受 `outline`、`manuscript`、`selection`、`full_check` 四种操作。文档操作只产生
  候选版本，不自动采用；全文检查只产生报告。
- 启动 Agent、提交、采用和恢复都必须携带 `short.pull` 生成的 `manifestPath`；本地快照
  dirty 时 CLI 直接拒绝。选区修改只发送权威基础版本、Unicode 码点范围和选区哈希，正文由
  Core 读取。

Codex 的完整操作规程位于用户安装的 `inkforge-short-story-operator` 与
`inkforge-production-short-story-operator` Skill；macOS 使用各自的 `scripts/run.sh`，不是以上裸 CLI 示例。

### 中短篇 V2 观察补充（2026-09-05 源码）

`short.agent.start` 的四个别名、请求字段和中短篇 13 个命令不变。保留启动返回的 runId，以
`short.agent.watch` 输入 `{"taskId":"<runId>"}` 观察；可选 lastEventId 仍是字符串。
watcher 保留 V1 phase/commandStatus 兼容；显式 engineVersion=2 时只认 V2 status，不从旧字段猜结果。

V2 `run_snapshot.baseSequence`（包括 0）与数字事件 ID 用作重连游标，事件只供观察；断线或终态事件后
必须 GET 同一 Run。最后的 `type=terminal,data` 是该 GET 的完整原对象：completed 退出码 0，failed/cancelled
退出码 5。V1 仍保留原“终态观察成功返回 0”契约，须同时看 phase/commandStatus，不能把退出 0 一概当成生成成功。

生成蓝图、正文或替换选区后，从 terminal.data.candidateVersionId 读取精确候选，接着使用现有
short.version.get/preview/adopt 查看完整版本和 Diff、确认 confirmationHash；Run completed 不表示版本已采用。
全文检查从 terminal.data.checkReport.text 读取完整报告，不创建候选、不调用 adopt；首尾空格、换行和 Unicode
原样保留。缺少对应结果、引擎类型错误或任务身份不匹配时以 CORE_RESPONSE_CONTRACT_ERROR/5 停止，不能选
版本列表最后一项或从 SSE resultId 拼造结果。停止 watcher 不取消服务端任务，未新增 short.agent.cancel；
既有版本下载和 outputFile 的完整 UTF-8 文件语义不变。

中短篇四项已完成仓内接线、全仓门禁与本地独立 Core/Agent、受控 Fake Provider 验收，当时 Catalog 为 16/21；
一致性终检阶段达到 17/21，当前加入文风画像后为 18/21，剩余 RAG 索引和两个开发视频操作共三项尚未迁移。
文风画像全仓与隔离跨进程验证通过，结果见其规格最终记录。真实供应商和生产尚未验收，固定 JAR、活动
Skills 和服务器未随源码更新。后续 Skill 说明更新见 `docs/specs/2026-09-01-durable-agent-v2-operator-skill-update.md`
的“中短篇四操作观察”专节，完整验收见中短篇迁移规格。普通 CLI 125、Operator 45 命令及三种长篇操作范围不变。

## 长篇写作边界

`long.agent.start` 的 `rewrite_chapter_selection`/`rewrite_outline_selection` 必须携带 `selectionTarget`（资源身份、`baseUpdatedAt`、正文 hash、Unicode 码点范围和选区 hash）。CLI 不接受 `selectedText`，也不把选区正文作为权威输入；正文由 Core 按来源绑定冻结。选区操作仍走 proposal → ReviewArtifact → 用户确认 → Core 应用。

`long.agent.start` 的 `answer_question` 只接受同一个 `chapterId` 的 chapter target/scope，并要求非空
`writingSessionId`、稳定 `clientRequestId` 和包含非空白字符的完整 `userInstruction`。它不创建
ReviewArtifact；`long.task.watch` 返回 V2 `completed` 后，使用 `long.session.get` 回读该会话中的权威
Agent 消息，不能把 SSE 或任务状态拼成回答。问答的 `writingSessionId` 缺失、为 `null`、为空字符串或
使用非字符串类型时，两种 CLI 都在业务 POST 前以 `WRITING_SESSION_REQUIRED` 和退出码 2 拒绝。
这只是底层 CLI 契约：两份 Operator Skill 目前仍只允许 `plan_chapter`、`write_chapter`、`review_chapter`，
不会因更换 Java 入口而开放 `answer_question` 或选区改写。

`long.artifact.approve` 对选区 Artifact 使用 `editedReplacement` 或 `editedReplacementFile`，对全文草案继续使用 `editedContent`。每次决定前先 GET Artifact 并查看完整 Diff，独立确认后提交稳定幂等请求，完成后再次 GET 回读；CLI 会执行 sourceBinding preflight 并拒绝错误的全文/选区编辑字段。

当前源码候选另支持 V2 `agent_updates` 部分采用：只有精确 GET 的详情同时为
`sourceBindingStatus=verified`、顶层和 payload 的 `kind=agent_updates`，且 `payload.updates` 为对象时，
`long.artifact.approve` 才原样透传输入中已有的 `selectedUpdateRefs`。省略、显式 `null`、空数组和非空
`section/index` 数组不会在 CLI 内互相改写；结构化资料候选不接受正文或 replacement 编辑字段，其他 V2 候选及
revise/discard 保持既有拒绝规则。这组 kind/updates 条件只决定结构化选择字段能否透传：非 null 选择不满足条件时
拒绝且不 POST；省略选择字段或其他 V2 候选沿既有语义忽略显式 null 时，不会因此新增 Artifact 类型门禁。
Core 按精确 revision 和冻结来源在同一事务采用，冲突后必须重新读取并确认。
这没有增加 125 个普通 CLI 命令，也没有扩大 45 命令/三 Operation 的 Operator 范围。五项结构化资料入口、
自动返工及作者采用已接通，该阶段使仓内 Catalog 达到 12/21，随后中短篇四项与一致性终检达到 17/21，
当前加入文风画像后为 18/21；结构化资料定向验证
与全量门禁见对应规格最终记录。
源码、构建产物与固定包分别验收，本批没有更新固定 JAR、活动 Skills 或部署服务器。

一致性终检继续使用原 `long.quality.run/get/skip/reset`，不新增命令或直接访问 Agent。原可选 `taskId` 兼容
同归属 V1 写作任务与 V2 写作 Run；受理响应的 `taskId` 是质量 Run，结果按原 `checkId` 回读，不改用写作 watcher。
`qualityGate=revise` 是完成报告，不触发自动返工；一次格式纠正由 Core 安排，CLI 不重复启动。
本 Python 实现仅作契约对照，活动入口仍为 Java。Skills 更新说明见
`docs/specs/2026-09-01-durable-agent-v2-operator-skill-update.md` 的“一致性终检迁移说明”，
具体实现和验收见 `docs/specs/2026-09-05-durable-consistency-quality.md`。

文风画像迁移不改变 `long.style.apply/clear` 的参数、输出和确认规则，也不新增画像创建、上传、编辑或
删除命令。`style.portrait` 是 Core 原文风接口的内部执行操作，不能作为 `long.agent.start` 的 operation；
画像任务也不改用长篇写作 watcher。新 V2 按用户级无小说 Run 冻结完整参考，整套五节或目标单节输出纯文本，
由 Core 沿原业务直接物化 WritingStyle；原 V1 任务保留，新 V2 不造旧任务影子行。Agent/Core、全仓及隔离
独立进程验证通过。完整行为及验收见
[文风画像迁移规格](../../docs/specs/2026-09-05-durable-style-portrait.md)，后续 Skills 更新说明见
[Operator Skill 更新文档](../../docs/specs/2026-09-01-durable-agent-v2-operator-skill-update.md)。
本轮源码修改不表示固定 JAR、活动 Skills 或服务器已经更新。

### 结构化资料的显式启动（当前源码）

本批为 `long.agent.start` 补接五项已有业务，并补回此前遗漏的 `rewrite_scene` 显式白名单，合计新增
6 个可选 operation 值；不是新增 6 个命令。命令总数仍为 125，不新增参数或公共 target 类型。

| operation | scope |
| --- | --- |
| `create_lore`、`revise_lore`、`create_outline` | `{"kind":"novel"}` |
| `revise_outline` | novel，或 `{"kind":"outline_node","outlineNodeId":"节点ID"}` |
| `manage_foreshadowing` | novel，或 `{"kind":"chapter","chapterId":"当前章节ID"}` |
| `rewrite_scene` | `{"kind":"chapter","chapterId":"当前章节ID"}`，沿用原整章候选语义 |

所有请求仍需 `chapterId` 和 `target={"type":"chapter","id":"同一章节ID"}`。节点归属由 Core 核对；
章节范围必须等于当前章。五项不携带 `selectionTarget`，`writingSessionId` 可省略或为 null；原问答仍要求会话。
结构化 scope 表示任务焦点，不按操作名限制候选更新分区或 create/update/delete，也不自动采用结果。

普通 CLI 的输入示例（不是受限 Operator Skill 的可调用示例）：

```json
{"clientRequestId":"structured-start-20260905-0001","novelId":"novel-id","chapterId":"chapter-id","operation":"revise_outline","target":{"type":"chapter","id":"chapter-id"},"scope":{"kind":"outline_node","outlineNodeId":"node-id"},"userInstruction":"保留已有主线，调整这个节点中的行动顺序。"}
```

CLI 仍只 POST Core `/api/v1/writing/runs`；Core 命中 V2 后才由新执行链生成候选、复审与等待确认，
受理不等于完成。五项已在仓内启用，最多一次自动完整返工后仍须作者确认；隔离接线及后续完整验收以
`docs/specs/2026-09-05-durable-structured-agent-updates.md` 为准。两份 Operator 仍只允许原三操作，
这 6 个新增可选值均不自动开放；固定 JAR、活动 Skills 和服务器未随此次源码修改更新。

2026-09-05 的 V2 `review_chapter` 保持显式 start 可省略 writingSessionId；完成后
`long.task.get/watch` 直接返回完整 reviewReport，不要求额外会话查询或 Artifact 决定。指定 outputFile 时
保存完整 JSON。`rewrite_scene` 仍生成整章候选，批准使用 editedContent/editedContentFile；
`rewrite_outline_selection` 只生成总纲/节点选区 replacement，批准只用 editedReplacement/editedReplacementFile。
自然入口新增审阅和场景改写，大纲选区须显式绑定来源。命令数 125 不变，活动 Operator 允许范围不变；
实现与验收状态见 `docs/specs/2026-09-05-durable-review-and-rewrites.md`，Skills 更新清单见
`docs/specs/2026-09-01-durable-agent-v2-operator-skill-update.md`。仓内更新尚未安装为本机新固定 JAR。

- 长篇命令只通过 `/api/v1/**` 访问 Core，不连接数据库、Agent Service 或内部接口。
- 小说、章节、任务、草案和质量状态始终以 Core 为权威；CLI 不创建 manifest、dirty 标志、本地章节
  镜像或任务账本。
- `long.novel.list` 固定查询 `long_serial`；调用方不能覆盖篇幅过滤条件。
- `long.novel.create` 固定创建 `long_serial`，成功后返回新作品和首章 ID。该接口当前没有幂等键；
  网络结果不确定时先 list 定位候选，再回拉作品、规划和首章核对；无法唯一确认时停止，不能直接重试。
- `long.novel.summary.save` 只修改已有作品摘要。写前先用 `long.novel.get` 取得摘要和
  `updatedAt`，展示完整 Diff 并确认后携带 `expectedUpdatedAt` 写入，写后再次回读；遇到
  `NOVEL_VERSION_CONFLICT` 必须重新读取、重新确认，不能自动替换版本重试。
- 普通查询默认完整内联返回。显式提供 `outputFile` 时，章节正文写为原始 UTF-8 文本，其余查询写为
  完整 JSON；不会按大小自动截断或切换输出形式。
- 人工章节保存使用 `expectedUpdatedAt` 做并发检查。Agent 产物只能通过 ReviewArtifact 的
  approve、revise 或 discard 流程处理，不能直接写入正式内容。
- `long.task.watch` 按显式 `engineVersion` 分派：历史缺字段响应兼容 V1 并只读取 `outcome`；V2 只读取
  `status/activeSteps/artifact/error`，其中 `activeSteps` 必须存在且为数组，出现的 `artifact/error` 必须为
  `null` 或对象；显式类型错误时失败关闭。V2 支持数字 SSE cursor 和 `run_snapshot` 重连。停止 watcher 不会取消
  服务端任务；真正取消必须显式执行 `long.task.cancel`。
- 本规格列出的整份大纲正文、大纲节点、设定、参考资料和小说文风应用命令已实现；伏笔和用户级文风资产写入仍未开放。
  任何调用都不能用读接口或批量请求绕过幂等、CAS、Diff 确认和来源绑定门槛。

## 自然请求与澄清回答（当前分支）

Java CLI 与 Python 对照实现共用以下输入，不新增命令名。当前分支已接线并做定向回归，完整验收状态见
`docs/specs/2026-09-04-durable-natural-language-entry.md`；本轮未安装新 JAR、未更新真实 Skill、未部署服务器。
以下是通用 CLI 的 stdin JSON，不是受限 Operator Skill 的可用示例。

`long.agent.start` 新建自然请求；每条新消息使用新的稳定 `clientRequestId`，同一请求重试复用原值：

```json
{"inputMode":"natural","novelId":"novel-1","chapterId":"chapter-1","writingSessionId":"session-1","clientRequestId":"natural-request-0001","userInstruction":"请先规划这一章，再等我确认。","targetWordCount":4000}
```

自然分支要求非空会话和完整非空白指令，`targetWordCount` 可省略（默认 4000），提供时必须为
1～10000000 的整数。不能混入 `operation/target/scope/selectionTarget/selectedAgents/workflow`；CLI
负责补固定 `workflow=long_serial`。当前 Core 使用内部 resolver v3，从本次冻结的十项无选区授权中解析：
新建/修改设定、创建/修改大纲默认 novel scope；管理伏笔、章节问答、规划、正文、审阅、场景改写默认当前
chapter scope。明确节点或其他不匹配范围必须澄清或走显式入口，不由模型猜 ID/scope；两种选区仍显式提交
完整来源绑定。历史解析器和原三项/五项授权不扩大；CLI 不传提示词版本，原显式请求形状不变。

当 `long.task.watch` 读到 V2 等待澄清时，输出与草案等待明确不同的 JSONL 行：

```json
{"type":"waiting_user","taskId":"run-1","waitReason":"clarification","clarificationCode":"uncertain","decisionStepId":"decision-1","prompt":"你希望先规划，还是直接生成正文？","revision":3,"data":{"engineVersion":2,"runId":"run-1","taskId":"run-1","chapterId":"chapter-1","workflow":"long_serial","operation":null,"status":"waiting_user","activeSteps":[],"currentStep":null,"lastEventSequence":4,"revision":3,"artifact":null,"error":null,"clarification":{"clarificationCode":"uncertain","decisionStepId":"decision-1","prompt":"你希望先规划，还是直接生成正文？"},"commandId":null,"commandStatus":null}}
```

`data` 始终是完整权威快照，不是缩略摘要。此行不带 `artifactId`；旧草案 `waiting_user` 行保持原样。
澄清不能同时有 Artifact、活动 Step、错误或取消请求，畸形快照报 `CORE_RESPONSE_CONTRACT_ERROR`，不降级 V1。

`long.task.resume` 只有明确指定 `inputMode=clarification` 才调用新澄清端点，继续同一 Run：

```json
{"inputMode":"clarification","taskId":"run-1","clientRequestId":"clarify-request-0001","expectedRevision":3,"decisionStepId":"decision-1","userMessage":"先规划，保留最后的悬念。"}
```

`expectedRevision/decisionStepId` 必须来自最新快照，冲突后先回读，不猜版本、不自动改请求重试；最多两次回答由
Core 判断。问题、指令和回答都保留原始空格和换行。省略 `inputMode` 的 `long.task.resume` 仍是明确的旧 V1
恢复；它不回答 V2 澄清。草案继续修改仍使用 `long.artifact.revise`，不能混入澄清请求。Python Core 回滚镜像
分别以 409 `WORKFLOW_NATURAL_ENTRY_UNSUPPORTED` / `WORKFLOW_CLARIFICATION_UNSUPPORTED` 拒绝这两个新分支，
不会伪造 V2 运行状态。

两份 Operator 仍为 45 个命令、三种显式长篇 Operation；上述两个命令一旦出现 `inputMode`，新版仓内
Operator 以 `OPERATOR_INPUT_MODE_NOT_ALLOWED` / 退出码 2 拒绝，即使同时伪装为允许的 `plan_chapter`。
不要绕过 wrapper 调用裸 CLI；Skill 更新清单见 `docs/specs/2026-09-01-durable-agent-v2-operator-skill-update.md`。

## 长篇章节影视化边界

`long.video.*` 覆盖当前“章节 → 镜头候选 → 人工编辑确认 → 分集 → 视觉设定 → 逐镜提示词 →
关键帧 → 逐镜生成 → 候选 Take → 选片确认 → 分集粗剪 → 声音字幕 → 整集导出”主链，
不暴露已经被当前产品方案替代的旧 `VideoScene` 选区规划命令。所有命令只调用 Core
`/api/v1/video/**`，不连接 PostgreSQL、Agent Service 或内部接口。

典型顺序：

```text
long.video.project.create
long.video.adaptation.create
long.video.plan.start
long.video.adaptation.watch
long.video.adaptation.get
long.video.plan.confirm
long.video.episode.save
long.video.asset.upload
long.video.asset.rights
long.video.canon.candidate.set
long.video.canon.approve
long.video.reference.save
long.video.prompt.start
long.video.adaptation.watch
long.video.prompt.save
long.video.render.list
long.video.render.start
long.video.render.get
long.video.render.watch
long.video.render.retry
long.video.take.confirm
long.video.take.download
long.video.post.show
long.video.keyframe.set
long.video.edit.save
long.video.edit.get
long.video.mix.save
long.video.mix.get
long.video.export.start
long.video.export.watch
long.video.export.download
```

- `long.video.plan.confirm` 用 `plan` 或 `planFile` 提交完整编辑后候选；命令先回读 Artifact 与改编
  revision，冲突时不发确认请求。
- `long.video.prompt.save` 用 `currentPrompt` 或 `currentPromptFile` 保存完整提示词，不截断。
- `long.video.asset.upload` 保持文件原始字节；`long.video.asset.download` 必须显式指定
  `outputFile`，二进制不会写入 stdout。
- `long.video.asset.preview` 调用浏览器内联预览接口，但在 CLI 中仍把完整字节写入显式文件。
- `long.video.adaptation.watch` 轮询公共改编聚合，输出 JSONL；停止 watcher 不取消服务端任务。
- `long.video.render.watch` 轮询一条逐镜耐久任务，输出 JSONL；停止 watcher 不取消供应商任务。
- `long.video.render.retry` 精确复用旧任务的冻结输入，不自动采用后来修改的提示词或参考图。
- `long.video.take.download` 必须显式指定 `outputFile`，完整视频字节不会写入终端。
- `long.video.edit.save` 与 `long.video.mix.save` 分别用内联 `edit`/`mix` 或
  `editFile`/`mixFile` 读取完整 JSON，不能同时提供两种来源；可选 `basedOnVersionId`
  从历史版本创建可追溯分支，省略时默认基于当前 head。
- `long.video.export.watch` 轮询 Core 的耐久整集导出任务；停止 watcher 不取消服务端任务。
- `long.video.export.download` 必须显式指定 `outputFile`，MP4 二进制不会写入 stdout。
- 项目创建和素材上传的现有 API 没有幂等键。网络结果不确定时先 list/get 核对，不能盲目重试。
- 正式镜头、视觉设定版本和提示词仍分别需要用户显式确认。CLI 不提供自动批准整条流水线的命令。
- 生产环境当前关闭视频预览写入；CLI 不会绕过 `VIDEO_PREVIEW_ENABLED`。

各命令的业务输入如下；所有命令还可以带可选 `profile`。表中的“二选一”表示必须且只能提供一项。

| 命令 | 必填字段 | 可选字段 |
| --- | --- | --- |
| `long.video.project.list` | `novelId` | `outputFile` |
| `long.video.project.get` | `projectId` | `outputFile` |
| `long.video.project.create` | `novelId`, `title` | `mode`, `targetAspectRatio`, `targetLanguage` |
| `long.video.asset.upload` | `projectId`, `filePath`, `name`, `modality`, `duty` | `sourceKind` |
| `long.video.asset.rights` | `assetId`, `rightsStatus` | 无 |
| `long.video.asset.download` | `assetId`, `outputFile` | 无 |
| `long.video.asset.preview` | `assetId`, `outputFile` | 无 |
| `long.video.adaptation.list` | `projectId` | `outputFile` |
| `long.video.adaptation.get` | `adaptationId` | `outputFile` |
| `long.video.adaptation.create` | `projectId`, `chapterId`, `expectedChapterUpdatedAt`, `clientRequestId` | 无 |
| `long.video.adaptation.watch` | `adaptationId`, `taskId` | 无 |
| `long.video.plan.start` | `adaptationId`, `clientRequestId` | `pacingPreset`, `targetEpisodeSeconds`, `baseShotPlanVersionId`, `revisionBrief` |
| `long.video.plan.confirm` | `adaptationId`, `clientRequestId`, `expectedArtifactRevision`, `expectedAdaptationRevision`, `plan`/`planFile` 二选一 | 无 |
| `long.video.plan.discard` | `adaptationId`, `clientRequestId`, `expectedArtifactRevision`, `expectedAdaptationRevision` | 无 |
| `long.video.episode.save` | `adaptationId`, `clientRequestId`, `expectedAdaptationRevision`, `shotPlanVersionId`, `breakAfterShotIds` | 无 |
| `long.video.prompt.start` | `adaptationId`, `clientRequestId`, `expectedAdaptationRevision`, `shotPlanVersionId` | `shotIds` |
| `long.video.prompt.save` | `adaptationId`, `shotId`, `expectedPromptRevision`, `currentPrompt`/`currentPromptFile` 二选一 | `candidateTaskId` |
| `long.video.canon.list` | `projectId` | `outputFile` |
| `long.video.canon.candidate.set` | `projectId`, `clientRequestId`, `settingKind`, `settingId`, `duty`, `variantKey`, `label`, `candidateAssetId` | `includeFeatures`, `excludeFeatures`, `defaultStrength` |
| `long.video.canon.approve` | `canonId`, `clientRequestId`, `expectedRevision`, `candidateAssetId` | 无 |
| `long.video.reference.save` | `adaptationId`, `shotId`, `expectedRevision`, `references` | 无 |
| `long.video.render.list` | `adaptationId` | `outputFile` |
| `long.video.render.start` | `adaptationId`, `shotId`, `clientRequestId`, `expectedPromptRevision`, `durationSeconds` | `resolution`, `generateAudio`, `watermark` |
| `long.video.render.get` | `taskId` | `outputFile` |
| `long.video.render.retry` | `taskId`, `clientRequestId` | 无 |
| `long.video.render.watch` | `taskId` | 无 |
| `long.video.take.confirm` | `adaptationId`, `shotId`, `takeId`, `clientRequestId`, `expectedTakeRevision` | 无 |
| `long.video.take.download` | `takeId`, `outputFile` | 无 |
| `long.video.post.show` | `adaptationId` | `outputFile` |
| `long.video.keyframe.set` | `adaptationId`, `shotId`, `role`, `assetId`, `clientRequestId`, `expectedRevision` | `sourceTakeId` 与 `sourceTimeMs` 同时提供 |
| `long.video.keyframe.clear` | `adaptationId`, `shotId`, `role`, `clientRequestId`, `expectedRevision` | 无 |
| `long.video.keyframe.extract` | `takeId`, `timestampMs`, `name`, `clientRequestId` | 无 |
| `long.video.edit.save` | `adaptationId`, `episodeNo`, `clientRequestId`, `expectedRevision`, `edit`/`editFile` 二选一 | `basedOnVersionId` |
| `long.video.edit.get` | `versionId` | `outputFile` |
| `long.video.mix.save` | `adaptationId`, `episodeNo`, `editVersionId`, `clientRequestId`, `expectedRevision`, `mix`/`mixFile` 二选一 | `basedOnVersionId` |
| `long.video.mix.get` | `versionId` | `outputFile` |
| `long.video.export.start` | `adaptationId`, `episodeNo`, `editVersionId`, `mixVersionId`, `clientRequestId` | `resolution`, `framesPerSecond`, `burnSubtitles` |
| `long.video.export.get` | `taskId` | `outputFile` |
| `long.video.export.retry` | `taskId`, `clientRequestId` | 无 |
| `long.video.export.watch` | `taskId` | 无 |
| `long.video.export.download` | `exportId`, `outputFile` | 无 |

## 命令清单

以下标记区由注册表测试精确校验。每行都是已注册的具体命令，不接受前缀通配。

长篇创作资料写命令遵循以下统一规则：

- 单例、实体、关系、经历和参考资料更新都必须携带读取结果中的 `expectedUpdatedAt`；冲突后停止，重新读取并重新展示 Diff，不自动换版本重试。
- 实体、关系、经历和参考资料创建使用稳定 `clientRequestId`。网络结果不确定时，只能用完全相同的请求重放，不能换 ID 盲目再建一份。
- 删除命令返回 Core 的完整影响报告。调用方必须先展示引用或影响，再由用户确认是否执行；CLI 不提供隐式级联清理。
- 参考资料保存成功只代表正式资料已提交。`ragStatus=disabled` 表示等待索引，`failed` 表示索引失败；只有回拉到 `ready` 才能表述为索引完成。
- 结构化写命令不接受 `outputFile`，不维护本地镜像；伏笔和用户级文风资产仍为只读。
- `long.outline.save` 必须携带读取大纲时得到的非空 `expectedUpdatedAt`；支持 `content` 或 UTF-8 `contentFile` 二选一。
- 大纲节点创建使用稳定 `clientRequestId`；更新和删除必须携带节点最新的 `expectedUpdatedAt`，冲突时重新读取后再决定。

<!-- command-list:start -->
```text
auth.login
auth.logout
auth.whoami
short.list
short.create
short.pull
short.draft.save
short.version.preview
short.version.submit
short.version.list
short.version.diff
short.version.get
short.version.adopt
short.version.restore
short.agent.start
short.agent.watch
long.novel.list
long.novel.get
long.novel.create
long.novel.summary.save
long.chapter.list
long.chapter.get
long.session.list
long.session.get
long.planning.get
long.lore.get
long.resources.get
long.outline-node.list
long.foreshadowing.list
long.task.list
long.task.get
long.task.watch
long.artifact.list
long.artifact.get
long.quality.get
long.chapter.create
long.chapter.save
long.chapter.status
long.chapter.progress.save
long.agent.start
long.task.resume
long.task.cancel
long.artifact.approve
long.artifact.revise
long.artifact.discard
long.quality.run
long.quality.skip
long.quality.reset
long.outline.save
long.lore.story-background.save
long.lore.world-setting.save
long.lore.writing-bible.save
long.lore.story-progress.save
long.plot-progress.save
long.outline-node.create
long.outline-node.update
long.outline-node.delete
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
long.reference.create
long.reference.update
long.reference.delete
long.reference.reindex
long.style.apply
long.style.clear
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
long.video.render.list
long.video.render.start
long.video.render.get
long.video.render.retry
long.video.render.watch
long.video.take.confirm
long.video.take.download
long.video.post.show
long.video.keyframe.set
long.video.keyframe.clear
long.video.keyframe.extract
long.video.edit.save
long.video.edit.get
long.video.mix.save
long.video.mix.get
long.video.export.start
long.video.export.get
long.video.export.retry
long.video.export.watch
long.video.export.download
```
<!-- command-list:end -->
