# Durable Agent V2 Operator Skill 更新契约

## 状态与适用边界

- 日期：2026-09-01
- 最近更新：2026-09-05；结构化五项、中短篇四项与一致性终检均已仓内接通，加入文风画像后 Catalog 当前为 18/21。
  中短篇和一致性终检完成本地独立 Core/Agent、受控 Fake Provider 验收及全仓门禁；
  文风画像也已完成全仓和隔离重启验收，不新增 CLI 命令，详见本文末专节。
  真实供应商、固定包/活动 Skills 与生产另行验收。
- 状态：CLI 与共享契约代码已完成本地验证，但尚未进入 `main`、尚未部署生产。Production Skill 只能在目标提交
  实际部署、真实 canary 通过，且该 Skill 可操作的全部目标都会创建 V2 Run 后开放 `answer_question`；单个
  user/novel allowlist 只用于 canary，不能代表通用 Skill 已经可用。
- 适用 Skill：`inkforge-short-story-operator`、`inkforge-production-short-story-operator`。
- 问答阶段只扩展现有 `long.agent.start` 的一个显式 Operation；2026-09-04 正文写作阶段另扩展既有
  `long.artifact.approve` 的 V2 全文编辑语义，见下文专节，两阶段均不新增命令名。
- macOS 两份 Skill 已按 `docs/specs/2026-09-04-java-cli-operator-cutover.md` 完成本机实际入口切换与离线验收，
  执行链为 `scripts/run.sh → Java Operator → Java CLI`。新版生产入口已于 2026-09-04 用既有 Keychain 会话通过
  指定账号的 `auth.whoami`，真实写作业务与 Windows 实机尚未验收，服务器部署状态不随本机切换变化。
  该入口变更不开放问答；Python CLI
  保留为契约对照，问答生产开放前仍须证明 Python/Java 两端对本契约全绿。

### 当前本地验证证据

截至 2026-09-01，本工作分支已经完成以下本地门禁；这些结果只证明实现与契约一致，不代表生产已开放：

- Python CLI 与 CLI migration baseline 的最终全量门禁 `584 passed`，相关问答/Skill 契约架构门禁 `6 passed`；
- Java CLI 变更定向测试 `23/23`，Java CLI 模块 `verify` 为 `61/61`；
- `contracts/cli/parity-v2-contract-error-cases.json` 的 16 个错误场景与
  `contracts/cli/parity-watch-cases.json` 的 7 个 watcher 场景均由 Python/Java 跨语言测试读取；
- Python Ruff、CLI 源码 Mypy 与 `git diff --check` 均通过。

2026-09-01 的 Python wrapper 只按命令名允许 `long.agent.start`，当时“未开放问答”仅是 Skill 指令，
尚无 operation 级硬拒绝。2026-09-04 的 Java Operator 已落实下文精确 Operation 检查，并完成本机实际入口
切换与离线验收。两份 `SKILL.md` 的允许集合仍只有原三种 Operation，在各自环境启用条件满足前继续拒绝
`answer_question`，不能把 executable 切换解释为业务开放。

此前两个 Python Skill wrapper 已经单独完成一项不扩大业务能力的凭据诊断收紧：macOS
Keychain 原生调用失败时，wrapper 把受控 `MacOSKeychainError` 转成稳定的
`SECURE_CREDENTIAL_BACKEND_REQUIRED`，不再把它吞成泛化 `UNEXPECTED_ERROR`。该变化没有增加命令白名单、
不会读取或打印密码，也没有明文、环境变量或文件凭据回退。更新者必须在目标发布提交进入 `main`、本节测试由该提交
复跑、下文对应环境启用门禁满足后，才按“Skill 文件更新清单”开放问答；不得直接从当前工作树复制未发布业务行为。

### 凭据后端诊断契约

- `auth.whoami`、业务命令或登录流程若无法使用 macOS Keychain，wrapper 稳定输出
  `SECURE_CREDENTIAL_BACKEND_REQUIRED` 并以退出码 `3` 停止；不得自动切换到明文、环境变量、仓库文件或日志中的
  token。
- `auth.login` 的密码只允许用户在真实 TTY 的隐藏提示中输入。Skill、测试、文档和自动化不得把密码放入 argv、
  stdin 管道、环境变量、JSON、证据目录或聊天记录，也不得代替用户输入。
- 该错误只表示当前本机安全凭据后端不可用，不能被 Skill 解释为 `AUTH_REQUIRED` 后自动登录，也不能用浏览器 Cookie、
  自拼 HTTP、SSH、数据库或内部 API 绕过。
- 两个已安装 Skill 的离线回归必须分别覆盖：原生 Keychain backend error 被精确转换、错误文本不包含底层异常正文、
  backend 不可用时零目标业务请求。2026-09-01 的 Python wrapper 门禁为 production Skill `13 tests OK`、
  local Skill `16 tests OK`，两者各有 1 个宿主未提供原生 Keychain 测试条件的显式 skip，且两份
  `quick_validate.py` 均通过；Java Operator 的当前安装与回归证据以 2026-09-04 入口切换 spec 为准。

## 命令面与 Skill 行为变化

2026-09-04 普通聊天迁移补充：`2026-09-04-durable-natural-language-entry.md` 已完成本地隔离验收。当前分支已接通
通用 Java/Python CLI 的自然输入与澄清模式，Web 区分新请求、当前澄清与明确草案返工；完整验收状态以该规格
为准。本轮没有更新两份已安装 Skill 的脚本、说明或固定 JAR，也没有部署服务器。

后续更新 Skill 说明时，应同步以下变化，但不扩大可调用范围：

- 底层 `long.agent.start` 的 `inputMode=natural` 新建 Run；`long.task.resume` 仅在
  `inputMode=clarification` 时继续同一 Run 的当前问题，必须携带 `decisionStepId/expectedRevision`。
  完整命令示例见 `tools/inkforge-cli/README.md` 自然请求专节，不复制为受限 Skill 的可调用示例。
- 两份 Operator 的 45 命令和三种显式长篇 Operation 不变；这两个命令携带任何 `inputMode` 都被新版仓内
  Operator 以 `OPERATOR_INPUT_MODE_NOT_ALLOWED` / 2 拒绝。不得用伪装 Operation、裸 CLI 或旧 resume 绕过。
- watcher 对澄清输出 `type=waiting_user,waitReason=clarification`，包含完整 `prompt`、
  `decisionStepId/revision/data`，不包含 `artifactId`。受限 Skill 应显示完整问题并报告当前范围不允许回答，
  不得当 Artifact 返工或自动恢复；原 Artifact 等待、批准与返工规则不变。
