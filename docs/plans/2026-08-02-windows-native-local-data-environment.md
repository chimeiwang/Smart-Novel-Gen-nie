# Windows 原生本地数据环境实施计划

> **执行要求：** 使用 subagent-driven-development 按任务执行；每项行为修改都遵循“失败测试 → 最小实现 → 定向回归 → 小步提交”。任何恢复操作都必须先通过本地目标身份检查，不得修改 PostgreSQL schema 或远程业务状态。

**目标：** 在 Windows 本机建立一套持久、独立、可恢复生产快照的 PostgreSQL 14.23 与 Memurai 数据环境，使日常 npm run dev 自动按需启动数据服务，并保证本地 Core/Agent 永不因残留环境变量连接远程 PostgreSQL 或 Redis。

**架构：** 新增一个 Python 工作区工具 inkforge-local-data，统一负责配置、进程身份、互斥状态机、快照、恢复和就绪证明；Core 仅新增可复用的本地副本执行态隔离模块；scripts/dev.mjs 只负责让 .env.local 的数据连接成为权威值、调用数据门卫，然后启动三个应用服务。数据服务不加入 dev.mjs 的子进程树。

**技术栈：** Python 3.12、uv、SQLAlchemy async、asyncpg、redis-py、Paramiko、psutil、PostgreSQL 14.23、pgvector 0.8.0、Memurai 4.1.8、Node.js 22、Windows PowerShell 5.1、pytest、Node test runner。

**状态：** 已确认，准备执行。

---

## 总体模块边界

~~~text
package.json / scripts/dev.mjs
          |
          | 仅调用 ensure，并使用已校验的子进程环境
          v
tools/inkforge-local-data
  ├─ config / secrets / manifest / ACL
  ├─ Windows 互斥锁与进程身份
  ├─ PostgreSQL / Memurai 生命周期
  ├─ snapshot / restore / ready marker
  └─ CLI: setup/start/status/stop/restore
          |
          | 仅在恢复副本中调用
          v
inkforge_core.db.local_restore_quarantine
  ├─ audit
  └─ quarantine（单事务、无 DDL）
~~~

关键约束：

- inkforge-local-data 是唯一数据运行时编排入口，dev.mjs 不复制 PostgreSQL、Memurai 或恢复逻辑。
- 本地 PostgreSQL 和 Memurai 由当前用户启动，脱离 Web/Core/Agent 子进程组。
- ready.json 只证明“当前数据库已经恢复、结构校验并隔离”，不代替实时健康探测。
- setup 不下载生产数据；start 不执行恢复或隔离；restore 才允许替换本地副本并清空已确认归属的本地 Redis。
- Core 的隔离模块只接受调用方创建的 AsyncSession，不读取 DATABASE_URL，不创建表，不接触远程连接。

---

### 任务 1：建立本地数据工具包与严格配置模型

**文件：**

- 修改：pyproject.toml
- 修改：uv.lock
- 新增：tools/inkforge-local-data/pyproject.toml
- 新增：tools/inkforge-local-data/src/inkforge_local_data/__init__.py
- 新增：tools/inkforge-local-data/src/inkforge_local_data/config.py
- 新增：tools/inkforge-local-data/src/inkforge_local_data/errors.py
- 新增：tools/inkforge-local-data/src/inkforge_local_data/io.py
- 新增：tools/inkforge-local-data/tests/test_config.py
- 新增：tools/inkforge-local-data/tests/test_io.py

- [ ] 先写失败测试，覆盖默认根目录、固定 Conda 路径、路径含空格、manifest/secret 分离、原子 JSON 写入和输出脱敏。
- [ ] 先写 URL 目标测试：所有 data:* 入口都用 dotenv_values(interpolate=False) 显式读取 .env.local，并让文件内 DATABASE_URL/REDIS_URL 覆盖父终端同名值；只接受 postgresql+asyncpg://inkforge_local:***@127.0.0.1:5432/inkforge_local 与 redis://:***@127.0.0.1:6379/0；拒绝缺键、插值、localhost、::1、服务器 IP、其他端口、其他库和缺少密码。
- [ ] 运行 uv run pytest tools/inkforge-local-data/tests/test_config.py tools/inkforge-local-data/tests/test_io.py -q，确认因包尚未实现而失败。
- [ ] 注册 uv workspace 成员、pytest testpath 和 [project.scripts] inkforge-local-data = "inkforge_local_data.cli:main"；工具直接声明 inkforge-core-api、asyncpg、redis、paramiko、psutil、keyring 与 python-dotenv 依赖。
- [ ] 实现不可变配置对象 RuntimePaths、LocalTargets、RuntimeManifest、ReadyMarker 和 SnapshotManifest。
- [ ] 实现安全原子写入：同目录临时文件、flush、fsync、os.replace；错误消息只输出主机、端口、数据库名和路径，不输出密码或完整 URL。
- [ ] 执行 uv lock 更新锁文件，再重跑定向测试并执行 uv lock --check，确认工作区依赖闭合。
- [ ] 提交：基础：建立本地数据工具配置边界

