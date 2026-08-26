# Core Java 单体替换

日期：2026-08-24

状态：已批准；Java Core 已于 2026-08-26 原位接管生产，部署来源传输与质量终检二次回归均已通过生产验收

基线提交：`c9afc95`

## 背景

当前 FastAPI Core 独占 PostgreSQL 访问、浏览器认证、业务规则、计费、ReviewArtifact、SSE、文件和
后台补偿任务。用户决定把 Core 及其后台职责、CLI 迁移到 Java 21 与 Spring Boot，保留 Python Agent
和 Next.js 浏览器前端。迁移完成后再新增手机号注册、支付等商业能力，并以本次迁移实践 TDD。

迁移不是逐行翻译 Python，也不是新增第二套生产 Core。当前产品行为、数据结构、Agent 契约、Web 和 CLI
是迁移输入；Java 必须先证明等价，再一次性接管现有 `core-api` 服务。

## 当前事实

- 产品基线见 `docs/requirements/00-overview.md`；
- 公共 OpenAPI 有 115 个路径、148 个操作；
- Core 另有 30 个不进入公共 OpenAPI 的内部操作；
- CLI 注册 125 个具体命令，但不是公共 API 全量镜像；
- 开发结构契约有 85 张表、22 个枚举，指纹为
  `8aaa4d25c3cd3114bc8659330700a2eecdbcdefc7f3d83473c93c1baee576629`；
- Python Agent 依赖 Core 工具网关、模型授权和用量上报、写作/质量/文风/RAG/视频回调；
- 生产服务名为 `core-api`，回滚依赖上一提交的 Python Core 镜像；
- 生产当前运行 Java Core 提交 `f54ebb03947f13807f110d4ce1e22188dd32ff16`；容器健康不等同于
  Core 到 Agent 的业务投递链路可用，切换后仍必须用真实浏览器和跨服务 POST 闭环验收；
- 视频 P0-P3 只获开发库授权，生产配置必须继续拒绝视频写入和真实 Seedance。

## 目标

1. 用 Java 21、Spring Boot 4.1.1、Spring MVC、jOOQ/JDBC 和 Spring Modulith 完整替换 FastAPI Core。
2. 保持全部公共/内部 HTTP 契约、错误、Cookie、SSE、文件、事务、副作用和恢复语义。
3. 使用 characterization、单元、真实 PostgreSQL 集成、差异、故障注入和端到端测试执行 TDD。
4. 在隔离测试数据库通过后，使用 `novelwriterdev` 开发库执行真实 Java Core 验收；不写生产库。
5. 全量测试通过后更新镜像、Compose、CI、部署、smoke 和回滚流程，使 Java Core 一次性接管生产服务。
6. 稳定观察期结束后删除 Python Core 和 Python CLI，保留 Python Agent 所需契约与服务鉴权实现。

## 非目标

- 不增加手机号、短信、邮箱、支付、订单、订阅、退款或新计费产品；
- 不修改现有 PostgreSQL 业务结构，不迁移业务数据，不启用自动 DDL；
- 不改变 API 路径、字段、operationId、状态码、错误码、Cookie、SSE 或业务状态机；
- 不在生产并行运行两个 Core，不双写，不按路由渐进切流；
- 不迁移 Agent、LangGraph、模型提示或供应商策略；
- 不把 Web 改写为 Java 服务端页面；
- 不在迁移中启用生产视频或执行未批准的生产迁移。

## 2026-08-26 生产切换后回归修复

### 生产证据

生产真实浏览器验收和只读日志诊断确认四个相互独立的问题：

1. Java `HttpClient` 默认尝试明文 HTTP/2 升级，向 Uvicorn 的
   `POST /internal/v1/runs` 携带 `Upgrade: h2c`；Agent 返回 400，写作、质量和画像等所有共享
   Agent job 提交均停留在 PostgreSQL 待重试状态。GET readiness 可以回退到 HTTP/1.1，因此原健康检查
   仍错误显示全绿；
2. 中短篇非选区请求按冻结 OpenAPI 正确发送显式 JSON `null`，Java 原始请求解析器却只区分字段缺失和
   Java `null`，把 Jackson `NullNode` 错当成整数并返回 422；
3. 画像任务首次提交失败后保持 `pending`，但生产没有画像 dispatcher 重试日志。画像装配仍使用顺序敏感的
   `@ConditionalOnBean(PortraitRunSubmitter.class)`，违反本规格已经对写作 dispatcher 确立的确定性装配规则；
4. 写作 SSE 虽每 15 秒发送心跳，Spring MVC 默认异步总超时仍约 30 秒。超时后全局 JSON 异常处理器尝试
   向已提交的 `text/event-stream` 写 `ApiErrorResponse`，形成重复断流和二次转换异常。

### 修复设计

- Core 到 Python Agent 的专用 `HttpClient` 必须显式固定 `HTTP_1_1`。超时、签名、正文、路径和错误码保持
  不变；不得通过修改 Uvicorn、开放额外端口或绕过服务身份修复；
- 原始 JSON 可空整数校验必须同时接受字段缺失与显式 `null`，但非空值仍只接受范围内整数，选区操作的
  必填与范围规则保持不变；
- 画像 dispatcher 必须始终随数据库文风仓储装配，并通过延迟端口解析处理 Agent 投递器是否存在；未配置
  Agent 时记录稳定可重试错误，不返回空 Bean，也不让 Spring 配置扫描顺序决定恢复能力；
- 长连接 SSE 必须显式关闭 Spring MVC 的总异步超时，继续依靠 15 秒心跳、客户端断开和 PostgreSQL
  `streamShouldClose` 收敛。该设置同时避免大文件流被框架总超时静默截断；客户端断开不得被转换成 JSON
  错误正文；
- 不修改 PostgreSQL schema、公共/内部 OpenAPI、Agent Pydantic 契约、计费单价、模型策略或生产视频开关。

### TDD 与验收

- 先增加配置级测试，证明 Agent 专用客户端不是 HTTP/2 默认值，并断言实际请求不携带 h2c 升级头；
- 先增加中短篇显式 `null` 请求测试，覆盖生成大纲、生成正文和全文检查的非选区字段；
- 先增加画像装配测试，证明实际投递 Bean 尚未出现时 dispatcher 仍存在，稍后出现时可解析同一端口；
- 先增加 Spring MVC 异步配置测试，证明运行时总超时被显式禁用；保留 SSE 心跳、终态关闭和游标回放测试；
- 相关测试通过后运行完整 `./mvnw verify`。Java Core 就绪检查启动后必须先使用同一个生产客户端向真实
  Uvicorn 发送一次 `{}` 无写入 POST，以 Agent 的 401/422 应用层拒绝证明协议链路成立，再持续执行 GET
  ready；Compose smoke 必须同时断言 `checks.agent=ok`，不得再以两个服务各自 GET ready 代替跨服务协议
  验收。真正的任务提交仍由 `AgentServiceClient` 测试覆盖 Ed25519、原始正文和幂等键；
- 修复部署后回读原任务状态或创建具名测试任务，确认写作、质量和画像至少各有一个任务进入 Agent 队列并
  正常收敛；不得把 202、SSE 或容器 healthy 当作完成证据。

### 本地验证证据

- HTTP 版本、真实请求头、显式 `null`、画像确定性装配、SSE 异步配置及 POST 门禁的定向 JUnit 全部通过；
- 画像、写作、质量三条 Spring Boot + PostgreSQL Testcontainers 运行时回归通过；
- 本地真实 Uvicorn 对无写入 `{}` POST 返回预期 422，证明探针不会进入任务队列；
- 部署、回滚及 Compose 安全相关架构测试共 75 项通过，Ruff 与 Shell 语法检查通过；
- 最终 `./mvnw verify` 通过：Core 411 项无失败、2 项外部数据库验收按配置跳过，CLI 49 项无失败。

## 2026-08-26 生产质量终检二次回归

### 生产证据

- 提交 `f54ebb03947f13807f110d4ce1e22188dd32ff16` 已通过 CI、镜像上传、生产原位替换、schema guard 与
  Compose smoke；生产 Web、Core、Agent 均运行该提交且无重启、OOM 或不健康状态，公网 readiness 明确返回
  `checks.agent=ok`；
- 部署前积压的文风画像已完成，长篇写作已进入等待作者确认；生产浏览器新建的中短篇蓝图任务已完成一次
  真实模型调用并形成候选，SSE 连续运行超过 30 秒，证明 HTTP/1.1、画像补投、显式空值和异步超时的首轮
  修复已经在真实环境生效；
- 同一账号新建的一致性终检运行 `cmt9obe8jlcbks5e2jq6150zw` 在 Agent 人工日志开始后约 37 毫秒即以
  “错误”结束，且没有模型调用或模型失败帧；此前积压质量运行也以相同方式失败，因此不是旧任务载荷的单例；
- 当前 Agent 普通容器日志只能看到“后台任务意外结束，等待监督器重启”，没有安全错误分类、任务标识或异常
  类型；初始生产证据只能把故障定位到质量 handler 的模型调用前阶段。随后 TDD 先证明内部质量上下文能正确
  接受显式 `null`，再以真实 PostgreSQL 红灯证明：无来源 WritingTask 时 Agent 按契约用
  `WorkflowRun.id` 申请模型授权，而 Java 计费仓储只按 `ChapterQualityCheck.id` 查找，导致授权在 Provider
  调用前失败。`ModelRuntime` 又丢失 Core 的明确不可重试决定，质量 handler 回写失败后把普通
  `RuntimeError` 交给队列，造成不必要的消费者监督器重启。

