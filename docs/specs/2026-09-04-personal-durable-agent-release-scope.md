# 个人项目 Durable Agent 发布范围纠正

## 状态

- 日期：2026-09-04
- 状态：已批准，直接在 `codex/durable-agent-execution` 上实施
- 背景：项目由单一可信维护者个人使用。此前把多人团队供应链威胁模型扩大到本次 Agent 重构，导致发布流程被不必要地固定关闭。本规格纠正该范围偏移。

## 决策

本项目接受“能够修改 `main` 并访问 production environment 的维护者也拥有生产发布权”这一单维护者模型。不再要求候选仓库之外的不可变 Controller、OIDC 单操作凭据、SSH Broker、signed attestation、sealed genesis/current、发布 receipt 链或 development evidence 生产者。

这不是证明上述企业级威胁不存在，而是明确它们不属于当前个人项目的工程目标。相关历史设计退出当前发布路径，不得继续阻止普通构建、部署或 Agent 功能验收。

## 必须保留的 Agent 可靠性边界

- Core 是 V2 Run、Step、Evidence、Event、Evaluation、ReviewArtifact、消息和计费的唯一业务权威。
- Agent 使用独立 execution Redis、AOF、noeviction、fencing token、幂等 journal 和终态回放；普通队列 Redis 不能替代它。
- `DURABLE_AGENT_EXECUTION_SCHEMA_READY`、`DURABLE_AGENT_EXECUTION_ROUTE_MODE`、用户/小说 allowlist 与 Agent readiness 继续控制 fresh V2。
- `V1_FRESH_AGENT_STARTS_ENABLED=false` 继续用于迁移和 drain 窗口；既有幂等请求仍可按原 Run 重放。
- PostgreSQL forward migration、pre/post contract、活动 V1/V2 联合 drain、恢复 quarantine、已有 V2 事实后禁止 DDL rollback 和 V1-only 应用回滚继续保留。
- CLI、Web、SSE、计费、取消、重启恢复、callback 回放和本地跨服务故障测试继续保留。

## 删除的企业级发布控制面

以下能力从当前 Agent 分支移除，而不是改成空成功：

- 独立 Durable Agent V2 release/development evidence GitHub Workflow；
- release control bundle、manifest、receipt、boundary ledger、attestation、trust verifier 和 broker；
- 文件型 `DurableAgentReleaseGuard` 及其 Compose 只读挂载；
- production GitHub secret inventory、OIDC、双 SSH 角色、公钥轮换和 sealed genesis 门禁；
- 只服务于上述控制面的规格、脚本和测试。

历史安全设计可以从 Git 历史读取，但不再作为当前发布要求，也不再保留一个固定失败的生产入口。

## 个人项目最小发布流程

### 普通应用部署

1. `main` CI 全绿后使用既有 production environment 与单一 SSH 身份部署。
2. 严格校验 known_hosts，上传精确 commit 的三个镜像和 Git bundle。
3. 服务器以简单互斥锁防止两个部署交错，校验 commit、镜像、`.env` 与服务密钥。
4. 普通部署不执行 DDL；只按实时 schema 状态选择兼容的 Core/Agent 配置。`route=off` 不会自行关闭
   `V1_FRESH_AGENT_STARTS_ENABLED`，只有进入迁移或 drain 维护窗口时才由操作者显式设为 `false`。
5. 新栈 readiness 或 smoke 失败时恢复先前已记录的三镜像组合。

### Durable Agent V2 迁移

迁移是独立人工动作，不随普通 `main` push 自动执行：

1. 先运行 V2-aware 兼容镜像，并设置 `schemaReady=false`、`route=off`、`V1 fresh=false`。
2. 证明 V1/V2 联合 drain 为零并完成 PostgreSQL 与 execution Redis 备份。
3. 对开发库执行具名 forward 两次，导出并复验 contract；在任何 V2 Run 产生前完成 rollback 演练。
4. 对正式库再次备份并执行同一具名 forward；确认 post contract。
5. 设置 `schemaReady=true`、`route=off`，初始化并复验 drain indexes。
6. 只为维护者自己的一个 `userId + novelId` 开启 allowlist，使用公共 CLI 完成 canary。
7. canary 失败时回到 route-off 并回滚应用镜像；一旦存在 V2 Run，不执行 DDL rollback。

生产确认令牌继续只允许从服务器固定的 `0600` 文件读取；不得放入 GitHub 输入、argv 或日志。

## CLI 与 Skills

公共 Python/Java CLI 的命令、JSONL、SSE 和退出码不因本次范围纠正变化。`answer_question` 的 Skill 更新只依赖：

- 目标环境已部署对应 CLI/Core/Agent；
- 该 Skill 能操作的目标都会创建 V2 Run，而不是回落 V1；
- 真实 canary、消息身份和恢复测试通过；
- wrapper 具有 operation 级允许集合。

企业级 Controller、OIDC、Broker、attestation 或 sealed genesis 不再是 Local/Production Skill 的开放前提。

## 验收

- 当前分支不再包含固定失败的 Durable Agent 发布 Workflow。
- 原有个人项目构建和直接 SSH 部署路径恢复，且普通部署不会自动执行 V2 DDL。
- 删除文件型 release guard 后，fresh V2 仍受 schema、route、allowlist、readiness、会话归属和任务互斥保护。
- 迁移 helper 不再依赖 release boundary driver，但仍要求 drain、备份、确认文件、SQL/contract hash 与幂等状态。
- Agent、Core、CLI、Web、迁移、Compose 和跨服务 E2E 门禁通过。
