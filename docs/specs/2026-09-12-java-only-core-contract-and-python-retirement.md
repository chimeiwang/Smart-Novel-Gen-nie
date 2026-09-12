# Java-only Core 契约接管与 Python Core／CLI 退役

日期：2026-09-12

状态：已批准，实施中

实施记录：代码迁移与本地回归见 [清理审计](../audits/2026-09-12-java-only-core-retirement.md)；
Compose 恢复演练因 Docker Hub 网络中断尚未通过，不据此宣称生产或全部环境验收完成。

## 背景

Java Core 已原位接管生产，但仓库仍把 Python FastAPI Core 当作公共接口和迁移基线来源：

- `scripts/export_openapi.py` 启动 `inkforge_core.app` 导出公共 OpenAPI；
- `scripts/export_core_migration_baseline.py` 从 Python 运行时导出 Java OpenAPI、内部接口、路由清单和兼容夹具；
- Java Core、Java CLI 和 TypeScript 客户端仍消费带有 Python 来源标记的冻结契约；
- 根 Python workspace、CI、开发入口、回滚和部分运维脚本仍包含 Python Core 或 Python CLI；
- 最新 `main` 已删除旧视频公共契约中的 DTO，但未删除引用这些 DTO 的 Java 死代码，导致 Maven 编译失败。

用户确认进入迁移观察期后的最终清理阶段：Core 和普通 CLI 只保留 Java 实现，Python 只保留 Agent 进程及
Agent 必需的 Python 契约、鉴权库。最初确认不包含生产部署；用户随后于 2026-09-12 明确要求重试验证，
测试通过后部署，因此追加授权本次分支推送、CI 和普通应用发布。该追加授权仍不包含数据库 DDL、
服务器数据迁移或生产视频开放。

## 当前事实

- 本规格开始时本地与 `origin/main` 均为 `7b1de237b3709612583932a516e9536520deebfa`；隔离分支已执行
  `git pull --ff-only`，结果为已是最新。
- 当前公共契约为 141 个路径、182 个操作；完整契约为 166 个路径、207 个操作，其中内部操作 24 个、
  provider media 操作 1 个。
- `npm run api:check` 在基线通过，但它仍通过 Python FastAPI 导出契约，因此不能证明 Java 已接管接口维护。
- Java Reactor 基线编译失败，错误集中在已退役的 chapter-adaptation、legacy video plan、旧 render/take/post
  源码继续导入已从生成契约移除的 DTO。
- Java CLI 的命令注册表已有 152 项，并已实现 V2 Artifact 按正整数 `revision` 精确读取；原工作区对应的
  Python CLI 未提交修改不会因删除 Python CLI 而丢失产品能力。
- 正式数据库已有 Durable Agent V2 事实，V1-only Python Core 已不具备回滚资格。应用回滚必须继续使用
  V2-aware Java Core 组合，数据库永久禁止 DDL rollback。

## 目标

1. 修复最新 `main` 的 Java 编译失败，彻底移除已经退出公共、内部和后台装配的旧视频 Java 死代码。
2. 以语言中立、由 Java 工程流程维护的 OpenAPI 作为 Core 唯一接口契约，不再启动或导入 Python Core。
3. 让 Java Core、Java 服务契约、Java CLI 和 TypeScript 客户端从同一份 canonical OpenAPI 生成。
4. 删除 Python FastAPI Core、Python CLI、跨 Core 差异运行器和所有活动的 Python Core 启动／回滚路径。
5. 保留 Python Agent 及其必需的 Python 共享契约、服务鉴权和 Agent OpenAPI，不改变 Agent 的运行机制。
6. 更新开发、CI、部署、Operator Skill 和文档，使仓库与本机活动入口都只把 Java 视为 Core／CLI 实现。
7. 用 Java 黑盒、PostgreSQL、Agent、Web、CLI、契约和 Compose 验证替代 Python Core 对照证明。

## 非目标