### 修复设计与 TDD 门禁

- 先用真实 Spring HTTP、PostgreSQL、Redis、Ed25519 和 Python Agent 非付费执行器复现“无可选
  `sourceTaskId/message` 的质量运行”，覆盖公共创建、队列领取、内部上下文、报告回调和 PostgreSQL 权威终态；
  不得只用 Java 内存 submitter 或直接伪造内部回调证明闭环；
- 内部质量上下文必须继续区分字段省略和显式 JSON `null`，两者都按冻结 Python 契约解释为“没有可选值”；
  非空任务仍必须精确绑定同一作者、小说和章节，不能为通过测试放宽服务身份或资源校验；
- 计费授权必须优先沿活动 `WorkflowRun(kind=quality_check) -> ChapterQualityCheck -> Chapter -> Novel -> User`
  完整归属链解析运行 ID，并限制运行与检查项均为活动状态；冻结基线中直接使用检查项 ID 的历史调用继续保留
  兼容分支，但不得让终态运行、跨作者或跨小说获得模型额度；
- `QualityJobHandler` 必须在模型前、模型中和 Core 回调失败时形成不含正文、令牌或供应商原文的安全分类日志。
  已成功写回质量失败终态的业务异常必须作为已知非重试任务收敛，不能让整个队列消费者退出；失败回调自身
  暂时不可用时保留可重试语义，不能用第二个异常覆盖首个安全错误分类；
- 修复不得修改 PostgreSQL schema、公共/内部 OpenAPI、质量报告契约、计价、模型策略、Agent 数据边界或
  生产视频开关。若根因属于现有契约实现，只修实现与测试；如发现冻结契约本身矛盾，必须另行申请变更；
- 本地定向测试和完整 `./mvnw verify`、Agent pytest/Ruff/Mypy 通过后，重新走提交、推送、生产部署和真实浏览器
  循环。最终验收必须看到一条新质量运行完成模型调用、内部成功回调和公共检查结果落库；202 或容器健康不能
  代替该终态证据。

### 本地闭环证据

- 使用独立 PostgreSQL 卷、真实 Java Core、真实 Python Agent、Redis、Nginx 和非计费 Fake Provider
  启动六容器隔离栈；没有连接开发库或正式库，也没有修改 schema；
- Playwright 用例 `用户可以运行质量检查并查看模拟模型零扣费摘要` 已走通注册登录、创建长篇、编辑章节、
  送审、执行一致性终检、内部上下文、以 `WorkflowRun.id` 取得模型授权、结构化报告成功回调和公共结果回读；
  认证准备与业务用例共 2 项通过；
- 隔离栈的 Core/Agent 日志没有新增消费者意外退出、h2c、无效 HTTP、异步超时、模型授权失败或质量提交失败；
- Agent 定向 pytest 51 项及全量 846 项、全仓 Ruff、Mypy 通过；`npm run api:check` 证明公共契约未漂移；
  完整 `./mvnw clean verify` 通过，其中 Core 412 项无失败、2 项按外部环境跳过，CLI 49 项无失败。上述证据
  只证明本地修复可部署，仍需完成生产部署后的新运行终态验收。

### 生产部署来源传输修复

- 提交 `4064adb` 的首轮部署在镜像上传阶段遇到 SSH 退出码 255，未执行生产切换；具名空提交
  `b527e2a` 受控重试后镜像上传成功，证明首次故障为瞬时传输中断；
- 第二轮在服务器代码获取阶段连续三次失败：一次 GitHub HTTPS TLS 非正常终止、两次约 130 秒连接超时。
  失败发生在镜像切换前，线上仍保持上一健康版本；继续提交碰运气不能算完成部署；
- CI runner 已持有 `fetch-depth: 0` 的权威 checkout 和精确 `github.sha`。部署必须从该 checkout 创建只包含
  目标提交可达历史的 Git bundle，经现有固定 known_hosts、BatchMode 和受控超时上传到服务器具名临时文件；
  服务器只能从该 bundle fetch，并再次校验本地提交等于 `DEPLOY_SHA` 后才允许读取配置、冻结回滚镜像或切换容器；
- bundle 必须先写入同目录 `.partial`，完整上传后原子改名；路径只能由 40 位小写十六进制 `DEPLOY_SHA`
  推导，部署脚本结束时无论成功失败都删除本次 bundle。不得把私钥、Token、`.env` 或服务密钥打入 bundle；
- 生产服务器直接访问 GitHub 只保留为没有提供 bundle 时的人工兼容路径。标准 GitHub Actions 部署必须提供
  bundle，不能因服务器公网 GitHub 路由故障阻断已通过 CI 的版本；
- 先用架构测试证明 workflow 创建、验证并上传精确 bundle，再用隔离 shell 夹具证明服务器从 bundle fetch、
  校验 SHA、清理临时文件且不调用远端 origin；通过 Shell 语法、部署架构测试和 Compose 安全测试后再提交部署。
- 红灯测试先得到 4 项预期失败；实现后部署定向测试 58 项、包含 Compose 与迁移门禁的相关测试 92 项、
  全量架构测试 222 项均通过，Ruff、`bash -n`、`sh -n` 和差异空白检查通过。真实 Git 对约 7.1 MB bundle
  完成 create、verify、fetch 和 `FETCH_HEAD == HEAD` 校验，且临时目录已清理。

### 生产闭环与评分展示回归

- 提交 `922c480b346d34939d0e36896dfc05b15dee9888` 的 GitHub Actions #116 已成功完成 CI、镜像上传、
  deployment source bundle 上传和远端部署，deploy job 用时 13 分 54 秒；公网 readiness 随后返回
  Redis、数据库、Agent、数据库结构、写作出站箱和后台任务全部 `ok`，证明标准部署不再依赖生产服务器访问 GitHub；
- 生产账号 `nie` 在既有长篇验收实例中重新执行一致性终检。新运行越过原先约 37 毫秒的授权失败点，完成
  真实模型扣费与结构化回写，公共页面显示 `完成`、`可通过`、`1/1 已处理`，并展示完整报告和总分 87；
- 该回归同时发现 Web 把百分制 `scoreOverall=87` 错误拼接为 `87/10`。共享质量报告与持久化契约始终是
  0..100，修复只调整 Web 展示和色阶：总分显示 `/100`，百分制色阶沿用原十分制门限的等比例 50/70；
  历史六项商业性评分继续保持十分制。该修复不修改数据库、OpenAPI、质量结果、计价或 Agent 行为，并以
  先红后绿的前端测试锁定。

## 目标架构

```text
浏览器 -> Nginx -> Next.js
                    -> Java Core -> PostgreSQL
                                 -> Redis
                                 -> 受控文件 / FFmpeg
                    Java Core <-> Python Agent

Java CLI ----------> /api/v1/**
```

Java Core 仍是唯一数据库业务所有者。开发差异测试允许 Python 和 Java 使用两个结构一致但完全隔离的
数据库；任何环境都禁止两个实现同时写同一个数据库。

模块依赖遵循应用端口单向规则：`writing`、`quality`、`video` 等业务模块定义自身需要的 Agent 出站端口，
`agentgateway` 只能依赖这些公开应用端口并提供适配器，业务模块不得反向导入 `AgentServiceClient` 或网关
异常。`operations` 只托管后台生命周期；对受 `DATABASE_URL`、`REDIS_URL` 等配置门禁的组件必须通过
可选协作者装配，缺少对应外部依赖时不注册检查或后台循环，但最小健康上下文仍必须可以启动。

## 实施范围

### Java Core

迁移以下模块：

- 平台：配置、requestId、错误、可信代理、健康、文件、安全和后台监督；
- 身份：注册、登录、JWT Cookie、限流和资源归属；
- 小说：项目、章节、设定、大纲、伏笔、参考资料、文风和中短篇版本；
- AI 控制面：写作会话、持久命令、Agent 工具网关、质量、ReviewArtifact、正式应用、Outbox 和 SSE；
- 计费：grant、TokenUsage、CreditLedger、任务归集和幂等；
- 视频：素材、章节改编、视觉版本、提示词、Seedance 任务、Take、关键帧、粗剪、声音字幕和导出；
- 运维：schema guard、readiness、日志、FFmpeg 和部署 smoke。

### Java CLI

迁移现有 125 个命令名、stdin JSON、stdout JSON/JSONL、文件输入输出、TTY 密码和退出码。迁移过程中
Python CLI 继续作为兼容客户端；Java CLI 全量等价后才替换正式操作入口。

- 先从 Python registry 只读导出语言中立命令基线，冻结命令顺序、输入/输出模式、文件输出能力、读写性质、身份和 `clientRequestId` 要求；Java registry 与 README 都必须逐项匹配该基线；
- Java CLI 是独立 Maven 可执行模块，不依赖 Spring Core 实现、jOOQ、数据库驱动或 Agent。内部按运行时、公共 HTTP/SSE 传输、安全凭据与配置、原子文件、本地快照、短篇命令、长篇命令和视频命令拆分，不把 125 个命令堆入单个分派类；
- Picocli 只负责唯一交互命令 `auth.login` 的参数/TTY 入口和顶层命令分派；其余命令仍拒绝 argv，从 stdin 严格读取一个完整 UTF-8 JSON 对象。公共 DTO 和 API 客户端继续从同一冻结 OpenAPI 生成，不手写第二套契约模型；
- 配置文件只保存 profile 与规范化 Core origin。会话 Cookie 只能进入操作系统安全凭据后端，不得进入配置、stdout、stderr、异常、日志或进程参数；没有受支持安全后端时登录必须失败，不能降级为明文文件；
- 文件读取保持原始 UTF-8/字节，文件写入必须在目标目录排他创建临时文件、完整写入并同步后原子替换；watcher 只观察服务端事实，Ctrl-C 或网络超时不得隐式取消远端任务。
- CLI 差异门禁必须直接调用两种实现，而不能只比较各自测试结果。第一层对 registry 中全部 125 个命令使用相同最小输入、内存身份和 fake Core 故障，逐项比较退出码、stdout JSON/JSONL 与 stderr；完整验收还必须补齐成功请求映射、文件字节和 watcher 时序 fixture，第一层通过不得被表述为逐命令全等价完成。

