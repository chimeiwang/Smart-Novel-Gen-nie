# Agent 人工日志卷权限修复

## 背景

生产 `agent-service` 以 `10001:10001` 运行，`agent_logs` 命名卷首次创建后却由 `root:root` 持有且权限为 `0755`。中短篇任务在模型调用前创建日期日志目录时触发 `PermissionError`，随后被统一映射为 `SHORT_MEDIUM_RUN_FAILED`。

## 目标

- 现有生产日志卷恢复为 Agent 用户可写，不删除、不重建卷。
- 每次生产部署都在版本切换前初始化日志卷根目录所有权，再启动 Agent。
- 生产 smoke 必须实际创建并删除探针目录，不能只检查 HTTP readiness。
- Agent 正式进程继续以 `10001:10001`、只读根文件系统和无额外能力运行。

## 非目标

- 不修改 PostgreSQL schema、写作契约或模型配置。
- 不把持久化日志改成 tmpfs 或宿主机 bind mount。
- 不递归修改日志卷内既有文件，不使用 `chmod 777`。

## 设计

`scripts/deploy-production.sh` 在版本切换和回滚 trap 注册前确保固定命名卷 `inkforge_agent_logs` 存在，再用当前 Agent 镜像运行一次隔离初始化容器。该容器只挂载日志卷，不接收模型密钥、服务私钥或业务环境变量，不加入任何网络。它以 root 启动，但删除全部 Linux capabilities 后只加回 `CHOWN`，执行一次非递归 `chown 10001:10001 /data/agent-logs` 后退出。

初始化失败时部署在任何 `compose up` 之前停止，现有生产容器保持不变。不能把初始化器建模为 `service_completed_successfully` 的 Compose 服务，因为生产使用的 `docker compose up -d --wait` 会把成功退出的一次性服务视为未处于运行状态并返回非零。

`scripts/compose_smoke.sh` 在 HTTP 和队列就绪检查前，以正式 Agent 容器身份在 `WORKFLOW_HUMAN_LOG_DIR` 下创建并删除唯一探针目录。探针失败必须使 smoke 非零退出。

现有生产卷执行一次精确 `chown 10001:10001`；不递归处理其他目录，也不删除或重建卷。

## 安全边界

- root 仅允许存在于无网络、一次性、只挂载日志卷的部署初始化容器。
- 初始化容器使用只读根文件系统、`cap_drop: ALL` 和 `cap_add: CHOWN`。
- Web、Core API、Agent、Nginx 与 Redis 正式服务继续保持非 root。
- 初始化命令不使用 Compose 服务定义，不读取 `.env` 中的密钥值，不挂载服务身份材料。

## 验收

- 架构测试证明初始化命令没有网络、密钥环境或多余挂载，并且只有 `CHOWN` capability。
- 部署测试证明初始化发生在首次 `compose up` 之前，失败时不会切换版本。
- smoke 测试证明日志目录不可写时部署失败，可写时原有就绪流程继续执行。
- 生产容器内 `test -w /data/agent-logs` 成功，实际创建并删除探针目录成功。
