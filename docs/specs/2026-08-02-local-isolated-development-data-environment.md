# 本地独立开发数据环境规格

## 状态

- 日期：2026-08-02
- 状态：已确认，进入实施
- 范围：Windows 原生 PostgreSQL、Redis 兼容服务、生产数据只读快照恢复与 `npm run dev` 一键启动
- 替代关系：本规格完整替代提交 `931b9ec` 中的 WSL2/Docker 方案；实施时不保留、不叠加该旧路线

## 背景

当前 `.env.local` 让本地 Core API 和 Agent Service 连接远程 PostgreSQL 与 Redis。执行
`npm run dev` 时，本地会同时启动 Web、Core API 和 Agent Service；远程服务保持运行时，两套服务会
共同读取同一组业务命令和 Redis 队列。这会形成双实例竞争，也可能让已经恢复终态的任务再次被消费。

本次核对确认：

- 根目录 `npm run dev` 已由 `scripts/dev.mjs` 统一编排 Web、Core API 和 Agent Service；
- Core 和 Agent 启动后会很快启动后台调度器与队列消费者，因此数据库、Redis、结构指纹和恢复隔离状态
  必须在三个应用进程创建前检查完毕；
- Node 的环境文件加载不会覆盖终端中已经存在的同名变量。若终端残留远程 `DATABASE_URL` 或
  `REDIS_URL`，仅调用现有加载方式仍可能误连远程；
- 本机 Windows 的 5432、6379 端口当前没有监听服务，本机尚未安装本地 PostgreSQL；
- 本机已有 Memurai Developer 4.1.8 可执行文件及一个停止状态的服务注册，但日常非提升用户不能依赖
  该服务注册完成按需启动；
- 本机已有未加入 PATH 的 Conda 25.11.1，位置为 `F:\ai\conda`，但尚无 `inkforge-data` 环境；
  conda-forge 可以提供 PostgreSQL 14.23 与 pgvector 0.8.0 的 Windows 原生包；
- 数据库结构契约要求 PostgreSQL 14.23，并精确要求 `vector` 扩展版本为 0.8.0；
- 远程 Redis 中的队列、租约、事件流和防重放键不适合复制到本地；
- 仓库不会自动创建 PostgreSQL schema；Core 的 readiness 失败也不能替代应用启动前的结构检查；
- 当前工作区存在与本任务无关的用户修改，实施时不得覆盖或提交。

## 已确认决策

- Web、Core、Agent、PostgreSQL 和 Redis 兼容服务全部直接运行在 Windows 本机。
- 不安装或使用 WSL、虚拟机、Docker、Docker Desktop、Docker Engine 或 Compose。
- PostgreSQL 使用现有 `F:\ai\conda` 管理的独立 conda 环境 `inkforge-data`，固定从 conda-forge
  安装 PostgreSQL 14.23 和 pgvector 0.8.0；它们仍是 Windows 原生进程，不要求进入 conda 交互 shell。
- Redis 使用现有 Memurai Developer 可执行文件，由当前 Windows 用户以项目专用配置和独立进程运行，
  不依赖远程 Redis，也不依赖需要日常提权启动的 Windows 服务注册。
- 本地数据库名和角色名固定为 `inkforge_local`，使用独立随机密码；Memurai 使用独立随机密码。
- 本地 PostgreSQL 与 Memurai 只监听 `127.0.0.1`，不得监听局域网地址或公网地址。
- 本地持久数据统一放在 `%LOCALAPPDATA%\InkForge\local-data`，不放入仓库；目录只允许当前用户访问。
- PostgreSQL 从远程当前一致性快照恢复；Redis 必须从全新空实例开始，禁止复制远程 Redis 的任何键、
  RDB、AOF 或目录。
- 原始 PostgreSQL 快照只作为不可修改的本地恢复源。恢复后、应用启动前，必须隔离快照中所有可自动
  调度的执行态，防止生产遗留任务在本地重放。
- `npm run dev` 负责检测并按需启动本地 PostgreSQL 与 Memurai；已经健康运行时直接复用，不重复启动。
- `npm run dev` 退出时只停止 Web、Core 和 Agent，不自动停止数据服务。数据库需要跨热重启保持运行，
  停止数据服务使用独立的 `npm run data:stop`。