- 新问题/回答不截断、不去空格换行，刷新后以权威 snapshot 恢复；未知控制 Step 完成只能触发回读，不能
  猜测问题已回答。没有新增 SSE 事件类型或 CLI 命令名。
- 仓内 README、`SKILL.md`、命令参考和固定 JAR 的升级是不同动作；本轮只提供说明，安装必须另获明确要求，
  不能把旧包的成功身份验证当作新模式可用。

### 整章审阅与改写（2026-09-05）

本节供后续更新两份 Skill 的说明与命令参考使用，当前不修改活动 Skill、固定 JAR 或其允许范围。
对应实现和验收记录见 `2026-09-05-durable-review-and-rewrites.md`。

| 操作 | 通用 CLI 输入与结果 | 后续 Skill 说明应写明 |
| --- | --- | --- |
| review_chapter | 显式 start 可省略 writingSessionId；V2 完成后 get/watch 的 data.reviewReport 保留全文 | 报告不产生 Artifact，不执行 approve；未绑定会话也能直接读取；不要用是否有消息判断任务失败 |
| rewrite_scene | 完整章节草案，approve 只接受 editedContent 或 editedContentFile | 当前 wrapper 未允许此操作；场景由指令指定，程序不承诺未绑定区域逐字不变 |
| rewrite_outline_selection | Outline 行或 OutlineNode 行的完整来源和精确 selectionTarget；approve 只接受 editedReplacement 或 editedReplacementFile | 当前 wrapper 未允许；来源必须是同小说的真实行 ID，不能拿 novelId/章节 ID 替代 |

审阅的正常顺序是 `long.agent.start` → `long.task.watch` → 必要时 `long.task.get`。watcher 最终
`type=terminal,data.status=completed,data.reviewReport` 才是 V2 已完成结果；V1 仍按 outcome 判定。
`long.task.get` 指定 outputFile 时保存完整 JSON，其中 reviewReport 保留空格、换行和 Unicode，不裁切正文。
会话存在时还会保存编辑消息，但调用者无须额外创建会话才能读报告。

两类改写的通用 CLI 顺序是 start → watch 的 waiting_user → artifact.get 指定 revision →
artifact.approve/revise/discard。正文编辑与选区编辑字段不可互换；决定带 expectedRevision 和稳定
clientRequestId，网络结果不确定时重放原决定或回读同一 Run，不能另起一个改写任务冒充重试。

自然入口新增 review_chapter 与 rewrite_scene；outline 选区仍需显式绑定，不能从文字猜选区。
后续意图提示词 v2 补充只修正 Core/Agent 的内部操作选择与旧任务恢复，不新增 CLI 参数、命令或结果字段，
不要求 Skill 传入提示词版本，也不表示固定安装包已升级。
两份 Operator 仍拒绝任何 inputMode、rewrite_scene 和 rewrite_outline_selection；原三操作中的
review_chapter 只有目标 Core 命中已验收 V2 路由时才返回上述新格式。更新 Skill 时应记录对应 Core 版本、
固定 JAR 来源和离线验证结果，不能把本节存在解释为安装或生产已经完成。

### 结构化资料显式启动与场景改写补漏（2026-09-05）

普通 Java CLI 与 Python 对照 CLI 的 `long.agent.start` 本批新增 6 个可选 operation 值：五项既有结构化
业务 create_lore/revise_lore/create_outline/revise_outline/manage_foreshadowing，以及此前已实现但显式
CLI 白名单遗漏的 rewrite_scene。命令总数仍为 125，不新增参数，不直接暴露 Agent。

- create_lore、revise_lore、create_outline 只用 `scope={"kind":"novel"}`；revise_outline 另允许
  `{"kind":"outline_node","outlineNodeId":"node-id"}`；manage_foreshadowing 另允许
  `{"kind":"chapter","chapterId":"chapter-id"}`。rewrite_scene 仍只用同章 chapter scope。
- 公共 target 一律为 `{"type":"chapter","id":"chapter-id"}`，同请求 chapterId 必须匹配；不能新造
  lore/outline/foreshadowing/novel target。节点归属由 Core 真实核对，CLI 不根据名称或指令猜 ID。
- 五项 scope 只是任务焦点，不把 operation 名称变成候选分区或 create/update/delete 限制。五项不携带
  selectionTarget；writingSessionId 可省略或 null，完整 userInstruction 原样传输。
- 普通调用仍为 start → watch/get → waiting_user 时精确 artifact.get → 作者确认后 approve/revise/discard；
  结构化部分采用继续遵循本文件专节，不能把受理、自动复审或来源补齐当作正式写入。

普通 CLI 的完整输入示例见 `tools/inkforge-cli/README.md`“结构化资料的显式启动”。本批仅更新仓内源码及
说明；五项使仓内 Catalog 达到阶段性的 12/21，中短篇四项与一致性终检阶段达到 17/21，加入文风画像后当前为 18/21。结构化五项公共 HTTP 接线
定向验证通过，全量门禁与实际跨进程/供应商状态以
`2026-09-05-durable-structured-agent-updates.md` 为准；未安装固定 JAR，
未修改活动 Skills，未部署服务器。两份 Operator 的 45 命令及三操作允许集合保持不变，这 6 项仍被拒绝；
本节示例不得直接复制成受限 Skill 的可执行步骤，也不得改走裸 CLI 绕过 Operator。

后续更新 `SKILL.md`、`references/cli-contract.md`、`references/long-serial-workflow.md` 时应明确记录这组
“底层已接线、当前 Operator 未授权”的差异，并保留 Core 公共接口、精确 revision、完整 Diff 确认与同请求重放
规则。安装包升级、Operator 允许集合变更和目标 Core 启用分别验收，不以文档或源码变化自动执行。

同批通用自然入口改用内部 resolver v3，可选十项无选区操作：create_lore/revise_lore/create_outline/
revise_outline 默认 novel scope，manage_foreshadowing 与原章节五项默认当前 chapter scope。说明和范围由
Core 冻结，模型不提供 ID/scope/arguments；节点或其他不匹配范围须澄清或走显式入口。历史 v1/v2 解析器和
原三项/五项冻结授权不扩大；CLI 不需要传提示词版本或新增参数。自动完整返工最多一次，仍等待作者确认，
来源补齐不表示正式写入。两份 Operator 继续拒绝自然 inputMode，不能因底层自然集合增加而修改受限 Skill。

2026-09-01 问答阶段的 CLI 命令名不变；当时只有 `long.agent.start` 的 Operation 集合增加了 `answer_question`。已有 Operation 的输入和结果
语义、身份预检、固定 origin/profile、Keychain 与幂等边界保持不变。`long.task.watch` 的命令名和中断语义不变，
但其输出判别已经从 V1-only `outcome.state` 扩展为按显式 `engineVersion` 分流的 V1/V2 契约；两份 Skill 必须同步
修改 watcher、终态和恢复说明，不能把“命令名不变”误写成“watcher 行为无需更新”。Skill 也不得把此次变化解释为
开放全部 V2 Operation、全部 scope 或 `route=all`。

