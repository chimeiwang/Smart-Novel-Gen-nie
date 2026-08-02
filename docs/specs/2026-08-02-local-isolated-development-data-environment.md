# Windows 本地开发数据库规格

## 状态

- 日期：2026-08-02
- 状态：用户已纠正并确认
- 原则：只解决当前开发机的本地数据启动，不建设通用数据管理平台

## 目标

- 在 Windows 本机运行 PostgreSQL 14.23、pgvector 0.8.0 和 Memurai。
- PostgreSQL 使用远程数据库的一次性只读导出作为本地初始数据；不复制远程 Redis。
- .env.local 的 DATABASE_URL 和 REDIS_URL 改为 127.0.0.1。
- npm run dev 启动前检查两个本地数据服务：已健康则复用，未启动则启动，然后照常启动 Web、Core 和 Agent。
- Ctrl+C 只停止三个应用服务，本地数据继续运行并保留数据。

## 实现

- PostgreSQL 使用本机已有 F:\ai\conda 创建 inkforge-data 环境，安装 PostgreSQL 14.23 和 pgvector 0.8.0。
- PostgreSQL 数据目录固定在 %LOCALAPPDATA%\InkForge\postgres\data。
- Memurai 使用 C:\Program Files\Memurai\memurai.exe，项目配置和数据目录放在 %LOCALAPPDATA%\InkForge\memurai。
- 一次性 setup 脚本负责初始化本地 PostgreSQL、生成本地密码、创建 Memurai 配置并更新被 Git 忽略的 .env.local。
- 第一次初始化后，使用本地 pg_dump 只读连接当前远程 PostgreSQL，再用 pg_restore 写入空的本地数据库。
- 启动脚本只做本地 URL 校验、健康检查和按需启动，不做快照版本管理、staging 换库、恢复 journal、任务状态机或远程 SSH 编排。
- 如果 5432 或 6379 已被占用但对应健康检查失败，立即报错，不杀进程。
- .env.local 中的数据库与 Redis 地址覆盖父终端同名变量，防止残留远程环境变量生效。

## 一次性数据检查

- 导出远程库前后不执行远程写入。
- 本地恢复完成后，先只读检查当前会被后台调度器领取的任务数量。
- 若实际数量为零，直接启动应用；若不为零，停止并报告具体类别，再只处理真实存在的数据，不预建通用隔离框架。

## 非目标

- 不复制远程 Redis、uploads 或日志。
- 不修改 PostgreSQL schema，不运行迁移或自动建表。
- 不提供生产级备份平台、重复恢复、崩溃回滚、Credential Manager、复杂 manifest 或通用进程状态机。
- 不修改生产服务和生产 Compose。

## 验收

- PostgreSQL 报告 14.23，vector 扩展报告 0.8.0。
- Memurai 可以使用 .env.local 中的本地密码 PING。
- .env.local 两个数据连接均为 127.0.0.1。
- 数据服务停止时运行 npm run dev 会先启动它们；数据服务已运行时不会重复启动。
- Web 43119、Core 8000、Agent 8001 均通过健康检查。
- 可以登录并打开现有小说 cmsab6kir4dtb9en83he6sdfj。
- Git 不包含 .env.local、本地密码、数据库文件或 dump。
