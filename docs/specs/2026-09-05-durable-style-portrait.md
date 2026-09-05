# 文风画像耐久执行迁移

状态：仓内实现、全仓门禁与隔离跨进程验收完成。基线 `be07176` 的 17/21 增至 18/21；不代表生产已开放。

## 目标与非目标

将已有 `style.portrait` 的整套五节生成与单节重做接入 V2。保留原公共接口、上传/删除/手动修改/应用文风行为，
不新增功能、CLI 命令、Reviewer、ReviewArtifact、用户采用流程或质量阈值。原成功本来就由 Core 直接更新
WritingStyle；本项不能把它改成必须另行采用的小说候选流程。全套中途失败不提前写入部分画像。

不新增数据库结构、不删除历史表/数据。此批只在当前分支实现与隔离验证；真实供应商、真实库、固定 CLI/Skills
更新和生产部署仍在总目标后续按既定流程验收，不以局部门禁代替整体完成。

## 原业务与公开兼容

- 文风为用户级私有资产，不属于小说。V2 使用 `novelId=null, chapterId=null`，目标为
  `style_profile/styleId`，来源为 `style_portrait_v2/styleId`，不继续伪造 `style:<id>` 小说身份。
- 原整套与单节画像 POST 无请求体、无 clientRequestId，保持不变。Core 为一次新请求生成内部稳定 key，
  不声称公开 POST 重试已经具备客户端幂等；同 style 跨 V1/V2 有活动任务仍返回原 409。
- V2 新任务只创建 WorkflowRun/Step，不创建 StylePortraitTask 影子行。旧表和原 V1 执行/回调保留。
  原任务 GET 与 StyleResponse.tasks 双读：V2 的 id 为 runId，styleId/section/时间来自冻结事实，
  pending/running/completed/failed 或 cancelled 分别投影为原 pending/processing/success/error。
  被删除文风的任务不能借历史 V2 重新公开，列表仍按当前文风归属查询。
- 原手工分节修改、参考文件增删在生成期间仍允许，不新增 CAS 或活动运行禁令；分节完成只更新目标字段和
  原统一计数/汇总，全套完成更新五节。失败保留既有画像，只写原稳定失败说明。
- CLI 仍只有 `long.style.apply/clear`，不添加画像创建、上传、编辑或删除入口；停止网页观察不等于取消任务。

## 完整来源冻结

原 V1 在 Agent 开始后读取当时 ready 文件；V2 改为 Core 受理事务内冻结当前 ready 文件完整内容，这是本项
真实且必要的行为变化。使用既有 style 锁与参考增删串行，读取受控文件后才提交 Run，不将路径传给 Agent。
受理后新增或删除参考不使该 Run 失效，也不重新读取文件。

唯一 JSON Evidence `style_portrait_context`，resourceId=styleId，包含：

- styleId、mode（full/section）、section（整套显式 null，单节为固定枚举）；
- references：按 createdAt/id 排序，每项 referenceId、filename、charCount、content、contentSha256；
- originalCharCount：沿原规则取文件元数据 charCount 之和，不把文件名和包装分隔符计入；
- sourceTextSha256：对各份 `参考资料：{filename}\n\n{content}` 以 `\n\n` 拼接的原始 UTF-8 摘要。

不重复存一份拼接正文；Agent 仅按上述确定性规则重建与原请求相同的 sourceText，并校验摘要。
单文件仍严格 UTF-8、非空、最多 50 MiB，原换行与 BOM 保留。字数沿原 Python 空白判定的非空白 Unicode
码点数；BOM 计数，不能改用小说正文的 countTextLength。usedCharCount=originalCharCount，truncated=false。
超模型预算必须明确失败，不采样、摘要、拆短来源或伪造已全量使用。

## 模型 Step 与结果

- 整套按 creativeMethodology、uniqueMarkers、generationStyle、expressionFeatures、styleTraits 固定顺序，
  共五次串行调用；单节只调用指定一节。Step input 精确为 `{section}`。每节均读取同一完整 Evidence，
  不把前面各节结果送给模型，不为迁移新增协议纠正、自动续写或评审。
- 新 Profile/Prompt/Output/预算使用独立版本，保留旧占位。静态系统提示与各节任务文字沿现有
  ModelPortraitGenerator；明确 `plain_text_v1` 路由，tools 为空、structuredOutput 为 null，
  不添加 response_format、JSON Schema 指令或 Beta strict，关闭 thinking，使用 batch_media lane。
