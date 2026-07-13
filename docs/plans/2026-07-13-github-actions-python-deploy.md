# GitHub Actions Python 三服务部署迁移实施计划

> **执行要求：**在当前会话中按步骤实施；每次修改先补失败测试，再进行最小修复。

**目标：**让 GitHub Actions 使用迁移后的 Python 三服务门禁和预构建镜像完成生产部署。

**架构：**CI 同时验证 Node 与 Python 工作区；Deploy 在 GitHub Runner 构建三个提交哈希镜像，经 SSH 加载到服务器，再由远程脚本以 `infra/compose.yaml` 和 `--no-build` 启动。服务器前置条件缺失时明确停止。

**技术栈：**GitHub Actions、Node.js 22、Python 3.12、uv、Docker Compose、SSH、pytest。

---

### 任务 1：锁定迁移后的工作流契约

**文件：**

- 新建：`tests/architecture/test_github_workflow.py`
- 修改：`.github/workflows/build.yml`
- 修改：`scripts/generate_api_client.mjs`

- [x] 添加架构测试，禁止 Prisma 和旧单体 Docker 路径，并要求当前 Node/Python 门禁与三镜像部署命令。
- [x] 添加 OpenAPI 生成器跨平台启动命令断言。
- [x] 运行 `uv run pytest tests/architecture/test_github_workflow.py -q`，确认测试因旧工作流失败。
- [x] 更新工作流的 CI Job 和 Deploy Job。
- [x] 再次运行架构测试，确认通过。

### 任务 2：恢复远程部署脚本的仓库与预构建镜像语义

**文件：**

- 修改：`scripts/deploy-production.sh`
- 修改：`tests/architecture/test_github_workflow.py`

- [x] 增加脚本契约测试，要求使用 `APP_DIR`、指定提交、四个服务密钥和 `--no-build --wait`。
- [x] 运行目标测试，确认旧脚本不满足契约。
- [x] 最小修改部署脚本，获取指定提交、验证服务器前置条件并启动预构建镜像。
- [x] 重新运行目标测试。

### 任务 3：本地全量验证与发布

**文件：**

- 修改：`docs/audits/2026-07-13-python-backend-rewrite-acceptance.md`

- [x] 运行工作流架构测试和 Compose 安全测试。
- [x] 运行 `npm run api:check`、`npm run test:web`、`npm run typecheck`、`npm run lint` 和 `npm run build`。
- [x] 运行 Python 全量 pytest、Ruff 和 Mypy。
- [ ] 更新验收记录，审计暂存文件后使用简体中文提交并推送 `main`。

### 任务 4：监控 Actions 至终态

- [ ] 在 GitHub Actions 页面确认新运行的 CI 与 Deploy 状态。
- [ ] 仓库内失败时读取直接日志，回到任务 1 或任务 2做最小修复并重新验证、提交和推送。
- [ ] 服务器缺少工具、配置、密钥、数据卷、容量或外部服务时停止，记录直接证据并通知用户。
- [ ] 只有 CI 和 Deploy 都成功时才声明部署完成。