截至 2026-08-25，独立 Java CLI 模块已按语言中立 registry 实现全部 125 个命令，并在启动时强制校验
处理器集合与基线零缺口。短篇本地快照、长篇写作与 Review/质量控制、全部 41 个视频命令以及 5 个
JSONL watcher 已接线；公共传输支持严格 Cookie JSON、重复查询参数、SSE 游标重连、流式 multipart 上传
和原子二进制下载。macOS Keychain 与 Windows Credential Manager 是仅有的生产凭据后端，Windows 实现
兼容旧 Python keyring 的复合 target 和 UTF-16 凭据格式，其他系统不降级。公共 OpenAPI 的 148 个操作
在 clean build 中机械生成并编译，但生成客户端及其 Jackson 2/HTTP 依赖不进入发行 JAR；运行时继续使用
不丢显式 null 的原始 JSON 传输。所有 JSON 文件输出现统一使用与既有 Python 客户端逐字节一致的稳定
缩进、UTF-8 和尾换行，避免迁移改变内容哈希。当前 49 项 Java CLI 测试、526 项 Python CLI 回归和 14 项 Python
registry/迁移基线测试通过，fat JAR 已在 macOS 直接启动并验证稳定错误信封与退出码；直接跨进程差异测试
已遍历全部 125 个命令的最小输入和 fake Core 错误边界，并据此修复中短篇文案、必填校验顺序、章节路径
校验顺序和质量状态错误语义偏差；另有 30 条跨产品代表成功链路和全部 5 个 watcher 的共享 fixture 已
直接比较输出、公共请求映射、JSONL 帧与终态退出码；10 条文件链路进一步直接比较文本/JSON 产物字节、
SHA-256、文件描述符、UTF-8 文件输入、multipart 素材上传和三类二进制下载。其余命令的成功分支尚未形成
逐命令共享 fixture，真实开发环境账号验收和生产操作 Skill executable 切换也未完成，因此 Python CLI
仍是正式入口。

### 保留 Python

- `apps/agent-service`；
- Agent 仍需的 `packages/service-contracts` 和 `packages/service-auth`；
- Java 与 Python 共享的语言中立 JSON Schema 和 golden vectors；
- Python Core 测试与兼容启动方式，直到生产观察期结束。

## TDD 与契约策略

每项可观察行为按以下顺序实施：

1. 从 Python 代码和测试导出 characterization fixture；
2. 先写 Java 测试，证明未实现时失败；
3. 编写最少 Java 实现使测试通过；
4. 增加权限、冲突、幂等、回滚、重启和资源失败测试；
5. 重构并保持测试绿色；
6. 在两个隔离 PostgreSQL 实例运行同一场景，比较归一化响应和数据库结果；
7. 运行现有 Web、Python Agent 和 Python CLI 对 Java Core 的黑盒测试。

业务差分不得把两种实现接到同一数据库，也不得仅比较各自已有测试是否通过。共享 fixture 必须声明每个
HTTP 步骤、预期状态、后续步骤确实需要捕获的动态值、允许归一化的时间字段以及只读最终快照查询；测试
分别启动完整 Python Core 与 Java Core、独立 PostgreSQL/Redis 和独立上传目录。除 fixture 具名声明的
ID、令牌与时间外，响应 JSON 不允许模糊比较；最终数据库快照只排除随机主键、密码哈希和审计时间，不得
排除业务状态、完整正文、余额、版本或关联副作用。

当响应字段是已声明随机 ID 的密码学派生值时，fixture 可以使用具名 `derivedNormalizations`，但测试运行器
必须先按该字段的公共规范独立重算并逐字节验证，再把它替换成稳定占位符参与双实现比较；禁止只检查格式、
直接忽略字段或把普通业务值列为派生值。当前唯一允许的算法是中短篇版本 `confirmationHash` 的规范化
SHA-256，它必须同时绑定文档类型、章节、基础版本、工作稿哈希、目标版本和不含哈希本身的完整 Diff。

基线目录：

```text
contracts/core/public-openapi-python-baseline.json
contracts/core/internal-endpoints.json
contracts/core/route-inventory.json
contracts/core/error-fixtures/
contracts/core/sse-fixtures/
contracts/core/service-auth-fixtures/
contracts/core/behavior-fixtures/
```

公共契约差异必须先更新本 spec 和产品基线；迁移实现不得为了方便自行改变基线。

Python Core 除具名启用 `response_model_exclude_none` 的接口外，会把响应模型中取值为 `None` 的字段序列化为
显式 JSON `null`；这项既有线格式不能因 Java 迁移而变成“键缺失”。Java 响应 DTO 必须继续使用普通可空
引用：OpenAPI 中列入 `required` 且允许 `null` 的字段不得增加 `@NotNull`，未列入 `required` 但带
`x-inkforge-source-nullable` 的响应字段也必须由受控生成模板使用 `JsonInclude.ALWAYS` 保留显式 `null`。
只有请求图中需要区分“字段缺失”和“显式 null”的字段使用 `JsonNullable` 与缺失校验；健康检查等 Python
端已经具名排除空值的接口继续按各自响应 DTO 的显式规则省略空键，不能用全局 ObjectMapper 开关混改。

### 维护性注释门禁

Java 等价迁移不能只依赖外部 spec 和测试解释实现。高风险代码附近必须使用简体中文记录后续维护者和 Agent
无法仅从语法可靠推出的设计理由，但不得用逐行翻译式注释掩盖职责混杂：

- 状态投影、回调和后台任务说明 PostgreSQL 权威事实、允许的状态转换、重放条件以及何时必须投影为
  `inconsistent`；Redis、SSE 和供应商状态不得被注释成最终业务事实；
- 每个跨表写事务说明锁顺序、幂等检查相对业务校验的先后、同事务提交范围，以及文件、Redis 或供应商
  副作用失败后的补偿责任；关键顺序不能只散落在 SQL 调用中；
- Python 兼容分支、历史字段和值域修正说明兼容的冻结行为、不能采用更直观实现的原因以及删除条件；
- Spring 装配和后台循环中的批量、间隔、超时及条件 Bean 说明资源预算和失败语义；部署、smoke 与回滚脚本
  按阶段标注执行目的，并说明 trap、原始失败码、镜像责任和禁止数据库反向迁移等不变量；
- Web 的 SSE、会话消息和审核状态对账说明临时展示状态与 Core 权威状态的边界，避免后续把旧事件载荷或
  乐观 UI 重新当成可操作业务事实；
- 简单 DTO、getter、生成客户端、显然的字段赋值和与名称完全重复的方法不要求注释。注释质量不按行数或
  覆盖率计分；发现一个类需要大量叙述才能解释多个无关职责时，应另立重构任务拆分，而不是继续堆注释。

本轮注释补强不改变公共/内部契约、数据库结构、锁顺序、状态机、超时值或产品行为。完成后运行格式、编译、
相关测试与全量 Java 验证，证明改动只增加维护语义。

## 数据库策略

- 单元测试不使用 H2 模拟 PostgreSQL；数据库测试使用 PostgreSQL 14 + pgvector Testcontainers；
- Java 只读解析当前 `schema-contract.json`，实现与 Python 等价的结构指纹和 profile；
- 不启用 Hibernate/JPA DDL、Flyway、Liquibase 或启动期 SQL；
- jOOQ 代码从受控测试 schema 生成，不手写数据库表 DTO；
- 启动受监督后台循环的 Spring/Testcontainers 完整上下文必须在测试类结束时主动关闭，再释放 PostgreSQL、Redis 和文件资源；测试不得让后台线程访问已停止容器并用预期外部故障污染后续 TDD 日志；
- 验证“未配置外部依赖”的最小 Spring 上下文时，测试必须显式覆盖 CI 继承的数据库、Redis 等占位配置，
  不能依赖执行机恰好没有环境变量，也不能通过放宽生产 readiness 掩盖测试环境污染；
- 本地测试先使用隔离数据库，随后连接 `novelwriterdev` 做只读 schema guard 和具名测试数据验收；
- dev 验收数据使用唯一前缀和精确 ID，记录创建清单并按清单清理，不扫描或删除其他用户数据；
- 禁止连接或写入 `novelwriter` 正式库。生产仅在最终切换门禁中做只读指纹、备份和 smoke。

Java 业务开发库验收必须启动真实 Spring HTTP 应用，并只从具名 `INKFORGE_DEV_DATABASE_URL` 取得连接；
连接串解析结果和数据库自身 `current_database()` 都必须精确等于 `novelwriterdev`，任一门禁不满足时在首个
写请求前失败。验收使用隔离 Redis、关闭真实 Agent/模型与 Seedance 投递，以随机 `jacc_` 用户名创建长篇、
章节正文、设定、资料、中短篇版本和非付费视频项目等代表事实，再通过公共接口回读。测试必须记录用户、
小说及文件的精确 ID，并在 `finally` 中先按 ID 删除本次小说、再按 ID 与用户名删除本次用户，最后查询确认
零残留；禁止按前缀批量删除、复用现有账号或把清理失败当作测试成功。