- 日常 `npm run dev` 不安装软件、不初始化数据库、不下载生产快照，也不自动清空 Redis。缺少一次性准备
  时给出明确命令并在应用进程启动前失败。
- `.env.local` 中写明的本地 `DATABASE_URL` 与 `REDIS_URL` 是开发启动的权威值。启动器必须显式读取
  这两个文件值并传给子进程，不允许终端残留的同名远程变量覆盖它们。
- 恢复后使用当前 `schema-contract.json` 做只读结构指纹校验，不运行迁移、`create_all()` 或任何结构演进。
- 远程操作仅限只读检查，以及通过远程宿主机的 PostgreSQL 身份把 `pg_dump` 一致性快照流式传回本地；
  不停止或修改远程服务，不在远程创建备份文件，不修改远程 schema 或业务数据。

## 目标

- 建立可持久重启、与服务器完全隔离的 Windows 原生 PostgreSQL 和 Redis 数据环境。
- 恢复当前小说、版本、用户和历史数据，同时阻止复制来的执行中任务自动重放。
- 用户完成一次性安装与恢复后，日常只执行 `npm run dev`，数据服务与三个应用服务按正确顺序就绪。
- 重复执行 `npm run dev` 时不创建第二个 PostgreSQL 或 Memurai 实例。
- 防止环境变量、端口占用或错误运行时把本地开发服务重新接到远程数据环境。
- 保持现有 Core/Agent 服务边界、数据库结构和生产部署编排不变。
- 不把密码、连接串、数据库快照、运行时配置或私钥提交到 Git。

## 非目标

- 本次不修复写作命令调度器的多实例领取、终态回执消费或队列心跳问题。
- 本次不让本地和远程 Core/Agent 共享 PostgreSQL 或 Redis。
- 本次不修改 PostgreSQL schema，也不新增迁移。
- 本次不修改、重启、升级或修复远程生产服务。
- 本次不建立生产数据的持续同步、逻辑复制或定时全量复制。
- `npm run dev` 不承担第三方软件安装、生产快照下载或破坏性恢复。
- `npm run dev` 退出时不自动关闭数据服务，也不清除正常的本地开发任务。
- 本次不把重新生成小说正文并入基础设施改造；本地环境验收后再走现有中短篇操作流程。

## 本地架构

```text
Windows npm run dev
      |
      +--> 本地数据门卫（检测、按需启动、等待健康、校验身份）
      |        |                         |
      |        v                         v
      |   PostgreSQL 14.23          Memurai（Redis 7 兼容）
      |   127.0.0.1:5432            127.0.0.1:6379
      |        ^                         ^
      |        |                         |
      +--> Core API :8000 ---------------+
      |        ^                         ^
      |        |                         |
      +--> Agent Service :8001 ----------+
      |
      +--> Next.js :43119 --> 浏览器
```

远程 PostgreSQL、Redis、Core 和 Agent 不在日常开发链路中。远程 PostgreSQL 只在用户明确执行一次性
快照命令时由服务器本机 `pg_dump` 读取。

## Windows 原生数据运行时

### PostgreSQL 与 pgvector

- 使用现有 Conda 创建独立环境 `inkforge-data`，包版本固定为 `postgresql=14.23`、
  `pgvector=0.8.0`，不复用项目 Python `.venv`。
- 启动器直接调用该环境中的 `pg_ctl.exe`、`pg_isready.exe`、`psql.exe` 和 `pg_restore.exe`；日常使用
  不要求用户激活 conda 环境。
- 数据目录为 `%LOCALAPPDATA%\InkForge\local-data\postgres\data`，日志和 PID 元数据位于同一专用根目录。
- `postgresql.conf` 只监听 `127.0.0.1`；`pg_hba.conf` 只接受本机密码认证，不使用 trust。
- 本地运行时清单记录 PostgreSQL 数据目录、系统标识符、二进制目录、期望主版本和本地数据库名；
  不记录明文密码。

### Memurai

