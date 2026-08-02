# 本地独立开发数据环境规格

## 状态

- 日期：2026-08-02
- 状态：待审阅
- 范围：Windows/WSL2 本地 PostgreSQL、Redis、生产数据只读快照恢复和本地启动隔离

## 背景

当前 `.env.local` 让本地 Core API 和 Agent Service 连接远程 PostgreSQL 与 Redis。执行
`npm run dev` 时，本地会同时启动 Web、Core API 和 Agent Service；远程服务保持运行时，两套服务
会共同读取同一组业务命令和 Redis 队列。本次故障已经证明，当前命令调度和终态回执消费尚不能安全
支持这种本地、远程混合运行方式。

本次只读核对确认：

- 本机 Windows 的 5432 和 6379 端口当前没有监听服务，也没有可用的 Windows Docker 命令；
- 本机已有 Ubuntu 22.04 WSL2，systemd 已启用，可以承载本地 Docker Engine；
- 远程宿主机运行 PostgreSQL 14.23，目标数据库当前约 37 MB；
- 远程 Redis 使用 `redis:7.4-alpine`，但其队列、租约、事件流和防重放键不适合复制到本地；
- 远程上传卷当前约 4 KB，可以单独归档并校验；数据库与上传文件不是同一个原子快照；
- 仓库不会自动创建 PostgreSQL schema，`infra/compose.test.yaml` 也要求已有的测试数据卷；
- 当前仓库存在与本任务无关的工作区修改，实施时不得覆盖或提交这些文件。

## 已确认决策

- 本地与远程使用彼此独立的 PostgreSQL 和 Redis，不再让本地开发服务加入远程运行集群。
- 本地数据服务运行在现有 WSL2 内的 Docker Engine 中，不要求安装 Docker Desktop。
- PostgreSQL 使用 `pgvector/pgvector:0.8.0-pg14`，同时匹配生产 PostgreSQL 主版本和当前
  `vector 0.8.0` 扩展版本；Redis 使用项目现有的 `redis:7.4-alpine`。
- 本地数据库名固定为 `inkforge_local`，不得复用远程数据库名；本地 Compose project 固定使用
  `inkforge-local-data`。
- PostgreSQL 从远程当前一致性快照恢复；Redis 必须从空实例开始，禁止复制远程 Redis 数据。
- 原始 PostgreSQL 快照只作为不可修改的本地恢复源；恢复完成后必须在 Core 启动前隔离快照中所有
  可自动调度的执行态，防止生产遗留任务在本地重放。
- 第一次应用验收强制使用 `MODEL_PROVIDER=fake` 和 `RAG_INDEX_ENABLED=false`。只有隔离审计为零、
  本地 Redis 隔离得到证明且三服务健康后，才恢复用户原有真实模型配置。
- 本地 PostgreSQL 和 Redis 端口只绑定 `127.0.0.1`，不得发布到局域网或公网。
- 远程操作仅限只读检查，以及通过宿主机 PostgreSQL 身份把 `pg_dump` 一致性快照流式传回本地；
  不停止远程服务，不在远程创建额外备份文件，不恢复远程数据库，不修改远程 schema 或业务数据。
- 恢复后使用当前 `schema-contract.json` 做只读结构指纹校验，不运行迁移、初始化 SQL、
  `create_all()` 或其他 DDL。

## 目标

- 建立可持久重启的本地 PostgreSQL 14 数据库，并恢复当前小说、版本、用户和写作历史。
- 建立与远程完全隔离的本地 Redis，使本地 Agent 只能消费本地任务。
- 隔离复制来的写作命令、质量检查、文风画像、RAG 索引和 Outbox 投递状态，同时保留正式小说、
  已应用版本、用户和可安全读取的历史终态。
- 让现有 `npm run dev` 无需改变 Core/Agent 架构即可连接本地数据服务。
- 在隔离验收后恢复当前真实模型配置；本地服务密钥保持不变，不把任何密码、连接串、数据库快照
  或私钥提交到 Git。
