# Windows 本地开发数据库实施计划

> **执行要求：** 保持最小实现；测试先行；不建设通用数据管理平台。

**目标：** 安装并启动本机 PostgreSQL/Memurai，把 .env.local 切到本地，并让 npm run dev 按需启动数据服务。

### 任务 1：准备本机数据服务

- 使用现有 Conda 在 %USERPROFILE%\.conda\envs\inkforge-data 安装 PostgreSQL 16.9、pgvector 0.8.0。
- 初始化 %LOCALAPPDATA%\InkForge\postgres\data。
- 创建本机 PostgreSQL 用户、数据库和 Memurai 配置。
- 更新 .env.local 为本地连接，秘密不写入 Git。

### 任务 2：接入最小启动脚本

- 新增 scripts/setup-local-data.mjs，负责仅首次初始化，不覆盖已有本地库。
- 新增 scripts/ensure-local-data.mjs，负责本地 URL 校验、健康检查和按需启动。
- 修改 scripts/dev.mjs，在三个应用进程创建前调用 ensure。
- 修改 package.json，增加 data:setup 和 data:start。
- 先写 Node 测试，覆盖父环境远程值被文件值覆盖、已运行跳过、未运行启动和错误端口拒绝。

### 任务 3：初始化本地空 schema

- 用现有远程 DATABASE_URL 执行 pg_dump --schema-only，只读导出结构，不导出表数据。
- 把结构写入本地空数据库，不复制远程 PostgreSQL 数据或 Redis。
- 核验 schema 指纹，并确认用户、小说、任务和 Outbox 表均为空。
- schema 文件保存在 Git 忽略目录，命令和日志不打印密码。

### 任务 4：真实启动验收

- 数据服务停止时运行 npm run dev，确认先启动 PostgreSQL/Memurai。
- Ctrl+C 后确认数据服务继续运行。
- 再次启动确认不重复创建实例。
- 验证 Web、Core、Agent 健康，在本地注册用户并创建新小说。
- 运行相关 Node/Python 测试、typecheck、lint，审查 Git 差异后提交。
