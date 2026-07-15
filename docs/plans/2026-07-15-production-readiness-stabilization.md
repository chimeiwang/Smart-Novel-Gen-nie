# 生产部署就绪稳定化实现计划

> **执行要求：** 使用子 Agent 驱动开发或按计划逐项执行；所有实现步骤必须先看到对应测试失败。

**目标：** 让生产发布只在 Agent 连续稳定就绪且当前 Compose Nginx 可用时成功，同时保留持续异常自动回滚。

**架构：** `compose_smoke.sh` 从 Compose 查询 Nginx 发布端口，并用有界连续成功计数验证 Agent readiness；实际 HTTP 与安全 JSON 解析由可独立测试的 `agent_readiness_probe.py` 完成。`deploy-production.sh` 在新版本和回滚版本的应用容器启动后都强制重建 Nginx，刷新 Docker DNS upstream。

**技术栈：** POSIX shell、Docker Compose、Python 3 标准库、pytest。

---

### 任务一：为稳定 Agent readiness 和真实 Nginx 端口补行为测试

**文件：**

- 修改：`tests/architecture/fixtures/fake_docker.sh`
- 修改：`tests/architecture/test_rollback_drill.py`
- 新建：`tests/architecture/test_agent_readiness_probe.py`

- [ ] 扩展 fake Docker：`compose port nginx 8080` 返回 `FAKE_NGINX_BINDING`；Agent `exec` 使用计数文件，在 `FAKE_AGENT_READY_AFTER` 之前输出 `BACKGROUND_TASK_BACKOFF` JSON 并失败。
- [ ] 新增测试：设置发布端口 `43120`、前两次 Agent 503、随后连续三次成功；执行 `compose_smoke.sh` 后断言返回码为 0、Agent 共检查五次、curl 日志只包含 `127.0.0.1:43120`。
- [ ] 新增测试：让 Agent 持续 503，最大检查四次；断言返回码非零、调用恰好四次、标准错误包含 `BACKGROUND_TASK_BACKOFF`。
- [ ] 使用本机 `127.0.0.1` 随机端口 HTTPServer 真实执行探针，覆盖 200 ready、503 白名单诊断、200 未就绪和 503 非法 JSON，并断言敏感字段不进入标准错误。
- [ ] 运行：`uv run pytest tests/architecture/test_rollback_drill.py -q`。预期新增测试因当前脚本只检查一次且默认访问 80 而失败。

### 任务二：实现 Smoke 稳定探针

**文件：**

- 修改：`scripts/compose_smoke.sh`
- 新建：`scripts/agent_readiness_probe.py`

- [ ] 用 `compose port nginx 8080 | head -n 1` 获取绑定地址，以 `${binding##*:}` 提取端口，并拒绝空值或非数字值。
- [ ] 增加 `SMOKE_AGENT_MAX_ATTEMPTS`（默认 45）、`SMOKE_AGENT_REQUIRED_SUCCESSES`（默认 5）、`SMOKE_AGENT_POLL_SECONDS`（默认 2）的正整数/非负间隔校验。
- [ ] 将 HTTP 请求和 JSON 解析迁入独立探针；CLI 只接收一个 URL，显式关闭 `HTTPError`，仅输出白名单诊断，非法 JSON 只输出 HTTP 状态码。
- [ ] Smoke 使用 `compose exec -T agent-service python - <url> < scripts/agent_readiness_probe.py` 执行探针，并只转发安全前缀输出。
- [ ] 每次失败把连续成功数清零；达到连续成功目标后通过；用尽次数后输出“Agent 服务未连续稳定就绪”并返回非零。
- [ ] 运行：`uv run pytest tests/architecture/test_rollback_drill.py -q`。预期新增测试通过。

### 任务三：为 Nginx upstream 刷新补部署行为测试

**文件：**

- 修改：`tests/architecture/test_deploy_scripts.py`

- [ ] 在成功部署测试中断言日志包含一次 `up --no-build -d --wait --no-deps --force-recreate nginx`。
- [ ] 在新版本失败并回滚测试中断言该命令出现两次，分别位于新标签和上一标签下。
- [ ] 运行：`uv run pytest tests/architecture/test_deploy_scripts.py -q`。预期新增断言失败。

### 任务四：实现新版本和回滚路径的 Nginx 刷新

**文件：**

- 修改：`scripts/deploy-production.sh`

- [ ] 新增 `refresh_nginx()`，执行：

```sh
compose up --no-build -d --wait --no-deps --force-recreate nginx
```

- [ ] 新版本全栈 `compose up --no-build -d --wait` 后、`verify_stack` 前调用 `refresh_nginx`。
- [ ] 回滚全栈恢复成功后、`verify_stack` 前调用 `refresh_nginx`；刷新失败必须保留“自动回滚也失败”语义。
- [ ] 运行：`uv run pytest tests/architecture/test_deploy_scripts.py -q`。预期通过。

### 任务五：完整验证并发布

**文件：**

- 验证：`scripts/compose_smoke.sh`
- 验证：`scripts/agent_readiness_probe.py`
- 验证：`scripts/deploy-production.sh`
- 验证：`tests/architecture/`

- [ ] 运行 Shell 语法检查：`sh -n scripts/compose_smoke.sh scripts/deploy-production.sh scripts/upload-docker-images.sh`。
- [ ] 运行部署相关测试：`uv run pytest tests/architecture/test_rollback_drill.py tests/architecture/test_deploy_scripts.py tests/architecture/test_github_workflow.py tests/architecture/test_compose_security.py -q`。
- [ ] 运行 Ruff：`uv run ruff check scripts/agent_readiness_probe.py tests/architecture`。
- [ ] 检查：`git diff --check` 和 `git status -sb`。
- [ ] 以简体中文提交并推送 `main`，随后重跑失败部署并监控到结束。
