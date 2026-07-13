# GitHub Actions Python 三服务部署迁移规格

## 背景

Python 后端迁移已经删除 Prisma、根目录单体 `Dockerfile` 和 `docker-compose.yml`，但 `.github/workflows/build.yml` 仍执行 `npm run db:generate`，并继续构建和上传旧单体镜像。结果是 GitHub Actions 在 CI 阶段立即失败；即使只替换生成命令，部署阶段也会因为旧文件路径不存在而继续失败。

## 目标

- CI 只使用当前 Node.js、Python 3.12、uv、FastAPI 和 OpenAPI 客户端入口。
- OpenAPI 生成器在 Windows 使用 Python Launcher，在 Linux Runner 直接使用 uv，不依赖单一平台命令。
- CI 覆盖 OpenAPI 漂移、Web 测试、Python 测试、Ruff、Mypy、TypeScript、ESLint 和 Next.js 构建。
- GitHub Runner 构建 `web`、`core-api`、`agent-service` 三个带提交哈希标签的镜像，并通过 SSH 上传到生产服务器。
- 生产服务器只加载预构建镜像并执行 `infra/compose.yaml`，不得在 2 核 2 GB 服务器现场构建依赖。
- 服务器缺少 Docker、Git、`.env`、四个服务密钥、现有 PostgreSQL 数据卷配置或其他生产前置条件时，部署必须明确失败，不得自动创建数据库、生成替代密钥或修改 schema。

## 非目标

- 不修改 PostgreSQL schema，不执行迁移、建表或初始化 SQL。
- 不把生产 `.env`、SSH 私钥、服务私钥或模型密钥传回 GitHub 日志。
- 不在本轮自动清理旧单体容器或删除生产数据卷。
- 不绕过 GitHub Environment 的生产密钥和变量控制。

## 设计

### CI 门禁

工作流使用当前稳定主版本的 `actions/checkout`、`actions/setup-node`、`actions/setup-python` 和 `astral-sh/setup-uv`。Node 依赖使用 `npm ci`，Python 依赖使用 `uv sync --frozen --all-packages --group dev`。所有检查都调用根目录已有命令或项目规定的 uv 命令，不恢复任何 Prisma 脚本。

### 镜像传递

部署 Job 设置 `INKFORGE_IMAGE_TAG` 为当前提交 SHA，执行：

```bash
docker compose --env-file .env.example -f infra/compose.yaml build web core-api agent-service
docker save inkforge-web:$INKFORGE_IMAGE_TAG inkforge-core-api:$INKFORGE_IMAGE_TAG inkforge-agent-service:$INKFORGE_IMAGE_TAG
```

镜像流经 gzip 和 SSH 传到服务器的 `docker load`，不写入仓库，不经过第三方镜像仓库。

### 远程部署

`scripts/deploy-production.sh` 在 `APP_DIR` 中获取指定提交，保留未跟踪的 `.env` 与 `infra/secrets`，验证 Docker Compose、配置文件和四个密钥均存在，然后以 `--no-build --wait` 启动生产编排。`INKFORGE_IMAGE_TAG` 由工作流显式传入，确保 Compose 使用刚上传的三镜像。

## 错误处理

- GitHub Runner 的代码检查或镜像构建失败：修复仓库内原因后重新推送。
- SSH 连接、服务器工具、服务器配置、服务密钥、数据卷或容量不足：停止自动修复，报告 GitHub Actions 中的直接证据，等待用户处理服务器。
- Compose 服务健康检查失败：读取对应部署日志；若原因属于镜像或仓库代码则修复，若属于服务器配置或外部数据库则停止并报告。

## 验收

- 架构测试证明工作流不再包含 `db:generate`、根目录 `Dockerfile` 或 `docker-compose.yml`。
- 本地相关 pytest、Ruff、Mypy、Web 测试、TypeScript、ESLint、OpenAPI 检查和 Next.js 构建通过。
- GitHub Actions 的 CI Job 成功。
- Deploy Job 成功，且页面显示整个 `CI and Deploy` 工作流成功；若服务器缺少前置条件，则以明确错误停止并报告。
