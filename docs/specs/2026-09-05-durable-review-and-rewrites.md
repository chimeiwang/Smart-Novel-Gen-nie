# Durable Agent V2 整章审阅与改写迁移

日期：2026-09-05。状态：三项操作本地验收完成；完整 Agent 重构仍在实施。

## 目标与范围

继续 2026-08-31 Agent 执行内核重构，在当前 `codex/durable-agent-execution` 分支迁移既有
`long_serial.review_chapter`、`long_serial.rewrite_scene`、`long_serial.rewrite_outline_selection`。
开始时 HEAD 为 `94a5298`，工作区干净，无后台 Maven、pytest 或隔离 E2E；上一阶段自然入口已完成本地验收。
本阶段开始时业务 Catalog 为 4/21，不把已有代码、本地验证、安装包及生产开放混为一谈。

保持既有创作操作、数据层和作者确认规则。复用耐久 Step、Evidence、候选和计费，不引入新的发布设施、
数据库结构或模型工具循环。本阶段只修改仓内源码及文档，不执行远程写、真实数据库迁移或生产部署。

## 整章审阅

- 旧操作是编辑直接生成完整只读报告，非候选复审、质量终检或 RevisionBrief。显式入口继续允许会话为空。
- Core 冻结完整章节、章节目标、批准计划、大纲及相关创作资料；可组合既有完整正文 Evidence Reader，
  不截取正文，不为审阅添加写作质量门禁。生成只消费冻结来源，不重新读取工作区。
- 新严格 `ChapterReviewInput` 仅含完整非空白 `userInstruction`；Provider 输出 `ChapterReviewOutput`
  仅含完整非空白 `report`。使用独立 `output.chapter_review_text.v1`；不得修改已用于候选评价的
  `output.chapter_review_report.v1` Schema 或其哈希。
- 单个 generation Step，由编辑执行，无 Reviewer、ReviewArtifact 或 waiting_user；不更新正式创作数据、
  ChapterQualityCheck、章节状态或完成门禁。Step.output 保存权威完整报告。
- 完成事务保存 Step 与 Run 终态、唯一 completed 事件；有会话时保存唯一编辑消息，
  `outcomeType=chapter_review_report`、`resultId=messageId`；无会话时 `resultId=stepId`。
- 公共 Python `WritingRunV2Response` 增可选 `reviewReport`，随后机械生成 OpenAPI/Java/TypeScript。
  GET 从唯一合法 completed generation Step 投影全文；其他操作缺省该字段。列表不加载或携带报告正文，
  SSE snapshot 不重复携带报告全文。
  Web 在该 outcome 完成后回读会话消息；CLI get/watch 从终态 GET 取得完整报告，保留文件输出和 Unicode 尾部。

## 场景改写

- 保持当前章节 target/scope、完整指令、目标字数和可选会话；不接受 selectionTarget，不新增 sceneId 或
  自动场景切分。模型依用户指令改写场景，结果仍是完整整章候选，不能声称程序保证未绑定区域逐字不变。
- 使用场景专用 `writer.scene_rewrite.v1` 生成提示与部署，复用 `ChapterDraftInput/Output/Result`、
  `chapter_writing_context` 及正文一致性/编辑双 Reviewer、完整返工和确定性候选 patch。
- 领域候选必须保留 `operation=rewrite_scene`，受控扩展整章操作集合，旧 write_chapter 持久形状及哈希不变。
  详情、自动/作者返工、来源复验与决定均按冻结 Run 的真实操作交叉校验，不能只在 Catalog 开启开关。
- 普通或 editedContent 批准由既有 Core writer 全文应用，回到 drafting、清 completedAt 并失效旧终检。
  不修改章节进展、剧情进展、Beat Plan、设定、大纲或伏笔，不新建下一章。

## 大纲选区改写

- 公共章节 target 是创作上下文锚点；`selectionTarget.resourceType` 分别为 `outline_content` 或
  `outline_node_content`。前者 resourceId 是 Outline 行 ID、scope 为 novel；后者 scope 为 outline_node，
  outlineNodeId 必须等于 resourceId。资源必须与当前小说一致。
- Core 冻结来源身份、updatedAt、完整原文 SHA-256、Unicode 码点范围、selectedTextHash 和完整原文。
  前后上下文窗口不能替代完整 Evidence。生成、复审、返工均消费同一来源。
- 新严格 `OutlineSelectionInput` 为 userInstruction/selectionTarget，加可选且成对的
  originalUserInstruction/previousCandidate；previousCandidate 为 artifactId/artifactRevision/replacement。
  Provider `OutlineSelectionOutput` 只返回非空白完整 replacement，程序派生 contentSha256。
- 启用 `plot.outline_selection.v1` 与独立 `output.outline_selection_replacement.v1`，配一个大纲编辑
  Reviewer `reviewer.outline_selection_editorial.v1`，使用大纲逻辑提示；不复用章节行文提示或双复审。
