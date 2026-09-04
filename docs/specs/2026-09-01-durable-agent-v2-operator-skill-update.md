# Durable Agent V2 Operator Skill 更新契约

## 状态与适用边界

- 日期：2026-09-01
- 终审更新：2026-09-04
- 状态：CLI 与共享契约代码已完成本地验证，但尚未进入 `main`、尚未部署生产。对应发布提交进入
  `main` 和 canary 通过都只是必要条件，不是生产 Skill 的充分开放条件；仓外不可变 controller、OIDC
  短期单 operation capability、真实双角色流式 broker、专用公钥轮换和 sealed genesis/current 任一未完成时，
  生产 Skill 必须继续拒绝 `answer_question`。
- 适用 Skill：`inkforge-short-story-operator`、`inkforge-production-short-story-operator`。
- 本次不新增 CLI 命令名，只扩展现有 `long.agent.start` 的一个显式 Operation。
- 上述两个现有 wrapper 当前实际调用 `tools/inkforge-cli` 的 Python CLI；Java CLI 是迁移目标但尚不能
  代替该事实。因此生产开放前必须由同一提交证明 Python 与 Java 两端对本契约全绿，不能只因 Java CLI
  已支持就提前修改 Skill。

### 当前本地验证证据

截至 2026-09-01，本工作分支已经完成以下本地门禁；这些结果只证明实现与契约一致，不代表生产已开放：

- Python CLI 与 CLI migration baseline 的最终全量门禁 `584 passed`，相关问答/Skill 契约架构门禁 `6 passed`；
- Java CLI 变更定向测试 `23/23`，Java CLI 模块 `verify` 为 `61/61`；
- `contracts/cli/parity-v2-contract-error-cases.json` 的 16 个错误场景与
  `contracts/cli/parity-watch-cases.json` 的 7 个 watcher 场景均由 Python/Java 跨语言测试读取；
- Python Ruff、CLI 源码 Mypy 与 `git diff --check` 均通过。

两个已安装 Skill 的 `SKILL.md` 目前仍未把 `answer_question` 列入允许集合，但现有 wrapper 只按命令名允许
`long.agent.start`，尚未按请求内的 `operation` 做硬拒绝。因此当前“未开放”只是一层必须遵守的 Skill 指令，不能
表述成 wrapper 已从技术上阻止该 Operation。按本文件更新 Skill 时，必须先补齐下文的 operation 级硬门禁；在各自
环境的启用条件满足前，该硬门禁仍须拒绝 `answer_question`。

两个已安装 Skill 已经单独完成一项不扩大业务能力的凭据诊断收紧：macOS
Keychain 原生调用失败时，wrapper 把受控 `MacOSKeychainError` 转成稳定的
`SECURE_CREDENTIAL_BACKEND_REQUIRED`，不再把它吞成泛化 `UNEXPECTED_ERROR`。该变化没有增加命令白名单、
不会读取或打印密码，也没有明文、环境变量或文件凭据回退。更新者必须在目标发布提交进入 `main`、本节测试由该提交
复跑、下文生产启用门禁满足后，才按“Skill 文件更新清单”开放问答；不得直接从当前工作树复制未发布业务行为。

### 凭据后端诊断契约

- `auth.whoami`、业务命令或登录流程若无法使用 macOS Keychain，wrapper 稳定输出
  `SECURE_CREDENTIAL_BACKEND_REQUIRED` 并以退出码 `3` 停止；不得自动切换到明文、环境变量、仓库文件或日志中的
  token。
- `auth.login` 的密码只允许用户在真实 TTY 的隐藏提示中输入。Skill、测试、文档和自动化不得把密码放入 argv、
  stdin 管道、环境变量、JSON、证据目录或聊天记录，也不得代替用户输入。
- 该错误只表示当前本机安全凭据后端不可用，不能被 Skill 解释为 `AUTH_REQUIRED` 后自动登录，也不能用浏览器 Cookie、
  自拼 HTTP、SSH、数据库或内部 API 绕过。
- 两个已安装 Skill 的离线回归必须分别覆盖：原生 Keychain backend error 被精确转换、错误文本不包含底层异常正文、
  backend 不可用时零目标业务请求。当前本机门禁为 production Skill `13 tests OK`、local Skill `16 tests OK`，
  两者各有 1 个只在当前宿主未提供原生 Keychain 测试条件时的显式 skip，且两份 `quick_validate.py` 均通过。

## 命令面与 Skill 行为变化

CLI 命令名不变；只有 `long.agent.start` 的 Operation 集合增加了 `answer_question`。已有 Operation 的输入和结果
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

