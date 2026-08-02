# 服务器开发数据副本实施计划

## 任务 1：建立服务器端副本

- 用 `pg_dump` 与 `pg_restore` 在服务器内复制 PostgreSQL，避免中断生产连接。
- 创建 `novelwriterdev`，恢复完成后核对公共表与数据。
- 确认服务器对外 Redis DB 1 为空，再把 DB 0 的键、值和 TTL 复制到 DB 1。

## 任务 2：切换本地开发配置

- 备份本地 `.env.local`。
- 只把 PostgreSQL 数据库名改为 `novelwriterdev`，把 Redis DB 编号改为 1。
- 撤销本机 PostgreSQL/Memurai 自动安装与启动代码，恢复 `npm run dev` 的三应用启动职责。

## 任务 3：验收

- 运行数据库结构指纹与逐表行数对比。
- 核对 Redis 键集合、类型和逻辑值。
- 运行相关测试、类型检查、Lint，并实际启动三个本地应用检查健康端点。