配置模型至少固定以下事实：

~~~python
LocalTargets(
    postgres_host="127.0.0.1",
    postgres_port=5432,
    database_name="inkforge_local",
    application_role="inkforge_local",
    redis_host="127.0.0.1",
    redis_port=6379,
    redis_database=0,
)
~~~

---

### 任务 2：实现 Windows 原生进程、互斥锁和身份探测

**文件：**

- 新增：tools/inkforge-local-data/src/inkforge_local_data/locking.py
- 新增：tools/inkforge-local-data/src/inkforge_local_data/processes.py
- 新增：tools/inkforge-local-data/src/inkforge_local_data/postgres.py
- 新增：tools/inkforge-local-data/src/inkforge_local_data/memurai.py
- 新增：tools/inkforge-local-data/tests/test_locking.py
- 新增：tools/inkforge-local-data/tests/test_postgres.py
- 新增：tools/inkforge-local-data/tests/test_memurai.py

- [ ] 先写真正跨进程的 Windows 文件锁失败测试：两个调用者只允许一个进入临界区；等待超时有稳定中文诊断；持有者异常退出后 OS 自动释放锁；线程测试不能代替跨进程测试。
- [ ] 先写 PostgreSQL 探测失败测试，覆盖 stopped、owned_ready、owned_starting、occupied_unknown、版本不匹配和 system identifier 不匹配。数据库 OID 只属于 ready 数据身份，不参与集群进程归属。
- [ ] 先写 Memurai 探测失败测试，覆盖端口关闭、认证失败、PID/可执行路径/启动参数不匹配和未知监听者。
- [ ] 先写命令构造测试，证明所有 subprocess 都使用参数数组，密码只通过 PGPASSFILE、受保护配置或子进程环境传递；数据长驻进程只继承 PATH、SYSTEMROOT、TEMP 等最小白名单环境，不继承 SSH、模型、JWT 或远程连接秘密。
- [ ] 运行三个测试文件，确认失败点是锁和适配器尚不存在。
- [ ] 使用 msvcrt 对固定文件字节做有限等待互斥；锁内记录 PID 和时间仅用于诊断，不能靠删除锁文件实现互斥。锁句柄显式不可继承；Windows 专用模块延迟导入或支持后端注入，保证非 Windows CI 可以收集测试。
- [ ] PostgreSQL 使用 pg_ctl、pg_isready、pg_controldata 和只读 SQL 共同校验；启动命令固定数据目录、日志、等待和超时。
- [ ] Memurai 以隐藏、脱离应用进程组的当前用户进程启动；PostgreSQL/Memurai 子进程均使用 close_fds=True 和最小环境，避免继承锁句柄或开发秘密；Memurai 以受保护配置启用 requirepass、bind 127.0.0.1、save ""、appendonly no、maxmemory 64mb、maxmemory-policy noeviction。
- [ ] Memurai 身份同时校验认证 PING、INFO PID、psutil 可执行路径和配置路径；只对已确认实例发送 SHUTDOWN NOSAVE。
- [ ] 重跑定向测试。
- [ ] 提交：基础：实现本地数据进程身份与互斥

---

### 任务 3：实现安全就绪证明与幂等运行时状态机

**文件：**

- 新增：tools/inkforge-local-data/src/inkforge_local_data/readiness.py
- 新增：tools/inkforge-local-data/src/inkforge_local_data/runtime.py
- 新增：tools/inkforge-local-data/tests/test_readiness.py
- 新增：tools/inkforge-local-data/tests/test_runtime.py

