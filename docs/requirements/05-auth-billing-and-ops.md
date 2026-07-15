# 认证、计费与运维需求

## 目标

提供账号认证、资源归属校验、模型计费、服务间互信、可恢复运行和适合 2 核 2 GB 单机的生产部署。

## 浏览器认证

- 首页和登录页公开，其余页面由 Next.js `proxy.ts` 检查 `inkforge-token` Cookie。
- 注册、登录、登出和当前用户接口由 Core API 提供。
- 用户名输入先去除首尾空白并转为小写，再按 3 至 32 位小写字母、数字、下划线或短横线校验和存储；密码至少 6 位。
- 密码由 Python bcrypt 哈希，禁止保存明文。
- 会话使用 HS256 JWT，写入 httpOnly、sameSite=lax Cookie，有效期 30 天。
- 登录失败不区分用户名不存在和密码错误。

## 资源授权

小说、章节、写作任务、会话、消息、质量检查、参考资料、文风和 ReviewArtifact 都必须沿关系校验到当前用户。历史 `Novel.userId = null` 只允许显式兼容，不能成为新数据规则。

浏览器只能访问 `/api/v1/**`。Nginx 必须阻断公网 `/internal/**`。

## 服务间互信

Core API 与 Agent Service 使用 Ed25519 服务令牌：

- 令牌绑定签发者、受众、权限、任务、运行、小说、请求体摘要和查询摘要；
- 令牌有效期短，校验时限制时钟偏差；
- 写入类请求的 `jti` 必须通过 Redis 防重放；
- 内部接口同时校验直接 TCP 对端网段，不信任 `X-Forwarded-For`；
- 私钥只挂载到对应签发服务，不能写入镜像或仓库。

Agent Service 不加入数据库网络、不接收 `DATABASE_URL`，只能通过 Core 内部接口读取上下文、提交草案和回写状态。

## 积分与模型计费

注册成功发放 1000 积分，并写入 `CreditLedger.signup_bonus`。

真实模型调用前：

- Core 根据用户、模型和请求估算成本；
- 余额不足时拒绝授权；
- Core 签发与任务、运行和请求绑定的短期模型授权。

调用结束后：

- Agent 上报实际 token usage；
- Core 在短事务中幂等扣减余额；
- 同步写入 `CreditLedger.ai_charge` 和 `TokenUsage`；
- 重复回调不能重复扣费。

计费和草案应用属于关键写入，禁止放入可丢弃队列。

## 运行恢复

- Core 在同一 PostgreSQL 事务中创建 `WritingTask` 和 `WritingRunCommand`；普通恢复和草案决定也先保存命令事实，再尝试提交 Redis 队列。
- 命令 dispatcher 使用命令 ID 作为稳定 job ID，并对 pending 到期命令退避补投；Redis 短时不可用不会丢失已经返回 202 的请求。
- 命令 dispatcher 也对账超时的 `submitted/processing` 命令，并消费 Agent 返回的真实 job 状态；Redis 已为终态而 PostgreSQL 尚未收到正式回调时，必须在锁定命令与任务的同一事务中幂等收敛失败，不能把终态误记为已重新提交。
- Agent 每个稳定步骤通过签名回调保存版本化图快照。
- 写作回调协议使用命令 ID 作为 `jobId`；Core 在持久化前复核当前活动命令，旧命令回调不得改变任务、快照、命令或事件流。
- 检查点事件序号只能单调前进；Redis 短期事件状态丢失后，只允许经过 PostgreSQL 身份校验的当前 job 从持久检查点之后重建序号基线。
- Agent 进程退出后，另一个兼容实例可以领取租约并从最后稳定检查点继续。
- Redis 丢失时，dispatcher 补投活动命令；旧任务对账器只处理没有活动命令的 active 或 waiting_call 任务，在任务行锁内先创建唯一持久命令再交给 dispatcher，不重新投递 awaiting_user_review。
- 旧写作任务的终态对账必须校验领取时的任务阶段和图快照仍未变化；延迟终态不得覆盖新阶段或新快照。
- 文风画像、质量检查和 RAG 索引分别从 `StylePortraitTask`、`WorkflowRun(kind=quality_check)` 和 `RagDocument` 恢复投递；进程内任务或 Redis 状态都不是这些工作的唯一事实来源。
- Agent 对重复稳定 job ID 返回 Redis 中的实际任务状态。Core dispatcher 遇到 `completed/failed/cancelled` 时必须幂等结束仍处于 PostgreSQL 活动态的画像、质量检查或 RAG 记录，不能把终态 job 当作已重新排队；已经完成的业务记录和 RAG 的新内容版本不得被旧 job 覆盖。
- Core 的命令、旧任务对账、画像、质量检查和 RAG dispatcher，以及 Agent 的队列消费者，都由生命周期任务监督器管理；后台协程异常退出后按 1、2、4、8 秒、最高 30 秒退避重启，稳定运行窗口结束后清零连续失败计数。就绪检查必须检查实际运行的内部 `Task`，启动、退避、连续失败和监督器退出时不能只因对象存在而报告健康。
- 后台循环只在明确的数据库、网络或 Redis 暂态异常上原地退避；TypeError、Pydantic 契约错误和其他未知程序错误必须退出循环交给监督器。Redis OOM、MISCONF 和 READONLY 等写入拒绝立即使消费者退出并让 readiness 失败。
- `WritingMessage` 只保存用户可见聊天记录，不能反推图状态。