输入必须为：

```json
{
  "clientRequestId": "long-answer-20260901-0001",
  "novelId": "novel-id",
  "chapterId": "chapter-id",
  "writingSessionId": "session-id",
  "operation": "answer_question",
  "target": {"type": "chapter", "id": "chapter-id"},
  "scope": {"kind": "chapter", "chapterId": "chapter-id"},
  "userInstruction": "这一章的主要冲突是什么？"
}
```

约束：

- `writingSessionId` 对问答必填且必须是非空字符串；CLI 在发送业务 POST 前以
  `WRITING_SESSION_REQUIRED` 拒绝缺失、`null`、空字符串和其他非字符串类型。Skill wrapper 仍按既有安全规则先执行一次
  `auth.whoami`，因此这里的“本地拒绝”表示零目标业务请求，不能误写成 wrapper 全程零网络。
- `target` 与 `scope` 只能指向同一个 `chapterId`；不得使用预留的 `novel`、`chapter_range` 或
  `outline_node`。
- `userInstruction` 保留原始完整文本且必须包含非空白字符。
- 首次提交与网络结果不确定后的重试必须复用完全相同的 `clientRequestId` 和请求正文。
- 不提交 `selectedAgents`、模型名、Prompt、预算、工具或 Reviewer；这些身份由版本化 Catalog 冻结。

### Skill wrapper 的 Operation 硬门禁

两份 Skill 的 Java Operator 入口（由 `scripts/run.sh` 调用，替代旧 `scripts/operator_support.py`）必须在成功
完成固定 origin/profile 的 `auth.whoami` 后、启动目标 CLI 业务命令前，对 `long.agent.start` 请求体的
`operation` 做精确字符串允许集合检查。该检查不是命令名前缀匹配，也不能由环境变量、调用参数或普通 JSON
字段关闭：

- 未满足本文件对应环境的开放条件时，允许集合精确为 `plan_chapter`、`write_chapter`、`review_chapter`；
- Production Skill 只有在“生产启用门禁”全部满足后，才把 `answer_question` 加入其集合；
- Local Skill 只有在其固定本地运行副本、Core 配置和全部可操作目标都保证 fresh `answer_question` 创建 V2 Run 后，
  才把 `answer_question` 加入其集合；单用户、单小说或单次 canary 不足以开放通用 Local Skill；
- `rewrite_chapter_selection`、`rewrite_outline_selection` 或其他 CLI 已认识但 Skill 未授权的 Operation 继续被 wrapper
  拒绝，不能因为底层 CLI 支持而自动扩大 Skill 能力；
- `operation` 缺失、不是字符串或不在当前 Skill 允许集合时，wrapper 以退出码 `2` 停止，stderr 输出稳定诊断码
  `OPERATOR_OPERATION_NOT_ALLOWED`，并保证已经发生的网络请求至多只有该次 `auth.whoami`，目标业务 POST 为 0 次；
- Operation 门禁通过后，wrapper 必须把原始请求完整交给 CLI，不能自己 trim、补业务默认值或改写 scope。

“wrapper 命令白名单不变”只表示仍允许精确命令名 `long.agent.start`，不表示可以省略上述请求体 Operation 门禁。

### 本地拒绝契约

现有 Skill wrapper 会先完成固定 origin/profile 的 `auth.whoami`。身份核对成功后，Python CLI 与 Java CLI
必须在发出 `/api/v1/writing/runs` 业务 POST 之前按下表拒绝无效问答；CLI 进程退出码均为 `2`：

| 条件 | 稳定错误码 | 业务 POST |
| --- | --- | --- |
| `operation` 不在显式允许集合 | `INVALID_OPERATION` | 0 次 |
| `target` 不是当前 `chapterId` | `INVALID_TARGET` | 0 次 |
| `scope` 不是当前章节 scope | `INVALID_SCOPE` | 0 次 |
| `userInstruction` 仅含 Unicode 空白 | `INVALID_USER_INSTRUCTION` | 0 次 |
| `writingSessionId` 缺失、`null`、空字符串或非字符串 | `WRITING_SESSION_REQUIRED` | 0 次 |
| 请求含命令不认识的顶层额外字段 | `UNEXPECTED_FIELD` | 0 次 |

Skill 不得把这些本地输入错误自动改写成另一种 Operation、scope 或默认会话，也不得在失败后换一个
`clientRequestId` 猜测重试。`auth.whoami` 失败时则必须更早停止，不能执行上表对应的任何业务命令。

上表的 `UNEXPECTED_FIELD` 只描述顶层字段。当前 CLI 对 `target`/`scope` 只做已定义身份字段的一致性检查；其内部
额外成员会随请求发送并由公共 Core 契约决定是否以 422 拒绝。Skill 必须始终生成本文件示例的精确
`target`/`scope`，不得利用这一区别发送扩展字段，也不得宣称所有嵌套额外字段都由 CLI 在零业务请求条件下拒绝。

## 2026-09-04 正文 V2 编辑决定更新

本节对应 `docs/specs/2026-09-04-durable-chapter-writing.md`。CLI 仍为 125 个命令，macOS 两份 Skill 仍为
45 个允许命令，两份 Skill 的 `long.agent.start` 仍只允许 `plan_chapter`、`write_chapter`、`review_chapter` 三种 Operation。
不开放问答、视频或新的选区启动能力；Agent 没有向 CLI 暴露直连入口，实际链路仍为
`Skill scripts/run.sh → Java Operator/CLI → Core /api/v1/** → Agent`，只有 Core 决定是否派发 Agent。
Python CLI 继续作为兼容对照，不回到已安装 Skill 的运行链。

本轮完整验证后，包含正文编辑变更的新 JAR 已显式安装到本机两份 Skill 的固定运行包；服务器仍未部署或开放
正文写作 V2。两份包 SHA-256 均为 `4e6a74f70a7ec5137534e31f0d0c2745966052d98592f4fafd355d32b57e5ec0`，
来源 revision 为 `a0b6a98913066f3d66e8d06a4274ab4f21d949a5`、repositoryDirty=true；保留了原账号/端点绑定。
旧包与原配置备份在 `/Users/boqiangnie/.codex/inkforge-cli-writing-backup.9hh3ty`。本轮只做离线入口验证，
没有重做生产身份或业务调用；不能把本机包已更新解释为服务器已启用。后续源码或 checkout 仍不会自动替换固定包。

