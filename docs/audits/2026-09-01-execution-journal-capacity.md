# execution journal Redis 容量与恢复演练

日期：2026-09-01

范围：只验证独立 execution journal Redis、AOF rewrite、终态压缩和重启恢复；未访问或修改任何真实环境。

## 静态容量边界

- execution Redis 容器上限为 128 MiB，`maxmemory` 为 32 MiB，`noeviction`；
- 以一次 AOF rewrite 最坏复制完整 32 MiB live dataset 计算，`2 × 32 + 64 = 128 MiB`。额外
  64 MiB 留给 Redis 基线、AOF rewrite/write buffer、allocator 碎片和页缓存；
- `used_memory >= 90% × maxmemory`、任意历史 eviction、AOF 状态异常、callback rejected 或 pending
  backlog 越界都会关闭新 provider 副作用；终态重放和精确取消不占新工作 admission；
- 已送达终态原子删除完整 `terminal_payload`，重建为 listpack 幂等 tombstone。真实 Redis 测试用大于
  512 KiB 的完整终态验证压缩后单 key `MEMORY USAGE SAMPLES 0 <= 2 KiB`，且压缩比大于 50 倍；
- 按 2 KiB/tombstone、2 MiB Redis 基线保守计算，90% 门限内只保存 delivered tombstone 时至少容纳
  `(0.9 × 32 MiB - 2 MiB) / 2 KiB = 13,721` 条，即 24 小时持续约 9.5 条/分钟。pending/rejected
  仍保存完整终态并永久保留，不能计入该 delivered-only 容量；任何流量或输出预算超过该边界前必须扩容或迁移
  journal，不能改成淘汰策略。

## 隔离容器压力与重启演练

使用 `redis:7.4-alpine`、uid/gid 999、只读根文件系统、无网络、0.10 CPU、128 MiB memory/swap 同上限、
独立临时卷和仓库 `execution-redis.conf`。演练结束后已删除临时容器和卷。

- 写入 19,992 条与 delivered journal 字段同形的 tombstone；
- 数据集达到 `used_memory=27.91 MiB`，即 Redis 32 MiB 上限的 87.2%；
- 在该水位手工触发 `BGREWRITEAOF`，同时原地修改全部 19,992 条记录以制造 CoW；
- rewrite 后容器观测内存为 45.98 MiB / 128 MiB，`aof_last_bgrewrite_status=ok`、
  `aof_last_write_status=ok`、`evicted_keys=0`、`OOMKilled=false`、无自动重启；
- 显式重启后 `DBSIZE=19,992`、AOF 加载完成、写状态仍为 `ok`，未丢记录。

真实 Redis pytest 还以 `appendonly yes + appendfsync always + aof-load-truncated no + noeviction` 跑过
全部 journal Lua，包括 accept/start/provider-attempt/terminal、原子 claim/lease、retry、rejected、delivered
压缩和 delivered 后换 fence 幂等收敛。

## 尚未解除的生产门禁

当前 Compose 六个容器的 memory limit 合计 1,696 MiB、CPU limit 合计 1.75；2 GiB 主机只剩 352 MiB
供 Linux、Docker daemon、宿主机 PostgreSQL 和其他页缓存使用。本机 Docker 环境为 10 CPU / 8 GiB，无法证明
完整 Compose 在真实 2 CPU / 2 GiB 宿主机上的 OOM、抖动和 30～60 分钟稳定性。因此正式放量前仍必须在同形
2 CPU / 2 GiB 预发布机运行完整 Compose、宿主 PostgreSQL 和 provider-like 并发压测，检查所有容器
`OOMKilled/restart_count`、PostgreSQL 内存、AOF rewrite 峰值、p95/p99 延迟与 readiness；在该门禁完成前，
资源基线只能判定为“execution Redis 单容器通过，整机未证明”，不能宣称满足生产 2 核 2 GB 基线。

另一个独立阻断是 PostgreSQL 时间点恢复：delivered tombstone 最短只保留 24 小时，若 Core 数据库恢复到更旧快照，
可能重新出现一个 journal 已过期但供应商早已执行/计费的 running Step。`scripts/backup.sh` 已让每份新备份携带并校验
`recovery-boundary.meta`，明确 PostgreSQL 恢复前必须先在当前 execution Redis 写入持久 quarantine；但仓库没有、
也未获授权提供可直接覆盖生产 PostgreSQL 的恢复命令。因此任何 Core 数据库生产恢复仍是人工阻断流程：先停 Agent
新执行，写 quarantine 并取得本地 `WAITAOF=1`，再恢复 Core 数据库，随后联合 Core callback/resultHash、账单和供应商
请求 ID 做具名对账，最后用报告 SHA 和精确令牌人工解除。未完成联合对账前不得恢复 provider 调用；24 小时 tombstone
不是跨数据库灾备保证。
