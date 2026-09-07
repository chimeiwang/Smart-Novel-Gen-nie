# 模型调用前取消的耐久收尾

状态：修复、Agent全套测试、真实开发原记录恢复及再次CLI取消验收完成；生产未切换。

## 生产兼容启动补充

首次生产兼容部署的Agent readiness失败，部署脚本已自动恢复旧三服务并通过smoke；正式库未迁移。
代码核实：新取消候选查询允许空journal无marker待机，但紧随的原claim_due_callbacks仍直接拒绝缺marker。
production lifespan启动回放监督器并严格检查其健康；开发canary已经有marker，未覆盖这一迁移前状态。

只允许在原claim Lua中为“marker不存在且独立execution Redis整库为空”增加只读空轮询返回。
空库判定与轮询必须在同一Lua原子执行中，不创建marker、不接纳Step、不允许provider，也不修改production
readiness或设置为dev。错误marker、任何孤儿journal、active／pending／leased／rejected／quarantine或其他key
均不得沿空库豁免；existing marker路径的claim/lease/CAS保持原样。执行Redis生产独立DB约束不变。
验收新增无marker空库、孤儿和各索引拒绝、错误marker、production真实lifespan／严格健康组合以及真实Redis；
修复后从冻结提交重建Agent并重做兼容部署，不能用提前写marker或跳过健康检查让首次迁移通过。

最小Lua修复已完成：新增的production／testing=False真实lifespan用例先稳定复现503，修复后健康测试26项、
日志／回放／真实Redis48项、完整Agent1666项通过；Ruff和294文件Mypy通过。真实生产只读探针也确认
原镜像仅在claim处拒绝空库，AOF与连接本身健康，探针前后整库保持零key。Core与Web构建输入未改变，
后续发布可在精确差异核验后复用已验证的不可变镜像，原builtRevision保持不变；Agent必须重建。

## 现场与根因

2026-09-07，隔离验收Run `cmtr2hc2v1knfcxvaszyyza3a` 被公共CLI取消后，Core已为cancelled，
Step为skipped／RUN_CANCELLED且无模型预留、调用或扣费；Agent journal却仍为accepted，
cancel_request_id已存在、provider_attempts=0、provider_started_ms为空，drain active持续保留一项。

屏障测试稳定复现：执行器读取尚无取消的accepted快照，等待Core preparing回执时收到取消；随后
stale分支按旧快照提交不带cancelRequestId的失败，journal正确拒绝，但执行器未转成取消终态。
此外，already_cancelled重放不补收尾；Core的pending Step已终态后不再重发执行请求，单靠租约恢复不足。
真实记录只用于验证修复恢复，不手工DEL、ZREM或改写数据库使门禁通过。

## 最小修复

1. provider前的终态提交统一服从最新持久取消事实。取消与stale、rejected、校验失败、重试耗尽等
   退出相遇时，不丢失取消身份，不把合法取消抛为后台故障；fence、requestHash和原始用量规则保持。
2. 原cancel入口重复收到同一取消意图时，若对应journal仍非终态、无活跃本机任务，继续精确取消收尾；
   已有结果／失败只重放原终态，不能覆盖结果或把已发生供应商调用的用量改成零。
3. 复用现有terminal callback replayer的每轮准备钩子，恢复重启前已落盘的“取消收到但未成终态”。
   候选只来自既有drain active索引，在原256项有界范围内读取；无新Redis索引、数据库表、公共／内部API
   或独立后台框架。只有accepted/started、cancel_request_id存在、provider_attempts=0且provider_started_ms
   为空的记录可自动补终态；任何已开始模型、缺失取消、已有终态或本机仍活跃的执行均不得盲目覆盖。
4. 恢复只从journal完整身份生成原cancelRequestId绑定的RUN_CANCELLED终态，使用既有Lua CAS、
   callback claim／lease与Core回执移出索引，不重建请求正文、不调用模型、不伪造成功或计费。
   同fence已由Core跳过的Step沿原superseded回执收敛；不改Core行为。
5. 恢复仍尊重restore quarantine。兼容迁移前空Redis尚无marker的启动阶段；缺marker且已有active、
   非法marker或索引超界必须明确失败，不能猜测重建索引。

## 验收

- 确定性屏障覆盖取消与preparing stale／其他provider前退出竞态，provider次数为零，终态含原取消身份。
- 同取消重放、新服务实例接管、后台replayer自动恢复均可排空；原成功结果、已调用模型、fence变化、
  并发收尾和quarantine不被覆盖或放宽。
- 隔离真实Redis验证索引读取、CAS和回执后的正常移出；运行受影响Agent测试、Ruff与Mypy。
- 新镜像在开发route=off下恢复现场那一条原记录，不手工修改数据库／Redis；原六笔真实调用和扣费不变。
  再用公共CLI复验一次取消，并确认联合verify-drain全零。生产仍需独立canary，不把开发修复当作已上线。

## 实际结果

2026-09-07：56项执行器测试与完整Agent1648项测试全部通过；真实Redis Lua、Ruff与Mypy通过。
`wait_idle` 在全部task已done但清理回调尚待调度时显式让出事件循环，避免同步gather造成测试／关闭等待饥饿。
取消继续遵守既有协议的cancelled／outcomeUnknown=false；未知token／cost保持null、实际providerAttempts保留，
不为取消修改共享协议或把非零尝试归零。零调用自动恢复范围不变。

开发Agent新镜像 `sha256:22d8b604e111383c2bad04ba055ecbf1f6dad4c8f786b15bc129cfb18eec8934`
仅重建Agent后自动收尾原Step；journal成为failure／delivered，providerAttempts仍0，原active索引正常移出。
五Run数据库审计除observedAt之外逐值相同，原六笔37.876积分结算未变。再次公共CLI启动并取消
Run `cmtr3lrwte3uy5j3lp5u55zhd` 成功，新增零模型／零费用／零候选；原章节完整data保持相同。
最终route=off、V1 fresh=false，联合verify-drain所有指标为0。完整证据位于本机
`output/inkforge-durable-realdev-20260907`，生产仍须独立切换与验收。