### 决定前读取与类型规则

1. 保留启动响应的 `runId`，使用 `long.task.get` / `long.task.watch` 的 `{"taskId":"<runId>"}` 观察；V2 读取
   `status/activeSteps/artifact`。`waiting_user` 只表示候选等待作者，未覆盖正式正文。
2. 从 Run 读取 `artifact.artifactId` 和 `artifact.artifactRevision`，执行
   `long.artifact.get`：`{"artifactId":"<artifactId>","revision":7}`。这里必须传 `revision`，不能省略或用
   `expectedRevision` 替代；示例数字须替换为实际返回值。
3. 独立阅读完整正文、全文 Diff 和来源，确认详情 `id/revision/engineVersion=2` 与请求一致，且
   `sourceBindingStatus=verified`。正文候选还须为 `kind=chapter_draft`、`payload.operation=write_chapter`、
   `payload.target.mode=existing_chapter`；不能根据命令名猜测候选类型。
4. `approve/revise` 内部仍会再次 GET 同一精确 revision 并核对来源，再 POST 决定；这不替代作者阅读与确认。
   `discard` 保持无详情前读的幂等路径，调用方仍须明确 V2 身份和 revision。

| V2 候选 | 批准时可选编辑字段 | 其他限制 |
| --- | --- | --- |
| `write_chapter` 当前章正文 | `editedContent` 或 `editedContentFile`，至多一个 | 必须是完整非空白正文，不接受 replacement |
| 章节规划 `beat_plan` | 无 | 用 `long.artifact.revise` 提交修改要求，不能把计划当正文编辑 |
| 已有选区草案 | `editedReplacement` 或 `editedReplacementFile`，至多一个 | 只提交选区替换文本，不接受 editedContent；本行不扩大 Skill 启动权限 |

在 2026-09-04 正文阶段，所有 V2 决定都禁止 `selectedUpdateRefs`；这是当时只覆盖规划、正文和选区候选的
历史规则。2026-09-05 起，只有下节所述 `agent_updates` 批准允许该字段，其他 V2 候选以及 `revise/discard`
仍保持原限制。省略全部编辑字段的 approve 采用原候选；编辑批准会先形成用户编辑 revision，再由 Core 在同一
事务采用。文件内容必须完整按 UTF-8 读取，保留换行、首尾空格及 Unicode 字符，不 trim、摘要、分块代替全文
或截断。文件路径只是 CLI 本地输入，不发给 Core。

正文文件编辑批准示例（ID、revision 与路径必须替换为已确认的实际值）：

```json
{
  "artifactId": "artifact-id",
  "engineVersion": 2,
  "expectedRevision": 7,
  "clientRequestId": "chapter-draft-edit-20260904-0001",
  "editedContentFile": "/absolute/path/已确认完整正文.txt"
}
```

用 `long.artifact.approve` 发送上述 JSON；内联方式将文件字段替换成 `editedContent`，不能同时携带两者。
返工使用 `long.artifact.revise` 和相同四个身份字段，另加非空 `userMessage`，使用本次决定独立、稳定的
`clientRequestId`；丢弃使用 `long.artifact.discard`，不加编辑字段。网络结果不确定时只重放完全相同的请求与
requestId；新修改要求或新 revision 不能复用旧请求内容，也不能用换 ID 的方式猜测上一决定是否成功。

决定响应及 Run 回读是 Core 权威状态；`completed` 本身不能区分批准和丢弃。批准后回读 `long.chapter.get`
确认完整正式正文及状态，不能把 SSE、CLI 文件或候选预览当正式结果。采用正文不会自动完成章节，也不会更新
章节进展、故事进展、计划、设定或伏笔。来源/revision 冲突时重新读取，不自动覆盖新来源或改用内部接口。

### 后续安装与 Skill 维护清单

- 先完成本分支 Java/Python CLI、Core 与 Agent 相关门禁，构建新 JAR，并执行真实 JAR/shell 的隔离入口验证。
- 经本机安装更新后，核对固定包 `jarSha256`、来源提交和 `repositoryDirty` 记录；没有这一步，不把源码或
  `target/inkforge-cli.jar` 当作日常 Skill 已安装版本。安装流程见 Java CLI README 与入口切换 spec。
- 实际维护 Skill 时同步 `references/cli-contract.md`、`references/long-serial-workflow.md`、
  `references/recovery.md` 及必要的 `SKILL.md`：写清精确详情、三类编辑字段、完整文件、幂等恢复和最终正文回读；
  不改变 45 命令/三 Operation 允许范围，不恢复 Python wrapper，不修改凭据规则。
- 本轮只更新 Application Support 下的固定运行包和配置，没有修改已安装 `~/.codex/skills` 说明或脚本文件，
  没有执行生产部署。新包安装与
  目标 Core/Agent 实际部署、V2 路由和业务验收是不同事实，后者完成前不得宣称生产正文 V2 已开放。

## 2026-09-05 结构化资料 V2 部分采用

本节最初记录部分采用接线检查点，当时 Catalog 为 7/21、五项结构化操作尚未启用。随后显式/自然入口、自动
返工和作者采用完成定向验证，该阶段仓内已启用 12/21；中短篇四项与一致性终检阶段达到 17/21，加入文风画像后当前为 18/21。结构化五项的门禁及
未部署状态见结构化资料规格，历史阶段数字不代表当前总数。
普通 Java/Python CLI 仍为 125 个命令；两份 Operator
仍为 45 个命令，`long.agent.start` 仍只允许 `plan_chapter`、`write_chapter`、`review_chapter` 三种 Operation。
本节没有增加命令、启动参数或 Skill 白名单。

当前源码中的 Java CLI 与 Python 对照 CLI 已允许 `agent_updates` 的 V2 approve 原样携带已有
`selectedUpdateRefs` 字段。这项源码变化已经完成构建和最终 Maven 门禁，但尚未安装到两份 Skill 的固定 JAR，
也没有修改活动 Skill。
仓库源码、构建产物、固定安装包、活动 Skill 和服务器部署是五个不同状态；后续安装时须重新记录固定 JAR 来源与
SHA-256 并完成两份入口回归，不能沿用上节旧 JAR 的验收结论。

### 精确候选与决定规则

1. 调用方先从 Run 取得 `artifactId/artifactRevision`，再用 `long.artifact.get` 精确读取该 revision 并完整展示
   候选、Diff 和来源。`long.artifact.approve` 还会再次 GET 相同 revision，并继续核对既有的
   `id/revision/engineVersion=2` 与 `sourceBindingStatus=verified`。只有调用方提交非 null
   `selectedUpdateRefs`、要求进入结构化部分采用分支时，详情还必须同时满足顶层 `kind=agent_updates`、
   `payload.kind=agent_updates`，且 `payload.updates` 为 JSON 对象；这组结构条件不满足时拒绝选择字段且不发送决定
   POST。它不为省略选择字段或沿既有语义被忽略的 null 新增 Artifact 类型门禁，其他合法 V2 approve 仍按原规则处理。
