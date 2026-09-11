# 正文复审输出格式故障排查与修复验证

日期：2026-09-11。状态：已完成隔离复现、代码修复和本地验证，尚未部署。

## 原生产记录

生产版本为 `b7fc243fe921fb8b524f45fe8318ee0a886cbc45`。Run
`cmtwv4pxq5d8tf8gqfjabsqti` 正文已完成，3,232 字符草案保留在
`cmtwv6w975d9jf8gqh1o9mk34` 的 revision 1。两个 Reviewer 失败后 Run 为 waiting_user。
一致性 Step `cmtwv6w9z5d9lf8gqdpky87ms` 为 schema_violation/type，编辑 Step
`cmtwv6wa25d9mf8gq89swkyvd` 为 schema_violation/maxItems。两者均未超 token 或时间预算。

原失败回复未保存；V2 不走 V1 人工日志 observer，Executor 日志遗漏安全 jsonPointer，
失败回调及 execution journal 也不保存该字段。因此旧 type 诊断无法从现存记录精确归因到字段。

## 隔离复现

在数据库外由服务器只读 PostgreSQL 取得原 Run 的 modelPolicyJson、Step input/budget、原 bundle
manifest 和完整 items，传入运行中 Agent 的独立诊断进程。按冻结 review evidencePolicy 构造并验证
EvidenceBundle，使用原输出 Schema、提示词哈希、模型、thinking disabled、100,000 总输出预算
和 75 秒调用超时。完整 user 消息使用与 Executor 相同的 canonical_execution_json_bytes。
每次调用独立，未写 Workflow 状态、账务、候选或正式内容；供应商诊断调用产生真实用量。

仅输出判定枚举、条数、字段类型、白名单路径和用量；不落盘或输出正文、推理、原回复、密钥。
两角色 user 消息 SHA-256 为
`2e71b8bcf6289db8b79f47585d15cbda3bd491acd656ce4c9857f4ecfffa193a`。

| 原提示词复现 | 输入 token | 输出 token | Schema 结果 |
| --- | ---: | ---: | --- |
| 一致性第 1 次 | 36,245 | 1,163 | 通过，issues_found，4 条 finding |
| 编辑第 1 次 | 36,240 | 1,521 | maxItems /findings：pass 同时带 7 条 finding |
| 一致性第 2 次 | 36,245 | 299 | 通过，issues_found，1 条 finding |
| 一致性第 3 次 | 36,245 | 819 | 通过，issues_found，2 条 finding |
| 一致性第 4 次 | 36,245 | 657 | 通过，issues_found，2 条 finding |
| 一致性第 5 次 | 36,245 | 610 | 通过，issues_found，2 条 finding |

六次均 finishReason=stop，合计输出 5,069 token，每次 cachedTokens=36,096。
编辑错误已在原冻结输入上精确复现；一致性 type 未复现，不能声称已找到其原始具体字段。

## 修复范围

- 两角色新增 v2 提示词/profile，明确任何问题对应 issues_found，pass/cannot_assess 必须配空 findings。
- 对齐 required-but-nullable 范围、可选 patch 省略、JSON 数字与证据 id/哈希引用要求。
- 输出 Schema、业务评审规则、预算、重试、调用数和已有草案均不改变；历史 v1 资产保留。
- V2 失败日志补充当前 Schema 白名单过滤后的 JSON Pointer，不记录未知键或字段值。
- 不实现自动格式纠错机制，不自动修改模型返回结论或删除 findings。

## 验证结果

仅替换 v2 system 提示词，原完整 user 消息、模型、预算、Schema 和来源保持不变，真实调用结果如下：

| v2 提示词验证 | 输入 token | 输出 token | 判定与条数 | 验收 |
| --- | ---: | ---: | --- | --- |
| 一致性第 1 次 | 36,452 | 2,336 | issues_found，8 条 | Schema、Finding 模型、证据引用通过 |
| 一致性第 2 次 | 36,452 | 1,052 | issues_found，4 条 | Schema、Finding 模型、证据引用通过 |
| 编辑第 1 次 | 36,457 | 1,254 | issues_found，5 条 | Schema、Finding 模型、证据引用通过 |
| 编辑第 2 次 | 36,457 | 13 | pass，0 条 | Schema、Finding 模型、证据引用通过 |

以上为有界诊断样本，不证明模型永远不会再次违反协议，也不能还原旧 consistency 的 type 字段。
两阶段共 10 次诊断调用，合计输出 9,724 token，未进入正式工作流或修改原 Run。

- Agent execution 全目录、DeepSeek Provider 与 Catalog 架构测试：771 passed、1 skipped；
  后续补齐旧 v1 首次派发兼容后，重新运行正文、Executor、专用格式回归和 E2E 控制测试，190 passed。
  两批有重叠，不能相加作为唯一测试数。既有 Starlette/httpx 弃用警告不影响通过。
- 全仓 Ruff、294 个源文件 Mypy、执行资产派生检查均通过。
- Java 相关 verify：ExecutionRegistryTest 17 项、HistoricalIntentExecutionPlanSnapshotTest 2 项通过，
  Reactor BUILD SUCCESS。Windows checkout 的历史 fixture 末尾被转换为 CRLF，首次 raw SHA 检查失败；
  验证时仅临时还原 LF，哈希精确匹配原常量，结束后恢复原文件字节，没有改历史 fixture 或断言。
  JooqWorkflowCallbackRepositoryTest 编译通过；本机没有 Docker，Testcontainers 方法未运行，
  本次没有把相关 verify 表述为全部 Java 测试通过。
- 旧 46 个 Prompt、57 个 Profile 与基线逐项相同；只新增各两个 v2 条目。输出 Schema、部署模型
  和 Step Budget Registry 与基线完全相同。新 manifest 为
  `2faa340853bfe503c99569675dca481274d8c7d8b6594df83bc6fa52d981dd8b`。
- 独立审查发现旧零尝试复审仍以 initial 派发，会被新 Catalog 的角色列表拒绝；已先建立失败用例，
  再仅为正文/场景改写的两对 v1→v2 角色保留初次派发入口。仍逐项校验旧 Profile、Prompt、Schema
  和预算，不用新提示词覆盖旧任务。回归覆盖两操作、两角色、三种派发模式，以及混合新旧引用拒绝。

## 发布状态与边界

未推送或部署。权威库仍有 1 个非终态 V2 Run，即本次 waiting_user 草案任务。
`scripts/deploy-production.sh` 第 707–730 行要求不同 manifest 切换前旧 V2 Run 全部终态；
本次没有批准、丢弃、取消该任务，也未关闭生产新建入口或绕过该部署门禁。