- 使用现有 Memurai Developer 的 Windows 原生可执行文件和项目专用配置；已有 Windows 服务注册不作为
  InkForge 日常启动入口，也不要求用户每次以管理员身份运行 `npm run dev`。
- 配置只绑定 `127.0.0.1:6379`，启用随机密码，使用 `64mb + noeviction`，并关闭 RDB/AOF 持久化；
  禁止读取远程 Redis 文件。
- Memurai 的日志、PID 和配置放在
  `%LOCALAPPDATA%\InkForge\local-data\memurai`，其中含秘密的配置只允许当前用户读取。
- 验收以 InkForge 实际使用的 Redis 命令、Lua、Streams、事务与队列行为为准，不只依赖产品版本文字。
- Developer Edition 存在连续运行时长限制；进程因该限制停止后，下一次 `npm run dev` 会按普通停止状态
  重新启动。无需为开发机引入常驻监控系统。

### 本地配置与数据目录

```text
%LOCALAPPDATA%\InkForge\local-data\
  postgres\data\
  memurai\
  snapshots\
  uploads\
  logs\
  runtime\manifest.json
  runtime\ready.json
```

- `manifest.json` 只保存运行时路径、进程身份校验信息和版本，不保存秘密。
- `ready.json` 只在快照恢复、结构指纹校验和执行态隔离全部成功后原子写入，记录 PostgreSQL 系统标识符、
  数据库名、结构指纹和本地恢复批次。它是“该数据库可安全启动应用”的证明，不是任务状态存储。
- PostgreSQL 与 Memurai 密码保存在受当前用户 ACL 保护的本地秘密文件，并同步写入被 Git 忽略的
  `.env.local` 连接串。
- 修改 `.env.local` 前，将原文件备份到上述本地运行时目录；不在仓库中产生秘密备份。
- `.gitignore` 明确忽略本地数据配置、快照和恢复产物；ACL 与 Git 忽略必须同时满足。

## `npm run dev` 启动契约

### 顺序

`scripts/dev.mjs` 在创建 Web、Core 和 Agent 子进程前调用独立的本地数据门卫：

1. 显式解析 `.env.local` 中的 `DATABASE_URL` 和 `REDIS_URL`，覆盖父终端的同名值，再校验最终传给
   子进程的实际生效值：两者主机均为 `127.0.0.1`，数据库名为 `inkforge_local`；不接受服务器 IP、
   主机名或非本地目标。
2. 验证独立 Conda PostgreSQL 环境、Memurai 可执行文件、运行时清单和 `ready.json` 均存在且相互匹配。
3. 取得 `%LOCALAPPDATA%\InkForge\local-data\runtime\ensure.lock` 的互斥启动权。锁记录 PID 和时间；
   若另一个存活进程正在启动数据服务，则在有限超时内等待健康结果，不再发起第二次启动；仅当记录的
   PID 已不存在时才回收陈旧锁。取得锁后仍需再次探测，避免检查与启动之间的竞态。
4. 探测 PostgreSQL：
   - 已健康且系统标识符、数据库名、版本、`vector` 版本与清单相符时，记录“已运行”并跳过启动；
   - 端口未监听时，使用专用数据目录执行一次 `pg_ctl start`，并在有限超时内等待健康；
   - 端口被未知或不匹配的 PostgreSQL 占用时立即失败，不停止、不复用该实例。
5. 探测 Memurai：
   - 使用本地专用凭据可以 `PING` 且运行时身份相符时，记录“已运行”并跳过启动；
   - 端口未监听时，以脱离应用子进程组的方式启动专用 Memurai 进程，并在有限超时内等待健康；
   - 6379 被未知进程占用、认证失败或运行时不匹配时立即失败，不停止、不复用该进程。
6. 运行只读 schema 指纹检查，并验证 `ready.json` 对应当前 PostgreSQL 系统标识符与数据库恢复批次。
7. 两个数据服务全部通过后释放互斥锁，再创建 Web、Core 和 Agent 子进程。

### 生命周期

