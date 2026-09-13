# LangGraph 兼容回退执行记录

日期：2026-09-13

状态：验证中；生产尚未切换，未删除任何业务记录。

规格：[兼容回退](../specs/2026-09-13-langgraph-aug29-compatible-rollback.md)。

## 工作区保全

- 原目录 `F:\code\inkForge` 保持原分支与未提交工作；先前切换前后状态及已跟踪差异 SHA-256 均为
  `4EAF91FD72F18634BC1C720A2FB27554B29AD850BCC2811E85C2790981713443`。
- 原始 8 月 29 日代码保留在 `codex/restore-20260829`，精确指向 `a37d8737`。
- 兼容发布在既有隔离目录的 `codex/restore-20260829-compatible` 分支实施，基于 `8eabd60b`。
- 先前未提交的 Java 发布审计保全在 stash `7bb451aba93d8298b84d1be0a8beb0160d2cea98`，没有删除。

## 生产只读基线与备份

- 2026-09-13 01:12 UTC：源码与三业务镜像均为 `8eabd60b`，健康。
- 实际 Core 开关为 `schemaReady=true / route=all / V1fresh=false`。
- `novelwriter` 结构状态为 `migrated-with-v2`；活动 V2 为 0。
- 01:29 后检查：数据库约 75 MB，服务器磁盘剩余 8.5 GB。
- 完整数据库、execution Redis 日志、部署环境与镜像清单已备份至服务器
  `/srv/smart-novel-gen/.langgraph-rollback-backups/20260913.hIDwZ1`；`pg_restore --list`、
  `redis-check-rdb` 与全部 SHA256SUMS 检查通过。敏感部署环境只保存在服务器受限目录，不进入仓库。
- 首次 pg_dump 因 postgres 无法穿过受限备份父目录失败；改由 root 打开归档输出流后成功，未放宽目录权限。
- 01:34 UTC 的 `content-before.json` 保存 24 张内容表逐行排序摘要，含 195 个小说、257 章、
  195 份总纲、101 个大纲节点；不打印正文内容、不修改数据。

## 本轮验证

- 原始旧版 Agent 图、Operation、Runtime、工具：286 项通过。
- 默认写作请求回退断言先失败（仍走 `buildNaturalRunRequest`），恢复旧入口后通过。
- Web 类型适配后 typecheck 通过；完整 Web 测试初次有 7 个旧 V2 前台静态断言失败，正在按回退需求收口。
- Mac JDK 21、真实 Testcontainers PostgreSQL／Redis 完整 verify 初次：Core 1213 项，0 断言失败、
  2 错误、4 跳过。错误为旧请求幂等重放被会话忙拦截，以及未改动视频探针的 1 秒夹具超时；未宣称全量通过。
- 旧请求幂等问题已有最小修复，正在同一隔离环境重跑；生产配置仍未改变。

### 发布前复核

- Web 373 项与 API client 3 项全部通过，typecheck、lint、生产 build 与 API 契约漂移检查通过。
- Agent 图、Operation、Runtime、工具及 Compose 安全测试 336 项通过；Ruff 全仓与 Mypy 131 源文件通过。
- 代码复核发现旧 resume key 被当作 start、信封请求被旧入口重建两项风险；两条新 PostgreSQL 回归先红，
  修复后重跑完整 Maven verify 于 09:58:57 +08 成功。旧 key 重放独立验证命令 kind 和 Novel 所有者。
- 首轮 Legacy Compose 在 post-V2 结构下通过真实 `list_outline_summary` 工具网关读取、V1 待审、
  显式采用和 completed；正式测试正文精确等于候选，大纲不变；容器、网络、卷零残留。
  该轮使用隔离 Fake Provider，不是生产模型质量验收；最后幂等补丁后的镜像再次联调也已通过，
  报告为 Mac 隔离目录 `output/legacy-langgraph-final/report.json`。
- 规格符合性和代码质量两阶段复核完成，两项 P1 已闭合；未因此放宽数据库或审核门禁。
- 最终完整 Maven：service-auth 11、service-contracts 5、Core 1215（4 跳过）、CLI 147，零失败／错误。