两份 Skill 的 `scripts/operator_support.py` 必须在成功完成固定 origin/profile 的 `auth.whoami` 后、启动目标 CLI
业务命令前，对 `long.agent.start` 请求体的 `operation` 做精确字符串允许集合检查。该检查不是命令名前缀匹配，也
不能由环境变量、调用参数或普通 JSON 字段关闭：

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
| V2 Operation/执行器/发布 guard 不可用 | `DURABLE_OPERATION_NOT_ENABLED`、`DURABLE_AGENT_EXECUTION_UNAVAILABLE`、`DURABLE_AGENT_RELEASE_GUARD_UNAVAILABLE` | 4 或 5，以 CLI 原值为准 | 停止；不得回落 V1。门禁恢复后只允许用原请求与原 `clientRequestId` 对账/重放 |
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
- `scripts/operator_support.py`：命令白名单不变，因为命令名未变化；新增本文件定义的
  `long.agent.start.operation` 精确允许集合硬门禁，不得新增任意前缀通配或可由调用方覆盖的开关。Local 与
  Production 两份脚本必须分别按各自启用状态维护，不能因其中一个环境开放而同步放开另一个环境。
- `tests/test_operator.py`：新增当前未开放状态下 `answer_question` 返回
  `OPERATOR_OPERATION_NOT_ALLOWED`/退出码 2、一次身份预检且零目标业务请求；既有三种 Operation 继续透传；启用版
  合法问答原样透传；缺会话与错误 scope 在身份预检后零目标业务请求；watch 完成后执行 `long.session.get` 回读。
  底层 CLI 单元测试另行证明非法输入本身可以在零网络条件下拒绝。
- wrapper 的合法问答测试必须断言请求正文逐字段等于调用方输入（仅由 CLI 补固定
  `workflow=long_serial`）；不得 trim `userInstruction`、补模型参数或删除 `writingSessionId`。
- 结果关联目前属于 Skill 的编排行为，现有 wrapper 不编排 watch→session，也不解析消息；因此必须用干净上下文
  forward-test 分别覆盖“收到 `frame.data.payload.resultId`”“首次 GET 已 completed、未收到终态事件”和“running 后 SSE
  断线、下一次持久 GET 已 completed”，并覆盖 0 条、重复两条、message ID 与 source 身份冲突时全部 fail closed。
  不得在 `tests/test_operator.py` 中复制一份并未被 Skill 调用的筛选算法来伪装单元覆盖；若以后新增 Skill 实际调用的
  确定性离线 resolver，再把这些身份用例下沉为 resolver 单测。
- Python CLI 与 Java CLI 都必须通过合法问答请求映射、非法输入、V1 历史响应和 V2 status/SSE 游标的
  同契约测试；合法问答、watcher 和本地/响应错误分别由
  `contracts/cli/parity-success-cases.json`、`contracts/cli/parity-watch-cases.json` 与
  `contracts/cli/parity-v2-contract-error-cases.json` 直接驱动两种 CLI。差异门禁必须比较退出码、完整
  JSON/JSONL 帧和公共 API 调用记录，不能只验证其中一个实现或只比较错误码。
- 生产 Skill 仍必须先 `auth.whoami` 并精确核对预期用户名；密码只能由用户在真实 TTY 隐藏输入。

每份 Skill 更新后都必须运行 Skill Creator 的 `quick_validate.py <skill-directory>`，再运行该 Skill 的
`python -m unittest discover -s <skill-directory>/tests`。两项离线门禁与上述干净上下文 forward-test 全部通过，
才可把更新视为可安装；生产 Skill 仍须额外满足下一节的生产启用门禁。

## 发布控制面变化（Skill 维护者必读）

公共 Python/Java CLI 的命令名、参数和凭据边界没有因本次发布安全改造而变化；Skill 不需要新增 SSH、部署或
数据库命令，也不得把下列服务器 driver 动作加入 wrapper 白名单。变化只发生在受保护 GitHub 发布工作流和
服务器端控制面：

- development evidence v2 与 SSH/genesis 信任根分别见
  `docs/specs/2026-09-01-durable-agent-v2-development-evidence-v2.md`、
  `docs/specs/2026-09-01-durable-agent-v2-ssh-genesis-trust-root.md`。其中新增的离线 helper/broker 都不是产品 CLI，
  不得加入 Skill 命令清单；未来若真实 provider canary 的公共 CLI 输入、JSONL 或恢复语义变化，必须先改本文件再改 Skill。

