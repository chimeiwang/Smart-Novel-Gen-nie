# Durable Agent 发布前现场检查

时间：2026-09-06 07:52（北京时间）。状态：发布尚未完成，等待现有旧任务处置及账号会话授权。

## 已证明的状态

- 本次业务候选为 `ef7e702`，21 个 Operation 仓内验收完成；分支仍为 `codex/durable-agent-execution`。
- GitHub `main` 与线上源码均为 `a37d87373ce9f10ed6c41dca9ff2a74956b76718`；最近一次相应 CI／部署成功，
  但它不包含当前候选。现场 Web、Core、Agent 镜像标签与该提交一致。
- 现场只有 `inkforge` 一套 Compose，含 Nginx、Web、Core、Agent、普通 Redis；尚无 execution Redis。
  开发库 86 张表、正式库 70 张表，均未发现 V2 engineVersion 列或 BillingReservation 表。
- 正式库通过修复后的隔离探针实时读取，精确命中旧版冻结契约在“视频关闭、手机号开启”下的投影，
  指纹为 `b5d2c319303f1ca52d411b8f986aa98a5d48168338c75c65d675d23968c22c78`。
- 服务器总内存约 1771 MiB、无 swap；首次检查可用约 354 MiB。因此没有额外在生产主机并起开发全栈，
  也没有把本机独立探针的内存结果当作完整 2 核 2 GiB 容量验收。

## 检查引入的一次重启及修复

首次按旧方式在活动 Core 容器中运行结构守卫时，额外 JVM 与业务进程共用 448 MiB 内存，触发容器
内存超限并使 Core 自动重启一次。该影响由本次检查引起，不能归咎于 Agent 候选代码。

随后已确认 Core 恢复健康，并完成独立受限探针修复，详见
`docs/specs/2026-09-06-schema-probe-memory-isolation.md`。用修复后的方式再次只读检查生产时，
Core 的实例、镜像与启动时间不变，重启计数保持 1，六项 readiness 全部通过，未留下探针容器。

## 尚待用户决定或完成

1. 线上旧 WritingTask 有 41 个 `awaiting_user_review` 和 7 个 `idle`，没有观察到 active/waiting_call
   或待投递命令、Outbox。指定账号占 18 个待审、5 个 idle；其他账号占 23 个待审、2 个 idle。
   现有迁移流程把这些未结束事实纳入 drain。没有自动取消、丢弃候选或直接改表；已询问用户保留还是
   允许处置。该数字只是现场快照，任何后续操作前必须重新核对精确任务 ID、归属和状态。
2. 生产 Operator 固定账号配置与指定账号一致，但 `auth.whoami` 在 macOS 原生
   `SecKeychainFindGenericPassword` 处等待，尚未发出网络请求。按生产 Skill 要求等待用户手动放行／
   解锁，不读取令牌或把密码改成命令行输入。没有把配置的用户名当作已通过服务端身份验证。
3. 真实开发库迁移／回滚／contract、低额度真实供应商验收、正式库联合备份和迁移、生产 canary 与放量
   观察均未完成；活动 Skills、固定 CLI 安装包和线上服务也尚未更新。

## 后续顺序

先明确旧任务处置并取得现有账号会话；继续原 `docs/DURABLE_AGENT_V2_ROLLOUT.md` 的开发库、兼容镜像、
联合 drain、备份、具名迁移、交集 allowlist 和新建隔离作品 canary。当前个人项目发布范围已经移除
Controller／OIDC 要求，不重新把它们作为门禁。生产视频保持关闭。