- [ ] 先写 ready.json 测试，要求数据库名、系统标识符、当前数据库 OID、结构指纹、恢复批次和 manifest 版本全部匹配；manifest 的进程归属不记录数据库 OID。
- [ ] 先写状态机失败测试：两者停止、两者健康、只停一个、未知端口、启动超时、第二个服务失败时回收本次新进程、显式停止、并发 ensure。
- [ ] 先写反向测试：ready 缺失或结构指纹不符时，ensure 不启动任何应用依赖方，也不回退远程地址。
- [ ] 运行定向测试，确认状态机尚未实现。
- [ ] 实现 RuntimeManager.ensure_ready()：锁外快速探测，锁内再次探测，按需启动，等待健康，校验结构与 ready marker，最后返回脱敏状态。
- [ ] 实现 RuntimeManager.start_for_restore() 私有编排入口；它允许数据库在 ready 缺失时启动，但不暴露公共跳过安全检查参数。
- [ ] 实现 stop_owned()：先分别确认两个实例身份，再开始停止；若任一身份未知，两个都不停止。
- [ ] 保证失败清理只停止“本次调用新启动且已确认归属”的进程，原本健康的服务保持运行。
- [ ] 重跑定向测试。
- [ ] 提交：基础：实现本地数据启动状态机

状态转移必须满足：

~~~text
stopped --------start-------> owned_starting ----healthy----> owned_ready
owned_ready -----reuse---------------------------------------> owned_ready
occupied_unknown ----------------拒绝，不接管----------------> error
本次启动超时 ----仅清理本次新进程----------------------------> error
~~~

---

### 任务 4：实现一次性 setup、秘密保护和本地配置切换

**文件：**

- 新增：tools/inkforge-local-data/src/inkforge_local_data/setup.py
- 新增：tools/inkforge-local-data/src/inkforge_local_data/environment.py
- 新增：tools/inkforge-local-data/src/inkforge_local_data/cli.py
- 新增：tools/inkforge-local-data/tests/test_setup.py
- 新增：tools/inkforge-local-data/tests/test_environment.py

- [ ] 先写依赖预检测试：仅接受 F:\ai\conda\envs\inkforge-data 中 PostgreSQL 14.23、pgvector 0.8.0 和现有 Memurai 可执行文件；逐一检查 initdb、postgres、createdb、psql、pg_ctl、pg_isready、pg_restore、pg_controldata；缺失时给出精确人工安装命令，不静默安装。
- [ ] 先写 setup 失败测试：已存在未知数据目录拒绝覆盖；半初始化不写 .env.local；重复 setup 复用同一身份和凭据。
- [ ] 先写 .env.local 更新测试：只替换 DATABASE_URL、REDIS_URL 和本地 uploads/logs 路径，保留模型与服务密钥配置；先把原文件备份到本地数据根；禁止父终端值参与生成。
- [ ] 先写 ACL 顺序测试：先创建运行时根、关闭继承并只授权当前用户 SID，验证实际 DACL 后才允许创建任何秘密、临时文件、Memurai 配置、远程配置和 .env.local 备份；更新后的仓库 .env.local 同样收紧 ACL。任一验证失败都必须发生在秘密写入前。
- [ ] 运行定向测试，确认失败。
- [ ] 使用 secrets.token_urlsafe 生成管理员、应用数据库和 Memurai 三套独立密码；秘密保存在已完成 DACL 验证的 runtime/secrets.json，manifest 不含秘密，原子写入临时文件也只能位于该受保护目录。
- [ ] 首次 setup 从现有未提交 .env 中读取 SERVER_IP、SERVER_PORT、SERVER_USER、SERVER_PASSWORD，并从其中的远程 DATABASE_URL 只提取数据库名。remote-access.json 只保存 host/port/user/database 等非秘密；SSH 密码导入 Windows Credential Manager。后续快照通过 keyring 将密码读入调用进程内存，不继续依赖仓库目录中的秘密，也不删除或改写用户原 .env。
- [ ] 使用 initdb 初始化独立集群，创建 inkforge_admin 集群管理员、inkforge_local 登录角色和同名数据库；pg_hba.conf 仅允许 127.0.0.1/32 的 scram-sha-256。
- [ ] setup 只生成 manifest，不生成 ready.json；空库不能被 npm run dev 当成可用业务库。
- [ ] 实现 setup/start/status/stop CLI，状态输出全部脱敏。
- [ ] 重跑定向测试。
- [ ] 提交：基础：实现本地数据一次性初始化