## 产品不变量

- 作者确认是 Agent 正式写入的唯一入口；
- 正文、进展、设定、大纲、伏笔、Beat Plan 和视频后期决定不得混写；
- 选区、改编、提示词、渲染和导出必须冻结来源；
- 不静默截断正文、草案、Diff、工具结果、日志或持久数据；
- `clientRequestId`、时间戳和 revision 的幂等/CAS 语义保持不变；
- 异步 202、SSE 和 JSONL 不代表完成，PostgreSQL outcome 才是权威；
- 历史版本不可变；软质量建议不能替代作者确认；
- Agent、浏览器和 CLI 不得绕过 Core 数据和服务身份边界。

### 长篇设定域迁移约束

长篇设定域的 Java 实现必须覆盖现有 32 个公共操作，并保持以下可观察行为：

- 人物、物品、地点、势力和术语共用一致的安全写入协议，但各自字段、枚举和关联类型保持强类型；
- 创建以 `kind + userId + novelId + clientRequestId` 生成确定性 ID；仅初始版本且请求内容完全一致时允许幂等重放，资源曾被修改后即使恢复原值也不得伪装成首次重放；
- 更新和删除必须在同一事务中先锁定小说，再锁定目标行并校验 `expectedUpdatedAt`；相同内容更新不推进版本；
- 人物所属势力、物品持有人、地点父级、势力驻地、经历所属角色/章节和关系两端都必须属于当前小说；地点父级不得形成直接或间接循环；
- 删除人物、地点或势力前必须完整统计受影响关系、经历、物品、状态历史、子地点、驻地和领地绑定；存在引用时拒绝删除，禁止依赖级联静默丢失；
- 人物经历和人物关系沿用确定性创建、初始版本重放、CAS、跨小说隔离和精确目标删除；经历未指定顺序时在该角色内按最大顺序递增；
- 故事背景、世界设定和作品圣经是按小说唯一的单例资源；首次创建要求空版本，后续写入要求精确 CAS；故事进展继续使用被锁定的 `Novel.updatedAt` 作为版本；
- 故事背景和世界设定不接受 `content=null`，故事进展保留可空语义且不得超过 30000 个 Unicode 字符；内容必须逐字保存，不修剪、不换行归一化、不截断；
- 作品圣经只接受长篇模式，空补丁拒绝，显式 `null` 与字段省略保持不同语义；
- ReviewArtifact 应用所需的设定与经历批量变更必须复用同一仓储事务，一条失败时整批回滚，不能退化为逐接口提交。

### 小说与工作区迁移约束

- 小说创建必须在一个事务中初始化小说、首章、文本总纲、剧情进度和作品圣经；任何一步失败不得留下半成品；
- 长篇默认目标字数为 1000000，首章名为“第一章”；中短篇必须显式提供 6000..80000 目标字数、16..128 字符请求标识、素材类型和非空素材，首章名为“全文”；
- 中短篇 `opening` 只初始化全文草稿，`outline` 只初始化文本总纲，其他素材类型不提前写入正式草稿；原始素材必须另存为已应用、带 revision 的 ReviewArtifact，并以请求标识摘要实现创建重试幂等；
- 小说名及可选元数据只在应用边界按既有规则去除首尾空白；正文、起始素材和工作区内容不得清洗或截断；
- 摘要更新先校验归属和 `expectedUpdatedAt`，再判断幂等；缺失小说返回 404，跨用户普通小说接口返回 403；
- Dashboard 和小说列表固定按 `updatedAt DESC, id ASC`，Dashboard 的章节按 `order ASC, id ASC`；外来文风不得通过 `appliedStyleId` 泄漏；
- 五个工作区接口必须在只读 `REPEATABLE READ` 事务中先设置隔离级别再做归属查询；分组接口对缺失和跨用户小说统一返回 404；
- bootstrap 只加载小说、章节摘要、当前章节详情、已批准 Beat Plan 摘要、作品圣经和当前用户可见的应用文风，不得预取设定、规划和资料组；
- lore、planning、resources 三组查询彼此隔离；完整 workspace 可以组合三组，但查询次数不得随章节数量线性增长；
- `chapterId` 无效时选择最后一个 drafting 章节，没有 drafting 时选择最后一章；正文和全部章节必须完整返回；
- 章节字数继续使用共享 Unicode 规则，忽略既定空白字符并按 Unicode code point 计数；
- 资料组中的 RAG 状态必须通过一次 ReferenceMaterial/RagDocument 连接投影，失败详情只返回既有公共错误文案；用户只能看到自己的文风。

### 参考资料与 RAG 迁移约束

- `ReferenceMaterial` 是作者正式资料，`RagDocument`、`RagChunk` 和 embedding 都是可重建检索投影；任何索引失败、重试或回调不得改写、清洗或截断原资料；
- 创建 ID 必须由 `reference + userId + novelId + clientRequestId` 确定性派生；只有资料仍处于初始版本、四个业务字段完全相同且对应 `RagDocument` 存在时允许幂等重放；
- 写入固定按小说归属、小说行、资料行、RAG 文档行加锁；更新和删除先校验 `expectedUpdatedAt` 再判断幂等，ReviewArtifact 批量资料变更必须复用同一事务并整批回滚；
- 标题、类型、正文和来源 URL 分离更新；标题变化同步检索标题但不推进索引代次，正文变化必须显式删除旧 chunk、按原始 UTF-8 字节重算 SHA-256，并把文档置回待重建状态；系统绝不抓取 `sourceUrl`；
- 文本按 1,800 个 Unicode code point 无损切分，最多 64 块；向量最多 4,096 维、所有块维度一致且只能包含有限数值，超限或数量不匹配必须失败而不是截断；搜索 `topK` 只允许 1..20；
- 显式重建必须同时匹配资料正文哈希和 RAG 文档哈希；已经处于同一待投递代次时保持幂等，否则删除旧 chunk 并以单调毫秒时间戳创建新代次；
- RAG `taskId/runId` 必须由资料 ID、正文哈希和精确代次稳定派生。三个内部回调必须先校验直连网段和绑定原始请求体的 Ed25519 服务身份，再锁定资料与文档并校验任务身份；旧代次或错误任务不得产生任何写入；
- 成功回调只允许从当前待处理状态创建完整 chunk 集合并进入 `ready`；同一成功回调可重放但不能替换 chunk。失败回调只把当前待处理代次置为公共“索引生成失败”，同一失败可重放，不能覆盖 `ready`；
- 自动投递失败不能让资料创建/正文更新失败，持久待投递事实由后台补偿；显式重建提交失败返回 503 但保留重试意图和同一代次。未配置索引器时普通资料 CRUD 仍可用，显式重建返回 503。

截至 2026-08-25，Java 已覆盖上述 6 个浏览器接口和 3 个内部索引接口：应用规则、真实
PostgreSQL/pgvector 仓储、原始请求体缓存、服务验签端口、Agent RAG 任务映射与受监督后台补偿均已接线。
领域、应用、仓储、模块边界和完整 HTTP 运行时测试已通过；ReviewArtifact 跨领域决定事务仍在后续
Review 迁移阶段统一接入，不能把当前模块完成误报为整套 Core 已完成。

### 文风画像迁移约束

- 文风、参考文件和画像任务全部按用户隔离；越权读取和写入统一隐藏为既有 404。创建文风只清理名称首尾空白，名称为空时明确失败，来源类型保持 `agent`；
- 上传只接受 `.txt`，最多 50 MiB，必须是严格 UTF-8 且至少包含一个非空白字符；字符数按非空白 Unicode 字符统计。文件名先做 NFC、路径与控制字符净化，再按 UTF-8 字节预算限制，最终存储 basename（含参考 ID 和下划线）不超过 240 字节；
- 文件只能以排他创建、`0600` 权限写入受控 `UPLOADS_ROOT/styles/{styleId}`，拒绝目录穿越、NUL、父目录或文件符号链接。数据库只保存兼容路径 `/app/uploads/styles/...`；文件写成但数据库失败时回收文件，删除则先提交数据库事实再做安全的尽力文件清理；
- 画像创建要求已配置 Agent 投递器、至少一个 `ready` 参考文件，且同一文风最多一个 `pending/processing` 任务。任务先耐久保存再投递，提交失败仍返回 pending taskId，由后台领取 pending 及超过 10 分钟的 processing 任务重试；
- 画像上下文按参考创建时间和 ID 稳定读取全部 ready 文件，格式固定为 `参考资料：{filename}\n\n{content}` 并用双换行连接，不得截断；存储元数据或路径异常必须拒绝；
- 内部回调必须绑定原始请求体、`PORTRAIT_WRITE` scope、`taskId/runId/style:{styleId}`；`runId` 必须等于任务 ID。状态机只允许 `pending -> processing -> success|error`，同状态回调幂等，其他跳转、文风不匹配或分节不匹配均冲突；
- 全量画像必须一次写入五个非空分节，分节画像只能改目标分节；回调契约固定 `truncated=false`，失败消息统一降级为“画像生成失败”，不得向作者泄露 Agent 内部详情。五个分节齐全时按固定中文标题重建 `portraitMarkdown`；
- 手动编辑分节只清理内容首尾空白并重新计算完整 Markdown。应用文风必须先锁小说并校验 `expectedStyleId`，再验证目标文风归属和画像完整性；支持应用、清除和同值幂等，CAS 冲突优先于目标校验。