2. 只有上述候选的 approve 才可携带调用方 JSON 中已经存在的 `selectedUpdateRefs`。CLI 不重排、不重编号、
   不补默认 section/index，也不增加新的命令参数：字段省略就保持省略，显式 `null` 原样发送并由 Core 解释为
   全选，空数组原样发送并保持“没有选中项”，非空数组保持原始 section/index。
3. `agent_updates` approve 不接受 `editedContent`、`editedContentFile`、`editedReplacement` 或
   `editedReplacementFile`。其他 V2 候选仍拒绝非 null 的 `selectedUpdateRefs`；V2 revise 仍不接受非 null
   选择字段，显式 null 沿用既有“按省略处理”的行为；discard 仍拒绝任何已出现的编辑字段，包括显式 null。
4. Core 以精确 Artifact revision 和原数组 section/index 物化选择，在同一事务内复验被选项的冻结来源并应用。
   被选目标或必要依赖已变化时返回冲突，CLI/Skill 必须重新读取、重新展示、重新确认，不能自动覆盖或换 ID
   猜测重试；未选资料的变化不得被 CLI 扩大成整作品 CAS。网络结果不确定时只对账或重放完全相同的
   `clientRequestId`、revision 和选择正文。

Agent 仍没有 CLI 直连入口。链路保持
`Skill scripts/run.sh → Java Operator/CLI → Core /api/v1/** → Agent`，候选生成、来源复验、事务采用和最终状态均由
Core 负责；CLI 透传选择不等于自行写资料。五项仓内启用不替代固定 JAR/Skill 更新、服务器部署及生产验收，
后者仍须分别完成，不能由本节代替。

## 2026-09-05 中短篇四操作观察

本节是后续两份 Skill 的更新契约，不直接编辑活动 `SKILL.md`、脚本或固定 JAR。中短篇四项已仓内启用，
当时 Catalog 为 16/21；后续一致性终检达到 17/21、文风画像达到 18/21，加入 RAG 后当前已验收为 19/21，另有两个开发视频操作尚未完成。四项已完成本地独立
Java Core/Python Agent、受控 Fake Provider 验收与全仓门禁，包含双段正文的 Agent 重启、每段仅一次实际
Fake 调用、三类候选幂等采用和全文检查零候选；不是实际供应商或生产验收。
完整证据以 `2026-09-05-durable-short-medium-workflows.md` 为准。
普通 CLI 125、短篇 13 与 Operator 45 命令不变，长篇三操作允许集合不变；不新增 short.agent.cancel。

后续应在现有 cli-contract、短篇工作流和 recovery 说明中同步：

1. short.agent.start 继续使用 outline/manuscript/selection/full_check 四个原别名、原公共字段和稳定
   clientRequestId，不传模型、Prompt、预算、segmentIndex/segmentCount 或新来源正文。保留实际响应 runId，
   short.agent.watch 仍输入 `{"taskId":"<runId>"}`，可选 lastEventId 仍为字符串。
2. V1 缺少 engineVersion 的历史响应仍兼容原 phase/commandStatus；显式字段只能是整数 1 或 2。
   V2 只按 status 判定，不借旧 phase/commandStatus 假报成功，观察期间不能换引擎。V1 原终态退出 0 不改，
   必须另外核对旧状态；V2 completed 退出 0，failed/cancelled 退出 5。
3. 数字事件 ID 和 run_snapshot.baseSequence（含 0）作为 SSE 重连游标；快照/完成事件不是业务结果。
   V2 断线或终态事件后必须 GET 同一 Run，最终 terminal.data 原样来自该 GET，不从 SSE payload.resultId、
   版本列表最后一项、可变工作稿或日志拼造候选和报告。
4. generate_outline/generate_manuscript/replace_selection 的 completed 必须带真实 candidateVersionId。
   用该精确 ID 执行现有 short.version.get、short.version.preview，并在阅读完整内容和 Diff、作者确认
   confirmationHash 后采用。Run 完成仅代表一份待采用候选，不能跳到 long.artifact.approve 或自动下一阶段。
5. full_check 的 completed 必须带完整 checkReport.text，且没有 candidateVersionId；逐字显示报告，
   不 trim、摘要代替原文或截断，不执行采用。输出文件和版本下载继续保留完整 UTF-8 内容与原换行。
6. 缺少对应结果、显式类型错误或任务身份不匹配时，保留 CORE_RESPONSE_CONTRACT_ERROR/5 并停止；不得
   回落 V1 或新建任务猜测重试。SSE 最多三次重连后仍非终态继续保留 SSE_RECONNECT_EXHAUSTED/5；停止
   watcher 只停止观察，服务端任务未取消，恢复时观察同一个 Run。

发布构建、固定安装包与活动说明更新分别核对，不能把本节或源码测试当成已安装/生产开放；本批不安装 Skill。

## 2026-09-05 一致性终检迁移说明（仓内验收完成）

本项改的是原质量检查的服务端执行内核，不给 CLI 直接暴露 Agent，也不新增命令或参数。
完整实现、全仓门禁和本地独立进程正常/纠正重启验收均已通过，见 `2026-09-05-durable-consistency-quality.md`；
本节不代表固定 JAR、活动 Skills 或生产已更新。

- 继续使用 `long.quality.run`，传原 `checkId`、稳定 `clientRequestId` 与可选原字段；受理响应里的 `taskId`
  是本次质量 `WorkflowRun.id`，仅表示受理，不表示检查通过或完成。
- 继续用 `long.quality.get` 和原 `checkId` 回读检查项；质量运行不转成 `long.agent.start`、
  `long.task.watch` 或短篇 watch，也不混入写作运行历史。CLI 不传模型 Profile、预算、纠正次数或内部 Step ID；
  原有用于选择连接配置的 CLI `profile` 字段不变。
- 完成时保留完整 `result`、`scoreOverall`、`qualityGate` 和 `rewriteBrief`。`qualityGate=revise`
  仍是执行完成的报告，不能当作命令失败、自动返工或新的写作硬限制。
- 原 `long.quality.skip` / `long.quality.reset` 与 `expectedUpdatedAt` 并发检查不变；有有效运行时仍按原规则
  拒绝更改检查状态。正文修改或重新送审后的旧结果不能覆盖新的检查项，不用重新启动同一请求来“催进度”。
