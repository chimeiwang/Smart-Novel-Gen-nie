# 服务器开发数据副本规格

## 状态

- 日期：2026-08-02
- 状态：用户已确认
- 原则：本地应用与服务器应用使用不同的数据空间，但数据服务都运行在服务器上。

## 目标

- 在服务器 PostgreSQL 中把 `novelwriter` 一次性完整复制为 `novelwriterdev`。
- 把本地开发原先连接的服务器 Redis DB 0 一次性完整复制到同一实例的 DB 1。
- 本地 `.env.local` 只切换 `DATABASE_URL` 和 `REDIS_URL`，分别指向开发数据库和 Redis DB 1。
- `npm run dev` 只启动 Web、Core API 和 Agent Service，不安装、启动或管理本机 PostgreSQL/Redis。

## 隔离边界

- 复制完成后不做自动同步；生产库与开发库各自独立写入。
- 不修改服务器生产应用的环境变量、Compose 或连接地址。
- PostgreSQL 开发库不存在时才创建；Redis DB 1 必须为空才允许首次复制。
- 本地配置继续由 Git 忽略，不提交数据库、Redis 或服务器密码。
- 服务器生产 Compose 内部 Redis 与宿主机对外 Redis 是两个实例；本次复制的是本地开发此前使用的宿主机 Redis DB 0，生产 Compose 内部 Redis 不变。

## 验收

- `novelwriter` 与 `novelwriterdev` 的公共表数量、结构指纹和逐表行数一致。
- 服务器对外 Redis DB 0 与 DB 1 的键集合、类型和逻辑值一致。
- 本地 `.env.local` 的 PostgreSQL 数据库名为 `novelwriterdev`，Redis 数据库编号为 1。
- 本地运行 `npm run dev` 后，Web、Core API 和 Agent Service 均健康。
