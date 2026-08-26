# Core Java 单体替换与 TDD 实施计划

状态：已批准，实施中

基线提交：`c9afc95`

## 目标

在不改变现有产品行为、不增加新功能、不修改 PostgreSQL 业务结构的前提下，用 Java 21 与 Spring Boot
完整替换现有 FastAPI Core。生产环境始终只运行一个 Core；开发过程分阶段完成，最终通过一次原子容器切换
让 Java Core 接管现有 `core-api` 服务名、端口、数据库、Redis、上传目录与 Agent 内部接口。

迁移完成并稳定运行后，才另行设计手机号注册、支付和其他新增能力。

## 已确认边界

### 纳入本计划

- `apps/core-api` 的全部公共 API、内部 API、业务规则和数据库访问；
- 浏览器认证、计费、ReviewArtifact、正式内容应用、写作任务、SSE、Outbox、后台补偿任务；
- Core 与 Agent 之间的 Ed25519 服务身份、请求绑定、重放保护和版本化契约；
- 视频素材、章节改编、逐镜生成、Take、关键帧、粗剪、声音字幕、FFmpeg 与整集导出；
- Core OpenAPI、TypeScript 客户端生成、数据库结构守卫、readiness 和部署验收；
- 现有 125 个 CLI 命令最终迁移到 Java CLI；在 Java Core 切换前，Python CLI 继续作为兼容验收客户端。

### 保留现状

- `apps/agent-service` 保持 Python、LangGraph 和现有模型运行时；
- `apps/web` 保持 Next.js，因为浏览器交互仍由 JavaScript/TypeScript 执行；
- PostgreSQL、Redis、Nginx、FFmpeg、宿主机部署方式和公网路径保持不变；
- Python `packages/service-contracts` 与 `packages/service-auth` 在 Agent 仍需要时保留，但新增语言中立契约和
  Java 实现，禁止 Java Core 直接依赖 Python 运行时。

### 明确排除

- 迁移期不增加手机号注册、短信、支付、退款或新的计费产品；
- 不借迁移修改 API 路径、字段、状态码、错误语义或现有业务流程；
- 不拆微服务，不引入消息队列，不迁移 PostgreSQL 数据；
- 不在生产并行运行 Python Core 与 Java Core；
- 不允许 Python 与 Java 同时写同一个数据库；
- 不以 Hibernate/JPA 自动建表或应用启动自动迁移替代现有具名 SQL 治理；
- 不在 Java 改写期间顺便清理 Agent 代码或改变模型供应商行为。

## 当前基线事实

- Python Core 约 55,314 行业务代码、41,287 行 Core 测试；
- 公共 OpenAPI 包含 115 条路径、148 个操作；
- Core 共注册 179 个 HTTP 路由装饰器，除公共 API 外还包含隐藏内部接口；
- 数据库契约包含 85 张 public 表、22 个枚举，当前指纹为
  `8aaa4d25c3cd3114bc8659330700a2eecdbcdefc7f3d83473c93c1baee576629`；
- 生产 Core 当前限制为 0.45 CPU、448 MB 内存；
- Agent 依赖 Core 的工具网关、计费授权、任务回调、质量回调、ReviewArtifact 和视频回调；
- 生产回滚依赖上一提交的 `inkforge-core-api:<sha>` 镜像仍然存在。

这些数字只是范围基线。迁移目标是行为等价，不是逐行翻译 Python。

## 目标架构

```text
浏览器 -> Nginx -> Next.js
                    -> Java Core -> PostgreSQL
                                 -> Redis
                                 -> 受控上传目录 / FFmpeg
                    Java Core <-> Python Agent

Java CLI ----------> /api/v1/**
```

Java Core 继续是唯一数据库业务所有者。Agent 不连接 PostgreSQL，Web 不新增业务后端或数据库访问。

## 技术基线