- 模型仅返回该节纯文本。程序封装 `resultKind=output, output={content}`，content 保存原始完整回复，
  不要求模型自报 section/模式/计数/哈希。Agent 必须检查 stop、无有效或无效工具调用且按原 strip 规则非空；
  length、过滤、未知/矛盾完成、空回复均失败，不纠正。
- Core 保存各 Step 原始输出；最终物化时才按原 Python str.strip 语义去掉节正文首尾空白，保留内部全部文本，
  不移除 BOM 或额外裁切。全套五节全部完成后一次更新 WritingStyle，单节只更新原目标字段。
  portraitMarkdown 仍由 Core 固定中文标题与五节完整文本拼接，不由模型另行生成。
- 后续 Step 复用原 Evidence，逐节独立授权、reservation、计费、journal、fence 与恢复；已经完成的节不重调。
  本项不创建额外模型汇总 Step。失败/取消/提交拒绝均收敛 Run，公开任务状态由 Run 投影，不复制状态机。

预算：Run 新 `budget.style.portrait.v2` 最多 5 次调用、input/cacheMiss 各 300000、completion/visible 各 30000、
reasoning 0、costMicros 1000000、wall 900 秒、protocolCorrectionSteps 0、每 Step providerRetries 2。
每 Step 最多 1 次模型、input/cacheMiss 各 60000、completion/visible 各 6000、reasoning 0、costMicros 200000、
wall 180 秒、providerRetries 2、protocolCorrections 0。不假设后四节一定命中供应商缓存。

## 用户级运行与删除收敛

- 增加只给用户级资产使用的 allowlist 判断：schemaReady、route=allowlist 且 user 在现有用户 allowlist 中。
  既有小说级 user+novel 双条件不变；画像不能借某本小说 ID 绕过归属。styles 使用自己拥有的 readiness 端口。
- 复验派发、回调、签名、取消和计费的显式 novelId=null；省略字段与 null 区分。已有带小说运行仍按原身份匹配，
  不为通过画像测试全局放松归属。用量归属为真正 user/run/step，不写伪小说或 V1 任务引用。
- 删除 Style 仍按原操作清理文风、引用和应用关系。删除事务不在 Style 锁内反锁 V2 Run；原取消协调器有界
  发现已删除目标，再走原取消/计费/租约路径。每节完成先核对目标仍存在，已删目标不得继续追加下一节或重建文风；
  迟到结果只保留执行/用量事实并取消。参考文件增删与手工分节编辑不是取消条件。

## 验收

1. 共享来源/输入/输出、真实版本资产、完整来源拼接/计数、纯文本 Provider 请求与失败类型的单元测试。
2. PostgreSQL 与真实 HTTP 覆盖原整套/单节接口、跨 V1/V2 互斥与双读、无小说身份、完整五节原子物化、
   单节不改其他四节、手工编辑/参考变化保持原规则、删除收敛、旧队列隔离、未知用量和取消结算。
3. 独立 Core/Agent/PostgreSQL/双 Redis 的受控 Fake 场景证明完整五节、首节终态暂缓后 Agent 重启、不重调已完成节、
   单节重做和逐 Step 计费/唯一 Run 终态；Fake 不代表真实供应商或生产。
4. 全仓 Maven、Python、Ruff、Mypy、Web、类型/lint/build、OpenAPI/共享导出基线与 manifest 检查。
   CLI 原应用/清除命令回归，文档明确没有新增画像命令或已更新固定安装的承诺。

## 已完成的仓内验证

跨进程首次提交暴露了现有 canonical JSON 的控制字符转义差异：Jackson 默认把 U+001C 等转义写成大写
十六进制，Python 使用小写，导致相同完整 UTF-8 参考的 JSON Evidence 摘要不一致而被 Agent 422 拒绝，
尚未调用模型。修复必须在 Java canonical 字符串编码中明确小写十六进制转义，并增加双语言共享向量；
不得删除控制字符、修改参考原文或放松摘要校验。普通 HTTP JSON 编码不需要改变；既有标准向量保持逐字节不变。
已有按错误大写转义生成的异常冻结记录不自动重算、不改写、不尝试调用；这类记录原本就无法通过 Agent 的
标准摘要校验。此次只修复新建执行的协议一致性，不新增历史数据迁移。

- Catalog 已接入文风画像，当前共 18/21；新共享 Schema 合计 291 个。执行资产 canonical manifest 为
  `15b2c6ff1a46699d3d926ef26c4ba15394cdc2e14fb68b0e2a71b9ebccf60b2e`。
  公共 Core 152、内部 Core 34、普通 CLI 125、Operator 45 均未变化。
