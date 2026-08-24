# TokenUsage 明细生产迁移与发布规格

状态：已批准  
批准日期：2026-08-23  
批准语义：用户明确要求先迁移数据库，再执行生产发布与线上试跑。

## 1. 目标

将 `scripts/migrations/20260823_token_usage_details.sql` 先在服务器专用 dev PostgreSQL 验证，导出真实
`schema-contract.json`，再在可恢复备份保护下迁移生产 PostgreSQL，并发布已经通过本地全量验证的模型
策略、DeepSeek transport、Token 明细和确定性 patch 工作流。

## 2. 固定边界

- 工作流只能执行 `20260823_token_usage_details.sql`，禁止接收任意 SQL、任意服务器路径或任意数据库 URL。
- SQL 文件必须匹配固定 SHA-256：
  `BF6817A82F74E76B8F98D356749795A1EC04BCFCED090DB3F8B463F62ABCAB93`。
- 服务器没有独立 dev 环境文件。工作流只允许从应用目录现有 `.env` 解析唯一生产连接，强制源数据库名为
  `novelwriter`，只把数据库路径派生为 `novelwriterdev`；query 只允许宿主机 libpq 与 Core asyncpg 都支持的
  `sslmode` 和 `application_name`，拒绝任何可覆盖数据库、主机或身份的参数。派生后以只读查询再次确认数据库名，不能
  输出连接串。
- `.env` 的主机必须是生产 Compose 使用的 `host.docker.internal`。宿主机上的 `psql`/`pg_dump` 只把这个
  固定主机映射为 `127.0.0.1`，Core 容器接收的完整 dev URL 继续保留 `host.docker.internal`；其他源主机一律
  拒绝。解析失败只允许输出固定原因码，不能回显 URL 或异常正文。
- 根目录 `.env.example` 是 README 指定的生产配置起点，数据库名必须与现网正式库一致为 `novelwriter`；开发
  配置仍由 `.env.local.example` 指向 `novelwriterdev`。
- 宿主机 `psql`、`pg_dump` 只接收不含密码的连接 URL，密码只写入运行编号绑定、权限为 `0600` 的临时
  `.pgpass`；Core 容器只通过标准输入读取完整 dev URL。临时凭据不得进入命令行、日志或 Artifact，并由
  远端和 runner 两层 trap 精确清理。
- 迁移 SQL 自身必须拒绝 `current_database() <> 'novelwriterdev'`，避免工作流配置错误触及生产库。
- dev SQL 不得在部署时动态替换数据库名。生产使用独立固定 forward SQL，SQL 自身只允许 `novelwriter`，并
  维护独立 SHA；固定 rollback SQL同样只允许 `novelwriter`。
- dev 与生产迁移前必须生成 PostgreSQL custom-format 备份和 `SHA256SUMS`，迁移必须连续执行两次。服务器
  部署用户对 `/srv/backups/inkforge-dev` 和 `/srv/backups/inkforge` 均无写权限；dev 备份固定写入应用目录下
  的私有 `.token-usage-dev-backups`，不得因此提权或复用生产备份目录。
- dev 迁移后从真实数据库只读导出结构契约；提交前人工/自动核对差异只能包含两个 nullable INTEGER 列和三个 CHECK。
- 结构契约从 Core 容器通过 `docker exec` 标准输出定向写入宿主机 `0600` 临时文件，不依赖服务器当前不可用的
  `docker cp` 容器文件复制；标准输出只能进入文件，不能进入日志。
- 固定 SQL 失败时，工作流只允许读取本次运行私有错误文件并输出预定义原因码；不得回显 PostgreSQL 异常正文、
  SQL、连接串或凭据。错误文件必须绑定运行编号并由 trap 清理。
- CHECK 定义一致性不得拿手写字符串直接比对 PostgreSQL 的格式化文本；迁移应在事务内临时表上创建同一组
  约束，以数据库解析后的规范定义作为比较基准，仍需逐个 `VALIDATE CONSTRAINT`。
- 生产迁移由部署脚本在新容器启动前执行。部署失败且本次部署首次增加这些字段时，先运行固定 down
  脚本删除三个约束与两个纯诊断列，再恢复旧镜像；正式正文、用户数据和旧 TokenUsage 字段不得变更。
- 生产部署通过固定 helper 安全解析 `.env`：密码只进入 `0600` 临时 `.pgpass`，宿主机命令只接收映射到
  `127.0.0.1` 的无密码 URL。生产备份写入应用私有 `.token-usage-production-backups` 并校验。
- 生产 schema 只接受 `unmigrated` 或完整 `migrated`；任意缺列、缺约束、未验证或定义漂移均视为 `partial`，
  必须在备份、迁移和切换镜像前停止。
- `reasoning_content` 正文不进入数据库、构建产物或工作流 Artifact。工作流 Artifact 只允许包含结构契约和非敏感校验元数据。

## 3. 分阶段流程

### 3.1 Bootstrap

单独向 main 合入固定 dev 迁移工作流、迁移 SQL 和静态架构测试。该提交不修改应用运行时代码或数据库，
即使触发现有部署，也只会重新部署当前生产基线。

### 3.2 Dev 迁移与 contract

1. 手工触发工作流 `inspect`，确认服务器存在 `psql`、`pg_dump`、Docker，并能从 `.env` 安全派生、经宿主机
   回环地址只读连接 `novelwriterdev`。诊断分支已于 2026-08-24 完成该只读检查；main 最终版本仍需再次确认。
2. 手工触发 `migrate_dev`：在应用私有 `.token-usage-dev-backups` 目录备份、校验 SQL 哈希、执行两次、验证
   旧行明细保持 NULL。2026-08-24 首次执行在 DDL 前因 `/srv/backups/inkforge-dev` 不可写而停止，只读诊断已
   同时确认应用私有目录可创建。