## 版本化数据迁移

2026-07-14 的 PostgreSQL schema 变更是用户明确批准的单次例外：新增 `WritingRunCommand`，为 `WritingStyle` 增加强制 `userId`，并为 `StylePortraitTask` 增加可空 `section`。迁移执行前必须完成可恢复备份；按已批准方案清空旧文风、文风参考和画像任务数据，同时保留用户、小说、章节、会话及其他正式数据。应用启动不得自动修改 schema。

## 人工日志

- Agent 日志写入 `/data/agent-logs` 命名卷。
- 同一任务恢复运行追加到同一文件。
- 保存完整模型 messages、模型正文和中文状态切换。
- 不记录 tools schema、tool_calls、工具参数或工具结果。
- 调试读取默认关闭；开启后仍需浏览器认证、用户归属和 `agent:debug:read` 服务权限。

## 生产编排

`infra/compose.yaml` 包含 Nginx、Web、Core API、Agent Service 和 Redis。生产 PostgreSQL 14 继续作为宿主机服务运行，只有 Nginx 发布容器端口。

生产发布由 GitHub Actions 在 Runner 上构建带提交哈希标签的 Web、Core API 和 Agent Service 三张镜像，经 SSH 加载到服务器，再以 `--no-build` 启动 `infra/compose.yaml`。2 核 2 GB 服务器不得现场安装依赖或构建镜像；缺少 `.env`、四个服务密钥、宿主机 PostgreSQL 连接或可恢复备份时必须停止部署。

生产 SSH 必须严格校验管理员离线核对过的主机公钥：

- GitHub `production` environment 必须配置 `DEPLOY_SSH_KNOWN_HOSTS` Secret；内容由管理员通过可信渠道取得并在线下比对，不能在部署时使用 `ssh-keyscan` 动态信任远端；
- workflow 把该 Secret 写入权限为 600 的临时 `known_hosts` 文件，所有 SSH、SCP 和上传脚本统一使用 `StrictHostKeyChecking=yes`；
- Secret 或文件缺失、不可读、为空时，必须在首次网络连接前停止部署；日志不得输出主机键、SSH 私钥、`.env` 或服务密钥内容。

生产 deploy job 使用独立 `production` 并发组，后续版本必须排队，不能取消正在执行的版本切换或自动回滚。部署脚本在切换前按 Compose project/service label 读取 `web`、`core-api` 和 `agent-service` 当前运行镜像：

- 三个服务均不存在时视为首次部署；新版本失败时明确报告没有可回滚版本，不伪造恢复成功；
- 只存在部分服务、镜像仓库不符合约定、三服务标签不一致或旧镜像任一缺失时，在启动新容器前停止部署并要求人工检查；
- 三服务标签一致且旧镜像均存在时，才把该标签作为自动回滚目标。

新版本 `compose up --no-build -d --wait`、只读 schema 指纹检查或生产 smoke 任一失败时，脚本自动用上一标签恢复三个服务，并再次执行 Compose 状态、schema 指纹和 smoke 检查。日志出现“新版本部署失败，旧版本已恢复”表示服务已恢复但本次发布仍失败，CI 必须保持非零；出现“自动回滚也失败”表示新旧版本均未通过验收，必须立即人工处理。回滚不得执行 `down -v`、删除卷或镜像、重写 `.env`、现场构建或数据库迁移。

网络边界：