- Java 21 LTS；
- 实施时锁定当期稳定 Spring Boot 4.x 补丁版本，不使用 snapshot/milestone；
- Maven Wrapper 与根聚合 `pom.xml`；
- Spring MVC、Spring Security、Bean Validation、Actuator；
- jOOQ、PostgreSQL JDBC、HikariCP；
- Spring Data Redis/Lettuce；
- Jackson，显式配置时间、枚举、空值和未知字段策略；
- JUnit 5、AssertJ、MockMvc、Testcontainers、WireMock、ArchUnit；
- Spring Modulith 约束模块依赖并运行模块级集成测试；
- JaCoCo 只作为未测试区域提示，不把覆盖率数字代替行为断言；
- 必要时对幂等、计费和状态机使用 PIT 变异测试；
- Servlet/JDBC 路线优先，不在第一版引入 WebFlux/R2DBC；
- FFmpeg 继续通过无 shell 的参数数组调用，Java 使用 `ProcessBuilder` 并实现超时、取消、回收和临时目录清理。

## Java 代码布局

迁移期间新增：

```text
pom.xml
.mvn/
mvnw
mvnw.cmd
apps/core-api-java/
packages/service-contracts-java/
packages/service-auth-java/
tools/inkforge-cli-java/
```

`apps/core-api-java` 首期保持一个 Spring Boot 可执行模块，业务按 Spring Modulith 包边界组织，不为每个领域
创建独立进程：

```text
cn.inkforge.core
  platform
  identity
  novels
  chapters
  lore
  outlines
  references
  styles
  shortmedium
  billing
  reviews
  writing
  quality
  video
  agentgateway
  operations
```

每个业务模块内部按 `api/application/domain/infrastructure` 分层；其他模块只能调用公开 application API 或消费
明确的领域事件，不能跨模块读取 repository 实现。

## TDD 总规则

每个可观察行为都按以下顺序实施：

1. 从当前 Python Core 提取或补写 characterization test；
2. 固化输入、响应、数据库结果和必要副作用，不复制动态 ID、时间或无意义顺序；
3. 让同一行为测试在未实现的 Java Core 上明确失败；
4. 编写最少 Java 代码使测试通过；
5. 增加权限、冲突、重复请求、事务回滚和进程恢复测试；
6. 重构 Java 代码，测试保持通过；
7. 在两个完全隔离、结构一致的测试数据库上分别运行 Python 与 Java，比较归一化结果；
8. 运行现有 Web、CLI 和 Agent 契约测试，确认没有跨语言回归。

生产不双 Core，不等于测试不允许两个实现存在。兼容测试可以顺序或并行启动两个进程，但必须使用两个独立
Testcontainers 数据库，绝不共享写入目标。

## 迁移门禁

任一阶段只有同时满足以下条件才能进入下一阶段：

- 对应 Java 测试先红后绿，有提交记录可追溯；
- Python 基线测试继续通过；
- Java 与 Python 黑盒兼容测试通过；
- `schema-contract.json` 只读校验 0 差异；
- 公共 OpenAPI 与冻结基线无未批准差异；
- Agent 共享样例能被 Python 和 Java 同时解析；
- 不存在静默截断、自动 DDL、无界重试或双写；
- 新增依赖通过许可证与漏洞检查，不能只依赖构建成功；
- 失败路径能返回现有中文错误结构，不泄露密钥、SQL 或内部异常。

---

## Task 0：编写并批准迁移规格与架构决议

**文件：**

- 新增：`docs/specs/2026-08-24-core-java-replacement.md`
- 新增：`docs/architecture-decisions/001-core-java-stack.md`
- 新增：`docs/architecture-decisions/002-core-java-contract-first.md`
- 新增：`docs/architecture-decisions/003-core-java-single-cutover.md`
- 修改：`AGENTS.md`
- 修改：`DOCS.md`
- 修改：`docs/requirements/05-auth-billing-and-ops.md`

- [x] 写明 Agent 与 Web 保留、Core 与 CLI Java 化的精确范围。
- [x] 写明生产单 Core、开发隔离对照、一次性切换和旧镜像回滚语义。
- [x] 明确 Servlet+jOOQ、Spring Modulith、Maven 和 Java 21 的选择理由。
- [x] 明确迁移期功能冻结和数据库结构冻结。
- [x] 用户确认 spec 后才创建 Java 工程或修改 CI。

