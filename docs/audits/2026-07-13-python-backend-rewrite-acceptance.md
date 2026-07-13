# Python 后端迁移最终验收审计

验收日期：2026-07-13

验收分支：`main`，由 `codex/python-backend-rewrite` 快进合并

状态：本地代码迁移验收通过；生产 Docker 切换演练不在本轮验收范围内，仍须在独立部署环境执行。

## 自动化验证证据

以下命令均在迁移工作树根目录执行，退出码均为 `0`。

| 验收项 | 命令 | 结果摘要 |
| --- | --- | --- |
| Python 全量测试 | `.\.venv\Scripts\python.exe -m pytest -q` | 823 passed，3 skipped；1 条第三方弃用警告 |
| Python 风格检查 | `.\.venv\Scripts\python.exe -m ruff check .` | 全部通过 |
| Python 类型检查 | `.\.venv\Scripts\python.exe -m mypy apps/core-api/src apps/agent-service/src packages/service-contracts/src packages/service-auth/src scripts tests` | 188 个源文件通过 |
| Web 与 API Client 测试 | `npm run test:web` | 7 项通过 |
| TypeScript 类型检查 | `npm run typecheck` | Web 与 API Client 均通过 |
| 前端 Lint | `npm run lint` | ESLint 通过 |
| OpenAPI 客户端漂移检查 | `npm run api:check` | 通过，无生成客户端漂移 |
| Next.js 生产构建 | `npm run build` | 构建通过；路由清单未出现业务 API Route |
| Playwright 本地端到端 | `$env:E2E_BASE_URL='http://127.0.0.1:43119'; npm run test:e2e` | 6 项通过，耗时 1.2 分钟 |

## 合并后复验

迁移分支快进合并到 `F:\code\inkForge` 的 `main` 后，在根仓库重新建立 Python 与 Node 依赖并再次执行门禁：

- Python 全量测试：824 passed，3 skipped；新增的 OpenAPI 换行符架构测试包含在内。
- Ruff、Mypy（188 个源文件）、Web 与 API Client 7 项测试、TypeScript、ESLint、OpenAPI 漂移检查和 Next.js 生产构建全部通过。
- 从根仓库启动 Next.js、Core API 和 Agent Service，三个健康检查均为 HTTP 200。
- 在合并后的 `main` 再次执行六个 Playwright 主流程，6 项全部通过，耗时 1.2 分钟。

根仓库位于 F 盘，本机由 uv 创建的 `F:\code\inkForge\.venv\Scripts\python.exe` 在短时间内连续作为子进程启动时会被 Windows 返回 `WinError 5`。相关四个子进程用例单独执行全部通过；全量复验最终使用同一 CPython 3.12 基础解释器从 C 盘启动，显式加载根仓库 `.venv` 依赖和根仓库源码后通过。该说明只记录本机启动器行为，不把环境错误写成代码通过或代码失败。

根仓库 `npm ci` 同时报告 2 个中等级依赖审计告警。本次迁移没有执行可能引入破坏性升级的 `npm audit fix --force`；该告警不属于 Python 后端迁移功能门禁，后续依赖升级需单独评估。

## GitHub Actions 部署链路修复复验

首次推送后的 `CI and Deploy #24` 在旧的 `npm run db:generate` 步骤失败，证明 `.github/workflows/build.yml` 没有随 Prisma 和旧单体 Docker 发布物一起迁移。修复后，本地复验结果如下：

- GitHub 工作流与部署脚本架构测试：4 项通过；全部架构测试：38 项通过。
- Python 全量测试：828 passed，3 skipped；Ruff 与 Mypy（177 个源文件）通过。
- Web 与 API Client：7 项测试通过；TypeScript、ESLint、OpenAPI 漂移检查和 Next.js 生产构建通过。
- GitHub Actions 工作流 YAML 解析、Git Bash 部署脚本语法检查通过。
- 本机未安装 Docker，因此提交哈希三镜像的真实构建、SSH 上传和服务器 `--no-build --wait` 启动必须以推送后的 GitHub Runner 与 Deploy Job 结果为准，不能在本地验收记录中提前声明成功。

## 本地三服务证据

使用根目录 `npm run dev` 启动三个真实本地进程，并使用 `MODEL_PROVIDER=fake` 避免调用真实模型和产生模型费用。

| 服务 | 地址 | 结果 |
| --- | --- | --- |
| Next.js | `http://127.0.0.1:43119/login` | HTTP 200 |
| Core API | `http://127.0.0.1:8000/api/v1/health/ready` | HTTP 200；configuration、database、database_schema、redis 均为 ok |
| Agent Service | `http://127.0.0.1:8001/internal/v1/health/ready` | HTTP 200；model_provider 为 ok |

## Playwright 主流程证据

以下六个场景使用单个 Chromium worker 串行执行，并且全部通过：

1. 用户可以注册、退出并重新登录。
2. 用户可以维护设定、大纲、参考资料和文风画像。
3. 用户可以创建小说并自动保存章节。
4. 用户可以运行质量检查并查看模拟模型零扣费摘要。
5. 模拟模型可以完成写作会话和草案应用。
6. 用户可以丢弃待确认草案。

本次运行没有失败，因此没有需要归档的失败截图或 trace。测试通过正式公共 API 创建随机用户及其专属小说、章节、草案和质量检查数据；该写入已经用户授权，未执行 DDL、迁移、自动建表或对既有业务记录的修改。

## 架构与删除证明

执行：

```powershell
rg -n "prisma|@prisma|DATABASE_URL|use server" apps/web/src apps/web/package.json --glob '*.ts' --glob '*.tsx' --glob '*.json'
```

结果：无匹配。`apps/web` 未发现 Prisma、数据库连接、业务 Server Action 或业务 API 后端残留。

执行：

```powershell
git status --short -- prisma apps/core-api/src/inkforge_core/db/schema-contract.json
```

结果：无输出。Prisma 目录和数据库结构契约没有工作树修改；Core readiness 的 `database_schema=ok` 同时证明当前数据库只读结构校验通过。

Agent Service 的架构测试、全量测试和静态检查均通过；其业务数据读取和草案提交继续经 Core `/internal/v1/**` 网关完成，没有引入数据库驱动或 `DATABASE_URL` 访问。

## 已接受限制

用户选择首版方案 A：不实现跨服务草案局部 patch。复审要求修改时，`CoreArtifactPort.apply_patch()` 明确拒绝局部 patch 路径，工作流退化为完整草案重新生成。该限制增加返工成本，但不绕过 ReviewArtifact、用户确认或 Core 正式应用边界。

## 明确排除项

当前 Windows 环境没有 Docker 命令，因此没有把以下生产现场事项记录为已通过：

- `infra/compose.yaml` 的实际镜像构建、全服务健康和 Nginx 冒烟；
- 独立验证数据库的备份恢复；
- Agent 运行中重启与 Redis 丢键接管；
- 上一版 Python 三服务镜像回滚；
- 2 核 2 GB 环境连续 30 分钟稳定性观察；
- Compose 环境下的完整 Playwright 流程。

这些事项不阻塞本地代码迁移交付，但在正式生产切流前必须按照 `docs/PYTHON_BACKEND_CUTOVER.md` 在独立测试数据库和具备 Docker 的部署环境执行。任何失败都应阻止生产切流，且不得通过修改 PostgreSQL schema 绕过。
