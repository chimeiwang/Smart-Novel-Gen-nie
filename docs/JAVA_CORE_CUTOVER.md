# Java Core 生产切换手册

本手册只描述把现有 `core-api` 服务从历史 Python 镜像原位替换为 Java 镜像。禁止新增第二个 Core、双写或
在切换过程中修改未获批准的 PostgreSQL 结构。执行正式切换仍须获得用户单独批准。

## 前置门禁

- `./mvnw verify`、Python/Web/架构测试、Python/Java 差异测试全部通过；
- Java 已在 `novelwriterdev` 通过真实 HTTP 业务验收，并按精确用户与作品 ID 清理至零残留；
- `inkforge-core-api:<sha>` 的 `cn.inkforge.core.runtime` 标签为 `java`，入口为单进程 `java -jar`；
- Java 镜像在 448 MiB、只读根文件系统、生产 JVM 上限下通过 readiness、schema guard 和 OOM 检查；
- 已把生产备份恢复到独立验证库并通过结构守卫；正式库备份、校验和及当前数据量基线已记录；
- Web、Core、Agent 三个现有生产容器完整，容器声明的镜像仓库符合约定，且各自实际使用的不可变镜像 ID
  仍在服务器；历史标签允许不同，部署会在切换前冻结当前实际运行的精确三服务组合；
- 第一次 Python→Java 切换使用的回退 Core 镜像，必须从切换前当前提交中的 Python Core 源码精确构建并
  完成验收；不能拿任意更早的历史标签冒充“上一版”；
- `.env`、服务密钥归属/权限和 `host.docker.internal` 数据库网关满足部署脚本门禁；
- 切换窗口内没有活动写作、视频生成或导出任务。

## 自动切换流程

GitHub Actions 先运行 CI，再构建并上传三张提交哈希镜像。服务器上的
`scripts/deploy-production.sh` 会依次：

1. 校验远端提交、`.env`、服务密钥、三张新镜像和新 Core 的 Java runtime 标签；
2. 读取当前三服务的不可变镜像 ID，分别标记到同一个 `rollback-<部署提交>` 标签并反查验证，再把上一
   Core 分类为 `java` 或无标签的历史 `python`；该步骤只增加本地镜像标签，不触碰运行中的容器；
3. 用无网络、最小 `CHOWN` capability 的一次性容器，非递归初始化 `uploads` 与 `agent_logs` 两个既有卷
   的根目录所有权；
4. 只通过已审核 helper 处理既有具名 `TokenUsage` 生产迁移门禁；
5. 以 `--no-build` 原位替换同名服务，不创建第二个 Core；
6. 调用镜像内 `/usr/local/bin/inkforge-schema-guard`，再执行上传卷/日志卷真实写入、HTTP、内部路由和
   Agent 稳定就绪冒烟；
7. 任一步失败时保持原始失败码，并按上一 Core 类型恢复第 2 步冻结的精确三服务快照。

回滚标签只是指向三个既有镜像 ID 的本地别名，不会复制镜像层，也不能据此把三个来源不同的历史版本重新
组合。只有切换前同一时刻实际运行的三容器组合可以成为自动回滚基线；任一服务缺失、仓库名异常、镜像 ID
缺失、既有同名回滚标签指向其他镜像或标签反查不一致时，部署必须在数据库迁移与容器切换前停止；部署脚本
不会覆盖已经冻结的恢复点。

正常 Java 启动只使用 `infra/compose.yaml`。`infra/compose.python-core-rollback.yaml` 只允许在恢复无 Java
runtime 标签的历史 Python Core 时叠加，用于恢复其 Python 健康检查；它不得用于新 Java 版本启动。

## 回退演练

回退演练只能使用 `infra/compose.test.yaml` 和独立测试数据库。当前镜像必须是 Java；回退镜像可以是 Java，
也可以是无 runtime 标签的 Python。第一次切换使用 Python 回退镜像时，该镜像必须来自同一待切换提交的
Python Core 源码和冻结依赖，避免用陈旧实现制造虚假的回退把握。脚本会比较忽略 contract 版本号和
CHECK 元数据的 v1 兼容指纹，但 Java 守卫仍会先执行完整当前契约校验。无论演练成功或失败，脚本最后都
恢复并验证当前 Java 栈。

```bash
ALLOW_ROLLBACK_DRILL=yes \
CURRENT_IMAGE_TAG=<当前 Java 标签> \
ROLLBACK_IMAGE_TAG=<上一已验证标签> \
ROLLBACK_ENV_FILE=.env.test \
scripts/rollback_drill.sh
```

`TEST_DATABASE_URL` 是容器内 Core 使用的地址，宿主机 Playwright 使用 `DATABASE_URL`；二者必须指向同一
个独立测试 PostgreSQL。测试库只通过 `127.0.0.1` 发布，并单独加入只有 PostgreSQL 使用的
`test_host_net`；Web、Core、Agent、Redis 和生产 Compose 都不得使用该网络。

禁止在演练或日常应用回退中执行 `down -v`、恢复生产数据库备份或运行任意 DDL。只有生产数据本身损坏且
取得单独授权时，才可进入数据库恢复流程。

### 2026-08-25 本地预切换证明

- 使用全新 Compose 项目、全新 PostgreSQL/Redis/上传/日志卷及独立端口，导入从 `novelwriterdev` 只读
  导出的结构；没有向开发库或正式库写入；
- 完成 `Java v2 → 当前源码构建的 Python v2 → Java v2` 原位回退与自动恢复；Python 回退阶段 13/13 个
  浏览器用例通过；
- 回退前后兼容结构指纹一致，Java 恢复后 schema guard、readiness 和 smoke 通过；
- Java 镜像 runtime 标签为 `java`，入口为 `java -jar`，448 MiB 限额下实测 Core 占用约 271.8 MiB；
- 演练容器和三个具名业务卷均已删除。该记录只证明本地切换机制可运行，不等于生产切换批准或生产部署。

## 切换后观察

至少连续观察 30 分钟：容器内存峰值、OOM/重启次数、数据库连接数、任务失败数、CRUD P95、SSE 首事件
延迟和队列接受延迟。出现 OOM、任务丢失、重复草案、重复扣费、结构漂移或回退失败时，停止后续发布并保留
上一镜像。Python Core 源码只能在观察期结束并完成单独删除审核后移除。