截至 2026-08-25，Java 已覆盖上述 11 个浏览器接口和 3 个内部画像接口：严格文件存储、应用规则、
真实 PostgreSQL 仓储、原始请求体服务验签、Agent 画像任务映射和受监督后台补偿均已接线。领域、应用、
存储、仓储、模块边界及完整 HTTP 运行时测试已通过，运行时验收实际遍历 14 个接口并确认完整来源不被
截断、失败详情被净化、应用文风 CAS 与删除清理语义正确；这只表示文风独立模块完成，不代表全套 Core
迁移或生产切换完成。

### 中短篇版本迁移约束

- 7 个公共版本接口只服务 `WritingBible.storyLengthProfile=short_medium` 的作者本人；长篇、缺失作品和跨用户访问统一返回既有 404。大纲固定绑定唯一 `Outline` 且不得携带章节，正文固定绑定作品内唯一全文章节；绑定错误返回既有 422；
- 不新增表。大纲、正文的不可变版本继续复用 `ReviewArtifact + ReviewArtifactRevision`，`artifactKey` 分别为 `short-medium:outline:{novelId}` 与 `short-medium:manuscript:{chapterId}`。版本只接受 `awaiting_user/applied`，来源只接受 `agent/manual/restore`，版本号在同一文档内严格单调；
- 版本 payload 必须保存完整正文和精确 UTF-8 SHA-256，正文版本必须冻结 `sourceOutlineVersionId`，大纲版本不得携带该字段。Agent 版本绑定 task/job，人工和恢复版本绑定 16..128 字符 `clientRequestId`；恢复版本还必须绑定不可变来源版本。任何正文、payload 或 Diff 都不得截断；
- Diff 按包含原分隔符的自然段比较，只返回 insert/delete/replace 块；所有位置使用 Unicode code point 偏移，字数沿用忽略 Unicode 空白和 BOM 的共享规则。`confirmationHash` 必须对文档类型、章节、基础版本、当前工作稿哈希、目标版本和完整规范化 Diff 做稳定 SHA-256 绑定；
- preview 先锁定作品、工作稿和该文档版本，要求请求基础版本等于当前最高 applied 版本；返回当前工作稿更新时间、内容哈希、dirty、完整 Diff 与确认摘要，不接受客户端提交正文；
- 人工提交先按 `clientRequestId` 重放，再依次校验当前基础版本、毫秒级 `expectedUpdatedAt`、完整内容哈希和确认哈希。工作稿未变化时返回当前版本而不新增版本；首个正文版本必须绑定当前已应用大纲，后续人工正文继承当前正文版本冻结的大纲；
- Agent 候选创建、完成回调和 WritingTask/Outbox 原子收敛留在后续写作模块统一实现；本模块只负责读取并采用已耐久存在的候选。采用要求 `awaiting_user`、候选基础版本仍为当前版本、工作稿干净且确认哈希匹配；采用正文时必须复用章节内容替换规则使旧质量结果失效；
- 采用按 `short-medium:adopt:{versionId}:{clientRequestId}` 写入既有 `WritingRunCommand` 稳定回执并幂等重放，不重复覆盖工作稿。恢复不得修改历史版本，而是从任意同文档历史版本复制完整内容，创建新的 applied 版本、记录 `restoredFromVersionId` 并替换工作稿；
- 版本列表固定按 `versionNumber DESC`，详情重新绑定可用于当前基础事实的完整 Diff；跨文档、跨 artifactKey 的比较返回 409。过期基础版本、dirty 工作稿、过期时间戳、内容哈希或确认哈希都明确冲突，禁止自动变基或静默覆盖。

截至 2026-08-25，Java 已覆盖上述 7 个浏览器版本接口：与 Python 基线一致的段落 SequenceMatcher、
Unicode 码点偏移与确认哈希，应用规则、真实 PostgreSQL 仓储、ReviewArtifact/Revision 双写、采用命令回执、
章节重开和质量失效均已接线。领域、应用、仓储、模块边界及完整 HTTP 运行时共 14 项测试通过；Agent
生成任务的不可变快照、完成回调、WritingTask/命令/Outbox 原子终态仍留在后续写作工作流模块统一迁移，
因此这里只能标记“中短篇版本接口完成”，不能标记完整中短篇 AI 管线或 Core 迁移完成。

### 写作会话迁移约束

- 6 个浏览器会话接口只接受 Cookie 当前用户身份。创建必须验证章节同时属于请求小说与作者；小说列表归属失败返回既有 403，章节不匹配返回既有 404，会话读取、修改、删除和追加消息越权统一返回 `WRITING_SESSION_FORBIDDEN`，不能泄漏会话是否存在。
- 会话标题、消息正文、意图和 metadata 必须逐字保存，不修剪、不归一化、不截断。创建默认 phase 为 idle；修改只应用非 null 的 title/phase，空补丁仍按既有行为推进会话更新时间，显式 null 与省略均不用于清空字段。
- 会话列表固定按 `updatedAt DESC, id ASC`；消息数用一次分组查询，最后消息用 `createdAt DESC, id DESC` 的窗口查询，查询次数不能随会话数量增长。无消息会话固定返回 messageCount=0、lastMessage=null。
- 会话详情中的消息固定按 `createdAt ASC, id ASC` 完整返回；损坏的历史 metadata 只降级为 null，不能使整个会话不可读，也不能回写或删除原始值。追加消息与会话 updatedAt 必须在同一事务提交。
- 会话恢复摘要只从该会话的 WritingTask 派生。currentTask 按 `awaiting_user_review -> active -> waiting_call` 的阶段优先级，再在阶段内取最新；lastTask 取最新 completed/error。Graph 快照必须拒绝运行时字段、缺失身份、错误归属和未知 operation；等待审核的兼容任务可用 generatedContent 作为活动 Artifact ID。
- 删除继续依赖冻结外键语义处理消息和任务关联，不扫描或级联删除小说、章节及正式内容；本模块不得新增表、自动 DDL 或改变会话/消息字段。

### 写作运行重构与迁移约束

- Java 不照搬 Python `commands.py/tasks.py/run_queries.py` 的大文件结构。写作运行必须拆为严格联合请求解析、来源快照装配、任务/命令事务仓储、统一结果投影、Agent 投递、回调状态机、Outbox 与 SSE 八个明确职责；这些组件仍属于单一 writing 模块和单一 Core，不形成第二套业务实现。
- 三种启动请求继续共享同一公共接口：旧长篇兼容请求、中短篇请求和显式 `long_serial` 请求必须先命中且只命中一个冻结分支。Java 接口生成器对匿名 `anyOf` 的错误字段并集不得成为运行时契约；原始 JSON 必须先做严格类型、额外字段和 Pydantic 跨字段等价校验，再转换为分支 DTO。
- 所有写作事务统一按小说、章节、会话/任务、Artifact、当前命令的顺序加锁；用户级 `clientRequestId` advisory transaction lock 必须先于跨表幂等解析。不得因为 Java 仓储拆分改变锁顺序、提前提交或让来源快照脱离任务与首命令事务。
- 旧兼容启动继续使用冻结的 legacy 幂等键语义；显式长篇、恢复、取消和草案决定使用版本化 `_inkforgeCommand` 信封、规范化请求指纹以及 WritingRunCommand/WorkflowRun 全局命名空间。相同请求重放必须返回同一任务/命令，不同请求复用标识固定冲突。
- 长篇写操作必须在锁内冻结章节、总纲、唯一已批准 Beat Plan 以及可选选区来源；选区位置一律使用 Unicode code point。任务、首命令、Graph 快照、会话消息和选区来源卡必须原子提交，来源哈希、时间和资源身份不匹配时不得创建任务。
- 中短篇启动只从唯一全文章节、唯一大纲工作稿、已应用起始素材和不可变版本 Artifact 装配任务。基础版本、dirty 工作稿、来源大纲与选区 hash 必须在锁内复核；同一作品只能有一个活动文档生成/改写任务，全文检查不得冒充候选版本。
- 公开运行状态只能由 PostgreSQL 的 WritingTask、WritingRunCommand 与 ReviewArtifact 相互印证后投影。命令/任务终态冲突、缺失候选、错误 Artifact 生命周期和损坏取消链必须显式 `inconsistent`，且任何不一致结果的 `ready` 必须为 false；完整复审报告、检查报告和正文不得截断。
- Python 冻结 OpenAPI 把 SSE 误投影成 `application/json + void`，无法生成可实现的 Spring 流接口。Java 专用迁移基线只为该响应增加 `text/event-stream` 与 binary `WritingEventStream` 映射到 `StreamingResponseBody`；Python 源契约、路径、请求头、事件帧和浏览器行为保持不变。这个生成修正属于语言适配，不构成公共 API 变更。
- FastAPI 的五个 `FileResponse` 路由同样没有导出响应正文 schema。Java 专用迁移基线把 route inventory 中标记为 `file` 的 200 响应统一投影成 binary `BinaryFileStream`，Spring 接口映射为 `StreamingResponseBody`；控制器仍按数据库事实设置实际 MIME、下载或内联 disposition，不能把文件读入内存或改成 JSON。
- 写作调度器不得依赖同一 Spring 配置类内 `@ConditionalOnBean` 的解析顺序，也不得用返回 `null` 的 `@Bean` 表示功能缺失。调度器始终存在并在调用时解析 Agent 投递端口；未配置 Agent 时以 `AGENT_SERVICE_UNAVAILABLE` 记录可重试失败。Redis 事件、回调、Outbox 和 SSE 组件只按明确 `REDIS_URL` 门禁装配。
- 本次结构重构不修改 PostgreSQL schema、不改变 Agent 契约、不新增产品能力。每个拆分职责先写 JUnit/真实 PostgreSQL 测试，再接 HTTP；完成全部回调、Outbox、SSE 和投递前不得把“启动与查询已迁移”表述为完整写作管线完成。