- 不修改 PostgreSQL schema，不执行视频退役 DDL，不连接或写入服务器数据库；
- 不绕过验证直接发布，不把本地通过描述成生产完成；推送、CI、部署和生产回读分别记录结果；
- 不改变 API 路径、operationId、字段、状态码、错误、Cookie、SSE、文件或业务状态机；
- 不迁移 Python Agent、LangGraph、模型、提示词、供应商或队列；
- 不删除 Agent 仍使用的 `packages/service-contracts`、`packages/service-auth` 或 Agent 契约生成流程；
- 不启用生产视频、真实 Seedance、自动 DDL 或双 Core；
- 不因目录后缀做大规模无语义移动。`apps/core-api-java` 直接治理为正式且唯一的 Core 源码目录。

## 核心决策

### 1. 唯一 canonical OpenAPI

将当前 Java 归一化后的完整契约提升为：

```text
contracts/core/openapi.json
```

它是 Core 公共、内部和 provider media 操作的唯一可编辑来源，继续使用 OpenAPI 3.0.3，保留当前生成器已经
验证的 required/nullability、枚举、文件、SSE、匿名 `anyOf` 和 Java 特殊类型映射。每个操作增加稳定的
`x-inkforge-exposure`、鉴权、产品模块、响应类别、事务和副作用元数据；迁移时从现有路由清单一次性带入，
此后不再维护第二份 Python 来源信息。

从完整契约确定性生成公共投影：

```text
contracts/core/public-openapi.json
```

公共投影只包含 `x-inkforge-exposure=public` 的 `/api/v1/**`。同样位于 `/api/v1/**` 的 provider media
HMAC 下载路径仍必须排除；`/internal/v1/**` 也不得进入浏览器或 CLI 客户端。
原 `*-python-baseline.json`、`*-java-baseline.json` 不再作为活动构建输入。Git 历史已保留迁移证据，不在活动
目录继续保留会被误用的 Python 基线副本。

Core 接口修改流程固定为：

```text
修改 canonical OpenAPI
  -> 生成 Java DTO 与 Spring API interface
  -> 实现或调整 Java controller
  -> Java 契约／路由覆盖测试
  -> 生成 public OpenAPI 与 TypeScript client
  -> Java CLI 和 Web 回归
```

禁止从 Spring 注解反向生成 canonical OpenAPI。当前 Spring API interface 本身由 OpenAPI 生成，反向导出会
形成构建循环，并让 Springdoc 版本差异改变 nullable、SSE 和错误响应。

### 2. 投影与漂移检查

新增不依赖 Python 的确定性 Node 脚本，完成以下职责：

- 从 `contracts/core/openapi.json` 生成公共投影；
- 稳定排序并保留 OpenAPI 元数据，拒绝重复 operationId；
- 校验公共、内部、provider media 的路径分类；
- 统一输出 UTF-8 LF，保证 Windows、macOS 和 Linux 的 `--check` 结果一致；
- 在 `--check` 模式比较已提交投影和生成的 TypeScript client，发现漂移时非零退出；
- 不连接网络、数据库或运行中的 Core。

`scripts/generate_api_client.mjs` 改为直接读取公共投影，不再执行 `uv`、`export_openapi.py` 或导入
`inkforge_core`。

### 3. Java 路由覆盖

用 Java 测试同时校验生成接口和实际 Spring MVC 路由：

- canonical 中每个 operationId 唯一，方法与路径组合唯一；
- 182 个公共、24 个内部和 1 个 provider media 操作分类准确；
- 每个契约方法／路径都存在实际 Java handler；两个健康操作可以继续由 `HealthController` 手写映射，但必须
  作为具名且唯一的映射参与同一集合比较，不能作为未校验例外；
- 每个 `/api/v1/**`、`/internal/v1/**` 和 provider media Java handler 都在 canonical 中；
- HTTP method、consume／produce、文件和 SSE 响应类别不漂移；
- Actuator 或框架内部端点不混入产品 API 计数。

用 canonical 扩展生成 `core-route-inventory/2.0` 与内部接口投影，删除其中的 Python `inspect` 行号、
`endpointModule`、`sourceFile` 和 `pythonTests`；Java handler 归属由运行时覆盖测试提供，不在第二份手写清单
重复登记。需要保留的鉴权、错误、Cookie、SSE、HTTP 与行为 golden fixtures 改由 Java 黑盒测试消费；
它们是语言中立证据，不由 Java 自己重新生成后再与自身比较。