- 提供可重复的本地数据服务启动方式和防误连检查。
- 完成 schema、数据可读性、Redis 隔离和三服务健康检查。

## 非目标

- 本次不修复写作命令 dispatcher 的多实例领取、终态回执消费或队列心跳问题。
- 本次不让本地和远程 Core/Agent 继续共享同一个任务队列。
- 本次不修改 PostgreSQL schema，也不新增迁移。
- 本次不修改、重启、升级或修复远程生产服务；已观察到的远程 Core readiness 异常另行处理。
- 本次不建立生产数据的持续双向同步、逻辑复制或定时全量复制。
- 本次不自动清理本地数据库卷或已经校验成功的本地快照；本流程不创建新的远程备份文件。
- 本次不把重新生成小说正文并入基础设施改造；本地环境验收后再通过既有中短篇操作流程执行。

## 本地架构

```text
Windows 浏览器
      |
      v
Windows npm run dev
Web :43119 -> Core :8000 -> PostgreSQL 14 :5432
                    |  \
                    |   +------------> Redis 7.4 :6379
                    v                      ^
                Agent :8001 ---------------+
                    |
                    +----签名回调----> Core :8000

PostgreSQL 与 Redis 由 WSL2 Docker Engine 承载，
所有发布端口都只通过本机回环地址访问。
```

远程 PostgreSQL、Redis、Core 和 Agent 不在上述链路中。远程 PostgreSQL 只在创建一次性一致性快照时
由服务器本机的 `pg_dump` 读取。

## 仓库交付物

### 本地数据 Compose

新增独立的 `infra/compose.local-data.yaml`，只包含：

- `postgres`：使用 `pgvector/pgvector:0.8.0-pg14`、数据库 `inkforge_local`、命名卷和健康检查；
- `redis`：使用 `redis:7.4-alpine`、项目现有 noeviction 配置和健康检查；
- PostgreSQL、Redis 都只绑定 Windows 可访问的 `127.0.0.1` 端口；
- PostgreSQL 数据使用独立命名卷，Redis 不使用生产快照或远程数据卷；
- Compose project name 与生产 `inkforge` 分离，避免误操作生产编排。

生产 `infra/compose.yaml` 保持不变。

### 本地配置

- 新增不含真实秘密值的 `.env.local-data.example`；
- `.gitignore` 明确忽略真实 `.env.local-data` 和本地数据库快照；
- 实施时生成独立的随机 PostgreSQL 密码，同时写入本地数据 Compose 环境文件与 `.env.local` 的
  `DATABASE_URL`；
- 将 `.env.local` 的 `REDIS_URL` 改为 `redis://127.0.0.1:6379/0`；
- `.env.local` 中现有模型配置、JWT 和 Ed25519 服务密钥路径保持不变；
- 修改 `.env.local` 前，把原文件备份到用户本地应用数据目录，不把备份放入仓库。
- `.env.local-data`、配置备份和数据库快照只允许当前 Windows 用户读取；仅靠 `.gitignore` 不视为
  访问控制。

### 快照隔离工具

新增只允许操作本地副本的隔离入口。入口必须：

- 从环境变量读取连接信息，不把带密码的 URL 放入进程参数；
- 解析并强制数据库主机为 `127.0.0.1`、数据库名为 `inkforge_local`，同时核对 Docker 容器属于
  `inkforge-local-data` project；
- 默认只输出待隔离记录的分类和数量，必须显式传入本地确认参数才在单一事务中执行；
- 把活动 `WritingRunCommand` 收敛为本地隔离失败，并把仍处于 `active/waiting_call` 的
  `WritingTask` 收敛为本地错误；
- 把 `WorkflowRun` 的 `pending/running` 收敛为 `cancelled`，并同步结束其活动步骤；
- 把 `StylePortraitTask` 的 `pending/processing` 收敛为 `failed`；
- 把等待重新索引的 `RagDocument` 收敛为本地 `failed`，后续由用户明确触发重新索引；
- 清除复制来的 `WritingEventOutbox` 通知积压；
- 不删除小说、章节、中短篇正式版本、用户、计费历史或已终态的写作历史；
- 可重复执行，第二次审计必须报告零条可自动调度记录。

