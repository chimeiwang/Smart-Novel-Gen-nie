# Python 后端迁移验收审计

状态：代码迁移完成，生产现场验证待执行。

## 已有直接证据

| 验收项 | 证据 | 结果 |
| --- | --- | --- |
| Web 不含业务后端 | `tests/architecture/test_no_typescript_backend.py` | 通过 |
| Agent 不进入数据库网络 | `tests/architecture/test_compose_security.py` | 通过 |
| 只有 Nginx 发布端口 | `tests/architecture/test_compose_security.py` | 通过 |
| 容器资源不超过 2 核 2 GB | `tests/architecture/test_compose_security.py` | 通过 |
| Next.js 无 `/api` 路由 | `npm run build` 路由清单 | 通过 |
| 前端契约与类型 | `npm run api:check`、`npm run typecheck` | 通过 |
| 前端行为 | `npm run test:web` | 通过 |
| Python 静态质量 | Ruff、Mypy | 通过，最终结果以本提交验证记录为准 |
| Python 单元与集成测试 | `uv run pytest` | 通过，最终结果以本提交验证记录为准 |
| 数据库结构未被仓库修改 | schema 归档与只读 `schema-contract.json` | 代码层通过 |

## 尚未执行的生产现场证据

当前 Windows 环境没有 Docker 命令，也没有被授权连接或修改现有数据库，因此以下项目没有伪造为已通过：

- `docker compose config` 与镜像实际构建；
- Compose 全服务健康和 Nginx 冒烟；
- 独立验证库的备份恢复；
- Agent 运行中重启与检查点接管；
- 真实数据库切换前后指纹比较；
- 2 核 2 GB 连续 30 分钟压力观察；
- 完整浏览器端到端业务流程。

这些项目必须在独立测试数据库副本和安装 Docker 的部署机上按 `docs/PYTHON_BACKEND_CUTOVER.md` 执行。任何失败都阻止生产切换，但不改变“数据库 schema 不得修改”的约束。