- 一次报告格式纠正由 Core 在同一个质量 Run 内安排独立 Step；Skill 不手动追加第二个 run，不回放坏参数，
  不根据模型调用次数推断业务是否完成。断线后先回读原检查项，必要时以原 clientRequestId 重取受理身份。

两份活动 Skill 无需新增允许命令；后续安装更新时只同步以上语义说明。Python CLI 仍是契约对照，不是活动入口。

## 观察与结果恢复

1. 从 `long.agent.start` 响应根对象读取 `engineVersion` 与 `runId`；`engineVersion` 必须是 JSON 整数，`runId`
   必须是非空字符串，不能根据其他字段是否存在猜引擎。已开放的 `answer_question` 只接受
   `response.engineVersion=2`；若该 Operation 返回 V1、缺少判别字段或判别字段类型错误，属于发布/路由契约违规，
   Skill 必须停止，不得读取 V1 `outcome`、回落旧问答流程或重新启动。其他仍受支持的历史 Operation 才按显式
   `engineVersion` 分流。
2. 使用 `long.task.watch`，输入 `{"taskId":"<runId>"}`。中断只停止观察，不取消任务；继续观察同一 Run。
   V2 状态中的 `activeSteps` 必须存在且是数组，`artifact` 与 `error` 出现时必须是 `null` 或对象；CLI
   遇到显式类型错误会输出稳定 `CORE_RESPONSE_CONTRACT_ERROR` 并以退出码 `5` 失败关闭。Skill 不得在外层把该
   失败降级为“仍在运行”、自行修补响应或改走 V1。
3. `answer_question` 不会进入 `waiting_user`，不会创建 ReviewArtifact，也不能调用 Artifact 决定命令。该 Operation
   若出现 `waiting_user`、非空 `artifact` 或 Artifact ID，必须按契约异常停止。
4. V2 成功的 PostgreSQL 持久终态是 `status=completed`。`long.task.watch` 对持久终态输出
   `frame.type=terminal`，并要求 `frame.data.engineVersion=2`、`frame.data.runId=<runId>`、
   `frame.data.status=completed`；该 terminal snapshot 不含回答正文，也不保证含 `resultId`。首次 GET 已完成时，
   watcher 会先输出同一数据的 `frame.type=snapshot`，再输出 `frame.type=terminal`；不得把两帧当成两个结果。
5. 若本次观察消费到持久 `completed` Event，其 JSONL 帧必须同时满足：
   - `frame.type=event`、`frame.event=completed`；
   - `frame.data.protocolVersion="2.0"`、`frame.data.engineVersion=2`、`frame.data.runId=<runId>`；
   - `frame.data.eventType=completed`，且必须与外层 `frame.event` 一致；
   - `frame.data.payload.outcomeType=chat_answer`；
   - `frame.data.payload.resultId` 必须是非空字符串，值为 `<WritingMessage.id>`。

   任一字段缺失、类型错误或内外事件类型不一致都必须停止。不得从不存在的 `frame.data.resultId`、顶层
   `frame.resultId`、terminal snapshot、SSE 文本片段或日志猜测结果 ID。
6. 使用 `long.session.get`，输入 `{"sessionId":"<writingSessionId>"}`。其响应根对象必须满足
   `response.id=<writingSessionId>`、`response.novelId=<novelId>`、`response.chapterId=<chapterId>`，且
   `response.messages` 必须是数组；任一身份不一致都停止。权威回答只可能来自
   `response.messages[i].content`，必须逐字符完整返回，不能 trim、摘要或从 `currentTask`/`lastTask` 猜测。
   每个候选消息还必须满足 `messages[i].sessionId=<writingSessionId>`、`messages[i].id` 为非空字符串、
   `messages[i].content` 为包含非空白字符的字符串、`messages[i].metadata` 为对象且
   `messages[i].metadata.source` 为对象。不得把 SSE 片段、日志或本地缓存当作最终回答。
7. 回答身份按以下优先级确定；这里的所有 `message` 都是 `response.messages[]` 的元素：
   - 若观察到 `completed(chat_answer)`，先要求 `message.id == frame.data.payload.resultId`，再同时要求该消息
     `role=agent`、`metadata.source.engineVersion=2`、`metadata.source.runId=<runId>`、
     `metadata.source.operation=answer_question` 且 `metadata.source.outcomeType=chat_answer`。必须恰好有一条消息同时
     满足完整 source 身份，也必须恰好有一条消息命中 `resultId`；两者必须是同一条，任一不匹配都停止，不能只相信
     `resultId`。
   - 若任意一次 PostgreSQL 持久状态对账已经得到 `completed`，但本次观察没有消费到 completed 事件（包括
     首次 GET 已完成，以及 running 后 SSE 断线、下一次 GET 才发现完成），则只按上述 role 与四项 source
     身份筛选；这里的“四项 source”精确指 `engineVersion/runId/operation/outcomeType` 四个字段与 `role` 的组合，
     不包含 `resultId`。必须恰好得到一条消息，并以其 `id` 作为回答 ID。
   - 筛选结果为 0 条或多条均属于权威结果身份无法证明。Skill 必须停止并报告契约异常，不得选择“最后一条”、
     按 `agentId` 猜测、复用旧回答或重新启动同一问题。
8. 只有完成上述全部身份校验后，才把唯一候选的 `response.messages[i].content` 作为本次完整回答。失败或取消不会
   留下成功的 Agent 消息；不得把已有旧消息误认成本次结果。

### 稳定错误与恢复分类

| 来源与条件 | 稳定错误码/状态 | 退出码 | 唯一允许动作 |
| --- | --- | --- | --- |
| wrapper 的 Operation 硬门禁拒绝 | `OPERATOR_OPERATION_NOT_ALLOWED` | 2 | 停止；不得调用目标 CLI 业务命令 |
| V2 snapshot、SSE 游标或响应类型违反契约 | `CORE_RESPONSE_CONTRACT_ERROR` | 5 | 停止并报告原字段；不得降级 V1 |
| watcher 被用户中断 | `WATCH_INTERRUPTED` | 130 | 只继续观察同一 `runId`，不取消、不新建 |
| Core 连续不可达超过 watcher 门限 | `WATCH_CORE_UNREACHABLE` | 5 | 保留同一 `runId`/`clientRequestId`，Core 恢复后对账同一 Run |
| 同一幂等键对应不同请求 | `IDEMPOTENCY_KEY_REUSED` | 4 | 停止；不得改正文后继续复用，也不得换新 ID 猜测重试 |
| 会话不属于同一小说或章节 | `WRITING_SESSION_MISMATCH` | 4 | 重新读取原会话、小说和章节身份并报告；不得自动替换会话 |
| 同一会话已有前台 Run | `WORKFLOW_FOREGROUND_RUN_EXISTS` | 4 | `long.task.list/get` 定位并观察已有 Run；不能假定它就是本次问题，也不能立即换 ID 新建 |
| V2 Operation/执行器不可用 | `DURABLE_OPERATION_NOT_ENABLED`、`DURABLE_AGENT_EXECUTION_UNAVAILABLE` | 4 或 5，以 CLI 原值为准 | 停止；不得回落 V1。服务恢复后只允许用原请求与原 `clientRequestId` 对账/重放 |
| V1 fresh-start 正在 drain | `AGENT_FRESH_STARTS_DRAINING` | 5 | 停止；不得用新 ID、其他 Operation 或非公共入口绕过 |