隔离工具只允许修改本地恢复副本的业务数据，不执行 DDL，也不改变结构指纹。

### 文档与自动检查

- README 增加本地数据服务首次安装、启动、停止、重新恢复和结构校验命令；
- Windows 文档和命令统一使用
  `wsl -d Ubuntu-22.04 --cd /mnt/f/code/inkForge -- docker compose --project-name inkforge-local-data
  --env-file .env.local-data -f infra/compose.local-data.yaml ...`，不假定 PowerShell 中存在裸 `docker`
  命令，也不依赖 Compose 自动发现非默认环境文件；
- 新增架构测试，确认本地数据 Compose 只发布回环端口、使用独立卷、包含健康检查且不改生产 Compose；
- 为本地恢复入口、隔离入口和凭据处理增加正反向测试；远程主机、错误数据库名、错误 Compose
  project、缺失容器或缺失确认参数必须在任何破坏性操作前被拒绝；
- 启动脚本继续拒绝缺失 `DATABASE_URL`、`REDIS_URL` 或服务密钥的配置。

## 远程备份与本地恢复

### 备份

1. 使用仓库 `.env` 中已有的服务器连接变量和用户机器现有 `known_hosts`；SSH 必须开启严格主机校验。
2. SSH 密码只从 `.env` 读入进程内存，不进入命令行参数、源文件或日志。
3. 不直接复用会把完整 `DATABASE_URL` 放入进程参数的现有备份/恢复/指纹脚本。
4. 远程命令使用 `sudo -u postgres pg_dump` 的宿主机身份认证，对数据库 `novelwriter` 创建
   custom-format 一致性快照，并通过 SSH stdout 直接流入本地权限受限的临时文件；远程不落盘。
5. 上传目录通过独立的只读 tar 流传回本地。它与数据库快照不具备跨资源原子一致性，只分别进行
   SHA-256 和归档可读性校验。
6. 临时文件校验成功后原子改名为正式本地快照；SSH 中断或校验失败时删除不完整临时文件。
7. 使用容器内 `pg_restore --list` 验证数据库归档可读，并把 SHA-256、大小和采集时间写入不含
   秘密值的本地清单。

`pg_dump` 使用一致性快照，不要求停止远程服务。本地数据库副本反映备份开始时已经提交的业务事实，
不承诺与备份结束后的远程新增数据同步。上传目录只是相邻时间点的文件归档，不宣称与数据库原子一致。

### 恢复

1. 先启动全新的本地 PostgreSQL 容器，等待健康检查通过。
2. 恢复入口必须同时验证目标主机为 `127.0.0.1`、目标数据库为本地专用数据库、目标容器属于
   本地 Compose project；任一条件不满足立即停止。
3. 恢复通过目标 PostgreSQL 容器内的本地 Unix socket 执行，不向 `pg_restore` 传递带密码 URL；
   使用 `--clean --if-exists --no-owner --no-acl` 只恢复 `inkforge_local`。
4. 使用从环境读取 URL 的本地校验入口执行当前 `schema-contract.json` 只读指纹校验；不得依赖 Core
   readiness 代替启动前检查，因为后台任务可能早于 readiness 失败开始运行。
5. 在 Core 启动前执行快照隔离工具，并确认第二次审计为零条可自动调度记录。
6. Redis 使用全新空库启动；恢复流程不读取远程 Redis，也不导入任何 Redis 文件或键。
7. 把 `.env.local` 临时切换为 `MODEL_PROVIDER=fake`、`RAG_INDEX_ENABLED=false` 后才允许首次启动应用。
8. 核对目标小说和当前已应用版本可以从本地 Core API 读取；隔离验收全部通过后再恢复原模型配置。

## 安全边界

- 不在工具输出中打印服务器 IP 以外的凭据、数据库连接串、密码、模型密钥或 SSH 主机密钥；秘密值
  也不得出现在子进程参数中。
