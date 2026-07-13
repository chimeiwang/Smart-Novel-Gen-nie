# 认证、计费与运维需求

## 目标

提供账号认证、资源归属校验、模型计费、服务间互信、可恢复运行和适合 2 核 2 GB 单机的生产部署。

## 浏览器认证

- 首页和登录页公开，其余页面由 Next.js `proxy.ts` 检查 `inkforge-token` Cookie。
- 注册、登录、登出和当前用户接口由 Core API 提供。
- 用户名为 3 至 32 位小写字母、数字、下划线或短横线；密码至少 6 位。
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

- Core 先创建并持久化 `WritingTask`，再提交 Redis 队列。
- Agent 每个稳定步骤通过签名回调保存版本化图快照。
- Agent 进程退出后，另一个兼容实例可以领取租约并从最后稳定检查点继续。
- Redis 丢失时，Core 对账器重新提交数据库中非终态任务；不得重复生成草案或扣费。
- `WritingMessage` 只保存用户可见聊天记录，不能反推图状态。

## 人工日志

- Agent 日志写入 `/data/agent-logs` 命名卷。
- 同一任务恢复运行追加到同一文件。
- 保存完整模型 messages、模型正文和中文状态切换。
- 不记录 tools schema、tool_calls、工具参数或工具结果。
- 调试读取默认关闭；开启后仍需浏览器认证、用户归属和 `agent:debug:read` 服务权限。

## 生产编排

`infra/compose.yaml` 包含 Nginx、Web、Core API、Agent Service 和 Redis。生产 PostgreSQL 14 继续作为宿主机服务运行，只有 Nginx 发布容器端口。

生产发布由 GitHub Actions 在 Runner 上构建带提交哈希标签的 Web、Core API 和 Agent Service 三张镜像，经 SSH 加载到服务器，再以 `--no-build` 启动 `infra/compose.yaml`。2 核 2 GB 服务器不得现场安装依赖或构建镜像；缺少 `.env`、四个服务密钥、宿主机 PostgreSQL 连接或可恢复备份时必须停止部署。

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
- Redis `maxmemory` 为 64 MB，关闭 AOF；
- 所有容器使用非 root 用户、只读根文件系统、健康检查和资源上限。

## 常用配置

| 变量 | 所属服务 | 用途 |
| --- | --- | --- |
| `DATABASE_URL` | Core | 现有 PostgreSQL 地址 |
| `JWT_SECRET` | Core、Web | 浏览器会话签名 |
| `REDIS_URL` | Core、Agent | 队列、事件和防重放 |
| `OPENAI_API_KEY` | Agent | 模型服务密钥 |
| `OPENAI_BASE_URL` | Agent | 模型服务地址 |
| `OPENAI_MODEL` | Agent | 模型名称 |
| `CORE_SERVICE_PRIVATE_KEY_PATH` | Core | Core 签名私钥 |
| `AGENT_SERVICE_PUBLIC_KEY_PATH` | Core | Agent 验签公钥 |
| `AGENT_SERVICE_PRIVATE_KEY_PATH` | Agent | Agent 签名私钥 |
| `CORE_SERVICE_PUBLIC_KEY_PATH` | Agent | Core 验签公钥 |
| `WORKFLOW_HUMAN_LOG_DIR` | Agent | 人工日志目录 |

## 验收标准

- 用户可以注册、登录、登出并查看计费摘要。
- 未登录或越权请求不能访问受保护资源。
- Agent 不能连接数据库，内部伪造、重放、跨任务或跨小说请求会被拒绝。
- 余额不足时模型调用不会开始；重复完成回调不会重复扣费。
- Agent 重启后任务可以从稳定检查点恢复。
- Nginx 是唯一公网入口，公网 `/internal/**` 返回 404。
- 数据库结构指纹在迁移前后保持不变。
