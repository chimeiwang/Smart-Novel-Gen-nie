# Windows 本地开发数据库规格

## 状态

- 日期：2026-08-02
- 状态：用户已纠正并确认
- 原则：只解决当前开发机的本地数据启动，不建设通用数据管理平台

## 目标

- 在 Windows 本机运行 PostgreSQL 16.9、pgvector 0.8.0 和 Memurai。
- PostgreSQL 不复制任何远程业务数据；Redis 也从空实例开始。
- .env.local 的 DATABASE_URL 和 REDIS_URL 改为 127.0.0.1。
- npm run dev 启动前检查两个本地数据服务：已健康则复用，未启动则启动，然后照常启动 Web、Core 和 Agent。
- Ctrl+C 只停止三个应用服务，本地数据继续运行并保留数据。

## 实现

- PostgreSQL 使用本机已有 F:\ai\conda 创建 %USERPROFILE%\.conda\envs\inkforge-data 环境；基础
  Conda 目录仅允许普通用户读取，不能把新环境建到 F:\ai\conda\envs。conda-forge 的 Windows
  pgvector 0.8.0 依赖 libpq 16.9，不能与 PostgreSQL 14.23 同环境安装，因此本地固定使用兼容组合
  PostgreSQL 16.9 + pgvector 0.8.0；生产 14.23 的只读导出恢复到本地 16.9。
- PostgreSQL 数据目录固定在 %LOCALAPPDATA%\InkForge\postgres\data。
- Memurai 使用 C:\Program Files\Memurai\memurai.exe，项目配置和数据目录放在 %LOCALAPPDATA%\InkForge\memurai。
- 一次性 setup 脚本负责初始化本地 PostgreSQL、生成本地密码、创建 Memurai 配置并更新被 Git 忽略的 .env.local。
- 仓库没有当前 schema 的空库初始化脚本。第一次初始化只用 pg_dump --schema-only 从远程读取表、枚举、
  索引和扩展定义，再写入本地空库；不导出任何表数据，此后没有同步关系。
- 启动脚本只做本地 URL 校验、健康检查和按需启动，不做快照版本管理、staging 换库、恢复 journal、任务状态机或远程 SSH 编排。
- 如果 5432 或 6379 已被占用但对应健康检查失败，立即报错，不杀进程。
- .env.local 中的数据库与 Redis 地址覆盖父终端同名变量，防止残留远程环境变量生效。

## 一次性结构初始化

- schema-only 导出只读远程系统目录和结构，不执行远程写入。
- 本地初始化完成后所有业务表均为空，不存在远程小说、用户、任务、计费或 Outbox。
- 本地用户、小说和任务都从本地开发流程重新创建。

## 非目标

- 不复制远程 PostgreSQL 业务数据、Redis、uploads 或日志。
- 不修改 PostgreSQL schema，不运行迁移或自动建表。
- 不提供生产级备份平台、重复恢复、崩溃回滚、Credential Manager、复杂 manifest 或通用进程状态机。
- 不修改生产服务和生产 Compose。

## 验收

- PostgreSQL 报告 16.9，vector 扩展报告 0.8.0。
- Memurai 可以使用 .env.local 中的本地密码 PING。
- .env.local 两个数据连接均为 127.0.0.1。
- 数据服务停止时运行 npm run dev 会先启动它们；数据服务已运行时不会重复启动。
- Web 43119、Core 8000、Agent 8001 均通过健康检查。
- 可以在本地注册用户、创建一部新小说并读取它。
- Git 不包含 .env.local、本地密码、数据库文件或 dump。