- `public_net`：Nginx、Web、Core；
- `agent_net`：Core、Agent、Redis；
- `data_net`：Core、Redis；Core 通过 Docker host gateway 访问宿主机 PostgreSQL；
- Agent 不得加入 `data_net`。

数据库约束：

- 生产 Compose 不创建 PostgreSQL 容器或数据卷，测试 Compose 使用独立测试数据库；
- Core 通过 `host.docker.internal` 连接现有宿主机 PostgreSQL 14；
- 不提供初始化 SQL；
- 不执行迁移、建表或删表；
- Core 启动就绪检查对现有 schema 做只读指纹校验。

2 核 2 GB 默认限制：

- 每个 Python 服务一个 worker；
- 同时只执行一个模型任务；
- Redis `maxmemory` 为 64 MB，关闭 AOF，并使用 `maxmemory-policy noeviction`；内存耗尽时必须明确拒绝新写入，不能淘汰队列、事件或防重放键；
- Agent 队列完成、失败或取消的 job 只在 Redis 保留默认 7 天、最少 24 小时的终态 tombstone；终态时间 ZSET 驱动有界清理，过期后删除 status 和索引，PostgreSQL 继续作为长期幂等事实来源。
- 升级前缺少终态 ZSET 的旧 status 使用 HSCAN 游标分批回填 tombstone，并清除 ready、processing、payload、lease、attempt 和 score 残留；过期租约缺少 payload 或 score 时原子收敛为 failed，不能留下 running 孤儿。
- ready ZSET 按优先级分别查询已经到期的成员，未来才可重试的高优先级 job 不得阻塞当前已到期的低优先级 job；同优先级仍按 readyAt 排序。
- 所有容器使用非 root 用户、只读根文件系统、健康检查和资源上限。

运维必须监控 Redis `used_memory`、`evicted_keys` 和写入被拒绝数量。`evicted_keys` 应持续为 0；内存接近上限或出现写入拒绝时先停止接收新的模型任务并扩容或清理可确认过期的数据，不能临时切回淘汰策略。

## 常用配置

| 变量 | 所属服务 | 用途 |
| --- | --- | --- |
| `DATABASE_URL` | Core | 现有 PostgreSQL 地址 |
| `JWT_SECRET` | Core、Web | 浏览器会话签名 |
| `REDIS_URL` | Core、Agent | 队列、事件和防重放 |
| `QUEUE_TERMINAL_RETENTION_DAYS` | Agent | Redis 队列终态 tombstone 保留天数，默认 7、最少 1；Compose 显式透传 |
| `RAG_INDEX_ENABLED` | Core、Agent | 同时启用资料索引投递和 embedding 就绪校验；两端必须使用相同值 |
| `OPENAI_API_KEY` | Agent | 模型服务密钥 |
| `OPENAI_BASE_URL` | Agent | 模型服务地址 |
| `OPENAI_MODEL` | Agent | 模型名称 |
| `CORE_SERVICE_PRIVATE_KEY_PATH` | Core | Core 签名私钥 |
| `AGENT_SERVICE_PUBLIC_KEY_PATH` | Core | Agent 验签公钥 |
| `AGENT_SERVICE_PRIVATE_KEY_PATH` | Agent | Agent 签名私钥 |
| `CORE_SERVICE_PUBLIC_KEY_PATH` | Agent | Core 验签公钥 |
| `WORKFLOW_HUMAN_LOG_DIR` | Agent | 人工日志目录 |

Core 与 Agent readiness 在后台任务不健康时保留 `checks` 兼容字段，并在 `backgroundTasks` 中返回具体任务名及稳定错误码，便于区分未启动、退避、连续失败和监督器停止。

`DEPLOY_SSH_KNOWN_HOSTS` 属于 GitHub `production` environment Secret，不是应用容器环境变量；只用于为发布流程生成严格校验的临时 `known_hosts` 文件。

## 验收标准

- 用户可以注册、登录、登出并查看计费摘要。
- 未登录或越权请求不能访问受保护资源。
- Agent 不能连接数据库，内部伪造、重放、跨任务或跨小说请求会被拒绝。
- 余额不足时模型调用不会开始；重复完成回调不会重复扣费。
- Agent 重启后任务可以从稳定检查点恢复。
- Nginx 是唯一公网入口，公网 `/internal/**` 返回 404。
- 数据库结构指纹在迁移前后保持不变。
- 生产 SSH 只信任离线核验的主机公钥，运行中的部署不会被后续提交取消。
- 新版本失败时可恢复到经验证的上一镜像；回滚成功仍保留发布失败状态。