---

### 任务 5：实现恢复副本的执行态审计与隔离

**文件：**

- 新增：apps/core-api/src/inkforge_core/db/local_restore_quarantine.py
- 新增：apps/core-api/tests/db/test_local_restore_quarantine.py

- [ ] 使用 SQLite schema_translate_map 测试夹具构造最小业务行，先写 audit_local_restore_state() 的失败测试。
- [ ] 先写命令/任务组合真值表：有活动命令时，idle/active/waiting_call/awaiting_user_review 任务转 error、命令转 failed；completed 任务不动且命令转 succeeded；error 任务不动且命令转 failed。无活动命令时，仅 active/waiting_call 任务转 error；idle/awaiting_user_review/completed/error 不动；已经 succeeded/failed 的命令一律不动。
- [ ] 先写 WorkflowRun/WorkflowStep、ChapterQualityCheck、StylePortraitTask/WritingStyle、精确 RagDocument 和 WritingEventOutbox 的正反向测试。
- [ ] 先写证据保留测试：尤其覆盖已有正式应用结果的 artifact_decision；逐字保留 payloadJson、resultJson、artifactId、decision、attemptCount、submittedAt、nextAttemptAt、graphStateJson、质量结果、Workflow input/output/durationMs 与 Outbox payload/sequence/durableBaseline/dedupe/attempt/published/redisEvent。
- [ ] 先写反例测试：waiting_user WorkflowRun 与 pending user_confirmation Step、published Outbox、普通 disabled RagDocument 和 RagChunk 全部不动。
- [ ] 先写幂等测试：连续执行两次，第二次更新数为零且审计结果不变。
- [ ] 运行 uv run pytest apps/core-api/tests/db/test_local_restore_quarantine.py -q，确认失败。
- [ ] 实现固定原因码 LOCAL_RESTORE_QUARANTINED、LocalRestoreAudit 数据类、audit_local_restore_state(session) 和 quarantine_local_restore_state(session, now)；原因码与人类可读说明由 Core 模块固定，now 仅作为测试注入。
- [ ] 固定字段映射：WritingTask 只改 phase/updatedAt；WritingRunCommand 只改 status/completedAt/updatedAt/lastError；WorkflowRun 改 status/errorMessage/updatedAt，关联 WorkflowStep 只改 status；ChapterQualityCheck 改 status/summary/updatedAt；StylePortraitTask 和受影响 WritingStyle 改错误说明/updatedAt；精确 RagDocument 改 status/errorMessage/updatedAt；Outbox 改 deliveryState/lastErrorCode/updatedAt 并清租约。
- [ ] 固定更新顺序：先按活动 command/legacy 条件更新 Task，再终态化 Command；先更新即将取消 run 的关联 Step，再取消 Run；Outbox 终态化与清租约在同一条更新中完成。
- [ ] 所有更新在调用方单一事务中完成；模块不创建 engine、不读取环境变量、不执行 DDL，也不得被 create_app、lifespan 或任何 API 导入调用。只有显式 restore 协调器在 staging 本地目标门卫通过后可以调用。
- [ ] 第二次审计十个分类全部为零才允许提交恢复事务；真实 PostgreSQL staging 验收同时验证枚举写入和审计结果。
- [ ] 重跑定向测试，并运行现有 writing/outbox/quality/style/RAG 定向回归。
- [ ] 提交：恢复：实现生产执行态本地隔离

十项审计键固定为：

~~~text
writing_commands_active
writing_tasks_reconcilable
quarantined_command_task_mismatch
workflow_runs_active
active_steps_on_locally_cancelled_runs
quality_checks_running
portrait_tasks_active
rag_documents_waiting_reindex
outbox_unpublished
superseded_outbox_with_lease
~~~

精确谓词如下：