### 4. Java 构建修复

先删除已退出运行时的旧视频 Java 源码和对应测试／装配残留，再进行契约接管。删除范围只能包括同时满足以下
条件的类型：

- 对应公共和内部路径已从 canonical 契约删除；
- Spring 配置、controller、dispatcher、reconciler 和 Operations starter 不再装配；
- 活动新 Episode 链、Project、Asset、VisualCanon、provider media 没有引用；
- 删除后 Maven 编译、模块边界和新视频定向测试通过。

不得为了通过编译把已退役 DTO 重新加回 OpenAPI，也不得删除新 Episode 共用的媒体表、jOOQ 类型、文件或
Agent 语言中立 schema。本次只清理源码，不执行 P4 物理数据库退役脚本。

### 5. Python Core 退役

删除：

- `apps/core-api` 及其 FastAPI、SQLAlchemy、Uvicorn 实现和 Core 测试；
- 根 Python workspace 中的 Core member、Core pytest 路径和 Core 专用依赖；
- `scripts/export_openapi.py`、`scripts/export_core_migration_baseline.py`、Python schema exporter；
- Java 的 `PythonCoreProcess` 和 Python／Java 双 Core 差异测试；
- 开发入口中的 Python Core 启动分支；
- CI、Docker、schema guard、recovery／rollback 脚本中的活动 Python Core 路径；
- 已无资格使用的 Python Core rollback overlay。

数据库结构契约改由 Java Core 自有资源维护。既有 pre／post Durable V2 profile 和只读 schema guard 继续
生效；本次不得改变任何表、枚举、约束或指纹。

旧 recovery drill 替换为已有的隔离 V2 Compose 最小恢复测试入口，复用 Java Core 与 Python Agent 的真实
重启、回调丢失、取消和 Redis AOF 场景，不新增维护服务或生产写入口。该测试工具使用 Python 不表示保留 Python Core。

### 6. Python CLI 与 Operator 退役

删除 `tools/inkforge-cli`、Python CLI workspace member、Python CLI 测试和 Python handler 元数据。
`contracts/cli/command-registry.json` 升级为 Java-owned 版本，去掉 `pythonHandler` 和 Python 来源路径，继续
保存命令名、输入／输出模式、文件输出、身份、幂等和写入属性。

Java CLI 必须保持全部 152 个普通命令一一注册，且 handler 集合与注册表双向一致。删除跨语言进程对照后，
保留语言中立输入／输出夹具、Java handler 覆盖和真实 HTTP contract 测试。

本机两份 Operator Skill 改为 PowerShell 直接启动固定 Java JAR：

- 本地开发 Skill 只允许回环 Core；
- 本机 Windows 两份 Skill 继续执行受限端点、84 命令与五操作白名单；macOS 历史投影仍为 45 命令／三操作；
- 不因 Java CLI 支持更多命令而扩大 Skill 授权；
- Windows 凭据继续使用 Credential Manager，不允许明文回退；
- 更新前备份活动 Skill，更新后验证 `configure`、`run`、端点拒绝和白名单拒绝。

原主工作区的 Python CLI 未提交 `revision` 修改已在 Java CLI 主线实现和测试中存在；迁移时补齐 Java CLI
文档说明，不复制或提交 Python 旧实现。

### 7. Agent 保留边界

以下 Python 内容继续保留：

- `apps/agent-service`；
- `packages/service-contracts` 与 `packages/service-auth` 中 Agent 使用的 Python 实现；
- `contracts/agent-service/**` 和 Agent OpenAPI 导出／校验；
- Agent、共享 Python 库和必要运维测试使用的根 Python 工具链。

Agent 可以继续使用 FastAPI 作为独立的内部 HTTP 服务。独立不表示没有外部契约：Agent 仍只通过版本化
HTTP／JSON、Ed25519 服务身份和 Core 内部工具网关交互，禁止数据库驱动、`DATABASE_URL` 和业务表直写。

## 实施顺序