- 冷启动：只启动当前未运行的数据服务；一个已经运行、另一个停止时，只启动停止的那个。
- 热启动：两个数据服务都健康时不执行任何启动命令，其 PID 保持不变。
- 并发启动：同一时间多个 `npm run dev` 最多只有一个进程执行数据服务启动，其余等待并复用结果。
- 应用退出：现有 `stopChildren()` 只管理 Web、Core 和 Agent；数据服务必须脱离该 children 列表，避免
  Windows `taskkill /T` 将它们一并终止。
- 显式停止：`npm run data:stop` 只停止清单确认属于 InkForge 的 PostgreSQL 与 Memurai；未知端口监听者
  一律拒绝处理。
- 启动失败：任一数据服务、身份检查、结构指纹或安全就绪标记失败时，不创建三个应用进程，也不回退
  到远程连接。

### 仓库命令

实施后提供以下稳定入口：

- `npm run data:setup`：在第三方原生依赖已安装的前提下，创建本地配置、数据目录、随机凭据和空集群；
- `npm run data:start`：只执行数据门卫的按需启动与健康检查；
- `npm run data:status`：显示脱敏后的版本、PID、端口、运行时身份和安全就绪状态；
- `npm run data:stop`：只停止本项目拥有的数据进程；
- `npm run data:restore`：显式执行远程快照下载、本地替换恢复、结构检查和执行态隔离；
- `npm run dev`：先执行与 `data:start` 相同的门卫，再启动 Web、Core 和 Agent。

第三方依赖缺失时，命令输出明确的一次性安装说明并退出；日常命令不会静默调用 winget、Chocolatey、
下载安装器或申请管理员权限。

## 远程快照与本地恢复

### 快照采集

1. 只从仓库外的本地秘密配置读取服务器连接信息，并使用现有 `known_hosts` 做严格 SSH 主机校验。
2. SSH 密码只存在于调用进程内存，不进入命令行参数、源文件或日志。
3. 远程使用宿主机 PostgreSQL 身份执行 custom-format `pg_dump`，通过 SSH stdout 直接流入本地权限
   受限的临时文件；远程不落盘。
4. 上传目录通过独立只读 tar 流传回本地。数据库与上传文件只保证各自可校验，不宣称跨资源原子一致。
5. 临时文件通过 SHA-256 和 `pg_restore --list` 或归档可读性检查后原子改名；失败时只删除本次未完成
   的临时文件。
6. 本地清单记录哈希、大小、采集时间和脱敏来源，不记录密码或完整连接串。

### 本地恢复

1. 恢复开始时先使旧 `ready.json` 失效，再确认 Core 和 Agent 未运行，并确认目标连接为
   `127.0.0.1/inkforge_local`、PostgreSQL 系统标识符和数据目录属于本地运行时清单。
2. 首次空库恢复可直接执行；替换已有本地数据库必须使用明确的本地替换参数。任何目标校验失败都在
   破坏性操作前停止。
3. 使用 `inkforge-data` 环境中的 `pg_restore`，以 `--no-owner --no-acl` 恢复已有生产结构与数据。本步骤只
   在本地副本重放既有结构，不引入迁移、初始化 SQL 或结构变化。
4. 恢复后立即执行当前 `schema-contract.json` 的只读指纹校验；不得依赖 Core readiness 代替此检查。
5. 在单一事务中执行生产执行态隔离；第二次只读审计必须报告零条可自动调度记录。
6. 启动全新空 Memurai 数据集，不导入远程 Redis 的任何内容。
7. 上述步骤全部通过后原子生成新的 `ready.json`；在此之前 `npm run dev` 必须拒绝启动应用。
8. 第一次应用验收使用 `MODEL_PROVIDER=fake` 和 `RAG_INDEX_ENABLED=false`。隔离与应用验收通过后，
   才恢复用户原有真实模型配置。

### 生产执行态隔离

隔离入口只允许修改本地恢复副本，不执行结构变更，并且可重复执行：

- 先处理任务与命令配对：存在 `pending/submitted/processing` 命令且任务仍为
  `idle/active/waiting_call/awaiting_user_review` 时，任务收敛为 `error`、命令收敛为 `failed`；命令的
  `payloadJson/resultJson/artifactId/decision` 原样保留，避免覆盖已经事务提交的草案决定结果；