- writing_commands_active：WritingRunCommand.status 属于 pending/submitted/processing。
- writing_tasks_reconcilable：WritingTask.phase 属于 active/waiting_call。
- quarantined_command_task_mismatch：只检查 lastError=LOCAL_RESTORE_QUARANTINED 的 failed command，其任务 phase 不是 error；completed→succeeded 分支由真值表和本次 affected IDs 事务内断言。
- workflow_runs_active：WorkflowRun.status 属于 pending/running。
- active_steps_on_locally_cancelled_runs：WorkflowRun.status=cancelled 且 errorMessage=LOCAL_RESTORE_QUARANTINED，关联 Step 仍为 pending/running。
- quality_checks_running：ChapterQualityCheck.status=running。
- portrait_tasks_active：StylePortraitTask.status 属于 pending/processing。
- rag_documents_waiting_reindex：RagDocument.status=disabled 且 errorMessage=等待重新索引。
- outbox_unpublished：WritingEventOutbox.deliveryState 属于 pending/delivering/blocked。
- superseded_outbox_with_lease：deliveryState=superseded 且 lastErrorCode=LOCAL_RESTORE_QUARANTINED，并且任一租约字段非空。

LocalRestoreAudit 同时返回每类 changed counts 和 remaining counts；第二次执行 changed 全零、remaining 全零。架构测试必须断言 app.py 不导入 local_restore_quarantine。

---

### 任务 6：实现严格 SSH 快照流与本地归档校验

**文件：**

- 新增：tools/inkforge-local-data/src/inkforge_local_data/remote.py
- 新增：tools/inkforge-local-data/src/inkforge_local_data/snapshot.py
- 新增：tools/inkforge-local-data/src/inkforge_local_data/archive.py
- 新增：tools/inkforge-local-data/tests/test_remote.py
- 新增：tools/inkforge-local-data/tests/test_snapshot.py
- 新增：tools/inkforge-local-data/tests/test_archive.py

- [ ] 先写 SSH 配置测试：从受 ACL 保护的 runtime/remote-access.json 读取非秘密 host/port/user/database，通过 keyring 只把 SSH 密码加载到当前进程内存；强制读取用户现有 known_hosts 并使用 RejectPolicy；缺少凭据或主机记录时拒绝连接。
- [ ] 先写日志与进程参数测试，证明 SSH 密码、数据库密码和完整 URL 不出现在异常、日志和 argv 中。
- [ ] 先写流式快照测试：持续并发排空 stdout/stderr 后再读取退出码，避免管道背压死锁；stdout 只分块写入 .partial 并同步计算 SHA-256；远程非零退出、断流、空文件或本地校验失败时不生成正式快照。
- [ ] 先写 archive 防穿越测试：拒绝绝对路径、盘符、..、符号链接和越界解压。
- [ ] 运行定向测试，确认失败。
- [ ] Paramiko 只执行代码内固定的只读命令；远程用户身份必须是受信配置中的 root，数据库名只接受固定标识符。先验证 /usr/bin/pg_dump 主版本与源库兼容，再固定执行 runuser -u postgres -- /usr/bin/pg_dump --format=custom --no-owner --no-acl --dbname=<已校验数据库名>；不读取远程 .env、不把数据库密码传给 pg_dump，也不回退 sudo。
- [ ] uploads 来源固定为 Docker 卷 inkforge_uploads；先用 volume labels 验证 com.docker.compose.project=inkforge 和 com.docker.compose.volume=uploads，再从唯一只读来源目录输出 tar。标签、卷或权限预检失败时直接停止。
- [ ] 快照前后分别在生产 core-api 容器中调用现有 verify_live_schema 只读守卫并记录同一 canonical fingerprint；两次不一致则拒绝快照。数据库快照与 uploads 归档分别生成哈希、大小和采集时间，再原子写 snapshot manifest；不宣称两者跨资源原子一致。
- [ ] 正式快照原子改名后设置只读属性；每次恢复前重新验证 manifest、大小、SHA-256、pg_restore --list 和 tar 安全清单，恢复过程始终只读源快照。
- [ ] 远程不创建文件、不停止服务、不查询或复制 Redis。
- [ ] 重跑定向测试。
- [ ] 提交：恢复：实现生产快照安全采集

---

### 任务 7：实现防误操作的本地恢复协调器

**文件：**

- 新增：tools/inkforge-local-data/src/inkforge_local_data/restore.py
- 新增：tools/inkforge-local-data/tests/test_restore.py
- 修改：tools/inkforge-local-data/src/inkforge_local_data/cli.py