1. 在最新 `origin/main` 的隔离工作树记录基线并修复 Java 旧视频死代码导致的构建失败。
2. 新增 canonical OpenAPI 投影和 Java 路由红灯测试，再切换 Maven、Java CLI 和 TypeScript 生成输入。
3. 迁移语言中立 fixtures、schema guard、CI、开发、部署和恢复脚本，消除活动 Python Core 引用。
4. 删除 Python Core，收敛根 Python workspace，只运行保留的 Agent／共享库验证。
5. 升级 CLI registry、删除 Python CLI，验证 Java 152 命令和 Windows Credential Manager。
6. 更新仓内 Operator 入口及本机两份已安装 Skill，保持授权不变。
7. 更新 ADR、requirements、DOCS／README、Java CLI 文档和审计记录。
8. 运行定向、全量和静态残留检查；按追加授权重试隔离 Compose 验收，通过后推送并经 CI 执行普通应用部署。
9. 发布前核对当前生产版本的独有修复、execution manifest 和可回滚 Java 镜像组合；发布后验证运行版本、
   readiness、只读 schema guard 和既有生产 smoke，保持生产视频关闭，不执行数据库迁移。

每一步必须保持分支可构建。不得先删除 Python 源码，再留下生成、CI 或运维链路待后续修补。

## 文档取代关系

- 新增 ADR 取代 ADR-002 中“Python Core 是迁移期行为基线”和 ADR-003 中“Python Core 是活动回滚目标”的
  当前适用性；两份旧 ADR 保留历史决策，不回写历史。
- `docs/specs/2026-08-24-core-java-replacement.md` 的清理目标由本规格落实；历史数量和切换证据保留。
- 根 `AGENTS.md`、`DOCS.md`、requirements 00／03／05、Java CLI README、部署和 Operator 文档改为
  Java-only Core／CLI 当前事实。

## 验收

### 静态残留

活动源码、脚本、构建、测试、CI 和编排中不得再出现以下依赖：

```text
inkforge_core
apps/core-api
tools/inkforge-cli
export_openapi.py
export_core_migration_baseline.py
pythonHandler
compose.python-core-rollback.yaml
```

允许项必须限于明确标记的历史文档、Git 历史以及 `apps/core-api-java` 路径自身，不能是可执行入口。

### Java

```powershell
.\mvnw.cmd verify
```

必须覆盖 Java Core、service contracts/auth、Java CLI、OpenAPI 生成、路由覆盖、PostgreSQL Testcontainers、
schema guard 和模块边界；不得用 H2 代替 PostgreSQL。

### Web 与公共契约

```powershell
npm run api:generate
npm run api:check
npm run typecheck
npm run lint
npm run test:web
npm run build
```

重复执行 `api:generate` 后工作树必须无生成漂移。

### 保留的 Python Agent

```powershell
uv sync --frozen --all-packages --group dev
uv run pytest
uv run ruff check .
uv run mypy apps/agent-service/src packages/service-contracts/src packages/service-auth/src
```

Python workspace 中不得再安装 Core 或 CLI package；Agent 及共享库测试必须通过。

### 部署配置

```powershell
uv run pytest tests/architecture/test_compose_security.py
docker compose --env-file .env.example -f infra/compose.yaml build web core-api agent-service
```

有 Docker 时执行本地隔离 Compose 健康、schema guard、Core→Agent POST 和生产开关拒绝 smoke。没有 Docker
时必须明确报告未验证项，不以静态配置检查替代运行证据。

### Operator

- Java JAR 的 SHA-256 与安装记录一致；
- 本地与生产 PowerShell wrapper 均不调用 `python`、`uv` 或 `inkforge_cli`；
- Windows 端点限制、84 命令白名单和五种既有长篇操作保持；不改动 macOS 的独立授权投影；
- `long.artifact.get` 的正整数 `revision` 能透传，非法值在联网前拒绝；
- Credential Manager 读写成功且没有明文 token 文件。

## 完成口径

只有上述本地验证全部通过，才能声明“仓库已完成 Java-only Core／CLI 清理”。未推送、CI 未运行、未部署、
服务器数据库未迁移和生产未回归必须分别报告，不能合并成“已上线”。