截至 2026-08-25，Java 已实现 6 个写作会话接口、6 个浏览器运行接口和 5 个内部工具/回调接口：三分支
启动解析、来源冻结、恢复与取消、耐久投递、回调状态机、27 个只读工具入口、Outbox、Redis 事件序号、
PostgreSQL 权威 outcome、SSE 回放和旧任务 reconciler 均已接线。真实 Spring HTTP + PostgreSQL + Redis
验收已走通会话、显式长篇复审、工具鉴权、事件、完成、恢复、取消和 SSE 终态关闭；同时修复了旧锁顺序
死锁风险、条件 Bean 扫描顺序、长篇结果空判别 NPE、消息 metadata 漂移和重复 Graph 解析。视频与 Java
CLI 实现已经完成；具名开发库验收已通过真实 Spring HTTP、耐久写作投递和受签名保护的完成回调闭环，
并按精确用户与作品 ID 清理。真实 Python Agent fake provider 的独立跨进程差异闭环和生产切换仍未完成，
因此不能把本段表述为已经完成生产迁移。

### 工作流调试接口迁移约束

- 2 个浏览器调试接口默认隐藏，`WORKFLOW_EVENT_DEBUG_ENABLED` 未开启时在完成 Cookie 认证后固定返回 404；开启但 Agent 客户端不可用时返回既有 503。
- Core 只把当前 Cookie 用户 ID 与可选 runId 转发到受签名 Agent 调试接口，不能接受浏览器提交 userId，也不能读取本地 PostgreSQL 冒充 Agent 运行日志。
- Agent 返回值必须按冻结 `WorkflowRunListResponse/WorkflowRunDetailResponse` 严格转换；完整日志 content 不得截断，远端地址、签名令牌和原始失败正文不得泄漏浏览器。

### ReviewArtifact 与正式应用迁移约束

- 4 个浏览器接口和 3 个内部接口共同维护同一 ReviewArtifact 权威事实。浏览器按 Cookie 用户归属读取、分页和决定；内部创建、修订、隔离与评审必须同时校验可信直连网段、原始请求体 Ed25519、`tool:write` scope 以及 task/run/novel/job 的当前身份；
- Artifact 状态只允许既有 `draft/under_review/awaiting_user/applying/applied` 有向流转，`applied` 不可重新打开。内部修订必须按 `novelId + taskId + artifactKey` 锁定活动草案并精确匹配 `expectedRevision`，每次创建或修订同步追加不可变 ReviewArtifactRevision；同一 kind 不得变化；
- payload 的 `kind` 必须与行类型一致，Agent 不得提交保留的 `_inkforgeControl`。Core 可在持久化时添加来源命令控制字段，但所有浏览器响应必须移除它；持久 payload、diff、文本和评审结论完整保存，不得截断；
- `beat_plan`、`chapter_draft` 及长篇大纲选区草案必须继承最初 start 命令冻结的 SourceBinding。用户非 discard 决定前重新锁定并核验来源；缺失绑定的历史草案只能明确显示 `legacy_missing`，不能伪装 verified；
- 选区草案创建时必须从权威 Chapter、Outline 或 OutlineNode 按 Unicode code point 范围重新冻结 selectedText、前后上下文、完整 candidate 与结构化 diff，并校验资源类型、毫秒更新时间、完整正文 SHA-256 和选区 SHA-256。应用时再次核验且只替换选区，选区外内容逐字不变；
- 评审按 artifact、revision、evaluator 唯一；完全相同重放幂等，不同结论冲突。revision 过期、旧 job、跨任务或跨小说写入都不得修改 Artifact；under_review 冲突隔离只能进入 awaiting_user，不增加 revision；
- 列表按 `createdAt DESC, id DESC` 使用不透明游标，limit 为 1..100；任务草案只返回当前活动状态中最新一条。普通读取越权维持既有隐藏语义，所有 JSON 解析错误返回稳定业务错误，不能泄露 SQL 或内部控制字段；
- 用户决定使用 `clientRequestId` 和规范化请求指纹幂等。Core 在同一外层 PostgreSQL 事务内按统一顺序锁定小说、章节、任务、Artifact、来源命令和当前命令，确认任务处于 awaiting_user_review 且没有活动命令，再完成正式写入或物理 discard、Artifact 状态和 `artifact_decision` WritingRunCommand；任一步失败整体回滚；
- 中短篇版本 Artifact 继续只能通过专用版本接口操作。普通 approve 只允许 agent_updates、文本大纲、章节正文、Beat Plan 和合法选区；revision_brief/freeform 等不可应用类型拒绝。章节写入必须复用正文重开与质量失效规则，Beat Plan supersede 旧正式版本；部分 agent_updates 只执行用户明确选择的 section/item；
- 决定成功固定返回 202/pending，并由 dispatcher 使用 commandId 作为稳定 Agent job 身份补投；即时 Redis 提交失败不能否定已提交的数据库决定，也不能再次应用正式内容。

### 质量检查迁移约束

- 3 个浏览器接口和 3 个内部接口继续围绕 `ChapterQualityCheck` 与 `WorkflowRun(kind=quality_check)` 维护同一权威事实。浏览器按 Cookie 用户和小说归属读写；内部上下文、成功与失败回调必须同时校验可信直连网段、原始请求体 Ed25519、`quality:write` scope 以及 task/run/novel 绑定；请求中的 `userId` 不能替代服务身份。
- 浏览器只允许把检查状态改为 `pending/skipped`，并用毫秒级 `expectedUpdatedAt` 做 CAS。完全相同的状态修改可幂等返回；其他修改必须先校验版本，再拒绝已完成章节和活动中的质量运行。`resetResult=true` 必须一次清空报告、全部历史评分、quality gate 与返工摘要，不能留下混合代次结果。
- 当前只允许待审章节的 `consistency` 终检。创建运行必须先按 `userId + clientRequestId` 获取 PostgreSQL advisory transaction lock，并与写作命令共用全局幂等命名空间；请求指纹必须绑定小说、章节、检查项、可空来源任务和完整消息。相同请求重放返回原 runId 且不再次投递，不同请求复用标识返回 409。
- 运行创建在一个事务中锁定小说、章节、检查项，校验可选 WritingTask 与同一作者、小说和章节精确绑定，拒绝第二个 pending/running 运行，再把检查项置为 running 并写入 WorkflowRun。持久输入必须完整冻结章节正文、正文 SHA-256、来源更新时间、来源任务和消息，不得截断或在投递时重新读取正文。
- WorkflowRun ID 是稳定 runId，Agent jobId 固定为 `quality-{runId}`；计费 taskId 有来源写作任务时沿用该任务，否则使用 runId。Agent 上下文只能读取该运行冻结的正文；持久输入损坏、跨资源、非最新或非活动运行必须明确失败，不能回退到当前正文。默认消息仍为“检查本章一致性”。
- dispatcher 必须领取 pending/running 运行并复用稳定身份补投；Agent 返回 queued/running 时标记 running，返回终态时收敛为失败。暂时性网络错误只记录稳定错误类并留待后台补投，确定性契约错误必须抛给受监督后台任务；单条暂时失败不能阻断同批其他运行。
- 成功回调必须完整保存共享 `ConsistencyQualityReport`，总分只取五项一致性评分的四舍五入平均值，旧六维评分字段保持空；失败回调只写稳定的 `QUALITY_RUN_FAILED`，不得把 Agent 内部失败消息落库或返回作者。终态回调重复到达保持幂等。
- 回调先锁章节、绑定的运行和检查项。只有最新运行可以更新检查项；旧运行只能收敛自己的 WorkflowRun。若当前章节正文哈希已不同于冻结快照，则运行进入 cancelled、错误固定为 `QUALITY_SOURCE_CHANGED`，最新检查项重置为 pending 且清空旧结果，过期结果永远不能覆盖新正文。
- PostgreSQL 继续保存运行、检查状态和结果的权威事实，Redis 或 Agent 队列只表示执行索引。启动补偿、服务重启和提交响应丢失必须继续补投同一个 runId；本模块不得新增表、自动 DDL 或修改冻结 schema。

截至 2026-08-25，Java 已覆盖上述 3 个浏览器接口和 3 个内部接口：共享跨表幂等解析、冻结正文快照、
真实 PostgreSQL 仓储、质量 Agent 协议映射、即时投递、受监督后台补投、原始请求体服务验签以及新旧运行
隔离均已接线。质量 dispatcher、Agent 映射、仓储和完整 HTTP/Redis 运行时共 12 项测试通过，模块边界与
ReviewArtifact 对共享幂等解析器的回归测试也通过；这只表示独立质量检查模块完成，不代表写作命令、SSE、
工具网关或整套 Core 迁移完成。

### 模型计费迁移约束

