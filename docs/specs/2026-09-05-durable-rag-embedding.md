# 参考资料索引耐久执行迁移

状态：仓内实现、全仓门禁与隔离跨进程验收完成。基线 `88d2a7b` 的 18/21 增至 19/21；不代表生产已开放。

## 目标与非目标

将现有后台 `rag.embedding` 接入 Core 权威 Run/Step 与 Agent 单次调用执行边界，不新增检索产品能力。
保留资料六个公共接口、CLI 资料 CRUD/reindex、1800 Unicode 码点分块、最多 64 块、每批 10 块和不扣用户积分。
查询时 `semantic_search_references` 的 embedding 仍走原查询客户端，本项不顺带迁移它。
不新增数据库结构，不删除 RagDocument/RagChunk、旧任务或历史数据，不改变正式作品内容。
当前阶段仅当前分支和隔离测试；不执行真实库变更、远程写入或生产部署，生产视频继续关闭。

## 原业务与代次绑定

- ReferenceMaterial 是完整原文；RagDocument/RagChunk 仍是公开的派生索引事实，不能被另一份业务状态替代。
- 原身份使用 referenceId、原始 UTF-8 contentHash、RagDocument.updatedAt（索引代次）；标题、类型、URL
  变化不推进代次。正文变化立即清除旧块；同 hash 在终态后显式 reindex 产生新代次，pending 重建复用原代次。
- 仅 create、正文变化或终态后 reindex 产生的新代次，按现有小说级 user+novel allowlist 决定执行引擎。
  对有效非空 V2 来源，在原业务事务内一同创建 Run/Evidence/首 Step；sourceType=rag_index_v2，
  sourceId=referenceId，target=reference/referenceId，novelId 为真实小说，chapter/session 为空。
  内部 idempotencyKey 使用原 RagJobIdentity.runId（包含代次），不只用 contentHash。
- 既有无 V2 绑定的 pending 代次继续按 V1 补投；dispatcher 不根据新配置重新选引擎。已有 V2 绑定即使
  route-off 也只恢复该 Run，不补建 V1。新旧回调均不得写入其他代次。
- 领域事务使用现有 CoreDatabase.transactionResult，使跨模块创建真正加入同一个事务；锁序须与
  Run 回调的 User/小说/Reference/RagDocument 顺序兼容，不在资料修改锁内反锁旧 Run。
- 自动提交不可用不得回滚资料 CRUD。网络提交在事务外，失败保留已保存资料及待处理意图；显式 reindex
  提交失败保持原 503/RAG_INDEX_SUBMIT_FAILED，成功保持 202/accepted，无新增 Run ID 响应。
  未装配原 Agent 客户端/投递端口时仍保持原未配置 disabled 语义。若已选 V2 但本地耐久服务在任何 Run
  写入前缺失，只将该代索引标记 failed 并保存稳定内部不可用标记，不回退 V1；自动入口保留原文，显式
  reindex 仍返回原 503。此处理不得吞数据库错误或登记中途错误。
- 所有新的 indexEnabled 代次（包括 V1/V2）都由 Core 提前确定性判空和判容量，既有 pending 代次不改变。
  空正文直接写入空索引 ready，不创建模型 Run/Step、预留或伪造调用记录；超过原 64 块容量只将该代索引
  明确标记 failed，不拒绝保存原文，不截断后尝试模型。这只提前已有执行结果，不引入新容量或拒存规则。

## 完整来源与批次协议