- 本地 PostgreSQL 包含用户拥有的生产数据副本，因此端口只能绑定回环地址，备份目录不得进入 Git。
- 本地快照、上传归档、`.env.local-data` 和配置备份都必须设置为仅当前用户可读；最终报告明确记录
  每份额外数据副本的位置、所有者和保留责任。
- 任何恢复和清理命令都必须先解析并显示无秘密值的目标摘要，再验证目标属于本地环境。
- 禁止对远程数据库执行 `pg_restore`、`DROP DATABASE`、DDL 或批量业务更新。
- 禁止复制远程 Redis；共享 Redis 会再次使本地 Agent 成为远程队列消费者。
- 不自动删除未知的本地端口监听进程、Docker volume 或现有 WSL 数据。
- 如果 SSH 主机校验、快照校验、本地恢复、schema 指纹或执行态隔离任一步失败，保留原
  `.env.local` 配置并停止。

## 验收

### 基础设施

- WSL2 中 Docker Engine 与 Compose 可正常工作，并由 systemd 管理；
- 本地 PostgreSQL 和 Redis 容器健康；
- Windows 仅在 `127.0.0.1:5432` 和 `127.0.0.1:6379` 访问数据服务；
- 实测 Windows 回环地址可以连接，并确认 Windows 局域网地址不能连接这两个端口；不能只根据
  Compose YAML 推断暴露范围；
- PostgreSQL 数据在容器重建后仍保留，Redis 不含远程任务、租约或事件流。

### 数据与结构

- 下载快照和上传归档的 SHA-256 校验通过，`pg_restore --list` 与 `tar -tzf` 可以完整读取；
- 本地数据库结构指纹与 `apps/core-api/src/inkforge_core/db/schema-contract.json` 完全一致；
- 本地 PostgreSQL 主版本为 14，`vector` 扩展版本为 0.8.0；
- 本地数据库可以读取目标小说 `cmsab6kir4dtb9en83he6sdfj` 及当前已应用版本；
- 远程 PostgreSQL schema 指纹前后相同；远程审计只出现允许的只读查询和 `pg_dump`，不以生产持续
  运行时的普通数据行数变化判断本任务是否写入。
- 隔离入口第二次审计报告写作命令、质量检查、文风画像、RAG 索引和 Outbox 五类待处理数量均为零。

### 应用

- `.env.local` 的 PostgreSQL 和 Redis 主机均为本机回环地址；
- 首次使用 fake 模型启动 `npm run dev` 后，Web、Core API 和 Agent Service readiness 均通过；
- 用户可以登录并打开目标小说；
- 解析 `.env.local` 并检查实际连接目标，证明本地 Core 只连接回环 PostgreSQL/Redis；
- 使用唯一 canary/jobId 验证该标识只出现在本地 Redis，并对远程 Redis 做同一精确标识的只读查询，
  不使用会受生产正常流量干扰的全量键数量比较。

### 仓库

- 新增架构测试通过；
- 运行 `tests/architecture/test_compose_security.py` 及本地数据 Compose 相关测试；
- 运行快照隔离与防误恢复负例测试、相关 Ruff、Mypy 和项目必要静态检查；
- Git 变更中不存在 `.env.local-data`、数据库备份、密码、连接串或无关工作区修改。

## 失败恢复

- Docker/Compose 安装失败：不修改 `.env.local`，本地服务保持停止。
- 快照或传输校验失败：不执行恢复，删除不完整本地临时文件并保留无秘密诊断证据。
- 本地恢复或指纹校验失败：停止本地应用，保留数据库卷用于诊断，不切回远程共享 Redis。
- 执行态隔离失败或仍有待调度记录：禁止启动真实模型，停止本地应用并保留审计数量。
- 本地应用健康检查失败：检查本地日志和连接目标，不为了临时通过而连接远程 PostgreSQL/Redis。
- 用户需要临时恢复原配置时，只能使用用户本地应用数据目录中的配置备份，并明确停止本地 Core/Agent，
  避免重新形成双实例共享队列。
