# LangGraph 兼容回退执行记录

日期：2026-09-13

状态：首轮发布成功，但线上只读验收发现 V1 查询 500；新任务已重新关闭，修复与复验中。未删除任何业务记录。

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
- Web 类型适配后 typecheck 通过；完整 Web 测试初次有 7 个旧 V2 前台静态断言失败，后续已按回退需求修正。
- Mac JDK 21、真实 Testcontainers PostgreSQL／Redis 完整 verify 初次：Core 1213 项，0 断言失败、
  2 错误、4 跳过。错误为旧请求幂等重放被会话忙拦截，以及未改动视频探针的 1 秒夹具超时；未宣称全量通过。
- 旧请求幂等问题已作最小修复，并在同一隔离环境重跑通过；该阶段尚未改变生产配置。

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

### 首次发布流水线

- 候选 `56f35dcf` 已通过 CI 的 Java、API 契约及 Web 测试，但 Python 全量为 3575 通过、2 跳过、1 失败，
  因此自动部署被跳过，生产没有切换。
- 失败来自 RAG 联调测试的 `SimpleNamespace` 夹具遗漏新增 `legacy_langgraph=false` 字段；
  本地复现同一异常后补齐夹具，不修改生产实现、不删除断言，再运行全量验证。

### 正式发布候选与维护窗口

- 最终候选 `31b48463f39f2876e2b7d6f1f2a4991e6d956c98`，CI 运行
  [34732654843](https://github.com/chimeiwang/Smart-Novel-Gen-nie/actions/runs/34732654843)。
  CI 的完整 Maven、公共契约、Web/API client、Python、Ruff、Mypy、typecheck、lint 和 build 全部通过。
- Linux CI Python 为 3576 通过、2 跳过，Mypy 为 131 源文件通过；本地完整 E2E 单测目录 355 通过。
- Windows 额外全量 Python 为 3530 通过、35 跳过、13 失败；失败集中于既有 shell 探针／密钥脚本的
  子进程文本解码，相关文件未在本次修改。此结果不记为通过，也未为其放宽生产测试。
- 02:10 UTC 增补 `v2-before.json`：WorkflowRun 102、Step 178、Event 1781，以及 Evidence、
  Evaluation、BillingReservation、ReviewArtifact／Revision／Evaluation 共 10 表全量摘要。
- 维护窗口内持有 `.inkforge-production.lock`，将运行 Core 改为
  `schemaReady=true / route=off / V1fresh=false`，Core 和 Nginx 重启健康。
- 02:32 UTC `route-off-drain` 和 `verify-drain` 均通过；全部 17 项阻断指标为 0，
  `v1DrainZero=true / v2Converged=true`。证据为备份目录内 `drain-before-deploy.json`。
- 02:41 UTC 首轮自动部署成功，schema 与 Compose smoke 通过；三业务镜像均为 `31b48463`。
- 02:44 UTC 开放 V1 后，以已有隔离验收作品启动只读 `review_chapter`，
  Run 为 `cmtz7npvball6cpeniwg9oglw`，显式 `engineVersion=1`，稳定请求标识为
  `langgraph-rollback-20260913-readonly-review-01`，没有批准任何候选。
- 随后的公开 GET 返回 500，requestId `022bbd61-1fbe-4e36-945d-eed97c367e13`。
  Java 日志确认全字段查询误选了不存在的 `ReviewArtifact.videoEpisodeId`；不是正文丢失。
  已在维护锁内重新关闭 V1 新任务，保留原 Run 对账，不换标识重发。
- `content-after-first-deploy.json` 的 24 表、`v2-after-first-deploy.json` 的 10 表与切换前逐表完全一致。
- 新增仅供隔离库初始化的缺列夹具；旧镜像真实复现 V1 GET 500，报告
  `output/production-schema-red/report.json`，测试容器、网络、卷零残留。
- 普通写作、审核和中短篇的全字段查询改为显式 19 个非视频字段；保留完整候选、Diff、来源、revision、
  悲观锁及既有归属条件。独立复核无阻断，不改变生产 schema 或生成代码。
- 修复后完整 Maven 于 11:04:25 +08 通过，Core 1218（4 跳过）、auth 11、contracts 5、CLI 147，
  零失败／错误。新增缺列 GET/list 回归与字段完整性测试通过；E2E 单测目录 356 通过，Ruff 通过。
- 第一次修复镜像联调发生 `RemoteProtocolError`，保留失败报告，不归为通过；完整 Maven 结束后复用
  同一镜像单独重试，03:06 UTC 闭环通过，报告 `output/production-schema-green-retry/report.json`。
  已证 `productionVideoEpisodeColumnAbsent=true`、真实 `list_outline_summary`、V1 等待作者确认、
  采用后 `outcome.state=succeeded`、正文精确一致、大纲未变、清理零残留。此联调仍使用 Fake Provider。
- 原生产只读任务的数据库诊断显示 `phase=completed / command=succeeded`，没有重复发起；
  观察器因 GET 连续 500 返回 `WATCH_CORE_UNREACHABLE`，修复上线后须用原 Run 公共 GET 再对账。
