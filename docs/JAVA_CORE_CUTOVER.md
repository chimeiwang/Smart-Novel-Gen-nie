# Java Core 发布与兼容回退手册

当前 Core 与 CLI 只保留 Java。首次 Python→Java 切换已成为历史；Python Core 镜像没有现正式库回滚资格。
正式数据库已有 Durable Agent V2 事实，应用回退必须保留 V2 查询与收敛能力，永久禁止 DDL rollback。
普通代码修改不自动授权生产发布。

## 前置门禁

- Maven verify、Java 独立 HTTP／数据库 golden、契约／路由覆盖、Agent、Web 和架构测试通过；
- `npm run api:check` 证明 canonical、公共投影和生成客户端无漂移；
- 三服务使用同一次已验证发布的镜像组合，Core 标签 `cn.inkforge.core.runtime=java`；
- 镜像在生产资源限额、只读根文件系统、JVM 上限下通过 readiness、schema guard 和 OOM 检查；
- 核对 V2 schemaReady／route／V1 fresh 配置、execution Redis 和恢复证据，生产视频继续关闭；
- 当前实际运行的 Web、Core、Agent 不可变镜像 ID 可回查；应用回退不恢复数据库备份、不执行迁移；
- 环境与服务密钥权限满足部署门禁，发布时没有正在处理的写作／媒体任务。

## 自动发布与回退

`scripts/deploy-production.sh` 校验提交、环境、密钥、新镜像及 Java runtime，然后冻结同一时刻实际运行的
三服务精确镜像组合为 `rollback-<提交>`。缺少服务、镜像身份异常、既有标签冲突或当前 Core 非 Java 时，
在业务迁移与容器切换前拒绝继续；不得拼接任意历史版本成为回退基线。

脚本按既有门禁处理具名 TokenUsage 迁移，再以 `--no-build` 原位替换同名服务。普通部署不会执行 Durable V2 DDL。
结构守卫使用：

```bash
scripts/verify-running-core-schema.sh <完整Core容器ID>
```

探针复用运行实例的不可变镜像和实际数据库配置，在独立受限一次性容器中执行，禁止在活动 Core 容器内
额外启动守卫 JVM。随后验证上传／日志卷写入、HTTP、内部路由与 Agent 稳定就绪。任何失败保留原始错误码，
并恢复被冻结的兼容 Java 三服务组合。Python 健康检查 overlay 和 Python 回退分支已删除。

## 本地隔离回退演练

仅使用 `infra/compose.test.yaml` 和独立测试 PostgreSQL。当前及回退 Core 都必须是支持现有 V2 数据的 Java
镜像。演练比较完整 schema 指纹，最终恢复并验证当前 Java 组合。

```bash
ALLOW_ROLLBACK_DRILL=yes \
CURRENT_IMAGE_TAG=<当前已验证Java标签> \
ROLLBACK_IMAGE_TAG=<上一兼容Java标签> \
ROLLBACK_ENV_FILE=.env.test \
scripts/rollback_drill.sh
```

容器内 `TEST_DATABASE_URL` 与宿主机浏览器测试的 `DATABASE_URL` 必须指向同一个隔离测试库。
禁止 `down -v`、恢复生产备份或运行 DDL；数据库恢复须单独授权。

## 只读结构导出与恢复验证

结构源为 `apps/core-api-java/src/main/resources/db/` 下的具名 profile。构建 JAR 后可在获准目标使用
`scripts/export_schema_contract.sh --output <新证据文件>`；数据库 URL 从环境或 stdin 读取，不进入命令参数，
已有证据默认禁止覆盖。导出不修改数据库，也不自动替换提交的契约。

`ALLOW_RECOVERY_DRILL=yes scripts/recovery_drill.sh` 转入现有 V2 隔离 Compose 最小故障恢复测试；
它不接受生产 TASK_ID，不删除生产队列键，不再执行 V1 Python Core 维护脚本。

## 发布后观察

至少观察 30 分钟：内存／OOM／重启、数据库连接、失败任务、CRUD P95、SSE 首事件和队列延迟。
遇到任务丢失、重复候选／扣费、结构漂移或回退失败时停止后续发布并保留证据。

## 历史首次切换证据

以下只用于追溯 2026-08-25 的首次切换机制，不能作为当前 Python 回退或生产执行依据。

### 2026-08-25 本地预切换证明

- 使用全新 Compose 项目、全新 PostgreSQL/Redis/上传/日志卷及独立端口，导入从 `novelwriterdev` 只读
  导出的结构；没有向开发库或正式库写入；
- 完成 `Java v2 → 当前源码构建的 Python v2 → Java v2` 原位回退与自动恢复；Python 回退阶段 13/13 个
  浏览器用例通过；
- 回退前后兼容结构指纹一致，Java 恢复后 schema guard、readiness 和 smoke 通过；
- Java 镜像 runtime 标签为 `java`，入口为 `java -jar`，448 MiB 限额下实测 Core 占用约 271.8 MiB；
- 演练容器和三个具名业务卷均已删除。该记录只证明本地切换机制可运行，不等于生产切换批准或生产部署。
