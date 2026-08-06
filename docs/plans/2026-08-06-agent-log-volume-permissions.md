# Agent 人工日志卷权限修复实施计划

> **执行要求：** 按测试驱动顺序逐项实施；每次只修改本任务涉及的文件。

**目标：** 永久消除 `agent_logs` 命名卷由 `root:root` 持有导致中短篇任务在模型调用前失败的问题。

**架构：** 部署脚本在版本切换前使用无网络、最小 capability 的一次性隔离容器初始化卷根目录所有权；部署 smoke 使用正式 Agent 身份执行真实写入探针。

**技术栈：** Docker Compose、POSIX shell、pytest 架构测试。

---

### 任务一：锁定部署初始化权限边界

**文件：**

- 修改：`tests/architecture/test_compose_security.py`
- 修改：`tests/architecture/test_deploy_scripts.py`
- 修改：`tests/architecture/fixtures/fake_docker.sh`
- 修改：`scripts/deploy-production.sh`

- [ ] 先增加失败测试，断言初始化容器只挂载日志卷、禁用网络、只保留 `CHOWN`，并发生在首次 `compose up` 前。
- [ ] 运行相关架构测试，确认因缺少部署初始化命令而失败。
- [ ] 在部署脚本中加入最小权限初始化容器，失败时在版本切换前停止。
- [ ] 重跑测试并确认通过。

### 任务二：锁定部署写入探针

**文件：**

- 修改：`tests/architecture/test_deploy_scripts.py`
- 修改：`tests/architecture/fixtures/fake_docker.sh`
- 修改：`scripts/compose_smoke.sh`

- [ ] 先增加失败测试，断言 smoke 会在 Agent 容器中创建并删除日志探针目录，失败时部署非零退出。
- [ ] 运行相关单测，确认因缺少写入探针而失败。
- [ ] 在 smoke 中增加基于 `WORKFLOW_HUMAN_LOG_DIR` 的实际写入探针，并让 fake docker 独立模拟该步骤。
- [ ] 重跑相关单测并确认通过。

### 任务三：同步当前运维要求并完成验证

**文件：**

- 修改：`docs/requirements/05-auth-billing-and-ops.md`

- [ ] 记录一次性 root 部署初始化容器的严格例外和 smoke 写入要求。
- [ ] 运行 `uv run pytest tests/architecture/test_compose_security.py tests/architecture/test_deploy_scripts.py -q`。
- [ ] 运行 `uv run ruff check tests/architecture/test_compose_security.py tests/architecture/test_deploy_scripts.py`。
- [ ] 运行 `docker compose --env-file .env.example -f infra/compose.yaml config`；本机无 Docker 时明确记录未验证项。
- [ ] 再次只读核对生产卷所有权与容器内实际写入结果。
