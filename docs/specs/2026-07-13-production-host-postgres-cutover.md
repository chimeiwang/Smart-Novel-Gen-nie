# 生产环境复用宿主机 PostgreSQL 切换设计

## 背景

Python 后端迁移完成后，生产编排默认要求挂载已有 PostgreSQL Docker 外部数据卷。实际服务器仍使用宿主机 PostgreSQL 14，当前旧单体容器通过宿主机网络连接该数据库，服务器不存在可复用的 PostgreSQL Docker 数据卷。直接创建空卷会让新服务连接空数据库；把 PostgreSQL 14 数据目录直接挂载给 PostgreSQL 16 容器则存在跨大版本物理格式不兼容风险。

生产数据库只读检查已确认：数据库约 28 MB，公共 schema 包含 42 张表，估算约 4714 行；仓库内数据库结构守卫与生产结构完全一致，差异为 0。服务器根文件系统约有 19 GB 可用空间，具备备份和独立恢复验证条件。

## 决策

生产环境继续使用宿主机 PostgreSQL 14，不搬迁数据库文件，不改写业务数据，不执行 DDL。生产 Core API 通过 Docker host gateway 连接现有数据库。测试环境继续使用 `infra/compose.test.yaml` 中的独立 PostgreSQL 容器和测试数据卷。

明确排除以下方案：

- 不创建空 PostgreSQL Docker 数据卷冒充现有生产数据卷。
- 不把 PostgreSQL 14 物理数据目录直接挂载给 PostgreSQL 16 容器。
- 本次切换不执行 Prisma migrate、Alembic、`create_all()`、初始化 SQL 或批量业务数据更新。

## 生产编排

`infra/compose.yaml` 只包含 Nginx、Web、Core API、Agent Service 和 Redis。生产文件不定义 PostgreSQL 服务，也不声明 PostgreSQL 数据卷。Core API 保留 `data_net`，并通过 `extra_hosts` 将 `host.docker.internal` 映射到 Docker host gateway；生产 `.env` 的 `DATABASE_URL` 使用该主机名。

`infra/compose.test.yaml` 定义测试 PostgreSQL 服务、测试数据卷和 Core API 对测试数据库的依赖。测试数据库仍使用已有的独立测试数据卷，生产数据库不会进入自动化测试范围。

Agent Service 不加入 `data_net`，不接收 `DATABASE_URL`。Nginx 仍是唯一发布端口的服务。所有应用容器继续使用非 root 用户、只读根文件系统、资源上限和健康检查。

## 备份与恢复验证

切换前执行两次备份：

1. 旧服务仍运行时执行在线预备备份。
2. 进入维护窗口并停止旧单体容器后执行最终备份。

每次备份使用 PostgreSQL custom format，并生成 SHA-256 校验文件。预备备份必须恢复到同一 PostgreSQL 实例中的独立临时验证数据库；恢复后运行结构守卫并核对公共表数量。验证数据库不得与生产数据库同名，验证完成后删除。

服务器当前旧容器没有上传目录挂载，仅发现容器内日志目录。切换前仍需再次探测旧容器挂载和常见上传目录；如果发现用户上传文件，必须先复制并校验，再继续切换。未发现上传数据时记录检查结果，不创建虚假备份。

## 密钥与配置

生产服务器生成两组新的 Ed25519 服务身份材料：Core 到 Agent、Agent 到 Core。私钥归属容器 UID/GID `10001:10001` 且权限设为 `600`；`.env` 归属 `root:部署用户组` 且权限设为 `640`，使 SSH 部署用户只能读取、不能修改；公钥材料权限设为 `644/root`。密钥只保存在服务器 `infra/secrets`，不进入 Git、镜像或日志。

原生产 `JWT_SECRET` 已暴露，因此切换时生成不少于 32 字节的新随机密钥。轮换后所有旧会话失效，用户需要重新登录；用户账号、密码哈希和业务数据不变。

新的 `.env` 继承旧 `.env.production` 中仍有效的模型、RAG 和调试开关，但移除旧 Node/LangGraph.js 专属变量。部署与诊断只输出变量是否存在，不输出任何秘密值。

## 切换流程

1. 检查服务器磁盘、Docker、Compose、Git、镜像、网络子网、宿主机 PostgreSQL 和当前旧容器状态。
2. 完成在线预备备份、SHA-256 校验和独立恢复验证。
3. 使用临时容器从 `host.docker.internal` 验证数据库端口和身份认证，不修改 PostgreSQL schema。
4. 进入 10 至 15 分钟维护窗口，停止旧单体容器并执行最终备份。
5. 记录最终数据库结构指纹、公共表数量和估算行数基线。
6. 写入新 `.env`，生成服务密钥，并通过 `docker compose config` 验证编排。
7. 启动 Redis、Agent Service、Core API、Web 和 Nginx，等待所有健康检查通过。
8. 执行无副作用生产冒烟：页面、Core readiness、Agent readiness、Nginx 内部接口阻断、数据库结构守卫，以及显式回滚事务内的写权限验证。
9. 再次核对数据库结构指纹和数据量基线，确认没有结构变化或异常数据丢失后结束维护窗口。

本地已经完成 6 个 Playwright 主流程。生产环境不运行这些会创建测试用户和业务记录的流程，只运行无副作用冒烟检查。

## 失败处理与回滚

在新服务开放流量前，任何镜像、配置、数据库连接、结构守卫或健康检查失败都必须停止切换。回滚步骤为：停止新编排，确认宿主机 PostgreSQL 仍健康，使用原 `.env.production` 和旧镜像重新启动旧单体容器。

新旧应用共用同一数据库结构，切换不包含 schema 迁移，因此正常回滚不恢复数据库备份。只有确认数据库本身损坏时，才允许在单独决策后从最终备份恢复生产库。

旧单体容器、旧镜像、原 `.env.production` 和最终备份至少保留 7 天。任何清理都不属于本次切换范围。

## 验收标准

- GitHub Actions 的 CI、三镜像构建上传和远程部署全部成功。
- 生产 Compose 五个服务全部健康，且只有 Nginx 发布端口。
- 现有数据库结构指纹与切换前一致，公共表数量一致，业务数据可以读取。
- 新 JWT 生效，旧会话失效，用户可使用原账号密码重新登录。
- Agent Service 无数据库凭据，公网 `/internal/**` 继续被拒绝。
- 容器没有持续重启、OOM 或数据库连接错误。
- 失败时旧单体容器可以使用原配置重新启动。