唯一 JSON Evidence 为 rag_embedding_context，resourceId=referenceId，字段为 referenceId、contentHash、
indexGeneration（UTC 毫秒规范时间）、content（完整原文）、chunkCount。Agent 校验原始 UTF-8 hash，按
1800 Unicode 码点重建全部分块并验证数量，不 trim、不归一换行、不摘要。
Run input 精确为 {referenceId,contentHash,indexGeneration}；Step input 精确为 {batchIndex}，从 0 开始。
每批最多 10 块，只向 /embeddings 发送真实模型名及本批完整文本，不能包装为 chat/Responses 或工具调用。
每批一个 generation Step，逻辑 Profile/Output purpose 为 embedding；最多 7 个串行 Step。
Step output 为 {embeddings}，保持本批完整有序向量；不得要求供应商自报业务身份、hash 或批号。
全部 Step 成功后 Core 一次事务按完整原文重建 chunks、核对全部向量并替换索引，才置 ready。
每次接续与最终应用检查正文 hash、document hash、索引代次；正文修改或删除使旧 Run 取消，迟到结果
只保留真实执行/用量事实。A→B→A 也必须因代次不同失效。标题变化不取消执行。
向量数量须匹配该批，维度 1..4096、全批次一致、所有元素有限且非布尔，不接受缺项或重复 index。
最终写入沿用 pgvector 的 float4 存储事实；虽为有限 double、但存储时溢出的数值，Core 保留本批完整结果
和真实用量后明确失败，不裁切，也不让数据库拒绝导致终报无限重放。数据库既有舍入行为保持不变，
例如真实 pgvector 接受 1e-100 并存为 0；不得凭 Java 类型转换猜测而额外拒绝，Step 仍保留原始向量结果。

## 供应商身份、预算与用量

- 新 Profile=rag.embedding.v2，Prompt=prompt.rag.embedding.v2（无聊天提示，静态协议说明不发供应商），
  Output=output.embedding_batch.v2，Deployment=deployment.rag.embedding.v2；独立 route=embeddings_v1，
  provider=openai_embeddings，transport=transport.openai-embeddings.v1，
  capability=capability.openai-embeddings.batch.v1，reasoning=disabled、请求幂等=false。
- 保留原任意非空 RAG_EMBEDDING_MODEL 和自定义 RAG_EMBEDDING_BASE_URL 的配置能力，不限制为某家
  厂商、不把真实 model 写成 fake/configured。两端按原规则去末尾 /、缺 /v1 则补 /v1，再取实际
  /embeddings 请求端点配置字符串的 UTF-8 SHA256，形成 endpoint.rag-embedding.<sha256>.v1；不持久化密钥或 URL。
  此配置指纹不隐式归一 host/默认端口/查询参数，也不声称证明供应商重定向后的实际目的地。
  原 Compose 为 Core 追加透传现有 model/base 两个非秘密配置，API key 仍只给 Agent；不增加开关或
  修改发布流程。这是该执行授权必需的配置接线，不代表已重启、部署或改变真实环境。
- Deployment 仅此条目允许 configuredBinding={key:binding.rag-embedding-config.v1,
  allowedEnvironments:[dev,test,production],pricingVersion:credit-pricing.v1,billable:false}，
  allowedModels=[]。Core 读取非秘密 model/base 配置，形成精确授权元组；Agent 只能报告真实身份，不能
  自报免收费。未配置或两端不匹配明确拒绝，其他 Deployment 静态授权规则不变。旧已开始调用不能因配置
  变化换模型重跑；已有终态仍按冻结身份送达。
  同一 Run 后续批次的部署身份必须与首个已完成批次完全相同，在调用前检查，避免混合不同向量空间。
  每批合法但跨批维度变化时，保留已调用结果和用量并明确结束为索引失败，不部分应用或无限重试终报。
- 共用原 ExecutionService、两道 Core 调用前回执、持久 journal、fence、取消及同一个全局并发门；
  独立 embedding 请求/响应类型，不伪装 ModelTurnResult，不另造队列或恢复状态机。
- Run 预算最多 7 调用，input/cacheMiss 各 420000，completion/reasoning/visible=0，costMicros=3500000，
  wall=1260 秒，protocolCorrections=0；每 Step 1 调用，input/cacheMiss 各 60000，costMicros=500000，
  wall=180 秒，providerRetries=2。无幂等的已开始未知结果不得安全重发；只允许调用未发生的安全重试。