- 3 个浏览器接口继续按当前 Cookie 用户返回余额摘要、总/月用量和写作任务逐调用用量；2 个内部接口必须同时校验可信直连网段、绑定原始请求体的 Ed25519 服务身份及 `billing:authorize` 或 `billing:usage:write` scope，并绑定请求中的 task、run、novel；
- 授权只接受 `fake/fake`（不计费）或 `openai_compatible/deepseek-v4-flash`（计费）。资源必须能沿 WritingTask、StylePortraitTask、ChapterQualityCheck、活动旧 VideoGenerationTask 或活动 VideoAdaptationTask 精确归属到请求用户与小说；伪造身份返回 403；
- 计费模型先从当前余额扣除按全部未缓存输入估算的成本，再以输出每 token 2,000 micros 计算可负担上限；实际授权取请求上限与可负担值较小者，低于 128 token 返回 402。fake 不受余额限制但仍要求真实资源归属；
- grant 使用 Core Ed25519 私钥签发严格 EdDSA JWT，header 只允许 `alg/typ`，claims 固定绑定 request/task/run/novel/user/provider/model/agent/maxOutput/billable、`iss=core-api`、`aud=agent-service`，有效期恰为 1,200 秒并只容忍 30 秒时钟偏差；视频任务 requestId 使用不泄露任务 ID 的稳定 SHA-256 前缀，其余使用 UUID；
- 用量回调必须先验证 grant，再逐项匹配 request/task/run/novel，输出 token 不得超过授权；`cachedTokens <= promptTokens`，可选 cache miss 与 cached 之和等于 prompt，可选 reasoning 不超过 completion，`total=prompt+completion`；reasoning 已包含在 completion 中，绝不重复计费；
- 正式成本固定为未缓存输入每 token 1,000 micros、缓存输入 20 micros、输出 2,000 micros。`requestId` 先取得 PostgreSQL advisory transaction lock，再在同一短事务锁定/扣减用户余额并写 TokenUsage；金额大于零时同时写一条 CreditLedger.ai_charge，任一步失败整体回滚；
- 相同 requestId 只有用户、小说、task、run、Agent、模型、四项 token 及两个可空诊断字段全部一致才安全重放。零金额真实调用仍写 TokenUsage、不写流水；重放时返回当前余额。历史只有单条 ai_charge 的请求仅在旧流水可证明的字段和金额完全相同时重放，不回填 TokenUsage；
- 余额摘要返回最近 20 条流水，固定按 `createdAt DESC, id DESC`；积分显示按 1 credit = 1,000,000 micros，最多保留三位小数。总/月用量不重复叠加 cached token；月界按 UTC 当月一日；
- 任务用量只允许任务作者读取，按 `createdAt ASC, id ASC` 返回全部明细且不分页、不截断。只有某次调用两个诊断字段都非空才可派生 visible completion；只有全部调用都完整且至少一条调用时，任务汇总才返回诊断合计和 `tokenDetailsComplete=true`；
- 本模块只能使用已批准并已进入冻结 contract 的 TokenUsage 字段，不新增、回填或自动迁移数据库结构，也不得把 grantToken、模型输入或输出返回浏览器或写入账单明细。

截至 2026-08-25，Java 已覆盖上述 3 个浏览器接口和 2 个内部计费接口：严格 Ed25519 模型 grant、
Python/Java 双向 golden fixture、安全私钥加载、资源归属、余额授权、PostgreSQL advisory transaction lock、
原子扣款双写、零金额与历史重放、总/月/任务用量查询均已接线。计费领域、应用、真实 PostgreSQL 仓储、
并发重试、模块边界和完整 HTTP/Redis 运行时共 16 项测试通过，共享服务身份包 7 项测试及 Python grant
兼容测试也通过；这只表示模型计费模块完成，不代表写作回调、Review、质量、视频、CLI 或整套 Core 迁移完成。

### 视频生产域迁移约束

- Java 视频域按项目与素材、章节改编与视觉设定、逐镜 Seedance 渲染、关键帧与后期制作四层迁移；四层共享一个模块和一套数据库事实，但通过应用端口隔离文件、媒体工具、Agent 和 PostgreSQL，不照搬 Python 视频大仓储或复活公共 `VideoScene`；
- `VideoRenderGateway` 与章节改编投递端口由视频应用层拥有，Agent HTTP 适配器统一位于 `agentgateway`；视频基础设施不得直接依赖 Agent 客户端或网关异常，Spring Modulith 必须验证这条单向边界且不存在循环；
- 已存在的旧 `VideoScene` 规划任务只保留五个 Agent 内部回调和后台补投收敛能力，不提供创建、重试、返工或任何公共准入。回调状态机与后台派发必须使用两个独立应用端口和两个独立 PostgreSQL 仓储；新章节改编域不得依赖这两个兼容端口；
- 用户上传固定采用 `项目归属/长篇校验 -> 排他流式落盘 -> 魔数与大小校验 -> ffprobe 真实时长 -> 数据库登记`。探测或数据库失败必须按精确 storageKey 补偿删除完整/半截文件；写文件前后都要复核可写项目，避免归属或篇幅状态竞态；
- 视频文件只允许 JPEG、PNG、WebP、MP4/MOV、WAV 和 MP3 魔数，图片、视频、音频上限分别为 30 MiB、200 MiB、100 MiB；内部供应商与后期流允许更大受控上限，但仍必须流式处理、计算完整 SHA-256、排他创建并拒绝路径穿越、覆盖和符号链接；
- 上传职责/模态矩阵继续来自共享产品契约，`episode_export` 只能由受控导出器创建。`series` 是章节改编和视觉设定的正式项目模式，素材库不得继承已退役旧 `VideoScene` 预览对 `concept/trailer/highlight` 的模式限制；
- 音视频没有可用 ffprobe 时不得写入伪造或空时长；非零退出、超时、畸形 JSON、非正、非有限或超出 Java 可表示范围的时长均明确拒绝。子进程必须使用无 shell 参数数组、关闭 stdin、并发有界读取 stdout/stderr、超时强制回收；
- `VideoAsset.byteSize` 的数据库类型是 BIGINT，整集导出上限可能越过 32 位整数。Java 专用迁移投影把该字段生成为 `Long`，但 HTTP JSON 字段、Python 源契约和 TypeScript 数字语义不变；这属于语言表示修正，不是公共 API 或数据库变更；
- 权利状态只允许 `confirmed/restricted/rejected` 公共写入；只有 confirmed 设置锁定时间，其他状态清空锁定时间。历史项目、素材和文件读取不受视频预览开关影响，所有新增或状态写入继续受开发视频门禁控制；
- 五个文件响应统一使用 `StreamingResponseBody`，按受控文件事实设置实际 MIME 与下载/内联 disposition，禁止把媒体整体读入堆内存。完整 48 个视频接口完成前不注册只实现部分方法的 `VideoApi` 控制器。

截至 2026-08-25，Java 已接通项目与素材、章节改编与视觉设定、逐镜 Seedance 渲染、Take、关键帧、
粗剪、声音字幕和整集导出四层，并显式实现全部 48 个视频 HTTP 操作；五个旧 `VideoScene` 内部回调及
既有任务补投被隔离为只收敛兼容边界。领域、应用、存储、媒体工具、真实 PostgreSQL 仓储和完整 HTTP
运行时测试已通过；对应 41 个 Java CLI 视频命令也已实现并通过命令层、文件传输和 watcher 测试。正式
Java 镜像中的 FFmpeg 与 ffprobe 已完成可执行性检查，媒体工具的故障、超时和边界由自动化测试覆盖；尚未
用真实业务媒体执行完整转码链路。`novelwriterdev` 完整结构只读守卫与具名业务验收均已由 Java 真实连接
通过，验收覆盖长篇、设定、资料、中短篇候选和视频章节改编，并按精确 ID 清理零残留。生产视频开关和
生产数据库均未改动。

截至 2026-08-25 的整体验证结果为：Java Reactor 中服务身份 7 项、服务契约 4 项、Core 402 项（常规
全量为 400 项通过、2 项具名开发库门禁跳过，随后两项均对 `novelwriterdev` 独立执行通过）和 CLI 49 项；
Python 全量 3,440 项通过、3 项外部环境门禁跳过，Ruff 与 267 个源码文件的 Mypy 通过；Web 290 项、
TypeScript 客户端 3 项、类型检查、Lint、API 生成检查和 Next.js 生产构建通过。两个共享业务 fixture 已在
两套完整、隔离的 Python/Java Core 与 PostgreSQL/Redis 上直接验证认证、小说、章节、中短篇设定、资料和
手工版本共 17 个 HTTP 步骤及最终数据库事实；响应空值和动态确认哈希均按上文严格规则校验。

同日又在全新隔离 Compose 项目中完成 `Java → 当前源码 Python → Java` 原位回退演练：Python 回退阶段
13/13 个浏览器用例通过，前后兼容结构指纹一致，Java 自动恢复后 schema guard、readiness 和 smoke 通过；
Java Core 在 448 MiB 限额下实测约 271.8 MiB。上述结果证明代码、镜像和回退机制已进入预切换状态，但不
替代剩余逐命令成功分支差异、真实 Python Agent 独立跨进程闭环、生产备份验证和生产切换批准。

## 部署与切换

仓库中的生产 Compose 与镜像流水线已经构建 Java Core，正式服务器已于 2026-08-26 按既有批准完成同名
`core-api` 原位切换。以下门禁继续作为后续修复部署和回滚约束，不能因为首次切换完成而删除：

1. Java 镜像沿用 `inkforge-core-api:<sha>` 和 `core-api` 服务名；
2. 镜像包含 JRE 21、FFmpeg、ffprobe 和 CJK 字体，继续使用非 root、只读根文件系统和受控 tmpfs；
3. Compose 不新增第二个 Core service；
4. CI 预构建镜像，服务器只加载并替换同名容器；
5. Java schema guard 替换容器内 Python 校验命令；
6. Java 部署失败恢复上一 Python 镜像，不执行数据库回滚 DDL；
7. 切换前必须有生产备份、空闲任务窗口、448 MB JVM 验证和明确用户批准；
8. 观察期结束后才删除 Python Core。