- [ ] 先写破坏性门禁测试：公共目标仅允许 127.0.0.1:5432、inkforge_local、manifest 中的数据目录和 system identifier；8000/8001 有监听时拒绝恢复；未知 Memurai 拒绝清空。内部 StagingTarget 的数据库名只能由当前恢复批次生成，不能来自 CLI/环境变量，并且仍须匹配同一 system identifier 和数据目录。
- [ ] 先写替换授权测试：首次空库可恢复；已有业务表或 ready marker 时必须显式 --replace-local；缺少该参数时数据库和 uploads 均不变。
- [ ] 先写 staging 恢复测试：管理员执行带 --exit-on-error --single-transaction --no-owner --no-acl 的恢复；恢复、权限授予、应用角色探测、结构指纹或隔离任一步失败时，原 inkforge_local 保持可恢复；成功后才切换数据库名。
- [ ] 先写切换回滚测试：数据库换名、uploads 目录换名或 ready 原子写入失败时，恢复旧数据库名和旧 uploads，不留下可误判的 ready。
- [ ] 先写 Redis 测试：只对身份已确认的本地 Memurai 执行 FLUSHALL；恢复完成后 DB 0 为空；远程 URL 永不传入 Redis 客户端。
- [ ] 运行定向测试，确认失败。
- [ ] 快照下载和完整校验可以在锁外完成；从原子移走旧 ready.json 开始，直到新 ready 成功或失败回滚完成，全程持有与 start/stop 相同的独占锁，并确认 Core/Agent 未运行。
- [ ] 启动 PostgreSQL 的内部恢复模式但不启动 Core/Agent；新建 owner=inkforge_local 的 inkforge_restore_<batch> staging 数据库，以管理员和 PGPASSFILE 执行 pg_restore --exit-on-error --single-transaction --no-owner --no-acl。
- [ ] 恢复后由管理员明确授予 inkforge_local 数据库 CONNECT/TEMP、public schema USAGE、全部表 DML、序列 USAGE/SELECT/UPDATE 和函数 EXECUTE；再以应用角色创建/写入/读取并回滚一个 TEMP 表，并核验业务表权限。
- [ ] 对 staging URL 执行结构守卫、隔离事务和第二次审计；随后彻底 dispose 所有 staging 连接池。
- [ ] 数据库换名只从维护库 postgres 的独立管理员连接执行；只终止当前本地集群中 inkforge_local、当前 staging、当前 previous 三个精确数据库名的连接，把旧 inkforge_local 暂时改名为 inkforge_previous_<batch>，再把 staging 改名为 inkforge_local；完成后的新 OID 写入 ready。
- [ ] uploads 先解到 staging 目录并校验，再做目录换名。每次破坏性状态转换前原子更新受 ACL 保护的 restore journal；进程异常退出后的下一次 restore 根据 journal 识别并安全回滚，data:start 在 journal 未收敛时拒绝启动。
- [ ] 数据库、uploads 或 ready 任一步失败时按 journal 反向顺序恢复旧名称，ready 保持缺失；Redis 已清空不影响该回滚。新数据库、uploads 和 ready 全部成功后才清理 previous；previous 清理失败只报告精确残留，不回滚已经生效的新环境。
- [ ] 确认本地 Memurai 归属后清空 DB 0，再原子生成 ready.json；任何失败都保持 ready 缺失。
- [ ] 增加 restore CLI：默认采集新快照；允许显式选择已校验 snapshot manifest；已有本地数据时要求 --replace-local。
- [ ] 重跑定向测试。
- [ ] 提交：恢复：实现本地 staging 恢复与就绪证明

---

### 任务 8：让 .env.local 成为 dev 子进程的数据连接权威值

**文件：**

- 新增：scripts/dev-environment.mjs
- 新增：scripts/dev-runtime.mjs
- 新增：tests/local-data/dev-environment.test.mjs
- 新增：tests/local-data/dev-runtime.test.mjs
- 修改：scripts/dev.mjs
- 修改：package.json

