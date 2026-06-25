# Smart Novel Gen

面向中文小说作者的本地创作工具，支持项目/章节管理、设定管理、文风画像、AI 续写、写作会话、质量检查、待审核草案和多 Agent 协作。

## 技术栈

- Next.js 16 + React 19 + TypeScript
- Prisma 6 + PostgreSQL
- LangChain / LangGraph / Zod
- OpenAI SDK 兼容接口，默认可接入 DeepSeek
- 原生 CSS 与 CSS 自定义属性

## 本地启动

```bash
npm install
cp .env.example .env
npm run db:generate
npm run dev
```

默认开发端口见 `package.json` 中的脚本配置。

## 环境变量

请基于 `.env.example` 创建本地 `.env`。不要提交真实密钥、数据库密码或生产配置。

常用变量：

- `DATABASE_URL`：PostgreSQL 连接地址
- `JWT_SECRET`：会话签名密钥
- `OPENAI_API_KEY`：OpenAI/DeepSeek 兼容 API Key
- `OPENAI_BASE_URL`：模型服务地址
- `OPENAI_MODEL`：模型名称

未配置真实模型 Key 时，部分 AI/Agent 能力会返回 Mock 内容或提示。

## 数据库

当前主数据库以 `prisma/schema.prisma` 的 PostgreSQL schema 为准。仓库中不包含本地数据库快照。

```bash
npm run db:generate
npm run db:migrate
```

生产或 PostgreSQL 专用命令以 `package.json` 为准。

## Agent 系统

Agent、写作流程、质量评审、草案审核和 LangGraph 编排的详细说明见：

- `AGENTS.md`
- `src/agents/AGENTS.md`
- `docs/AGENT_NOVEL_WRITING_ROADMAP.md`