**验收：** 文档之间不存在“渐进生产切流”“双写”“支付随迁移实现”等冲突表述。

## Task 1：建立完整接口与行为清单

**文件：**

- 新增：`contracts/core/public-openapi-python-baseline.json`
- 新增：`contracts/core/internal-endpoints.json`
- 新增：`contracts/core/route-inventory.json`
- 新增：`contracts/core/error-fixtures/`
- 新增：`contracts/core/sse-fixtures/`
- 新增：`contracts/core/service-auth-fixtures/`
- 新增：`scripts/export_core_migration_baseline.py`
- 新增：`tests/architecture/test_core_migration_baseline.py`

- [x] 先写失败测试，要求基线包含 115 条公共路径、148 个公共操作以及所有隐藏内部接口。
- [x] 导出当前 OpenAPI，保存 operationId、方法、路径、认证要求和响应 schema。
- [x] 静态扫描所有 Router，人工分类公共、内部、健康和调试入口。
- [x] 为统一错误、分页 cursor、请求 ID、Cookie、SSE、文件下载和重定向保存合法样例。
- [x] 为 Ed25519 token、body/query digest、过期、错误 audience、错误权限和重放保存跨语言向量。
- [x] 为每个路由登记所属模块、读写性质、事务、副作用和 Python 测试位置。
- [x] CI 禁止在未更新 spec 的情况下改变基线数量或删除 operationId。

**TDD 红灯：** 删除任一路由登记、错误样例或签名向量时，基线测试必须失败。

## Task 2：创建 Java 工作区和最小垂直切片

**文件：**

- 新增：`pom.xml`
- 新增：`.mvn/wrapper/**`
- 新增：`mvnw`
- 新增：`mvnw.cmd`
- 新增：`apps/core-api-java/pom.xml`
- 新增：`apps/core-api-java/src/main/java/cn/inkforge/core/**`
- 新增：`apps/core-api-java/src/test/java/cn/inkforge/core/**`
- 修改：`.github/workflows/build.yml`

- [x] 先写 JUnit 测试，要求 `/api/v1/health/live`、未知路径和 requestId 行为与 Python 一致。
- [x] 创建最小 Spring Boot 应用，不连接数据库、不注册业务写接口。
- [x] 实现统一 JSON 配置、中文错误信封和 requestId filter。
- [x] 增加 ArchUnit/Spring Modulith 测试，禁止领域包反向依赖 controller 或基础设施实现。
- [x] CI 增加 `./mvnw verify`，但生产 Compose 仍构建 Python Core。
- [x] 固定 Maven wrapper、依赖锁定策略和 Java toolchain。

**验收：** Java 应用可独立启动，最小测试先红后绿，且本次提交不会改变生产镜像。

## Task 3：数据库、jOOQ 与结构守卫

**文件：**

- 新增：`packages/service-contracts-java/pom.xml`
- 新增：`apps/core-api-java/src/test/resources/db/`
- 新增：`apps/core-api-java/src/main/java/cn/inkforge/core/platform/db/**`
- 新增：`apps/core-api-java/src/test/java/cn/inkforge/core/platform/db/**`
- 修改：`apps/core-api-java/pom.xml`

- [x] 先写 Testcontainers 测试，要求使用 PostgreSQL 14 + pgvector，而非 H2。
- [x] 从已批准开发库只读导出测试 schema baseline；它只用于隔离容器，不是生产迁移入口。
- [x] 在测试容器内重建 85 张表、22 个枚举和必要扩展。
- [x] 从真实 Testcontainers schema 运行 jOOQ codegen，生成代码不得手工编辑。
- [x] 实现 Java canonical schema fingerprint，并与 Python 相同 fixture 比较。
- [x] 验证当前指纹 `8aaa...629` 精确一致。
- [x] 禁止 `spring.jpa.hibernate.ddl-auto`、自动 Flyway、Liquibase 和启动期 DDL。
- [x] 事务测试覆盖复合外键、部分唯一索引、PostgreSQL enum、`TIMESTAMP(3)`、quoted camelCase 和 pgvector。