- `./mvnw verify` 全仓通过：身份 11、契约 5、Core 1144（3 skipped）、CLI 135；
  `/tmp/inkforge-style-v2-maven-all-2.log`。涵盖真实 PostgreSQL 的五节回调/逐节结算/取消与删除、
  原 HTTP 上传和任务查询、整套一次物化、单节保留其他字段、新旧双读和互斥。
- Python 全仓 `5306 passed, 3 skipped`；`/tmp/inkforge-style-v2-python-all-3.log`，包含画像验收脚本测试。
  首轮唯一失败是 Catalog 测试尚把新增画像套用创作 thinking/选区输出断言，已改为精确的画像纯文本契约后复跑全绿。
- Web 347、api-client 3 通过；typecheck、lint、build 与 `api:check` 通过，日志前缀
  `/tmp/inkforge-style-v2-`。Mypy 288 个源文件通过；Core 19 文件与 Agent Service 基线检查通过，
  共享 Schema 导出基线及执行 manifest 派生检查通过。
- 用户级执行修复保持最小范围：Agent 终态/进度回调保留必填 `novelId:null`，其他可选空字段仍省略；
  Java Accepted 回执区分必填字段省略与显式 null，原小说任务及签名规则不放宽。
- 首轮新增 PostgreSQL 测试夹具漏填终态时间/取消身份，并曾尝试在同 Run 上反转终态；已修正测试数据，
  分别使用独立 Run 验证各状态，数据库结构、约束和业务规则均未因此修改。
- 控制字符规范化共享向量先红后绿；`/tmp/inkforge-style-v2-canonical-red.log` 保留复现，修复后的全仓 Maven
  同时验证原向量与新增控制字符/字面文本向量，Python 全仓验证同一份向量。常规字符串哈希保持不变。

## 独立进程与最终结果

`output/durable-agent-v2-e2e/20260905-style-3/report.json` 为 `passed`，对应
`/tmp/inkforge-style-v2-e2e-4.log`。全套与单节均通过原公共 API、真实 Java Core/Python Agent、隔离 PostgreSQL、
普通 Redis 与独立 execution Redis 验证；模型为受控 Fake：

- 整套五个 Step、五次模型调用，首节结果已进入 journal、回调尚未送达时真正重启 Agent；恢复后第一节仍只
  调用一次。下一节暂缓时正式文风仍未写入部分结果，五节结束后一次完成。
- 单节一个 Step、一次模型调用，只重做指定节；其他节保留手工修改。Step 原始文本和最终 Python strip 结果
  分别按完整内容核对，BOM、换行、特殊空白、完整来源与原非空白字符计数均保留。
- 每 Run 恰好一个完成事件；每 Step 一份 settled reservation 和 TokenUsage，全部 token 字段一致，Fake
  余额差为零。无 V1 画像/写作任务影子、命令、ReviewArtifact 或 Evaluation。最终 journal 均 delivered，
  完整终态 payload 已按既有规则清除。
- 第一次隔离运行在模型调用前暴露上述 canonical 编码差异；修复后重新构建 Core/Agent。第二次已完成首节，
  但旧验收器用 splitlines 拆 Redis HGETALL，被 U+0085 分行符破坏；只将验收器改为 Redis JSON 对象读取。
  最后一次复用同一套修复后镜像，Core Image ID 为
  `sha256:c6a51ccce85cc8a8ddd578850c320b8dae10be6b03867f87ed31db8fd9ab50a0`，Agent 为
  `sha256:203945023ee551364f14cea1932eb812d2eef4083c61708a54e7b5fcd9e16c3c`；两次 Image ID 一致，
  Agent 源码核对一致，没有复用修复前镜像或为过测试删除控制字符。
- 最终完整 harness 与架构检查 `331 passed`，包括 Redis JSON 读取的空值/Unicode 与无效形状负例；
  `/tmp/inkforge-style-v2-harness-final-3.log`。全仓 Ruff、manifest 检查、文档与 `git diff --check` 通过。
- 三次隔离运行均完成清理；最终容器、网络、卷残留为零，临时测试密钥目录已删除。
  `twoCoreTwoGiBHostGate=not_proven`，不把本机容器测试当作真实生产主机或供应商验收。

本批未推送、部署、修改真实数据库、调用真实供应商、替换固定 CLI JAR 或更新活动 Skills。剩余三项为
RAG embedding 和两个开发视频模型工作流，生产视频保持关闭。