3. 使用当前 Core 容器的只读 schema 导出能力生成 contract，并通过 Actions Artifact 下载。
4. 将真实 contract 写回功能分支，删除 `test_model_metadata.py` 的临时内存兼容层，运行 schema/全量验证。

### 3.3 生产迁移与发布

1. 功能分支经 PR 合入 main；CI 完整通过后进入 production environment。
2. 部署脚本确认旧镜像可回滚，再判定生产 schema；仅 `unmigrated` 时备份并运行固定生产 forward 两次。
   备份成功后、第一次 forward 前即记录本次部署的回退责任；若 SQL 尚未提交，down 对 `unmigrated` 安全空操作，
   从而消除 SQL 已提交与 shell 标志赋值之间的空窗。
3. 启动新镜像，执行 Compose、只读 schema 指纹和 HTTPS smoke。
4. 任一部署验收失败时，只在确认迁移由本次部署首次应用后执行固定 down；down 失败则禁止恢复旧镜像，
   down 成功且本次已经开始镜像切换时才恢复旧镜像和旧 schema 就绪状态。

2026-08-24 首次生产发布在任何 TokenUsage DDL 之前停止：应用账号执行全库 `pg_dump` 时无权读取
`VideoProject`。8 月 23 日记录的最终备份发生在 25 张视频表再次创建之前，不能证明迁移后应用账号仍有
完整备份权限。继续发布前必须先通过固定只读动作列出 `public` 下缺少 `SELECT` 的表和序列，并确认这些
对象是否由其他角色创建；诊断不得输出数据库用户名、连接串或密码。只有缺失范围明确后，才允许以服务器
既有数据库管理员通道向当前应用角色补最小读取权限，随后必须先单独完成全库 custom-format 备份及
`pg_restore --list` 校验，再重新执行部署。不得通过排除视频表或降级为 schema-only 备份绕过该门禁。

只读工作流 `32681718756` 已确认：`public` 共 69 张表，应用角色仅对 25 张 `Video*` 表缺少
`SELECT`；这 25 张表属于同一个其他角色，应用角色不是该 owner 角色的成员；库内没有序列，schema
`USAGE` 正常。部署 SSH 账号不存在可用的默认 owner 连接、`sudo postgres` 或 `runuser postgres`
通道。因此当前只能停止在 DDL 前，不能由应用角色自行补权。继续执行需要复用上次视频迁移使用的表
owner/DBA 连接，或者由服务器管理员为这一次固定 `GRANT SELECT` 提供受控执行通道。

用户已于 2026-08-24 明确授权执行所需生产权限修复。受控修复只允许复用现有部署密钥尝试服务器
`root` 或发行版预置管理员账号，并要求连接本身是 root 或具备免密 `sudo`，再由本机 PostgreSQL
`postgres` 角色执行；SQL 必须验证数据库名、当前数据库角色为超级
用户、应用角色来自生产 `.env` 且不是超级用户、固定 25 张表全部存在，并且权限状态只能是“全部缺失”
或“全部已有”。修复只执行 `GRANT SELECT`，不授予写权限、不改变 owner。修复后必须切回普通部署账号
验证 `table-select-missing:0`，并先生成、校验完整备份；任一前置条件不满足即停止。

受控执行结果：工作流 `32683476824` 确认现有密钥无法直接登录 root；增加发行版预置管理员账号与免密
`sudo` 检查并完成安全复审后，工作流 `32683626141` 仍确认没有可用管理员通道。两个运行均在 PostgreSQL
连接和 `GRANT` 之前停止，正式库权限、TokenUsage 结构和生产容器均未改变。继续执行必须先让现有
`SERVER_SSH_KEY` 对应公钥能够登录一个 root/免密 sudo 管理员账号，或给当前 `SERVER_USER` 提供受限的
PostgreSQL 管理执行能力。

用户随后指出项目根目录 `.env` 已保存独立服务器账号密码，并要求数据库变更前单独确认。2026-08-24
在获得“补齐”确认后，使用该 root 通道完成固定 25 张视频表的 `GRANT SELECT`：应用角色缺失读取权限
由 25 降为 0；未授予写权限，未改变 owner 或业务行。随后以应用目录 owner 的普通部署身份执行生产
helper 全库备份，custom-format 文件为 18,226,819 字节，`SHA256SUMS` 与 `pg_restore --list` 均通过。
复核时 TokenUsage 仍为 `unmigrated`，全部生产容器保持 healthy；后续 TokenUsage DDL 仍等待独立确认。

用户确认继续后，原 main 发布运行 `32680529416` 的 attempt 2 成功完成。生产 helper 状态为
`migrated`；`TokenUsage` 两个 nullable INTEGER 列和三个已验证 CHECK 均存在，迁移时 3,129 条历史
记录的明细列保持 NULL。Web、Core API、Agent Service 均运行镜像
`fc7b8c814bd5a263f3e698588e06df3876d828ac` 且 healthy，HTTPS live 返回 `200/ok`、readiness 返回
`200/ready`，发布备份再次通过 SHA-256 与 `pg_restore --list`。生产 CLI 的 `auth.whoami`、中短篇列表和
长篇列表只读检查通过；未从发布授权推导任意付费模型任务或作品写入。

## 4. 验收

- dev 与生产备份都有完整性校验文件；迁移双跑成功。
- dev 导出 contract 与 ORM、迁移脚本精确一致，本地临时兼容测试已删除。
- main CI、生产 Compose、Core/Agent readiness、schema guard 和 HTTPS smoke 全部通过。
- 线上只读执行 `auth.whoami`、作品列表/读取；真实付费模型任务必须使用明确作品和操作，不从“发布”授权推导任意正文写入。