CLI 本地 `WRITING_SESSION_REQUIRED`、`INVALID_TARGET`、`INVALID_SCOPE`、`INVALID_USER_INSTRUCTION` 与
`UNEXPECTED_FIELD` 仍按上一节退出码 `2` 处理。若通过当前 CLI 的合法问答仍收到服务端
`WRITING_SESSION_REQUIRED`，视为部署或契约不一致，停止而不是补默认会话。其他 401/403/404/409/422/5xx 继续按
既有 Skill 恢复规则原样保留 `code/message/details/requestId`；上表没有授权自动重试或自动修正请求。

## Skill 文件更新清单

- `SKILL.md`：只在对应环境启用条件满足时把 `answer_question` 加入 `long.agent.start` 允许集合，并保留“V2 必须
  显式 operation”的规则；删除“所有长篇 Agent 结果都必须进入 ReviewArtifact”“watcher 只观察 outcome”等普遍
  断言，改成普通草案 Operation 走 Artifact、V2 问答走 completed→session message 的显式分支。生产标准流程不能再
  假设每次 Agent start 都会进入 `waiting_user`。
- `references/long-serial-workflow.md`：加入上述启动、watch、session 回读流程，明确无 Artifact。
- `references/cli-contract.md`：记录 `writingSessionId` 必填、稳定 `clientRequestId`、退出码与响应判别规则。
- `references/recovery.md`：删除“所有长篇只看 `outcome`”的 V1-only 假设，按响应中显式
  `engineVersion` 分流：V1 读取 `outcome.state`，V2 读取 `status`；V2 `answer_question` 完成后按本文件的
  Run/message 双重身份回读。watch 中断或提交结果不确定时只对账同一 `runId`/`clientRequestId`，不得新建 ID；
  V2 问答不进入 Run 的 `waiting_user`，也不恢复 Artifact 决定流程。
- `agents/openai.yaml`：同步 `default_prompt`，明确长篇必须按 `engineVersion` 分流，且
  `answer_question` 的 V2 成功结果是会话消息、没有 ReviewArtifact；不能继续把所有长篇任务概括为
  ReviewArtifact/outcome 闭环。
- `scripts/run.sh` 所调用的 Java Operator：命令白名单不变，因为命令名未变化；实现本文件定义的
  `long.agent.start.operation` 精确允许集合硬门禁，不得新增任意前缀通配或可由调用方覆盖的开关。Local 与
  Production 必须分别按各自启用状态维护，不能因其中一个环境开放而同步放开另一个环境。旧
  `scripts/operator_support.py` 已由 2026-09-04 入口切换 spec 取代，不再作为新增实现位置。
- Operator 回归测试：覆盖当前未开放状态下 `answer_question` 返回
  `OPERATOR_OPERATION_NOT_ALLOWED`/退出码 2、一次身份预检且零目标业务请求；既有三种 Operation 继续透传；启用版
  合法问答原样透传；缺会话与错误 scope 在身份预检后零目标业务请求；watch 完成后执行 `long.session.get` 回读。
  底层 CLI 单元测试另行证明非法输入本身可以在零网络条件下拒绝。
- wrapper 的合法问答测试必须断言请求正文逐字段等于调用方输入（仅由 CLI 补固定
  `workflow=long_serial`）；不得 trim `userInstruction`、补模型参数或删除 `writingSessionId`。
- 结果关联目前属于 Skill 的编排行为，现有 wrapper 不编排 watch→session，也不解析消息；因此必须用干净上下文
  forward-test 分别覆盖“收到 `frame.data.payload.resultId`”“首次 GET 已 completed、未收到终态事件”和“running 后 SSE
  断线、下一次持久 GET 已 completed”，并覆盖 0 条、重复两条、message ID 与 source 身份冲突时全部 fail closed。
  不得在测试中复制一份并未被 Skill 调用的筛选算法来伪装单元覆盖；若以后新增 Skill 实际调用的
  确定性离线 resolver，再把这些身份用例下沉为 resolver 单测。
- Python CLI 与 Java CLI 都必须通过合法问答请求映射、非法输入、V1 历史响应和 V2 status/SSE 游标的
  同契约测试；合法问答、watcher 和本地/响应错误分别由
  `contracts/cli/parity-success-cases.json`、`contracts/cli/parity-watch-cases.json` 与
  `contracts/cli/parity-v2-contract-error-cases.json` 直接驱动两种 CLI。差异门禁必须比较退出码、完整
  JSON/JSONL 帧和公共 API 调用记录，不能只验证其中一个实现或只比较错误码。
- 生产 Skill 仍必须先 `auth.whoami` 并精确核对预期用户名；密码只能由用户在真实 TTY 隐藏输入。

每份 Skill 更新后都必须运行 Skill Creator 的 `quick_validate.py <skill-directory>`，再运行对应实现的离线回归
和干净上下文 forward-test。Java Operator 的 JUnit 与真实 JAR/shell 验证按 2026-09-04 入口切换 spec 执行，
不再要求以 Python wrapper 测试证明 Java 入口。问答开放还须满足下一节条件；仅切换 Java executable 不受问答
开放条件阻塞，也不因此获得问答授权。

## 退役发布控制面（Skill 维护者必读）

个人项目范围纠正见 `docs/specs/2026-09-04-personal-durable-agent-release-scope.md`。独立 Durable Agent
release/development-evidence Workflow，以及 control bundle、release manifest/receipt、boundary、SSH broker/trust、
GitHub evidence 和文件型 release guard 已删除；不存在可供 Skill 调用的兼容命令或替代别名。

这些删除没有改变公共 Python/Java CLI 的命令名、参数、JSONL、SSE、退出码或凭据边界。Skill 不得新增 SSH、部署、
数据库、Compose 或内部 API 命令，也不得把服务器端 `deploy-production.sh`、
`durable-agent-execution-migration.sh`、`durable-agent-v2-rollout-gate.sh` 加入 wrapper 白名单。普通应用部署继续使用
项目既有入口；V2 迁移和 canary 是维护者在 Skill 外执行的运维步骤。未来若公共 CLI 输入、JSONL 或恢复语义变化，
必须先更新本文件，再更新两份 Skill。

