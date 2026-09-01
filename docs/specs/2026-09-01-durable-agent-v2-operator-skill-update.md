# Durable Agent V2 Operator Skill 更新契约

## 状态与适用边界

- 日期：2026-09-01
- 状态：CLI 与共享契约代码已完成本地验证，但尚未进入 `main`、尚未部署生产；生产 Skill 在对应发布提交进入
  `main` 且 canary 门禁通过前不得提前开放。
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

两个已安装 Skill 目前仍未开放 `answer_question`，但已经单独完成一项不扩大业务能力的凭据诊断收紧：macOS
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

## 唯一行为变化

`long.agent.start` 的允许集合新增 `answer_question`。已有 Operation、输入字段、退出码、身份预检、固定
origin/profile、Keychain、幂等和 watcher 行为保持不变。Skill 不得把此次变化解释为开放全部 V2 Operation、
全部 scope 或 `route=all`。

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
| 请求含命令不认识的额外字段 | `UNEXPECTED_FIELD` | 0 次 |

Skill 不得把这些本地输入错误自动改写成另一种 Operation、scope 或默认会话，也不得在失败后换一个
`clientRequestId` 猜测重试。`auth.whoami` 失败时则必须更早停止，不能执行上表对应的任何业务命令。

## 观察与结果恢复

1. 从 `long.agent.start` 响应读取 `engineVersion` 与 `runId`，不能根据字段是否存在猜引擎。
2. 使用 `long.task.watch`，输入 `{"taskId":"<runId>"}`。中断只停止观察，不取消任务；继续观察同一 Run。
   V2 状态中的 `activeSteps` 必须存在且是数组，`artifact` 与 `error` 出现时必须是 `null` 或对象；CLI
   遇到显式类型错误会以契约错误失败关闭。Skill 不得在外层把该失败降级为“仍在运行”、自行修补响应或改走 V1。
3. `answer_question` 不会进入 `waiting_user`，不会创建 ReviewArtifact，也不能调用 Artifact 决定命令。
4. V2 成功终态为 `status=completed`。`long.task.watch` 输出的 completed JSONL 帧精确形状为
   `frame.type=event`、`frame.event=completed`；必须先核对 `frame.data.engineVersion=2` 与
   `frame.data.runId=<runId>`，再从 `frame.data.payload.outcomeType=chat_answer` 和
   `frame.data.payload.resultId=<WritingMessage.id>` 读取结果身份。不得从不存在的
   `frame.data.resultId`、顶层 `frame.resultId` 或日志文本猜测。
5. 使用 `long.session.get`，输入 `{"sessionId":"<writingSessionId>"}`，从 PostgreSQL 权威会话消息中读取
   对应的完整 Agent 回答。不得把 SSE 片段、日志或本地缓存当作最终回答。
6. 回答身份按以下优先级确定：
   - 若观察到 `completed(chat_answer)`，先以 `message.id == completed.resultId` 精确定位，再同时要求该消息
     `role=agent`、`metadata.source.engineVersion=2`、`metadata.source.runId=<runId>` 且
     `metadata.source.outcomeType=chat_answer`；任一不匹配都停止，不能只相信 `resultId`。
   - 若任意一次 PostgreSQL 持久状态对账已经得到 `completed`，但本次观察没有消费到 completed 事件（包括
     首次 GET 已完成，以及 running 后 SSE 断线、下一次 GET 才发现完成），则只按上述 role 与三项 source
     身份筛选；必须恰好得到一条消息，并以其 `id` 作为回答 ID。
   - 筛选结果为 0 条或多条均属于权威结果身份无法证明。Skill 必须停止并报告契约异常，不得选择“最后一条”、
     按 `agentId` 猜测、复用旧回答或重新启动同一问题。
7. 失败或取消不会留下成功的 Agent 消息；不得把已有旧消息误认成本次结果。

## Skill 文件更新清单

- `SKILL.md`：把 `answer_question` 加入 `long.agent.start` 允许集合，并保留“V2 必须显式 operation”的规则。
- `references/long-serial-workflow.md`：加入上述启动、watch、session 回读流程，明确无 Artifact。
- `references/cli-contract.md`：记录 `writingSessionId` 必填、稳定 `clientRequestId`、退出码与响应判别规则。
- `references/recovery.md`：删除“所有长篇只看 `outcome`”的 V1-only 假设，按响应中显式
  `engineVersion` 分流：V1 读取 `outcome.state`，V2 读取 `status`；V2 `answer_question` 完成后按本文件的
  Run/message 双重身份回读。watch 中断或提交结果不确定时只对账同一 `runId`/`clientRequestId`，不得新建 ID；
  V2 问答不进入 Run 的 `waiting_user`，也不恢复 Artifact 决定流程。
- `agents/openai.yaml`：同步 `default_prompt`，明确长篇必须按 `engineVersion` 分流，且
  `answer_question` 的 V2 成功结果是会话消息、没有 ReviewArtifact；不能继续把所有长篇任务概括为
  ReviewArtifact/outcome 闭环。
- wrapper 命令白名单不变，因为命令名未变化；不得新增任意前缀通配。
- wrapper 测试新增：合法问答原样透传；缺会话与错误 scope 在身份预检后零目标业务请求；watch 完成后
  `long.session.get` 回读。底层 CLI 单元测试另行证明非法输入本身可以在零网络条件下拒绝。
- wrapper 的合法问答测试必须断言请求正文逐字段等于调用方输入（仅由 CLI 补固定
  `workflow=long_serial`）；不得 trim `userInstruction`、补模型参数或删除 `writingSessionId`。
- 结果关联目前属于 Skill 的编排行为，现有 wrapper 不编排 watch→session，也不解析消息；因此必须用干净上下文
  forward-test 分别覆盖“收到 completed.resultId”“首次 GET 已 completed、未收到终态事件”和“running 后 SSE
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

## 生产启用门禁

只有当发布清单冻结的 Python CLI、Java CLI、Core 与 Agent 来自同一提交，两种 CLI 的同契约与跨语言
差异门禁全绿，开发库迁移与真实 provider canary 已通过、生产 route-off 迁移完成，并且生产路由已经能保证
该 Skill 接受的每个 `answer_question` 都创建 V2 Run 时，生产 Skill 才能开放该 Operation。

单用户与单小说交集 allowlist 只授权发布流程做 canary，不足以更新通用生产 Skill：allowlist 外小说当前可能
回落到 V1，而 V1 的 outcome/消息身份不是本契约。canary 必须使用发布流程冻结 userId/novelId 的公共 Python CLI
调用；通用生产 Skill 继续拒绝 `answer_question`。只有 canary 通过并切到能覆盖该 Skill 全部目标的 V2 路由后，
才按本文件更新 Production Skill。Local Skill 也只能在其固定本地环境已启用同一 V2 路由后开放，不能根据代码存在
就提前开放。

任何一步失败都保持 route-off 或回滚兼容镜像，不用 SSH、数据库、内部 API 或自拼 HTTP 绕过公共 CLI。
