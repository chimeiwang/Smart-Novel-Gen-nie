# Python 后端生产切换手册

## 前置条件

- 已在独立环境验证现有 PostgreSQL 备份可恢复。
- 已记录切换前数据库结构指纹。
- `.env` 中的 `DATABASE_URL` 指向现有数据库，`POSTGRES_DATA_VOLUME` 指向现有数据卷。
- 已执行 `uv run python scripts/generate_service_keys.py --output-dir infra/secrets`。
- Agent Service 配置中不存在 `DATABASE_URL`。

## 切换步骤

1. 停止旧应用写入，但保持 PostgreSQL 在线。
2. 运行 `scripts/backup.sh`，保存数据库和上传文件备份及校验和。
3. 运行 `scripts/schema_fingerprint.sh`，确认结构与仓库契约一致。
4. 运行 `scripts/deploy-production.sh` 构建并启动新编排。
5. 运行 `scripts/compose_smoke.sh` 检查页面、Core 就绪、Agent 就绪和公网内部接口阻断。
6. 完成注册登录、项目读取、章节保存、写作 SSE、草案应用、质量检查和计费抽样。
7. 再次运行 `scripts/schema_fingerprint.sh`，确认切换没有改变数据库结构。

## 回滚

应用回滚只切换到已验证的旧镜像标签，不恢复或覆盖生产数据库。运行前设置 `ALLOW_ROLLBACK_DRILL=yes` 和 `ROLLBACK_IMAGE_TAG`，再执行 `scripts/rollback_drill.sh`。

只有在确认数据本身损坏且已有停机窗口时，才允许把备份恢复到独立验证库。`scripts/restore_verify.sh` 会拒绝验证库地址与生产地址相同；它不是生产数据库恢复命令。

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