具体镜像与原子切换契约如下：

- 正常 `core-api` 镜像必须由仓库 Maven Wrapper 在 JDK 21 builder 中 clean 构建 Spring Boot fat JAR，
  runtime 只包含 JRE 21、该 JAR、FFmpeg/ffprobe、CJK 字体、CA 与 HTTP 健康探针；不得包含 Python、uv、
  Python Core 源码或第二个 Core 进程。镜像以 `cn.inkforge.core.runtime=java` 标签声明实现身份；
- 448 MiB 容器必须显式限制 heap、Metaspace、code cache、direct memory 与线程栈，并启用
  `ExitOnOutOfMemoryError`。正常入口固定单进程 `java -jar`，Compose 健康检查使用镜像内 HTTP 探针，
  不依赖 Python；
- Compose 为可选供应商媒体 URL 与令牌保留空字符串默认值时，Java 必须把“两者都为空”视为功能未配置并
  正常启动，不得实例化令牌编码器；只配置其中一项必须在配置校验阶段明确拒绝，不能以 NPE 失败；
- 独立 Compose 验收可继续使用 PostgreSQL 16 验证兼容性，但 pgvector 版本必须固定为冻结结构契约中的
  `0.8.0`，不得使用会随时间漂移的浮动镜像标签；
- `infra/compose.test.yaml` 的隔离 PostgreSQL 只允许通过 `127.0.0.1` 发布测试端口，默认由 Docker 动态
  分配；PostgreSQL 必须额外挂入只有它使用的非 internal 测试桥接网络，否则 Docker Desktop 会记录端口绑定
  却不实际发布。该桥接网络不得被 Web、Core、Agent 或 Redis 使用，生产 Compose 仍不得发布、创建
  PostgreSQL 或定义该网络。回滚演练中的容器 Core 使用 `TEST_DATABASE_URL` 访问同一测试库，宿主机
  Playwright 辅助脚本使用单独的回环 `DATABASE_URL`，两者不得指向开发库或正式库；
- 测试 Compose 不得只覆盖 Core 的 `JWT_SECRET` 或引入第二个 `TEST_JWT_SECRET`；Core 与 Web 必须和生产
  一样解析同一个 `JWT_SECRET`，否则 readiness 会全部通过但浏览器注册后的 Cookie 会被 Web 误判并清除；
- 用户直接运行的回滚与冒烟入口必须保留可执行位；脚本之间调用仍显式使用 `sh`，避免部署行为依赖宿主机
  checkout 对可执行位的偶然处理；
- Java Core 镜像必须在切换到非 root 用户前预建并归属 `10001:10001` 的 `/data/uploads`，Agent 镜像同样
  预建 `/data/agent-logs`。这样首次挂载空命名卷时，Docker 复制出的卷根目录即可由正式进程写入；不能依赖
  宿主机曾经手工修过的卷权限，也不能把正式进程改回 root；
- 为兼容已经存在且所有权未知的生产卷，部署脚本必须在版本切换前分别创建 `inkforge_uploads` 与
  `inkforge_agent_logs`，再用对应新镜像运行无网络、只读根文件系统、删除全部 capability 后只加回
  `CHOWN` 的一次性初始化器，对两个卷根目录执行非递归 `chown 10001:10001`。任一初始化失败都必须在
  Compose 切换前终止；不得递归改动既有业务文件；
- 编排冒烟不能只验证 HTTP readiness：必须以正式 Java Core 和 Agent 进程身份，分别在 `UPLOADS_ROOT` 与
  `WORKFLOW_HUMAN_LOG_DIR` 下创建并删除唯一探针目录。任一真实写入失败都视为部署失败；
- 镜像内提供只读 `inkforge-schema-guard` 命令，复用同一冻结 contract、数据库名配置和 schema profile，
  成功只输出实时指纹，结构不一致输出不含凭据的差异并非零退出。新 Java 栈的部署验证和回滚演练必须调用
  该命令，不能再用 Python 模块实现 Java 栈检查；回滚演练可显式请求忽略 contract 版本号与 CHECK 元数据的
  v1 兼容指纹，以便和历史 Python 镜像比较同一份实时结构，但该模式仍必须先通过当前完整结构契约校验；
- 首次 Python→Java 切换仍需能恢复当前已验证的旧 Python 镜像。正常 Compose 保持纯 Java 健康检查；只有
  自动回滚到无 Java runtime 标签的历史 Core 时，部署脚本才叠加具名、只改 Core 健康检查的
  `infra/compose.python-core-rollback.yaml`，并使用旧镜像自己的 Python schema guard。该兼容文件不得创建
  第二个 Core、不得用于新版本启动，上一版本已经是 Java 时不得使用；
- 自动回滚的权威基线是切换前实际运行的 Web、Core、Agent 三个容器对应的不可变镜像 ID，不是三个容器的
  历史标签必须相同。部署脚本必须先校验三服务完整、容器声明的镜像仓库符合约定且三个镜像 ID 仍可读取，
  再把三个 ID 分别标记到同一个仅供本次部署回滚的确定性标签，并逐一反查标签是否仍指向原 ID。快照期间
  不得重建、停止或替换任何生产容器；同一部署标签已存在但指向其他镜像时不得覆盖，任一标记或反查失败
  必须在数据库迁移和版本切换前终止。后续自动回滚只能使用这组三服务精确快照，不能从互不相关的历史标签
  猜测或拼接版本；
- 回滚演练使用的浏览器 E2E 夹具必须遵守当前公共契约和产品域语义。通用的章节、结构化大纲、质量与长篇
  写作验收创建 `long_serial` 作品；只有明确验证中短篇创建的用例使用 `short_medium`，并完整提供
  `clientRequestId`、`sourceKind`、`sourceText` 与合法目标字数。不得用 Java 的宽松兼容行为掩盖旧 Python
  回滚镜像会拒绝的无效请求；
- 回滚 E2E 必须验证当前统一长篇工作区：章节编辑器与聊天协作栏同时存在，一级入口只保留章节、创作资料
  和视频制作。已经退役的“AI 创作/阅读与小修”模式开关、进入小修流程和固定章节审核栏不得继续作为夹具，
  也不得为了让旧测试通过而复活；待确认变更统一从聊天顶部入口进入审核托盘，再以互斥弹窗查看完整差异，
  从托盘进入详情时必须先关闭托盘，禁止叠加两个审核弹窗；
- 自然语言长篇启动允许 Agent 在受服务身份保护的回调中完成操作分类；当启动命令没有显式 `operation` 时，
  Python 与 Java 结果投影必须只从该任务持久化快照的 `currentOperation.kind` 取得操作身份，再按操作类型、
  活动产物 ID 和生命周期验证结果，不得从用户文本猜测，也不得把已存在的权威草案误报为缺失；
- 终态 SSE 只通知权威结果，不承诺重复携带已持久化的 Agent 正文。Web 在当前会话收到等待确认或成功终态后，
  必须重新读取当前会话消息但保留刚收敛的工作流界面状态，使历史 Python Core 与 Java Core 都能显示权威
  Agent 回复；不得依赖刷新页面，也不得把 SSE 临时文本反向持久化；
- 镜像上传复用判断必须把根 Maven/POM/Wrapper、Java Core、Java 服务契约/鉴权、冻结契约、共享数据库
  contract 与 Core Dockerfile 全部列为 Core 构建输入；Python Agent 的复用输入保持独立。部署前必须验证
  新 Core 镜像 runtime 标签为 `java`，然后只替换现有同名服务并执行 schema、HTTP、内部路径和 Agent
  稳定就绪 smoke。
- Java CI 门禁失败时必须保留 Maven 完整日志，并把末尾诊断同时写入 GitHub Step Summary 与错误注解；
  不能只暴露非零退出码，否则无日志下载权限的值守者无法区分测试失败、依赖下载故障与运行环境差异。

## 验收标准

### 工程

- `./mvnw verify` 使用 Java 21 通过；
- Spring Modulith/ArchUnit 验证模块边界；
- 无启动期 DDL、双写、静默截断或无界重试；
- 高风险状态机、事务、兼容和部署恢复代码满足上述维护性注释门禁；
- 新依赖有固定版本、许可证和安全检查。

### 契约与功能

- 148 个公共操作和 30 个内部操作全部登记并由 Java 覆盖；
- OpenAPI、错误、Cookie、SSE、文件和服务鉴权 golden fixtures 一致；
- 两种创作模式、计费、ReviewArtifact、质量、写作恢复和视频 P0-P3 全部通过差异测试；
- 125 个 Java CLI 命令与 Python CLI 归一化输出一致；
- 当前 Web 与 Python Agent 不需要业务兼容分支即可工作。

### 数据与真实环境

- Testcontainers schema 与 contract 0 差异；
- Java 对 `novelwriterdev` 的只读 schema guard 通过；
- dev 数据库具名验收覆盖认证、普通 CRUD、草案、写作 fake Agent 和视频非付费链路，测试数据精确清理；
- 正式库在切换前没有 Java 测试写入或未批准 DDL。

### 部署

- Java 镜像在 448 MB 限额稳定；
- Compose、HTTPS、内部路径阻断、Core/Agent readiness 和 smoke 通过；
- Java、Python 与生产部署失败都能从工作流摘要和错误注解读取脱敏诊断；
- 当前 Java → 上一 Python → 当前 Java 的回退与自动恢复演练通过；
- 最终一次性切换成功并完成观察期后，才可宣称迁移完成。