- Reviewer 只有在全部问题均为高置信、明确局部的 `outline_selection.local` 时才允许最多一次完整
  replacement 自动返工；返工绑定同一来源、`originalUserInstruction` 与精确 `previousCandidate`。
  结构问题、依据或范围不明确、复审不可用以及第二轮仍有问题都保留候选交作者，不做局部正式文本 patch。
- 新大纲选区持久 Schema，或严格限定类型组合的共用值对象，保留旧章节选区 Schema/哈希。
  详情重建完整 before/after，作者 revise/approve/discard 和来源/revision CAS 沿用耐久审核链。
- 批准仅允许 editedReplacement；普通批准和编辑批准分别复用既有 `outline_content_selection` /
  `outline_node_content_selection` writer，选区外逐字不变。不得接受 editedContent/selectedUpdateRefs，
  不更新章节、节点结构或其他资料层。不同章节锚定同一大纲来源时也必须互斥并复验来源。

## 冻结资产、预算和自然入口

新资产必须成套注册 Profile、Prompt、Deployment、Output、StepBudget 和 Catalog，保留已支持资产内容/hash。
重试与协议纠正使用既有上限 2/1；这些数值不授权额外物理调用或无限恢复。

| 操作/Step | 调用数 | input/cache-miss | completion | reasoning/visible | costMicros | 秒 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 审阅生成及 Run | 1 | 80000/80000 | 12000 | 0/12000 | 400000 | 180 |
| 场景生成 | 1 | 30000/30000 | 16000 | 8000/8000 | 600000 | 300 |
| 场景每位 Reviewer | 1 | 30000/30000 | 2000 | 0/2000 | 200000 | 75 |
| 场景 Run（最多两轮） | 6 | 180000/180000 | 40000 | 16000/24000 | 2000000 | 900 |
| 大纲选区生成 | 1 | 30000/30000 | 8000 | 4000/4000 | 300000 | 120 |
| 大纲选区编辑复审 | 1 | 15000/15000 | 1000 | 0/1000 | 100000 | 60 |
| 大纲选区 Run（最多两轮） | 4 | 90000/90000 | 18000 | 8000/10000 | 800000 | 480 |

新预算按完整冷缓存及两轮生成/复审核算，不沿用未启用占位中的不一致累计数值。超限明确失败，不能裁切来源或结果。
审阅关闭 reasoning；两类改写使用有界 reasoning，Reviewer 关闭 reasoning。

普通自然请求新增审阅和场景改写，授权列表从三项扩为五项，让已有用户入口可调用已迁移能力。
共享 IntentContext 上限、Agent resolver 支持集合、Core 冻结计划/业务续接必须同步。
旧自然计划继续按原冻结三项、子计划哈希和总预算恢复，不能补入新操作或重算为新资产。
新计划按实际五项预算最大值加最多三次 resolver 核算。大纲选区仍使用显式来源绑定，resolver 不猜范围或资源。

## CLI、文档与验收

继续使用现有 long.agent.start、long.task.get/watch、long.artifact.*，不增加仅包装已有 API 的命令。
CLI 只访问 Core 公共接口。同步 Java/Python 对照、Web 完成报告读取、README 与 Skills 更新契约；
本次文档必须说明报告字段、两种候选编辑字段、自然入口与显式选区、源码和安装包的区别。
本轮不扩大既有 Operator wrapper 白名单或直接修改活动 Skill。

测试先覆盖真实行为再实现，至少验证：

1. 审阅有/无会话、完整大报告、空报告拒绝、重复回调/恢复不重复模型、消息或费用；正式数据零变化。
2. 场景完整候选、同来源双审/返工/patch、编辑批准、取消和旧质量失效，保留真实 operation 与旧章哈希兼容。
3. 总纲与节点选区 PostgreSQL 纵切、Unicode、编辑批准/返工/丢弃、跨小说/错误资源/旧版本/旧 revision 零副作用。
4. 自然五项选择及旧三项冻结计划恢复，CLI V1/V2 完整读取与 Web 会话消息回读。
5. 共享协议、Agent、Core、CLI 和 Web 相关测试，随后完整 pytest/Ruff/Mypy/Maven/Web/生成契约门禁；
   Maven 串行。复用现有隔离 Compose/Fake Provider 验证跨进程结果、费用及清理，不用真实供应商结果冒充本地测试。

本阶段未完成全部接线与验证前保持实施中；本阶段完成也不代表其他 Operation、V1 退役、真实环境迁移与账号验收完成。

## 实施与验证记录

当前三项源码、公共报告投影、CLI 读取契约和 Web 消息回读已接通，并完成下述本地门禁和跨进程验收。

- `./mvnw verify` 五个 reactor 全部通过：服务身份 11、共享契约 5、Core 863（3 skipped）、CLI 127。
  日志 `/tmp/inkforge-review-rewrites-maven-final.log`。PostgreSQL 行为使用真实 Testcontainers 验证。
