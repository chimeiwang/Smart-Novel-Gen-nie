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
  `1DE1CD58C589403303B40F2AA2AE9DE3C44F272E5DD6C09159327535F04C5142`。
- dev 数据库配置只允许从服务器应用目录下固定候选文件读取；检查阶段只报告文件与工具是否存在，不能输出连接串。
- dev 与生产迁移前必须生成 PostgreSQL custom-format 备份和 `SHA256SUMS`，迁移必须连续执行两次。
- dev 迁移后从真实数据库只读导出结构契约；提交前人工/自动核对差异只能包含两个 nullable INTEGER 列和三个 CHECK。
- 生产迁移由部署脚本在新容器启动前执行。部署失败且本次部署首次增加这些字段时，先运行固定 down
  脚本删除三个约束与两个纯诊断列，再恢复旧镜像；正式正文、用户数据和旧 TokenUsage 字段不得变更。
- `reasoning_content` 正文不进入数据库、构建产物或工作流 Artifact。工作流 Artifact 只允许包含结构契约和非敏感校验元数据。

## 3. 分阶段流程

### 3.1 Bootstrap

单独向 main 合入固定 dev 迁移工作流、迁移 SQL 和静态架构测试。该提交不修改应用运行时代码或数据库，
即使触发现有部署，也只会重新部署当前生产基线。

### 3.2 Dev 迁移与 contract

1. 手工触发工作流 `inspect`，确认服务器存在 `psql`、`pg_dump`、Docker 和唯一 dev 环境文件。
2. 手工触发 `migrate_dev`：备份、校验 SQL 哈希、执行两次、验证旧行明细保持 NULL。
3. 使用当前 Core 容器的只读 schema 导出能力生成 contract，并通过 Actions Artifact 下载。
4. 将真实 contract 写回功能分支，删除 `test_model_metadata.py` 的临时内存兼容层，运行 schema/全量验证。

### 3.3 生产迁移与发布

1. 功能分支经 PR 合入 main；CI 完整通过后进入 production environment。
2. 部署脚本确认旧镜像可回滚，再备份生产数据库并运行固定迁移两次。
3. 启动新镜像，执行 Compose、只读 schema 指纹和 HTTPS smoke。
4. 任一部署验收失败时，只在确认迁移由本次部署首次应用后执行固定 down，再恢复旧镜像和旧 schema 就绪状态。

## 4. 验收

- dev 与生产备份都有完整性校验文件；迁移双跑成功。
- dev 导出 contract 与 ORM、迁移脚本精确一致，本地临时兼容测试已删除。
- main CI、生产 Compose、Core/Agent readiness、schema guard 和 HTTPS smoke 全部通过。
- 线上只读执行 `auth.whoami`、作品列表/读取；真实付费模型任务必须使用明确作品和操作，不从“发布”授权推导任意正文写入。