- 若活动命令关联的任务已经是 `completed`，命令收敛为 `succeeded`；若任务已经是 `error`，命令收敛为
  `failed`。已经终态的任务本身不改写；
- 没有活动命令的遗留 `active/waiting_call` 任务收敛为 `error`；其 `graphStateJson` 原样保留；
- 没有活动命令的 `idle/awaiting_user_review` 任务不改，避免破坏正常空闲任务和待用户确认草案；
- `pending/running` 的 `WorkflowRun` 收敛为 `cancelled`；仅其关联 `WorkflowStep` 中，`pending` 收敛为
  `skipped`，`running` 收敛为 `failed`；`waiting_user` 运行及其待用户步骤不改；
- 所有仍为 `running` 的 `ChapterQualityCheck` 收敛为 `failed`，并记录本地隔离原因；
- `pending/processing` 的 `StylePortraitTask` 收敛为现有合法终态 `error`，并同步更新对应
  `WritingStyle.errorMessage`，避免父记录继续显示处理中；
- 仅 `status=disabled` 且 `errorMessage="等待重新索引"` 的 `RagDocument` 收敛为本地 `failed`；
  因“检索索引服务未配置”而 disabled 的记录保持不变，后续只允许用户明确重新索引；
- `pending/delivering/blocked` 的 `WritingEventOutbox` 收敛为现有合法终态 `superseded`，清除租约字段但
  保留历史证据；
- 保留小说、章节、中短篇正式版本、用户、计费历史和已经终态的写作历史。

隔离只在“恢复生产快照”流程中执行。日常 `npm run dev` 不重新隔离当前本地任务，否则会破坏本地任务
的正常恢复语义。

## 安全边界

- 所有数据连接都必须在应用进程启动前解析并验证为回环地址；禁止通过启动失败自动切回远程环境。
- 端口已被未知进程占用时只报告脱敏诊断并退出，不杀进程、不改端口、不尝试接管。
- 本地进程身份以运行时清单、PostgreSQL 系统标识符、专用凭据和实际协议探测共同确认，不能只用
  “端口能连通”判断。
- 不在工具输出中打印数据库连接串、密码、模型密钥、SSH 密码或私钥内容；秘密也不得出现在子进程
  命令行参数中。
- PostgreSQL URL 必须拆分为独立连接字段，密码通过受保护的临时凭据文件或子进程环境传递；不得把
  `postgresql+asyncpg://` URL 原样传给命令行工具。
- 启动 Windows 可执行文件时使用参数数组，不拼接 shell 命令；路径必须支持空格。若一次性安装脚本
  使用 PowerShell，则必须兼容本机 Windows PowerShell 5.1。
- 本地 PostgreSQL 含生产数据副本，数据、秘密和快照目录必须使用当前 Windows 用户专属 ACL。
- 禁止对远程数据库执行 `pg_restore`、`DROP DATABASE`、DDL 或批量业务更新。
- 禁止复制远程 Redis；本地 Redis 必须始终是独立数据集。
- 停止与恢复命令必须先显示无秘密目标摘要并验证本地运行时身份。
- 不自动删除未知进程、未知数据目录、已校验快照或用户原有配置。

## 仓库交付物

- 重构 `scripts/dev.mjs`，把数据环境门卫作为三个应用进程之前的独立前置阶段；
- 新增职责单一的 Windows 原生数据运行时管理模块，提供 setup/start/status/stop，不把恢复、SSH 和
  业务隔离逻辑堆进 `dev.mjs`；
- 新增本地快照采集、恢复和执行态隔离入口；所有危险操作共享同一套本地目标校验；
- 更新 `package.json` 的 `data:*` 命令；
- 更新 `.env.local.example`、`.gitignore` 和 README，说明一次性安装、日常启动、显式停止、重新恢复、
  Memurai Developer 限制和故障诊断；
- 不新增 Compose 文件，不修改生产 `infra/compose.yaml`；
- 增加启动状态机、目标防误连、并发幂等、恢复隔离和真实本机集成测试。

## 验收

### 原生运行时