- Core 固定 billable=false，仍建立 reserved=0 的原 BillingReservation；不新增收费路径或账务表。
  credit-pricing.v1 是用户积分定价规则，不代表供应商成本。可靠 prompt_tokens 可记 inputTokens；缺失
  cached/cacheMiss/cost 保持 null，矛盾或无效供应商用量不得造零。embedding 本身没有生成 token，
  completion/reasoning/visible=0 为此协议事实，不沿用 chat 推断。用量不完整不抹掉有效向量结果，按
  partial/unknown 和原零金额待对账状态收敛，不扣余额、不伪造 TokenUsage 非空字段。

## 验收与 CLI 文档

1. 双语言冻结来源、分块、indexGeneration、配置绑定与 endpoint 黄金向量；独立 embedding HTTP 形状、
   返回 index/数量/维度/有限数、完整和缺失用量、并发/取消/未知调用恢复的单元测试。
2. PostgreSQL 与原 HTTP 覆盖 CRUD 保留、原子 V2 绑定、旧 pending 不抢迁、重建幂等、空正文零调用、
   容量失败不丢原文、多批原子应用、标题不失效、正文/删除/A→B→A 失效及零收费审计。
3. 独立 Core/Agent/PostgreSQL/双 Redis 与受控 embedding HTTP：至少两批，首批结果 journal 落地后
   重启 Agent，证明首批不重调、索引不部分 ready、最终唯一完成与零余额变化；Fake 不代表真实供应商。
4. 按风险执行全仓 Java/Python/Web、类型/静态检查与所有契约/manifest 导出检查。CLI 仍 125 命令、
   Operator 仍 45，公共 Core 152、内部 Core 34 不变。维护者文档清楚说明无新增命令、原 reindex 参数
   响应保持、服务端代次恢复改变，不把源码通过测试说成固定安装包或生产已更新。

## 仓内验证结果

- Catalog 只新增启用 `rag.embedding`，合计 19/21；自然入口仍为十项，普通 CLI 125、Operator 45、
  公共 Core 152、内部 Core 34 未变化。共享 Schema 由 291 增至 295，新增四个 RAG 协议类型。
  最终执行资产 manifest 为 `9f679762c74ec39314e0daa222db3a5a98ad15309fedd44ce496822398b891a5`。
- `./mvnw verify` 最终全仓通过：身份 11、共享契约 5、Core 1166（3 skipped）、CLI 135；
  日志 `/tmp/inkforge-rag-v2-maven-all-3.log`。此前定向 108 项通过，覆盖原 HTTP、旧队列隔离、
  新代次原子绑定、三重来源失效、零金额待对账、模型漂移拒绝、跨批维度失败和取消。
- Python 最终全仓 `5390 passed, 3 skipped, 1 warning`；日志 `/tmp/inkforge-rag-v2-pytest-2.log`。
  三项 skip 均为未显式提供服务器 dev 数据库的既有视频实库测试，不通过修改真实库强行消除。
  全仓 Ruff 通过，Mypy 四目录 291 个源文件通过；日志分别为
  `/tmp/inkforge-rag-v2-ruff-3.log`、`/tmp/inkforge-rag-v2-mypy-2.log`。
- Web 347、API-client 3 通过，最终日志 `/tmp/inkforge-rag-v2-web-final-1.log`；Web/API-client typecheck、
  lint、build 通过。manifest、Core 19 文件、Agent 2 文件、共享 295 Schema 可复现、OpenAPI 与 `api:check`
  均通过。Compose 新增非秘密配置透传的架构检查 27 项通过，未把 API key 给 Core。
  最终完整 harness 加 Compose/Catalog 架构检查 `398 passed, 1 warning`，日志
  `/tmp/inkforge-rag-v2-harness-final-1.log`。
