# ADR-004：Core 权威的耐久 Agent 执行内核

日期：2026-08-31

状态：已接受

## 背景

当前跨服务 LangGraph 与 Core 持久命令同时编排一条业务流程，造成多套状态权威、昂贵模型调用无法逐次恢复、
用户决定需要无意义的 Agent 恢复，以及前端长期看不到真实进度。生产数据表明队列受理通常不足两秒，主要时延
来自开放式多轮工具循环和超长 reasoning，而不是缺少 worker。

## 决策

1. Java Core 是唯一业务编排器；Python Agent 只执行一个有界、版本化 Step。
2. 复用并演进现有 `WorkflowRun/WorkflowStep`，不再新增第三套 Run/Step 概念。
3. 新增不可变 Evidence、耐久 Event 和证据化 Evaluation；PostgreSQL 是唯一业务权威。
4. 每个昂贵模型调用对应一个 Step；协议纠正、Reviewer 和返工都是独立 Step。
5. 用语言中立 Operation Catalog 统一 Java、Python 和 TypeScript 的操作、证据、Schema、审核、应用和预算策略。
6. 新写作路径不使用跨服务 LangGraph、开放式业务工具循环或模型提交工具。
7. `ReviewArtifact`、不可变 revision、Core 正式应用事务、服务身份和计费边界继续保留。
8. Redis 只承担唤醒、限流、短期缓存和重放保护，不决定 Run、Step、Event 或结果。
9. 新旧引擎按新建 Run 单选路由；不影子调用、不双写，旧任务只由旧引擎收敛。

## 理由

- 单一状态机可以证明恢复、取消、用户决定和终态；
- 一个模型调用一个持久 Step，把最大不可恢复计费工作限制为一次调用；
- Core 冻结 Evidence 后，生成、Reviewer 和返工不会读取不同版本的作品；
- 固定流水线和预算消除无界工具轮次、五角色扇出和隐藏自动重写；
- 复用已有通用 Run/Step 与 ReviewArtifact，比继续扩展 WritingTask 或另建平行系统更少产生长期概念债务；
- 账号/小说 allowlist 可以在不让同一 Run 双写的情况下完成生产 canary。

## 后果

- 需要具名 PostgreSQL 迁移和新的 Core/Agent 内部契约；
- Java Core 增加调度、租约、Evidence 和 Event 职责；
- Python Agent 删除写作业务状态，保留 Provider、模型 Profile、用量和执行能力；
- 公共 API 在迁移期需要 V1/V2 查询适配，但新内部模型只有 V2 规范命令；
- 旧 LangGraph 任务必须先排空，不能直接转换 checkpoint；
- 生产发布必须增加真实供应商预发布、指定账号 canary、观察窗和独立回滚能力。

## 被否决方案

- 继续在现有 LangGraph 上补事件和 checkpoint：仍有双重编排与无界工具循环；
- 为五个角色拆微服务：增加部署和一致性成本，不能解决权威状态问题；
- 新建 `AgentRunV2` 平行表：会形成第三套 Run/Step 领域概念；
- 使用 Redis Stream 作为业务 Event 权威：TTL、清空和网络故障无法满足长期恢复；
- 直接全量生产切换：真实供应商协议和长任务恢复风险无法由 fake provider 测试覆盖。