**验收：** Java 只读连接 `novelwriterdev` 时结构守卫 ready；对任一列、约束或索引漂移必须拒绝就绪。

2026-08-25 已使用受数据库名门禁的 Java 只读验收测试真实连接 `novelwriterdev`：结构 ready、0 diff、
实时指纹与冻结 contract 一致；未执行 DDL、DML 或生产库连接。

## Task 4：语言中立契约与 Java 服务鉴权

**文件：**

- 新增：`contracts/core/agent/*.schema.json`
- 新增：`packages/service-auth-java/**`
- 新增：`packages/service-contracts-java/**`
- 修改：`packages/service-contracts/tests/**`
- 修改：`packages/service-auth/tests/**`

- [x] 从当前 Pydantic 契约导出稳定 JSON Schema，并写测试禁止无版本变更的结构漂移。
- [x] Java DTO 从语言中立/冻结 OpenAPI 机械生成，不手写第二套字段定义。
- [x] Java 实现 Ed25519 签发、验签、body/query digest、权限、task/run/job 绑定和时钟偏差规则。
- [x] Java 与 Python 对全部 golden vectors 逐字节一致。
- [x] Java Redis replay store 覆盖首次接受、重复拒绝和 TTL；Redis 故障关闭测试随实际适配器完成。
- [x] 构建 Java Agent HTTP client，并以本地 HTTP 桩验证超时、无效响应、调试查询及 Seedance 未知提交结果。
- [x] Agent Service 源码不做业务改造，只允许为语言中立契约增加兼容测试。

**验收：** 现有 Agent 不改业务代码即可与 Java 测试 Core 完成签名请求和回调。

## Task 5：平台 HTTP、配置、文件与可观测性

**范围：** `platform`、`operations` 模块。

- [x] 为配置缺失、生产弱密钥、代理网段、内部路径和文件路径攻击先写失败测试。
- [x] 实现配置校验、可信代理、客户端 IP、Cookie 安全属性和统一异常映射。
- [x] 实现 liveness/readiness、数据库/Redis/Agent/后台任务检查及现有响应字段。
- [x] 实现流式上传、排他创建、`O_NOFOLLOW` 等价保护、SHA-256 和受控下载。
- [x] 实现后台任务监督器，未知崩溃必须使 readiness 失败。
- [ ] 实现结构化日志、requestId、敏感字段清洗和完整异常诊断。
- [ ] 在 448 MB 容器限制下做启动、空闲、上传和并发基准；不满足时在切换前另行批准资源调整。

**验收：** Python 与 Java 的健康、错误、安全边界和文件行为黑盒一致。

## Task 6：身份认证模块等价迁移

**范围：** `identity`。

- [x] 先写注册、登录、退出、whoami、重复用户名、错误密码、限流和 Cookie 黑盒测试。
- [x] 保持现有 bcrypt、JWT claims、过期时间和 Secure/SameSite 行为。
- [x] 保持 Redis 限流失败语义，不引入手机号字段或 OTP。
- [x] 验证 Python/Node 历史浏览器会话可被 Java 读取，Java 签发的会话符合冻结契约。
- [ ] 权限错误继续返回当前 401/403/404 语义，不能泄露资源是否存在。

**验收：** 现有 Web 登录和 Python CLI 登录测试改指向 Java 后全部通过。

## Task 7：普通内容领域迁移

**范围：** `novels`、`chapters`、`lore`、`outlines`。

- [ ] 按 route inventory 为每个读写接口先补 characterization test。
- [ ] 先迁只读查询，再迁写入；但生产不按路径切流。
- [ ] 保持用户归属、revision/CAS、排序、删除语义、字数统计输入和完整正文保存。
- [ ] 每个 repository 使用真实 PostgreSQL 事务测试，拒绝跨用户、跨小说和旧 revision。
- [ ] 同一 fixture 分别运行 Python/Java，比较响应和最终数据库快照。
- [ ] 保留 Python Core 全套测试，直到最终切换后的回滚观察期结束。

