# TokenUsage 明细生产迁移与发布 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 先以固定、可审计流程验证并迁移 TokenUsage 明细结构，再安全发布当前功能分支并完成线上验收。

**Architecture:** 使用独立 GitHub `workflow_dispatch` 完成 dev 检查、备份、双跑迁移和 contract 导出；生产迁移嵌入已有可回滚部署脚本，在 Compose 启动前执行，并为本次新增的纯诊断字段提供固定 down。所有数据库动作使用固定 SQL 和生产 environment，不接受任意命令输入。

**Tech Stack:** GitHub Actions、POSIX shell、PostgreSQL `psql/pg_dump`、Docker Compose、Python schema guard、GitHub CLI。

---

### Task 1：建立固定 dev 迁移工作流

**Files:**
- Create: `.github/workflows/token-usage-details-migration.yml`
- Modify: `tests/architecture/test_github_deploy_workflow.py`
- Existing: `scripts/migrations/20260823_token_usage_details.sql`

- [ ] **Step 1: 写失败的工作流静态测试**

测试解析 YAML 并断言：仅 `workflow_dispatch`；action 只能 `inspect/migrate_dev`；使用 production environment；
固定 SQL 路径与 SHA；禁止任意 SQL/URL/path 输入；SSH 严格 known-host；备份先于两次 `psql`；导出 Artifact 不含环境文件。

- [ ] **Step 2: 运行测试确认 RED**

Run: `uv run pytest tests/architecture/test_github_deploy_workflow.py -q`  
Expected: FAIL，原因是固定迁移工作流尚不存在。

- [ ] **Step 3: 实现最小工作流并验证 GREEN**

`inspect` 只检查工具，并从服务器 `.env` 的 `novelwriter` 连接安全派生、只读确认 `novelwriterdev`；
`migrate_dev` 复用该固定派生规则，运行备份、SQL 哈希、双跑、旧行 NULL 查询和只读 contract 导出，再上传
单一 JSON Artifact。派生器拒绝改变目标或身份的 query 参数，宿主机命令使用无密码 URL 和 `0600`
临时 `.pgpass`，完整 dev URL 仅通过标准输入交给 Core 容器；SQL 自身也必须拒绝任何非 `novelwriterdev`
数据库。

- [ ] **Step 4: 提交 bootstrap**

提交信息：`运维：增加 TokenUsage dev 迁移工作流`。把该固定提交单独合入 main，等待当前生产基线 CI/部署完成。

### Task 2：执行 dev 迁移并回写 contract

**Files:**
- Modify: `apps/core-api/src/inkforge_core/db/schema-contract.json`
- Modify: `apps/core-api/tests/db/test_model_metadata.py`

- [ ] **Step 1: 触发 inspect 并读取日志**

Run: `gh workflow run token-usage-details-migration.yml -f action=inspect`  
Expected: 只显示工具、`.env` 存在性和 `novelwriterdev` 只读确认结果，不输出 URL。

- [ ] **Step 2: 触发 migrate_dev 并下载 Artifact**

Run: `gh workflow run token-usage-details-migration.yml -f action=migrate_dev`  
Expected: 备份成功、迁移两次成功、旧行明细为 NULL、contract Artifact 上传成功。

- [ ] **Step 3: 核对并写回 contract**

只接受 TokenUsage 两列和三个 CHECK 的结构差异；用真实 JSON 替换 contract，删除测试中的内存字段/索引兼容补丁。

- [ ] **Step 4: 全量验证并提交**

Run: `uv run pytest -q`、Ruff、Mypy、API check、typecheck、lint、build。  
提交信息：`数据库：同步 TokenUsage 明细结构契约`。

### Task 3：接入生产迁移与可恢复发布

**Files:**
- Create: `scripts/migrations/rollback_20260823_token_usage_details.sql`
- Modify: `scripts/deploy-production.sh`
- Modify: `tests/architecture/test_deploy_script.py`
- Modify: `tests/architecture/test_github_deploy_workflow.py`

- [ ] **Step 1: 写生产迁移顺序与 rollback 失败测试**

断言部署脚本在确认旧镜像可恢复后才备份/迁移；迁移双跑早于 Compose；只有本次首次应用时 rollback 才执行固定
down；down 成功后才恢复旧镜像；未知/部分 schema 必须停止。

- [ ] **Step 2: 实现固定 down 与部署编排**

down 先精确核验两个列和三个约束，再删除约束与列；部署记录 `migration_applied_by_deploy`，失败 trap 依据该标志回退，
禁止对预先存在的已迁移 schema 执行 down。

- [ ] **Step 3: 全量验证、PR 合入与监控**

推送功能分支、创建 PR、合入 main；使用 `gh` 等待 CI 和 production deploy。任何失败先读取证据，再按现有 CI/回滚流程处理。

### Task 4：生产线上验收

**Files:**
- No repository changes expected.

- [ ] **Step 1: 验证公网与服务健康**

检查 `https://inkforge.cn`、Core readiness、部署 smoke 和 GitHub deploy 日志中的 schema 指纹。

- [ ] **Step 2: 使用生产 CLI 做只读试跑**

执行 `auth.whoami`、作品列表和一个明确作品的只读回拉；不自动启动付费模型任务或写入正文。

- [ ] **Step 3: 汇报证据边界**

分别报告：数据库迁移、contract、CI、生产部署、HTTPS/CLI 验收。任何未验证项保持未完成。
