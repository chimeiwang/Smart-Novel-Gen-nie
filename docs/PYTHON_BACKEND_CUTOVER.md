# Python 后端生产切换手册

## 前置条件

- 已把现有 PostgreSQL 备份恢复到独立验证库，并确认结构守卫通过。
- 已记录切换前数据库结构指纹、公共表数量和数据量基线。
- `.env` 中的 `DATABASE_URL` 通过 `host.docker.internal` 指向现有宿主机 PostgreSQL 14。
- 已执行 `uv run python scripts/generate_service_keys.py --output-dir infra/secrets`。
- 两把服务私钥归属容器 UID/GID `10001:10001` 且权限为 `600`；两份 JWKS 权限为 `644`。
- 已轮换 `JWT_SECRET`；切换后旧会话失效，用户需要重新登录。
- Agent Service 配置中不存在 `DATABASE_URL`。

## 切换步骤

1. 旧服务仍运行时执行在线预备备份，校验 SHA-256，并恢复到独立验证库运行结构守卫。
2. 从临时容器通过 `host.docker.internal` 验证 PostgreSQL 网络和身份认证。
3. 停止旧单体容器冻结写入，但保持宿主机 PostgreSQL 在线。
4. 再次运行 `scripts/backup.sh` 生成最终备份和校验和，并记录最终数据基线。
5. 由 GitHub Actions 构建并上传三张带提交哈希标签的镜像，再在服务器运行 `scripts/deploy-production.sh`，以 `--no-build` 启动新编排。
6. 运行 `scripts/compose_smoke.sh` 检查页面、Core 就绪、Agent 就绪和公网内部接口阻断。
7. 执行结构守卫和显式回滚事务内的写权限冒烟，不在生产运行会创建测试业务数据的 Playwright 流程。
8. 再次核对数据库结构指纹、公共表数量和数据量基线，确认切换没有改变数据库结构或丢失数据。

## 回滚

首次切换失败时停止新 Compose，确认宿主机 PostgreSQL 健康，再使用原 `.env.production` 和旧镜像重新启动旧单体容器；不得自动恢复或覆盖数据库。日常应用回滚只切换上一版 Python 三服务镜像。`scripts/rollback_drill.sh` 只能在 `infra/compose.test.yaml` 和独立测试数据库中运行；它会检查当前与回滚版本的三张镜像，切换后执行冒烟、完整 Playwright 场景和只读数据库结构指纹检查，最后无论成功或失败都自动恢复当前镜像栈。

```bash
ALLOW_ROLLBACK_DRILL=yes \
CURRENT_IMAGE_TAG=<当前标签> \
ROLLBACK_IMAGE_TAG=<上一版标签> \
ROLLBACK_ENV_FILE=.env.test \
scripts/rollback_drill.sh
```

迁移前的旧 Next.js 单体镜像名为 `inkforge:<tag>`，其编排结构与 Python 三服务不同，不能通过 `INKFORGE_IMAGE_TAG` 切换。旧单体兼容性属于一次性迁移验收，必须使用提前归档的单体镜像和独立验证库执行只读检查，不能与日常 Python 版本回滚混为一谈。

每次正式切换前都必须把预备备份恢复到独立验证库。只有确认生产数据本身损坏且获得单独授权后，才允许把备份恢复到生产库。`scripts/restore_verify.sh` 会拒绝验证库地址与生产地址相同；它不是生产数据库恢复命令。

## Agent 重启接管演练

先在独立测试环境启动一条已经写入稳定 Graph 快照、但仍处于运行阶段的写作任务，然后执行：

```bash
ALLOW_RECOVERY_DRILL=yes TASK_ID=<写作任务标识> scripts/recovery_drill.sh
```

脚本在 Core API 容器内使用只读事务记录基线，停止 Agent Service 后只删除当前任务对应的 Redis 队列字段，再启动 Agent Service 并等待 Core 对账器重新提交。脚本不会执行 `FLUSHDB` 或删除其他任务。只有任务推进到待用户确认或完成阶段，且没有重复草案键、多个新草案或重复计费请求时才通过。Agent Service 不会获得数据库连接。

## 2 核 2 GB 观察项

连续 30 分钟混合操作期间记录：容器内存峰值、OOM 次数、数据库连接数、任务失败数、CRUD 第 95 百分位延迟、SSE 首事件延迟和队列接受延迟。同一时刻只允许一个模型任务。出现 OOM、任务丢失、重复草案或重复扣费时不得切换生产流量。

稳定性演练只能使用独立测试数据库和 `infra/compose.test.yaml`。准备 `.env.test` 并安装 Playwright Chromium 后执行：

```bash
ALLOW_STABILITY_DRILL=yes STABILITY_ENV_FILE=.env.test scripts/stability_drill.sh
```

脚本强制运行至少 1800 秒，串行重复完整 Playwright 场景，并把端到端日志、容器资源采样、重启次数和 OOM 结果写入 `output/stability/`。任何一次端到端失败、容器重启或 OOM 都会返回非零退出码。