- allowlist 发布改为单个 `finalize-allowlist-transaction` 进程串行完成 route-off → 精确 allowlist、postflight、
  receipt prepare、current commit point 与锁清理；runner 断联后的恢复只调用同 owner 的
  `transaction-status` / `reconcile-transaction`，不得人工重跑某条 DDL、Compose 或重新签发 lease；
- 每个 Compose、allowlist Core recreate 和每次生产 `psql -f` 前都会即时重采 live PG/Core/普通 Redis/
  execution Redis 身份与零 drain，并消费具名一次性 boundary。`claimed` 但没有 `applied` 表示结果未知，
  必须保留锁并进入具名恢复，禁止换 ID、复用旧 evidence 或直接重试破坏性命令；
- allowlist guard 状态只允许 `off → pending → committed` 或 commit point 前 `pending → off`。pending 绑定
  lock/run/manifest/control/scope/execution fingerprint、最长 120 秒且不可续租；Core 对 fresh V2 在幂等重放后、
  所有业务锁后紧贴首条 INSERT 再复验，失效时稳定 503 且不回落 V1；
- receipt 的唯一 commit point 是 current 指针原子替换、receipt 根目录 fsync 和精确重读。current 已精确指向
  本事务 candidate 后，只能补完 committed/finalize，绝不能写 `failed`、切回 route-off 或倒退 current；
- 当前 guard v1 只支持单 user + 单 novel allowlist，`route=all` 稳定拒绝。通用 Production Skill 因此仍不能
  把 canary 能力当作全量开放；缺 guard 文件/挂载时所有 fresh V2 同样稳定 503。

首次受保护发布还需要仓外、具名 bootstrap：必须已有可复验的受保护 current receipt，且当前生产 Core 必须真实
包含 V1 fresh-start gate。仓库不能证明任一条件时发布保持阻断；不得用裸 `git HEAD`、任意 40 位 SHA、手写
genesis receipt 或“人工先改 `.env`/重启”绕过。生产 SSH 还必须完成旧 key 撤销与新专用 forced-command/最小权限
证据；任一外部证据缺失时 SSH 步骤数必须为 0。

当前仓内 Workflow、checkout 前 guard 和 verifier 都来自候选可修改的 `github.sha`，不能成为自身信任根。生产 P0
只能由候选提交无法修改或取消的仓外执行根闭合：独立且受 ruleset 保护的 release repository，或其中 full-SHA 固定的
required reusable workflow，并叠加 custom deployment protection；外部执行器按 GitHub OIDC 的精确
repository/workflow/ref/SHA/run subject 换取短期、单 operation broker capability。真实双角色流式 broker、
`authorized_keys` 专用公钥轮换、旧 key 撤销、sealed genesis/current receipt 链和上述策略的仓外 API/攻击演练证据也
必须同时存在。仓内语义 attestation、environment 审批、main 合并或 canary 全绿都不能替代该 P0。

## 生产启用门禁

只有当上述仓外不可变执行根、OIDC 短期 capability、真实 broker、公钥轮换和 sealed genesis/current P0 全部闭合，
且发布清单冻结的 Python CLI、Java CLI、Core 与 Agent 来自同一提交，两种 CLI 的同契约与跨语言差异门禁全绿，
开发库迁移与真实 provider canary 已通过、生产 route-off 迁移完成，并且生产路由已经能保证该 Skill 接受的每个
`answer_question` 都创建 V2 Run 时，Production Skill 才能同时更新 `SKILL.md` 与 wrapper Operation 允许集合。

单用户与单小说交集 allowlist 只授权发布流程做 canary，不足以更新通用生产 Skill：allowlist 外小说当前可能
回落到 V1，而 V1 的 outcome/消息身份不是本契约。canary 必须使用发布流程冻结 userId/novelId 的公共 Python CLI
调用；通用生产 Skill 继续拒绝 `answer_question`。只有 canary 通过并切到能覆盖该 Skill 全部目标的 V2 路由后，
且上述仓外 P0 全部闭合，才按本文件更新 Production Skill。Local Skill 不依赖生产 SSH 信任根，但也只能在其固定
本地运行副本、Core 配置以及该 Skill 可操作的全部用户/小说目标都保证 fresh 问答创建 V2 Run，并完成对应本地 canary
后开放；单一 allowlist canary 或代码存在都不足以修改 Local wrapper 允许集合。

当前仓内发布 Workflow 在 streaming broker/sealed genesis 门禁处固定失败，`route=all` 也未开放，所以当前时点两份
已安装 Skill 都必须继续拒绝 `answer_question`。任何一步失败都保持 route-off 或回滚兼容镜像，不用 SSH、数据库、
内部 API 或自拼 HTTP 绕过公共 CLI。