- [ ] 先写 Node 失败测试：父进程有远程 DATABASE_URL/REDIS_URL 时，构造出的 childEnv 仍使用 .env.local 文件值；文件值不安全时在启动任何子进程前失败；data gate 与三个应用实际收到同一个已校验 childEnv。
- [ ] 先写数据门卫调用测试：ensure 非零退出时 Web/Core/Agent spawn 次数为零；ensure 成功后才按原顺序创建三个服务。
- [ ] 先写生命周期测试：Ctrl+C 只终止 Web/Core/Agent，不把 PostgreSQL/Memurai 放进 children 或 taskkill /T 目标。
- [ ] 运行 node --test tests/local-data/dev-environment.test.mjs tests/local-data/dev-runtime.test.mjs，确认失败。
- [ ] 使用 Node 22 parseEnv 显式解析文件并覆盖 DATABASE_URL、REDIS_URL；其他文件值只在父环境缺失时补入，保持现有开发覆盖能力。
- [ ] 把环境构造和本地 URL 校验抽到 dev-environment.mjs，把可注入测试的 runDevelopment() 与门卫调用抽到 dev-runtime.mjs；dev.mjs 仅为薄入口。错误信息只显示字段名和安全目标摘要。
- [ ] dev-runtime.mjs 同步调用 .venv\Scripts\inkforge-local-data.exe start，成功后再创建现有三个应用子进程。
- [ ] package.json 增加 data:setup、data:start、data:status、data:stop、data:restore、test:local-data；所有入口调用同一 Python CLI。
- [ ] 重跑 Node 定向测试和现有 dev 启动契约测试。
- [ ] 提交：开发：接入本地数据门卫

---

### 任务 9：补充仓库安全门禁与开发文档

**文件：**

- 修改：.env.local.example
- 修改：.gitignore
- 修改：README.md
- 新增：docs/LOCAL_DEVELOPMENT_DATA.md
- 新增：tests/architecture/test_local_data_runtime.py

- [ ] 先写架构失败测试：dev.mjs 必须在服务列表启动前调用数据门卫；禁止引入 Docker/WSL；禁止本地数据工具导入 Agent；Core 隔离模块不得读取环境或创建 schema。
- [ ] 先写敏感文件门禁：仓库不得追踪 snapshots、ready、manifest、secrets、Memurai 配置或 .env.local 备份。
- [ ] 运行 uv run pytest tests/architecture/test_local_data_runtime.py -q，确认失败。
- [ ] 更新示例连接为 inkforge_local、带密码的 Redis URL和 127.0.0.1；示例不包含真实密码。
- [ ] 文档明确一次性 Conda 环境安装、data:setup、data:restore、日常 npm run dev、显式 data:stop、Memurai Developer 时限及端口冲突诊断。
- [ ] 说明 data:start 不会自动恢复、日常 dev 不隔离本地任务、恢复会清空本地 Redis、远程 Redis 永不复制。
- [ ] 重跑架构测试，并执行 git grep 敏感路径与占位检查。
- [ ] 提交：文档：说明 Windows 本地数据环境

---

### 任务 10：代码级全量验证与独立复审

**文件：**

- 复核：本计划涉及的全部代码、测试和文档