**验收：** 对应公共接口、Web 页面和 CLI 命令在 Java 测试环境通过。

## Task 8：资料、文风与中短篇版本领域迁移

**范围：** `references`、`styles`、`shortmedium`。

- [ ] 先测试 TXT 上传、完整文本、不静默截断、素材私有归属和文件失败清理。
- [ ] 实现 RAG 投递事实、文风画像任务和 Agent 回调等价行为。
- [ ] 实现中短篇不可变版本、diff、adopt、restore 和 review 状态规则。
- [ ] Agent 不可用、重复投递、回调重放和未知 jobId 必须有测试。
- [ ] Web/CLI 现有场景全部指向 Java 测试 Core 验收。

## Task 9：计费、ReviewArtifact 与正式写入迁移

**范围：** `billing`、`reviews`。

- [ ] 先写积分微单位、grant、TokenUsage、重复 requestId、零费用和余额不足测试。
- [ ] 事务内原子验证 user/novel/task/run，再写 TokenUsage 与 CreditLedger。
- [ ] 保持现有 Ed25519 grant、有效期、model/agent 绑定和四项 token 规则。
- [ ] 先写 ReviewArtifact 状态机、revision、评审、patch/rewrite 和用户确认测试。
- [ ] 实现 `proposal -> ReviewArtifact -> 复审/返工 -> 用户确认 -> 正式应用`，禁止绕过。
- [ ] 正式应用失败必须整体回滚，重复确认必须幂等。
- [ ] 不实现支付订单、手机号或任何新表。

**验收：** 当前计费和草案全套测试、Agent grant/charge 契约、Web 审核流程全部通过。

## Task 10：写作、质量、Outbox、SSE 与恢复迁移

**范围：** `writing`、`quality`、`agentgateway`。

- [x] 先将任务状态、命令状态、checkpoint、Outbox、SSE 序号和终态回调固化为状态转移测试。
- [x] 实现 Agent 工具网关全部只读工具、权限交集和并发属性。
- [x] 实现 writing/quality dispatcher、到期补投、租约、幂等、取消和 reconciler。
- [x] 实现 SSE Last-Event-ID、重复过滤、序号缺口和断线恢复。
- [x] Redis 只保留执行索引；PostgreSQL 继续保存业务权威事实。
- [ ] 对提交成功但响应丢失、重复回调、旧 jobId、服务重启和后台任务崩溃做故障注入。
- [ ] 使用 fake Agent 完成长篇、中短篇、质量检查和 ReviewArtifact 全闭环。
- [ ] 使用真实 Python Agent 的非付费 fake provider 做跨服务验收。

**验收：** Agent 无需维护 Python Core 专用兼容分支即可与 Java Core 完成所有现有工作流。

## Task 11：视频与媒体生产域迁移

**范围：** `video`。

当前进度（2026-08-25）：项目/素材、章节改编、视觉设定、逐镜渲染和 P1–P3 后期四层已完成，全部
48 个视频 HTTP 操作已显式接线；`series` 项目不再被旧 `VideoScene` 试制模式错误阻断。当前机器没有
FFmpeg/ffprobe，因此实现与隔离测试已完成，但生产镜像内的真实媒体烟测仍保持未完成。

- [x] 按 P0–P3 现有 spec 为公共与内部接口建立 Java characterization tests。
- [x] 迁移素材权利、视觉设定、章节改编、提示词和不可变版本链。
- [x] 迁移 Seedance 任务、provider media token、Take 归档、确认和补偿任务。
- [x] 迁移关键帧、粗剪、声音字幕、导出任务和完整历史分支。
- [x] 使用 `ProcessBuilder` 实现 ffprobe、抽帧、合成、字幕烧录、取消和子进程回收。
- [x] 故障注入覆盖数据库提交响应丢失、临时文件清理、哈希不符、跨项目素材和导出重试。
- [ ] 在 Core Java 生产镜像内运行现有真实 FFmpeg 烟测等价版本。