- 测试发现并修复真实装配问题：依赖跨配置 `ConditionalOnBean` 的 router 可能未装配，V2 已登记仍会直投
  V1。最终在原 Service 和 dispatcher 装配时包一层相同无状态路由器，HTTP 证明不再混投；缺旧出站端口
  的最小上下文仍保留原 disabled 行为。登记服务缺失只在未写 Run 前明确处理，不吞数据库或完整性异常。
- 部分用量结算不会先锁 User，因此最终写 RagChunk 的 Novel 外键可能与资料更新反锁。领域物化先取
  Novel KEY SHARE，再锁 Reference/RagDocument；真实 PostgreSQL 并发测试覆盖不预锁 User 的分支。
- 真实 pgvector 验证有限 double 的溢出会拒绝存储，Core 保留结果/用量后明确失败，防止终报重复回滚。
  同一测试也证明小数下溢被原数据库接受；撤回了未经验证的额外下溢拒绝，保留原存储行为和 Step 原向量。
- 共享 model 仅 embedding 路由保留任意非空配置；旧四种路由保持原长度和 strip 规则。条件 Schema 使用
  `allOf` 内的 `anyOf` 交集，同时满足 JSON Schema、OpenAPI 3.0 Java 生成和 TypeScript 必填字段语义。
  早期 `if/then/else` 导致 Java 生成拒绝、顶层 `anyOf` 导致 TS 错误联合，均已修复且重新生成、复验；
  没有跳过校验、手写 DTO 或在前端类型断言绕过。生成构造器排序变化只通过测试的具名 builder 适配。

## 独立进程与重启结果

`output/durable-agent-v2-e2e/20260905-rag-2/report.json` 为 `passed`，对应
`/tmp/inkforge-rag-v2-e2e-2.log`。通过原公共资料 API、真实 Java Core/Python Agent、隔离 PostgreSQL、
普通 Redis、独立 execution Redis 和本地受控 `/v1/embeddings` HTTP 供应商验证：

- 完整原文含 BOM、CRLF、补充平面字符和边缘空白，重建 11 个块、两批。供应商返回逆序带 index 的向量，
  最终 Core 全部有序写入，与完整原文/字数/哈希逐项匹配，没有抽样或截断。
- 首批终态已落 journal、尚未送达 Core 时真正重启 Agent；首批与第二批各一次物理 HTTP 调用。
  第二批暂缓时仍零 RagChunk、非 ready，全部成功后才完成原子索引。
- 两个 completed Step、一个最终完成事件；两份 `reconciliation_required` 预留 reserved/charged 均为零，
  prompt 用量完整，cached/cacheMiss/cost 保持 null，没有伪造 TokenUsage。用户余额变化为零。
  无 V1 队列 payload/status、旧写作 Task/Run、ReviewArtifact 或 Evaluation；最终 journal 均 delivered。
- 首次组合 `up --build` 在环境启动阶段退出，尚无业务场景或模型调用，证据保留在 `20260905-rag-1`；
  原因未进一步定性，不据此修改产品代码。随后单独构建 Core/Agent 成功，日志
  `/tmp/inkforge-rag-v2-build-diagnosis-1.log`；最终复用的是这次新构建镜像，不是旧画像镜像：
  Core `sha256:21d68e07d403503538a6ed7ec6492ef0febb654e2904b878fa8476201f4e0598`，
  Agent `sha256:c3e497b02dda312ef82cf3a897909c61640521cae457ee4ea90fd30eb45e39ef`，Agent 选定源码核对一致。
- 两次验收及诊断均已清理临时资源；最终容器、网络、卷残留为零，临时测试密钥目录移除。
  `twoCoreTwoGiBHostGate=not_proven`，本地受控供应商不是实际供应商或生产主机验收。

本批未推送、部署、访问真实数据库或真实供应商、替换固定 CLI JAR 或修改活动 Skills。CLI/Skills 维护者
更新说明已补入 `2026-09-01-durable-agent-v2-operator-skill-update.md`；剩余两项开发视频操作，生产视频仍关闭。