- Python 全仓 4535 passed、3 skipped；只有既有 Starlette 弃用警告。
  日志 `/tmp/inkforge-review-rewrites-python-final-complete.log`。后续验收脚本的中间态修正另有定向回归。
  最终 E2E 断言/控制器整组 215 passed，日志 `/tmp/inkforge-review-rewrites-e2e-unit-final-complete.log`。
- Web 335 项与 API 客户端 3 项通过；typecheck、lint、build、api:check 均通过。
  日志分别为 `/tmp/inkforge-review-rewrites-web-full.log`、`/tmp/inkforge-review-rewrites-typecheck.log`、
  `/tmp/inkforge-review-rewrites-lint.log`、`/tmp/inkforge-review-rewrites-build.log`、
  `/tmp/inkforge-review-rewrites-api-check.log`。
- Ruff 全仓通过；Mypy 服务源码 280 文件、长篇 CLI 24 文件通过；新 E2E 模块使用明确 package base
  单独检查，不把跨包重复模块解析错误当作源码错误。最后三个 Agent 输入校验回归在 Provider 前拒绝额外
  Evidence、布尔 schemaVersion 和越界选区，不放宽旧操作或依赖 Python 的静默切片行为。
- 历史 `94a5298` 的三项自然计划由独立 19707 字节 literal fixture 恢复，固定文件哈希
  `00cdb1dd3ccadf463d18fa8016238eabcf4b5d7032841bd348feb4c0335684dd`、外层计划哈希
  `b31f1ad36c5111d1171595ec2c8769599348d2da8e286fb0f572a161c6238137` 和历史 manifest
  `7405feccad1c014edbae8833ce260e2db67772b96d90d2814af9892203382142`；回归不读取当前 Registry。
  三项 operation、resolver 及其 Profile/Prompt/Deployment/Output/StepBudget 闭包与历史提交逐项一致。
- 独立复核收回了两项不应夹带的行为：保持原同章节 mutation 互斥，额外覆盖不同章节但同一大纲来源；
  任务列表不加载或返回完整报告，只有 GET 投影全文。没有修改生产部署、DDL 或活动 Skills。

当前 Catalog 7/21 已启用，共享 Schema 238 个，执行资产 fingerprint 为
`2db29fa6d5e31651e0932e710c8da991c8ecdffe12dcafca57ca617f6023edbb`。
公共 Core 152、内部 Core 34、供应商媒体入口 1、CLI 125 和 Operator 45 命令均未增加。

隔离验收历史报告保持原样：

- `output/durable-agent-v2-e2e/20260905-review-rewrites-1/report.json`：Agent 镜像未包含最后的输入校验修复，
  源码哈希检查拒绝，0 场景执行，清理有效；不能用该镜像代表最终源码。
- `output/durable-agent-v2-e2e/20260905-review-rewrites-2/report.json`：重建后的镜像源码哈希一致；
  无会话审阅、有会话且 Core 重启后恢复报告、自然审阅、显式场景编辑批准四场景通过。自然场景的合法
  operation=null 中间态被验收脚本误判，已修正等待断言并补回归；业务实现未因此放宽。清理有效。
- `output/durable-agent-v2-e2e/20260905-review-rewrites-3/report.json`：同样前四场景通过，后续自然场景
  批准已完成，但脚本错误要求决定回执与 GET 完全相等。源码确认决定回执 taskId 为空、GET 为 runId 是
  既有兼容投影；现只允许这一处差异，剔除该别名后其他完整字段必须相等，revision/Artifact 漂移有负例。
  没有为此修改业务响应，清理有效。
- 最终 `output/durable-agent-v2-e2e/20260905-review-rewrites-4/report.json` 为 passed，九场景全部通过：
  无会话审阅、有会话且 Core 重启恢复报告、自然审阅、显式场景全文编辑批准、自然场景批准/丢弃、
  总纲选区编辑批准、节点选区编辑批准、大纲选区同 Run 返工后丢弃。
  每个模型 Step 的 Fake Provider 物理调用恰好一次，独立 reservation/TokenUsage 精确匹配；
  无 V1 Task/Command、无重复候选/消息/事件/应用。审阅未改正式层，场景采用失效旧终检，
  大纲选区外逐字不变且其他正式层哈希不变。容器、网络、卷和临时密钥全部清理，零残留。

最终验收复用的 Core 镜像为
`sha256:4f718f71bd6354512d04bd6fde759ea0950578f7f4a25dfe7a8e767163ca321f`，Agent 为
`sha256:122348dab2aa1d6eac65538d82cc79eacd47b942261b96255b7bc756846134e4`，Agent 关键源码与镜像哈希一致。
本阶段没有访问真实开发库、生产或真实供应商，2 核 2 GB 整机性能仍为 not_proven；未更新活动 Skill 或本机固定 JAR。
其余 14 项业务 Catalog、需要的系统用途、V1 退役和真实环境切换/验收仍属于原总目标，不把本阶段完成当作总重构完成。