## 生产启用门禁

只有当 Python CLI、Java CLI、Core 与 Agent 来自同一已部署提交，两种 CLI 的同契约与跨语言差异门禁全绿，
开发库迁移与真实 provider canary 已通过、生产 route-off 迁移完成，并且生产路由已经能保证该 Skill 接受的每个
`answer_question` 都创建 V2 Run 时，Production Skill 才能同时更新 `SKILL.md` 与 wrapper Operation 允许集合。

单用户与单小说交集 allowlist 只授权维护者做 canary，不足以更新通用生产 Skill：allowlist 外小说当前可能
回落到 V1，而 V1 的 outcome/消息身份不是本契约。canary 必须使用维护者明确配置 userId/novelId 后的公共
CLI 调用；通用生产 Skill 继续拒绝 `answer_question`。只有 canary 通过并切到能覆盖该 Skill 全部目标的 V2 路由后，
才按本文件更新 Production Skill。Local Skill 也只能在其固定本地运行副本、Core 配置以及该 Skill 可操作的全部
用户/小说目标都保证 fresh 问答创建 V2 Run，并完成对应本地 canary 后开放；单一 allowlist canary 或代码存在都
不足以修改 Local wrapper 允许集合。

当前提交尚未部署，且 `route=all` 也未开放，所以当前时点两份已安装 Skill 都必须继续拒绝
`answer_question`。任何一步失败都保持 route-off 或回滚兼容镜像，不用 SSH、数据库、内部 API 或自拼 HTTP
绕过公共 CLI。

## 文风画像耐久迁移（2026-09-05）

本项实现与验证见 `2026-09-05-durable-style-portrait.md`。原网页整套画像仍是五节依次生成，单节重做仍只生成
指定一节；迁移后各节分别保存耐久执行事实，重启恢复不重新调用已完成的节。受理时即冻结全部参考资料，
受理后的参考文件增删不改变这次任务输入；五节全部成功才一次更新文风，单节只更新对应字段和原计数、汇总。

对 CLI / Skills 维护者的影响：

- 没有新增、删除或改名 CLI 命令；命令数 125、Operator 允许命令 45 不变。
- 原 `long.style.apply` / `long.style.clear` 的参数、输出、退出码与 Core 公共接口不变，无需迁移调用示例。
- CLI 仍不提供文风创建、参考上传、画像生成、单节编辑和文风删除命令；不要将内部 `style.portrait` 加入
  `long.agent.start.operation`，它是用户级资产的内部执行操作，不是小说级 CLI 启动参数。
- Agent 不直接对 CLI 暴露接口；普通 CLI 与 Operator 始终只访问 Core 公共 API。共享模型结果中的
  `plain_text_v1` 是内部路由，不是需要 Skill 传入的新参数。
- 后续只需在 Skill 的能力说明中保留“仅应用或清除已有文风”，不要把网页画像能力写成 CLI 已支持。
  本批不替换固定 JAR、不修改活动 Skills、不声称生产已生效。

## 资料索引耐久迁移（2026-09-05，仓内验收完成）

实施与验收状态以 `2026-09-05-durable-rag-embedding.md` 为准。本项改变服务器端索引执行和恢复方式，
不新增公共接口或 CLI 命令，也不直接修改活动 Skill、入口脚本或固定安装包。

- `long.reference.create/update/delete/reindex` 沿用既有参数、响应和退出码；`long.resources.get` 仍读取资料列表，
  不存在 `long.reference.list` 命令。具体允许集合仍以原
  CLI/Operator 契约为准，不因内部 `rag.embedding` 操作存在扩大 Skill 权限。
- `long.reference.reindex` 仍提交原 referenceId、expectedContentHash 等既有字段，202/accepted 只说明
  受理；后续通过 `long.resources.get` 回读资料的 `ragStatus`、`contentHash`、`errorMessage`，不能把受理当作已可检索。
- 正文变化使旧代次失效；同内容在终态后重建是新代次。断线后先回读资料状态，不应为恢复而自动反复
  reindex。服务器按已保存代次恢复未完成批次，不重复调用已完成批次，也不把旧结果覆盖新正文。
- 空正文的空索引直接 ready；超出原 64 块容量只报告索引失败，完整原文仍保留。没有新增索引积分扣费。
- 不传 batchIndex、模型名、端点、预算或内部 Run/Step ID，不加入 `long.agent.start.operation`，
  不通过 `long.task.watch` 假造原接口未返回的 RAG taskId，不给 CLI 开 Agent 直连入口。

维护 Skill 时只同步上述观察和恢复说明，无需增加命令、Python 依赖或新的凭据存储方式。

## 开发视频耐久迁移（2026-09-06，仓内与隔离跨进程验收完成）

最终状态以 `2026-09-06-durable-video-model-workflows.md` 为准。本批只替换已有拆镜、逐镜提示词的内部
执行方式，公开 Task 身份不变，不新增 CLI 命令、参数或 Agent 直连入口，也不替换本机固定 JAR。

- 仍用 `long.video.plan.start` 或 `long.video.prompt.start` 受理；保存原响应中的 taskId，使用
  `long.video.adaptation.watch` 观察原 adaptationId/taskId。断线后先用 `long.video.adaptation.get`
  回读状态，不用新的 clientRequestId 自动重启模型任务。watch 退出不等于取消。
- 内部逐阶段 Step ID、模型路由、预算和纠正次数不成为 CLI 参数。原 Task 的 pending/processing/completed
  等状态仍由 Core 投影；受理成功不表示生成或作者采用已经完成。
  原 Task.attemptCount 保留兼容计数，不等于 V2 模型 Step 数，也不能据此判断模型是否已执行；完成仍以
  Core 回读的任务状态和对应完整候选为准。
- 拆镜完成只提供候选，仍由作者使用原 `long.video.plan.confirm` 的 revision 参数确认；提示词仍是待保存
  批次，原 `long.video.prompt.save` 使用 candidateTaskId 等原字段保存。不能借用长篇 Agent 批准命令，
  不能直接覆盖正式方案或 PromptHead。
- 保持普通 CLI 的 125 个命令与两份 Operator 的 45 个允许命令。普通 CLI 存在视频命令不表示 Operator
  获准使用；本轮不向活动 Skill 白名单加入视频、不开放生产视频，不要求安装 Python/uv。
- Seedance 渲染、关键帧和整集导出不是本次模型迁移范围，不得把其恢复、收费或完成状态类推为已验证。

Skill 维护者只需同步任务观察、恢复与作者确认说明；如将来申请视频能力，仍需另行确定允许范围。