**验收：** 浏览器能在 Java 测试环境完整走通当前视频工作台；历史 Python 产物仍可读取和下载。

## Task 12：OpenAPI、Web 与完整兼容门禁

**文件：**

- 修改：`scripts/generate_api_client.mjs`
- 修改：`packages/api-client/**`
- 新增：`apps/core-api-java/src/test/java/cn/inkforge/core/compatibility/**`
- 修改：`.github/workflows/build.yml`

- [ ] Java 实现必须通过冻结 OpenAPI，而不是依赖注解默认值碰巧生成相似 schema。
- [ ] 对比方法、路径、operationId、required/nullability、enum、响应和安全声明。
- [ ] TypeScript 客户端改由 Java OpenAPI 生成，结果不得产生未解释漂移。
- [ ] 运行全部 Web 测试、typecheck、lint、Next.js build。
- [ ] 在 Java Core + Python Agent + Next.js 的完整 Compose 测试环境运行浏览器 E2E。
- [ ] 删除任一 Python Core 路由实现前，route inventory 必须证明 Java 已覆盖。
  - [x] 使用 2 个共享 fixture 启动两套隔离 Core/数据库，直接比较认证、小说、章节、中短篇设定资料和版本共 17 个 HTTP 步骤及最终业务快照。

**验收：** 148 个公共操作、全部内部接口、Web、Agent 和数据库副作用兼容门禁全部绿色。

## Task 13：Java CLI 等价迁移

**文件：**

- 新增：`tools/inkforge-cli-java/**`
- 修改：`tools/inkforge-cli/README.md`
- 新增：`tools/inkforge-cli-java/src/test/**`

- [x] 以现有 125 命令 registry 为冻结基线，先写 Picocli registry 失败测试。
- [x] 保持命令名、参数、stdin JSON、JSONL、文件下载、TTY 密码和 exit code。
- [x] 从同一公共 OpenAPI 生成 Java client，不为 CLI 手写第二套 DTO。
- [x] 先迁只读命令，再迁写命令；所有写命令保持 clientRequestId 和用户确认语义。
- [ ] 同一命令分别运行 Python CLI 与 Java CLI，归一化后输出一致。
  - [x] 全部 125 个命令的最小输入、远端错误、退出码和输出信封直接差分一致。
  - [x] 30 条代表成功链路、全部 5 个 watcher 和 10 条文件链路直接差分一致。
  - [ ] 补齐其余命令的成功分支，并对 Java Core 执行具名开发数据端到端验收。
- [ ] Java CLI 完整通过后，生产操作 Skill 才允许切换 executable。
- [ ] Python CLI 保留到 Java Core 与 Java CLI 共同稳定观察期结束。

## Task 14：生产镜像、部署脚本和回滚演练

**文件：**

- 修改：`infra/docker/core-api.Dockerfile`
- 修改：`infra/compose.yaml`
- 修改：`scripts/deploy-production.sh`
- 修改：`scripts/compose_smoke.sh`
- 修改：`scripts/upload-docker-images.sh`
- 修改：`tests/architecture/**`

- [ ] Java 镜像继续命名 `inkforge-core-api:<sha>`，服务名和网络别名保持 `core-api`/`core-api-internal`。
- [ ] 镜像安装 JRE、FFmpeg 和 CJK 字体，仍使用 UID/GID 10001、只读根文件系统和受控 tmpfs。
- [ ] 替换当前容器内 Python schema 校验命令，调用 Java schema guard/Actuator readiness。
- [ ] 健康检查不得依赖镜像内 Python。
- [ ] JVM 显式设置 heap、Metaspace、退出 OOM 和容器内存感知参数，并在 448 MB 限额验证。
- [ ] 部署脚本不得启动第二个 Core service；`compose up` 只替换同名容器。
- [ ] 在独立演练环境先运行 Python 镜像，再部署 Java 镜像并验证；失败后恢复 Python 镜像。
- [ ] 回滚期间不运行数据库 down，因为迁移期没有业务 DDL。
- [ ] 连续执行两次 Java 部署，验证幂等、上传卷、Redis、Agent 和历史任务恢复。