- [ ] 运行 uv run pytest tools/inkforge-local-data/tests apps/core-api/tests/db/test_local_restore_quarantine.py tests/architecture/test_local_data_runtime.py -q。
- [ ] 运行受影响的 writing、outbox、quality、styles、references 回归测试。
- [ ] 运行 uv run ruff check .。
- [ ] 运行 uv run mypy apps/core-api/src apps/agent-service/src packages/service-contracts/src packages/service-auth/src tools/inkforge-local-data/src。
- [ ] 运行 node --test tests/local-data/*.test.mjs。
- [ ] 运行 npm run typecheck、npm run lint 和 npm run test:web。
- [ ] 运行 tests/architecture/test_compose_security.py，证明生产 Compose 未被改动或弱化。
- [ ] 使用 requesting-code-review 做一次独立代码复审；修复后重复相关验证。
- [ ] 审查 git diff、git diff --check 和 git status，确保不包含 apps/web/next-env.d.ts 及用户的未跟踪文档。

---

### 任务 11：在当前 Windows 机器完成一次性原生依赖准备

**文件：**

- 仅本机状态：F:\ai\conda\envs\inkforge-data
- 仅本机状态：%LOCALAPPDATA%\InkForge\local-data
- 仅本机状态：.env.local（Git 忽略）

- [ ] 再次确认 5432/6379/8000/8001/43119 未被未知进程占用。
- [ ] 执行 F:\ai\conda\Scripts\conda.exe create --prefix F:\ai\conda\envs\inkforge-data --override-channels --strict-channel-priority -c conda-forge postgresql=14.23 pgvector=0.8.0 -y，避免用户级 Conda 配置改变来源或环境位置。
- [ ] 核验 postgres --version 为 14.23，读取 extension control/SQL 文件确认 pgvector 0.8.0。
- [ ] 执行 uv sync --frozen --all-packages --group dev。
- [ ] 执行 npm run data:setup，确认 ACL、manifest、秘密文件、空集群和 .env.local 本地目标均正确。
- [ ] 执行 npm run data:status，确认输出脱敏且 ready 为 false。
- [ ] 失败时只清理本次新建且路径已确认位于本地数据根的未完成产物；不删除已有未知目录。

---

### 任务 12：采集生产快照并恢复为隔离的本地副本

**文件：**

- 仅本机状态：%LOCALAPPDATA%\InkForge\local-data\snapshots
- 仅本机状态：%LOCALAPPDATA%\InkForge\local-data\uploads
- 只读远程来源：/srv/smart-novel-gen

- [ ] 对远程 schema 先做只读指纹记录；不输出连接串。
- [ ] 执行 npm run data:restore -- --replace-local，使用现有 SERVER_* 本地秘密和 known_hosts。
- [ ] 验证数据库快照与 uploads 的 SHA-256、pg_restore --list 和安全 tar 清单。
- [ ] 核验本地 PostgreSQL 14.23、vector 0.8.0、schema 指纹和 ready marker 完全一致。
- [ ] 核验十项执行态审计均为零，ReviewArtifact、小说、章节、版本、用户和计费记录未被隔离器改写。
- [ ] 核验小说 cmsab6kir4dtb9en83he6sdfj 及当前已应用版本可以只读查询。
- [ ] 核验本地 Memurai DB 0 为空；不读取、不转储远程 Redis。
- [ ] 对远程 schema 再做只读指纹，确认前后一致。

---

### 任务 13：执行真实冷启动、热启动、并发与应用全链路验收

**文件：**

- 仅本机运行状态与脱敏验收日志

- [ ] 先执行 npm run data:stop，确认两个归属实例均停止。
- [ ] 在当前终端临时设置 MODEL_PROVIDER=fake、RAG_INDEX_ENABLED=false，执行 npm run dev；确认数据服务先健康，三个应用才启动。
- [ ] 等待 Web 43119、Core 8000、Agent 8001 readiness 全部通过；登录并打开目标小说。
- [ ] Ctrl+C 后确认三个应用退出而 PostgreSQL/Memurai PID 仍存活。
- [ ] 再次执行 npm run data:start，确认两个 PID 不变；停止其中一个后再执行，确认只恢复停止的服务。
- [ ] 并发启动两个 data:start，确认每种数据服务只存在一个实例。
- [ ] 用父终端临时注入故意错误的远程 DATABASE_URL/REDIS_URL，再运行测试入口，确认子进程仍采用 .env.local 本地值。
- [ ] 使用唯一 canary/jobId 运行一个 fake 本地任务，确认 PostgreSQL checkpoint、Redis 队列、Core 回调和 SSE 全链路完成。
- [ ] 只读查询远程 PostgreSQL 与 Redis 中同一精确 canary，确认没有本地测试标识。
- [ ] 恢复用户真实模型配置后再运行一个新的本地写作任务；不重跑已隔离的生产任务。
- [ ] 最后执行 npm run data:status，并保留数据服务供后续 npm run dev 使用。

---

## 完成条件

- 代码、文档和本机运行时均通过上述验证。
- npm run dev 可以在数据服务已停止或已启动两种状态下稳定工作。
- 本地数据库含所需生产数据副本，本地 Redis 是独立空环境，远程 PostgreSQL/Redis 没有被本地服务消费或写入。
- PostgreSQL schema-contract.json 未修改，未执行迁移、create_all 或自动建表。
- 用户原有无关修改未被覆盖、暂存或提交。
- 最终提交信息使用简体中文，并在提交前再次检查敏感信息。
