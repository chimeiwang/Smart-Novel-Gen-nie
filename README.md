# InkForge（墨铸）

面向中文小说作者的创作工作台，提供项目与章节管理、设定、大纲、文风画像、参考资料、AI 写作会话、质量检查、待审核草案和多 Agent 协作。

## 当前技术栈

- Next.js 16、React 19、TypeScript：页面、SSR/SEO 和浏览器交互。
- FastAPI、Pydantic、SQLAlchemy 异步接口：核心业务 API。
- LangGraph Python、LangChain Core：Agent 编排和模型运行时。
- PostgreSQL、pgvector：现有主数据库，结构禁止在本重构中修改。
- Redis：运行队列、SSE 短期重放、限流和服务令牌重放保护。
- Nginx、Docker Compose：单机生产部署。

## 目录

```text
apps/web                 Next.js 前端
apps/core-api            Python 核心接口服务
apps/agent-service       Python 智能体服务
packages/api-client      OpenAPI 生成的前端客户端
packages/service-auth    服务身份共享库
packages/service-contracts 服务间 Pydantic 契约
infra                    生产镜像、Nginx 和 Compose
```

## 开发验证

首次本地启动前准备 PostgreSQL 和 Redis，然后执行：

```bash
cp .env.local.example .env.local
uv sync --frozen --all-packages --group dev
uv run python scripts/generate_service_keys.py --output-dir infra/secrets
npm install
npm run dev
```

Windows PowerShell 使用 `Copy-Item .env.local.example .env.local`。填写 `.env.local` 中的现有 PostgreSQL 地址后，`npm run dev` 会同时启动 Next.js `43119`、Core API `8000` 和 Agent Service `8001`。本地默认使用 fake 模型，不调用外部模型，也不产生计费。

本地启动不会创建数据库、执行迁移或修改 schema；PostgreSQL 必须已经具备项目当前结构。

### 静态验证

```bash
npm install
npm run typecheck
npm run lint
npm run test:web
npm run build

uv sync --frozen --all-packages --group dev
uv run pytest
uv run ruff check .
```

## 生产部署

1. 基于 `.env.example` 创建 `.env`，填写现有 PostgreSQL 地址和数据卷名称。
2. 运行 `uv run python scripts/generate_service_keys.py --output-dir infra/secrets` 生成服务密钥。
3. 运行 `docker compose -f infra/compose.yaml up --build -d`。

Nginx 是唯一公网入口。Agent Service 不加入数据库网络，也不会接收 `DATABASE_URL`。Compose 只挂载已有 PostgreSQL 数据卷，不包含初始化 SQL 或迁移。

架构与需求入口见 `DOCS.md`、`AGENTS.md`、`apps/agent-service/AGENTS.md` 和 `docs/README.md`。