**验收：** 回滚演练证明旧 Python 镜像能在不改数据库的情况下恢复，并通过现有 smoke。

## Task 15：一次性生产切换

### 切换前硬门禁

- [ ] Task 0–14 全部完成；
- [ ] 用户明确批准具体 Java Core 提交和切换窗口；
- [ ] Java Core 全量测试、Python 基线测试、Web、Agent、CLI、OpenAPI、schema、Compose 全绿；
- [ ] 开发库和独立演练库无结构差异、无 Java 特有数据；
- [ ] 生产备份及 SHA-256/恢复清单可读；
- [ ] 上一 Python 生产镜像完整存在；
- [ ] 没有 pending/running/archiving/rendering 等不可安全中断任务，或已有明确恢复验证；
- [ ] JVM 448 MB 稳定性、FFmpeg 峰值和 2 核 2 GB 整机容量已验证。

### 切换步骤

1. 冻结发布，记录当前生产提交和镜像；
2. 只读检查数据库身份与 schema 指纹；
3. 生成并校验生产备份；
4. 通过现有 CI 构建 Java `inkforge-core-api:<sha>`；
5. `docker compose up --no-build -d --wait` 替换同名 Python Core 容器；
6. 运行 Java schema guard、Core/Agent readiness、Compose smoke、HTTPS 与 `/internal/**` 边界检查；
7. 使用现有账号执行只读 Web/CLI 验收，再执行一条明确、可回滚的 fake Agent 闭环；
8. 验收失败立即恢复上一 Python 镜像；
9. 成功后解除维护窗口，进入观察期。

### 观察期

- [ ] 至少跨过后台补偿、SSE 重连、Agent 回调和视频任务的完整调度周期；
- [ ] 监控 JVM 内存、GC、线程、连接池、Redis、数据库锁、5xx、任务积压和文件增长；
- [ ] 不在观察期增加支付、手机号或其他新功能；
- [ ] 观察期结束并再次批准后，才删除 Python Core 代码和 Python CLI。

## Task 16：清理旧实现并建立新增功能起点

- [ ] 删除 `apps/core-api` Python 实现及其 Core 专用依赖；
- [ ] 把 `apps/core-api-java` 重命名或治理为正式 `apps/core-api`；
- [ ] 删除 Python CLI，正式入口指向 Java CLI；
- [ ] 保留 Agent 所需 Python contract/auth 包，并由语言中立 schema 校验；
- [ ] 更新 AGENTS、DOCS、requirements、部署文档和架构审计；
- [ ] 归档本计划和迁移兼容基线，但保留 golden fixtures；
- [ ] 全量验证当前功能后建立“手机号身份”和“支付计费”两个独立新 spec；
- [ ] 新功能不得复用迁移授权修改数据库。

## 全量验收命令基线

实施后至少需要形成以下统一入口，具体 Maven profile 在 Task 2 固化：

```bash
./mvnw verify
uv run pytest
uv run ruff check .
uv run mypy apps/agent-service/src packages/service-contracts/src packages/service-auth/src
npm run api:check
npm run typecheck
npm run lint
npm run test:web
npm run build
docker compose --env-file .env.example -f infra/compose.yaml build web core-api agent-service
```

在最终清理 Python Core 后，`uv run pytest` 仍用于 Agent 与保留的 Python 共享契约，不再包含 Core 测试。

## 预计周期

以单人边学习 Spring Boot、边执行严格 TDD 估算：

- Task 0–4：4–8 周；
- Task 5–9：8–16 周；
- Task 10–11：8–16 周；
- Task 12–14：4–8 周；
- 切换、观察和清理：2–6 周。

完整周期更现实地按 6–12 个月规划。任何缩短周期的决定都应减少迁移范围，而不能删除事务、兼容、故障注入或
回滚门禁。