- 所有数据服务均为 Windows 原生进程；机器不依赖 WSL、虚拟机或 Docker。
- PostgreSQL 报告版本 14.23，`vector` 扩展报告 0.8.0。
- Memurai 通过 InkForge 实际使用的 Redis 命令、Lua、Streams、事务和队列集成测试。
- Windows 只能从 `127.0.0.1:5432` 和 `127.0.0.1:6379` 访问数据服务；实测局域网地址不可连接。
- PostgreSQL 在显式停止、重新启动后保留数据；Memurai 不含任何远程任务、租约或事件流。

### 启动状态机

- 两个数据服务都停止时，首次 `npm run dev` 各启动一次，健康后才启动三个应用服务。
- 两个数据服务都健康时，再次执行数据门卫不会调用启动命令，两个 PID 均保持不变。
- 只有一个数据服务停止时，只启动停止的服务。
- 两个数据门卫并发运行时，每种数据服务最多产生一个本地实例。
- `Ctrl+C` 结束 `npm run dev` 后，Web、Core、Agent 停止，PostgreSQL 与 Memurai 继续运行。
- `npm run data:stop` 能停止两个已确认归属的本地数据进程；对未知端口监听者拒绝操作。
- 缺少依赖、配置、`ready.json`、健康检查、结构指纹或本地身份校验时，三个应用进程均未启动。
- 即使父终端残留远程 `DATABASE_URL/REDIS_URL`，应用子进程最终只收到 `.env.local` 中经过回环校验
  的本地连接；日志不泄露两者内容。

### 数据与应用

- 本地数据库结构指纹与 `apps/core-api/src/inkforge_core/db/schema-contract.json` 完全一致。
- 本地数据库可以读取目标小说 `cmsab6kir4dtb9en83he6sdfj` 及其当前已应用版本。
- 执行态隔离后的第二次审计分别报告 WritingRunCommand 活动态、WritingTask 可对账执行态、任务与命令
  终态错配、WorkflowRun 活动态、已取消运行的活动 WorkflowStep、ChapterQualityCheck 运行态、
  StylePortraitTask 活动态、RagDocument 精确待索引态、WritingEventOutbox 待投递态以及已 superseded
  但仍持有租约的 Outbox 均为零。
- 首次用 fake 模型执行 `npm run dev` 后，Web、Core API 和 Agent Service readiness 全部通过。
- 用户可以登录并打开目标小说。
- 使用唯一 canary/jobId 验证标识只进入本地 Redis；对远程 Redis 只做同一精确标识的只读查询。
- 隔离验收后恢复真实模型配置，再运行一个新的本地写作任务，证明 PostgreSQL 检查点、Redis 队列、
  Agent 回调和 SSE 全链路正常。

### 代码与安全

- 状态机单元测试覆盖“均停止、均健康、单个停止、错误监听者、并发启动、超时失败、显式停止”。
- 快照、恢复、隔离和秘密处理包含正反向测试；任何错误目标在破坏性操作前被拒绝。
- 运行相关架构测试、Python 测试、Ruff、Mypy，以及 `npm run typecheck`、`npm run lint`。
- Git 变更不包含 `.env.local`、本地运行时配置、快照、密码、连接串或无关工作区修改。
- 远程 schema 指纹前后相同；远程操作记录只包含允许的只读查询和 `pg_dump`。

## 失败恢复

- 原生依赖安装或本地初始化失败：不修改 `.env.local`，不启动应用，保留脱敏日志。
- 数据门卫启动超时：停止本次新拉起且归属明确的失败进程；已经健康运行的另一个数据服务保持不动。
- 端口冲突或运行时身份不符：不杀未知进程，报告端口和检查类型后退出。
- 快照传输或校验失败：不恢复数据库，只删除本次未完成的临时文件。
- 本地恢复、结构指纹或执行态隔离失败：删除未生成的 `ready.json`，禁止启动应用，保留本地数据库用于诊断。
- 应用健康检查失败：检查本地日志和连接目标，不为了临时通过而连接远程 PostgreSQL 或 Redis。
- 需要恢复原 `.env.local` 时，从 `%LOCALAPPDATA%` 中的受保护备份恢复；在此之前明确停止本地 Core 和
  Agent，避免重新形成共享远程队列的双实例。
