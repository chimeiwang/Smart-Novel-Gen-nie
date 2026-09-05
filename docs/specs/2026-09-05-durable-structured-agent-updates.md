# Durable Agent V2 设定、大纲与伏笔迁移

日期：2026-09-05。状态：共享模型、语言中立 Schema、Core 来源读取、不可变候选、完整 Diff/写入物化、
生成回调及审核详情/决定已通过本地隔离验证；Agent 执行、证据扩展、自动返工策略与入口尚未全部接通，五项尚未启用。

## 范围复核结论

用户要求在现有功能不变的前提下重构 Agent，并要求 CLI 变化有明确说明。五项业务迁移原本就在
2026-08-31 计划中，但这不能授权任意增加采用限制或对外接口变化。此前本草稿把“全资料 CAS”、
“replace 禁止逐项采用”和新的公共聚合 target 写成既定方案，范围把握不当；这些选择现已撤回。
其中全资料 Reader、写路径锁和聚合公共 target 从未实现；未接入的独立 SelectionPlan 也撤回，直接复用现有过滤语义。

下一步只接通现有功能的耐久执行，不借此统一清理 V1 的边缘行为，不加入新的安全或发布控制面。
确定性协议检查用于拒绝无法写入现有领域的数据，不能把作者现有合法选择变成不允许的操作。

## 目标与非目标

在当前 `codex/durable-agent-execution` 分支继续既定 Agent 内核迁移，接通
`long_serial.create_lore`、`revise_lore`、`create_outline`、`revise_outline` 和 `manage_foreshadowing`。
前序检查点为 `cb519ba`；当前仍为 7/21，不能因本规格或共享模型存在便改称 12/21。

本阶段不新增创作领域、数据库列或表，不重做发布流程，不修改固定安装 JAR、活动 Skill 或 Operator 白名单；
不执行远程写、真实库迁移、生产部署或真实供应商调用。普通 CLI 的既有 start/get/watch/artifact 命令继续只访问
Core 公共 API，具体输入与部分采用变化必须同步到 Skills 更新契约。

## 已核实的兼容语义

五项 V1 业务都生成 `agent_updates`，并可在同一候选中同时包含不同资料分区。操作名称代表创作意图和主责
Profile，不是一个互斥的资料分区或 CRUD action 白名单。不得把五项拆成禁止跨分区的三个输出类型，
也不得把 create/revise 强行限制成只能 create 或只能 update。正式写入继续由作者确认后的
`AgentUpdatesExecutor` 在同一个 Core 事务内调用现有领域仓储完成。

V1 Agent 的 propose/builder → artifact_contract → CoreArtifactPort → Java Review 接口链路不经过 Web
sanitizer。正式能力以当前 Java writer、共享/公共契约及测试为准，不能取旧 Web 类型的较窄交集。
已存在的 `outlineAdjustments.order`、`linkedChapterId` 和 `references.sourceUrl` 必须保留。
不扩展到 writer 不支持的角色关系、WritingBible、PlotProgress、Novel.storyProgress、chapterTitle 或 payoffNote。

### 完整输出和字段存在性

使用一个严格 `AgentUpdatesOutput`：`{summary, updates}`。summary 保留原始文本及已有 1..1000 字符约束，
不复用会 strip 的文本类型，不额外要求非空白。updates 中支持下列分区同时存在：

- 十个数组：characters、locations、items、factions、glossaries、characterExperiences、outline、
  outlineAdjustments、foreshadowing、references。
- 三个全文：outlineContent、worldSetting、storyBackground。
- outlineTreeMode 是 outlineAdjustments 的 patch/replace 控制，不单独计为一个更新。

至少有一个非空数组或一个实际提供的全文。缺少字段表示不修改；顶层分区 null 非法；全文空串仍表示显式清空，
不能 trim、丢弃或当作未提供。数组及全文不新增任意条数/字符上限，超过现有传输或模型预算应明确失败，
不能静默截断。每个对象拒绝未知字段；内部可用 action 判别单项类型，顶层分区不能互斥。

五类设定实体及角色经历、参考资料保留 create/update/delete；伏笔保留 create/update/payoff/abandon。
outline 仅承载 nodeId 及 status/actualWordCount 中实际提供的更新；outlineAdjustments 承载现有节点结构字段，
保留 nodeId/nodeTitle、clientKey/parentKey 及 patch/replace 语义，replace 只能包含 create。
新增/修改字段类型以 `apps/core-api/src/inkforge_core/lore/schemas.py`、outlines/schemas.py、references/schemas.py
及 Java 领域验证为依据；可空字段的显式 null 与未提供必须区分，不能通过 model_dump 默认填充把未修改字段清空。
身份字段只复制已冻结的已有 ID 或现有唯一名称定位语义，不使用有额外长度或 strip 行为的通用文本类型来改写它们。

共享模型必须保留现有 writer 的解析优先级，不用更严格的模型代替业务变更审批：

- 五类设定实体同时提供 id 与类型专用 ID 时，仍按 id 优先处理，不新增两者必须相等的约束；
  空 id 仍回退类型专用 ID 或现有名称定位。references 则保留 writer 已有的非空 id/referenceId 一致性要求。
- patch 中重复 clientKey 仍由后创建节点覆盖映射，后续 parentKey 指向最新映射；只有 replace 拒绝重复 key。
- 有效 parentKey 仍覆盖 parentId；replace 中被覆盖的旧 parentId 不能单独导致失败。
  空 clientKey/parentKey 仍表示没有临时映射；patch 中父节点可能经中间 update 改型，共享模型不能按
  最初 create.kind 拒绝后续子节点，实际层级交给 Core 顺序验证。
- 不把公共表单 Service 的校验搬到实际绕过该 Service 的 Agent writer：设定 name/term、带 ID 的伏笔 name、
  带 ID 的参考资料 title 保留可写空串/空白的旧行为；伏笔 create 只要求非空字符串。
  大纲标题及参考资料 create 标题保留实际 writer 的非空白检查，并与 Java String.strip() 的空白集一致；
  序列化不修剪、归一化或替换原文。
- 角色经历 order、大纲 order/字数/章节序号使用 PostgreSQL INTEGER 的有符号 32 位表示范围；
  这不是新增字数或章节数量产品限额。章节范围保留实际领域层的正数规则；order 及字数不套用仅存在于
  公共 DTO 的非负约束，不能在内部迁移时顺便更改旧 Agent 写入行为。

这些检查只约束结构化候选，不表示五项已有可运行链路；数据库归属、现有节点及正式应用仍由 Core 验证。

### 模型与 Core 派生数据分离

Provider 只生成 summary 和业务 updates。已有资源 ID 可从 Evidence 复制，节点 clientKey/parentKey 是候选内
临时关系标识，不是持久化 ID。模型不生成 clientRequestId、expectedUpdatedAt、内容哈希或费用；
Core 根据冻结来源与 Run/Artifact 身份补齐现有 writer 需要的幂等键、CAS 时间和真实资源定位。

Agent 完整校验 Provider 输出后只派生 `updatesSha256`，形成严格 `AgentUpdatesResult`；
哈希针对保留字段存在性的 updates canonical JSON，Core 再次复验。不能从叙述正文猜测 JSON、补业务字段或
在失败时退回 V1 工具循环。共享输入保留完整 userInstruction；返工额外成对携带 originalUserInstruction 和
同一候选的 artifactId、artifactRevision、summary、updates，不读取可变 workspace。

模型无需输出 fieldChanges。现有 Java writer 从不把它作为业务字段写入，主 UI 读取的也是 Artifact.diff；
V2 由 Core 从冻结 before 与严格 update/action 确定性派生完整 Diff，不让模型重复或伪造 oldValue/newValue。
正式应用仍只读取经过验证的 updates，不从 Diff 反推命令。

### 不可变候选与执行输出 Schema

下一切片使用独立 output.agent_updates.v2 作为严格 Provider 输出资产，复用现有 model_output_schema()
内联路径，不改通用 JSON Schema 校验器；原 output.agent_updates.v1 占位内容保留。仅新增受支持的输出
资产不代表五项 Operation 已启用，Profile、Step Budget 和 planner 未接齐前继续保留 v2Enabled=false。

Core 在候选入口同时校验冻结 Provider Schema 和共享模型无法导出到 Schema 的确定性语义，并要求 Result
精确只有 summary、updates、updatesSha256，按保留字段存在性的 updates 重算哈希。Core 的语义检查必须与
已验证的 Python 共享模型一致，不能重新加入已撤销的双 ID 相等、patch key 唯一或动态父类型限制。

durable.agent-updates-artifact.v1 只规范保存一份原始候选，以及 operation、novelId、Evidence bundle/manifest、
生成 Step/result hash；不把正式写入需要的 CAS、create 请求键或完整 Diff 再交模型。存储 Diff 仅为可重建
标记，展示和采用时从冻结事实派生完整 Diff/兼容 writer payload，不复制第二份候选作为权威。
重建必须复验候选、冻结 Schema、来源身份和用途，失败不能被当成新的模型生成或从当前 Head 补数据。
生成 Step/result 身份必须与调用方从权威生成记录取得的期望值比较，不能仅检验格式，也不能用候选自身
的同名字段冒充期望值。候选摘要与完整 Step 结果的对应关系仍须在后续回调/读取适配中核验；独立值对象
不能代替该数据库来源链的验收。

## 复审和用户决定

保留“设定/伏笔由校验复审，大纲由编辑复审”的职责。新建结构化资料专用 Reviewer Profile/Prompt/Rubric，
不能修改已用于章节选区的 reviewer.consistency.v1 或 reviewer.editorial.v1。
生成器与 Reviewer 使用完全相同的不可变 Evidence 和精确 Artifact revision。

遵守总规格已批准的最多一次自动完整返工、生成 1 + Reviewer 1、全 Run 最多 4 个模型 Step；
不照搬 V1 默认五轮。结构化资料不支持正文 text_replace patch，也不解析 Reviewer 建议散文来修改字典。
Reviewer 不可用保留候选并明确“自动复审未完成”；剩余问题交作者，不把软质量建议升级为硬失败。

保留既有 `selectedUpdateRefs` 部分采用。省略或 null 是全选，空列表不能偷偷按全选处理；section/index
始终指原候选，不先过滤后重排。V2 只对 agent_updates 的 approve 接受该字段，其他 V2 Artifact 和
discard/revise 继续拒绝；公共契约只校验形状，Core 在锁定实际 Artifact 后校验种类及引用。
不新增 editedUpdates 参数：旧 AgentUpdates 没有结构化用户编辑 API，仍用部分采用或明确返工完成决定。

采用直接复用现有 `AgentUpdatesExecutor.filter`，不维护另一套更严格的选择规则：未知/越界引用的忽略、
文本引用、去重、全分区覆盖逐项、原数组顺序和空列表最终无更新错误都保留原行为。
replace 仍表示用所选、合法的候选节点替换整棵旧树，不能一概禁止按 item 选择，也不能自动补选作者未选的节点
或偷偷改成 patch。UI 应说明原有 replace 的真实效果；合法性仍由现有结构/父引用规则判断，失败在整个事务内回滚。

全文空串与缺少字段在完整候选中继续严格区分。V1 现有全选路径可应用空串，而指定 refs 的 filter 会丢弃空串；
本次迁移保持这一选择语义，不顺带把部分采用改成新的清空动作。若后续要统一它们，必须作为单独产品变更说明。

## 来源与采用原子性

遵守原规格的“目标实体及直接关联”最小充分 Evidence，不采用统一完整 workspace 或全资料哈希门禁。
生成、复审和恢复保留不可变来源；正式采用按实际写入目标及必要直接依赖核验归属、原值和版本。
没有参与所选更新、也不是必要依赖的资料变化，不得单独阻止采用。冻结上下文用于重建模型输入，
不等于把所有读取过的资料自动变成全局写锁或冲突条件。

定向读取基础使用 Core 内部的资源类型/ID 清单，不新增公共 target 或 CLI 参数。每项单独保存完整目标行、
实际外键引用和具名直接关系集合；关系集合即使为空也保留空集合事实。角色经历通过所属角色核验小说归属，
章节引用只提供章节元数据，不顺带读取正文；伏笔的 plantedAt/payoffAt 是文本，不臆测为章节外键。
单例全文缺失可表示为绑定小说的 absence，具体操作是否允许缺失继续由 planner/writer 判断。
数据库表名和关联条件来自固定代码映射，模型不能提供 SQL。相关记录在调用方事务内锁定，读取不提交事务，
不增加新的全小说锁。跨目标来源分开标识，不在读取器中提前实现全局 CAS。

删除依赖必须由 Core 明确请求；现有 writer 对有关联的人物、地点、组织及有直接子节点的大纲拒绝删除，
不能把数据库外键的级联/置空能力当成 writer 会自动执行的清理。大纲单节点删除只核直接子节点集合，
replace 才把整个旧树作为实际删除目标。生成/复审引用和删除依赖带不同用途标记，正式采用只能按
所选动作取必要投影复验，不对整份参考 bundle 做一刀切相等比较。该读取基础先以隔离 PostgreSQL 测试证明，
随后再接 operation planner；仅存在读取器不代表操作已启用。

用途采用 metadata.roles 明确列举：同一直接关系若同时是删除阻断条件，保存一份快照并同时标记
direct_relation/delete_impact，不能要求批准适配猜用途或重复复制关系全文。人物关系和组织领地关系须核验
两端都属于当前小说；遇到异常跨小说行应明确失败，不能收入其他作品的关系内容，也不能静默过滤删除阻断事实。

读取器本身不完成 approve CAS，也不能靠空结果的 FOR UPDATE 防止新增成员。后续 planner/批准适配必须
复用现有领域事务与 Novel/advisory 锁顺序后查询必要空集、单例缺席或 replace 成员集；只冻结/比较所选目标，
不将锁的技术串行范围转化为新的用户冲突规则。现有 FK SET NULL 不一定推进宿主 updatedAt，故正式目标
还必须复验完整可写 before 的哈希，不能只比时间戳。

Core 必须在同一个正式事务内完成所需来源锁定、CAS、已有 filter、现有 writer 和 Run/Artifact 终态；
不能在检查之后释放锁再写，也不能让模型生成 CAS 元数据。复用现有领域验证和事务行为，
不为未采用的全资料方案修改所有伏笔写入口或增加公共 CAS 字段。

初始证据、跨分区目标覆盖、所选节点的结构依赖与删除影响须逐操作补测试后接线；不能用本规格取代实现证明。
模型要求更新的真实目标若没有必要的冻结来源，必须显式补齐合法证据流程，不能偷偷读当前 Head 后当作旧来源。
后续接线应遵守总规格已有的 EvidenceExpansionRequest → Core 验证 → 新 bundle revision/新 Step 路径，
仍消费原 Run 预算；不能以一律禁止跨分区更新来替代必要证据补齐。当前切片没有实现这条扩展链路。
只读规则和删除依赖不成为可写分区；没有 updatedAt 的关系不能伪造时间。总纲绑定真实 Outline 行，
create_outline 不负责创建缺失的 Outline 行。Reference 只使用正式资料，不把可重建 RAG 状态纳入业务 CAS。

以下为后续 Core 接线要求，当前共享模型尚未实现这些业务链路：`DurableAgentUpdatesArtifact` 应保存真实
operation、novelId、Evidence bundle/manifest、生成 Step/result hash、原顺序的完整 Provider updates 与派生
candidate hash。Core 应从冻结原值唯一解析已有 ID/名称，确定性注入
writer 所需的时间戳与稳定 create 幂等键，物化为既有 `{kind:'agent_updates',updates,baseOutlineUpdatedAt,
baseLoreUpdatedAt}` 兼容形状及完整 Diff。新建同名资料仍按旧规则处理；update/delete 名称零或多匹配拒绝。
原候选、物化结果与派生 Diff 都可从冻结事实验证；不从当前 Head 拼回遗失信息，不让模型控制 CAS 元数据。

## 公共目标、自然入口与互斥

优先保持现有公共请求与 CLI 用法，不因内部 Catalog 的 lore/outline/foreshadowing 标签便新增一套
要求调用者重写命令的公共 target。公共章节锚点与内部正式资料目标明确分开，具体目标由 Core 根据
已验证的请求、scope 和冻结来源确定，不能由模型猜 ID。当前选区入口已有两者分离的实现，应先核对复用。

- create_lore、revise_lore、create_outline：显式 scope=novel。
- revise_outline：显式 scope=novel 或 outline_node，节点必须属于同一小说；scope 是请求焦点，不删除既有跨分区候选能力。
- manage_foreshadowing：显式 scope=novel 或同一章节锚点的 chapter。
- 五项执行链真正接通后再扩自然授权列表。默认范围必须保留原请求意图，不能因为数据库有 novelId 就擅自扩大。
  不让模型猜资源 ID、scope 或参数；resolver v2 Prompt 与 ProposedCommand 保持当前职责，历史冻结授权不扩大。

历史三项/五项计划 literal 保持原内容、哈希和预算；`durable.intent-selection.v1` 仍严格表示原当前章操作。
如果内部目标扩展确实需要新 selection 版本，只扩内部快照，不据此增加无必要的公共参数或重复持久化状态。

自然 Run 初始 operation=null、target=chapter/chapterId 不改；选择只追加控制 Step 事实，继续同一 Run。
保留现有请求冲突规则和 Dispatch 按 novelId 串行的实现。新操作所需的重叠目标校验应直接对应实际写面，
不先引入所有资料、所有未决请求一律互斥的新规则。显式和自然使用同一 planner，全部接线完成前不得翻转 v2Enabled。

## 预算

保留总规格确定的生成/复审各一次、最多一次自动返工、总 Run 最多四次模型调用。每个 Step 独立预算，
cache-miss 覆盖无缓存命中的情况，不能把 Run 总预算复制到单 Step。具体 token/金额/时长向量待最小充分
Evidence 与输出实现后按真实调用结构冻结，不把此前为全资料方案拟定的向量当作已经确认的产品限制。
人工返工仍消费原 Run 剩余预算，不能通过重派或更换 Profile 绕过总额度。

## 前端与 CLI 消费要求

Web 必须准确展示 Core 派生 Diff 中实际将被写入的字段，包括 order、linkedChapterId、sourceUrl，
不能让作者批准不可见变更。显示与采用保留现有语义，不把本次兼容迁移夹带成新的清空操作。
V2 agent_updates 的选择随决定提交，其他 Artifact 行为不变。不得用旧 sanitizer 清洗 Core 权威候选。
修改 UI 前继续遵守 DESIGN.md；保持现有交互结构，不夹带视觉重做。

通用 CLI 的操作集合、scope、自然入口授权及决定字段必须与 Core 同步；不新增仅包装现有端点的命令，
不自动扩大受限 Operator 的三操作范围。所有变化写入 README 和 Skills 更新契约，明确源码、构建产物、
安装和服务器生效是不同状态。

## 分步实施与验收

1. 先实现严格共享 Provider 输出/结果/返工输入模型、字段存在性及 action 回归，不启用 Catalog、不改路由。
2. 在 Core 来源与范围方案补齐后，实现不可变资料 Evidence、完整候选、Diff、来源/CAS 与正式 writer 适配，
   再接生成、复审、一次返工和作者决定；不执行 DDL。
3. 接显式及自然入口、旧计划兼容、Web/CLI 消费，保持已完成七项不变；业务功能完整前保留 v2Enabled=false。
4. 先定向 pytest/Ruff/Mypy/JUnit 与真实 PostgreSQL，后串行 Maven 全 verify、Python/Web/生成契约全量门禁。
5. 使用隔离 Compose/Fake Provider 验证五项、多分区、部分采用、整树依赖、空串/Unicode、来源变更、重复决定、
   同 Run 返工与重启恢复；核验正式数据差异、幂等、费用、事件和清理，不把本地测试当成生产或真实模型验收。

新增验收必须覆盖：无关资料变更不阻止当前合法采用、实际目标或必要依赖变化仍会冲突、合法 replace 子集仍可采用、
无效父引用整体回滚、跨分区与 create/revise 反向 action 正例、原有字段完整展示、全文空串/字段存在性及原有过滤语义、
CLI 调用保持兼容、真实写面冲突，以及旧 resolver v1/v2 与旧 selection v1 恢复。

## 本地验证记录（2026-09-05，仅共享模型）

本切片实现十个数组分区、三个全文分区的 Provider 输出、结果哈希和返工输入模型，保留字段存在性及原文；
没有实现或注册五项业务 planner、Evidence reader、Artifact 应用或模型执行资产。

- 兼容修正后，`uv run pytest -q`：4738 passed、3 skipped；日志为
  `/tmp/inkforge-structured-contract-python-full.log`。保留既有 Starlette 弃用警告。
- 随后终审补正删除大纲节点的 title/nodeTitle 优先级，并新增四个组合回归；补改后执行
  `uv run pytest packages/service-contracts/tests -q`：697 passed，其中当前结构化模型为 175 项；日志为
  `/tmp/inkforge-structured-contract-package-final.log`。全仓数字不冒充补改后的全量重跑。
- 最终 `uv run ruff check .`、两个新 Python 文件的 Ruff 格式检查和四个服务/共享源码目录的 Mypy 均通过；
  Mypy 覆盖 281 个源码文件，日志为 `/tmp/inkforge-structured-contract-mypy-final.log`。
- `npm run api:check`、执行资产 manifest `--check` 和 `git diff --check` 通过。
  新模块尚未加入语言中立 Schema 导出器，共享 Schema 清单仍为 238；不能据此声称跨语言契约接线已完成。
- Catalog 仍为 7/21；Java Core、Web、CLI 及执行资产源码相对 `cb519ba` 无变化，因此本切片未重跑
  Maven、Web 构建或隔离业务 E2E。后续 Java 全量门禁使用 clean verify，避免已撤回类的旧编译缓存影响结果。

普通 CLI 命令、参数及 Operator 范围均未变化，无须因本切片更新已安装 Skills；后续实际接线影响消费者时，
再同步 CLI/Skills 更新契约。没有执行部署、真实库迁移、远程写、真实供应商调用或安装包更新。

## 后续本地进展：Schema 导出与定向来源读取（2026-09-05）

在上节共享模型基础上，现有导出器已纳入 agent_updates，排除七个私有基类，新增 34 份公开模型 Schema；
共享清单由 238 增至 272。这些是协议生成文件，不是新增 34 个操作。新增 Schema 保留标准 $defs/anyOf，
已通过全部文件的 JSON Schema 编译和可重现导出测试。现有 Java DTO 生成器仍只消费两份 OpenAPI baseline，
不直接消费这批独立 Schema；后续执行 Schema 应复用现有内联生成路径，不能据此宣称 Java DTO 接线完成。

Core 新增 AgentUpdatesEvidenceReader 端口和 JooqAgentUpdatesEvidenceReader：按明确资源 ID 返回目标、
一跳引用、具名关系集合及显式删除依赖；不读取完整 workspace，不截断被选内容，不读 RAG 派生状态。
关系用途通过 metadata.roles 明确表达，关系两端小说归属会复验，无 updatedAt 的关系保留空时间与完整内容。
该类当前由测试直接构造，尚未装配到 operation planner，也不承担最终选中项 CAS。

真实隔离 PostgreSQL 测试覆盖 13 种来源类型、完整长文本、单例缺席/空串、经历间接归属、
人物/领地跨小说关系、无关变更隔离、更新时间不变但字段改变、空集合/无时间戳关系、完整删除依赖用途、
快照深冻结和外层事务持锁生命周期。首轮失败只来自测试 fixture 的 RagSourceType 拼写错误，已按冻结枚举
reference_material 修正；随后 9 项通过，复核补充两项关系归属测试及删除用途断言后 11 项全部通过。

最终验证结果：

- `./mvnw clean verify`：五个 reactor 全部成功；服务身份 11、服务契约 5、Core 882（含 3 skipped）、
  CLI 127，无失败或错误。日志 `/tmp/inkforge-structured-evidence-maven-full.log`。
- `uv run pytest -q`：4742 passed、3 skipped，保留既有 Starlette 弃用警告；日志
  `/tmp/inkforge-structured-evidence-python-full.log`。
- 共享契约及导出定向测试 698 passed；四个服务/共享源码目录及导出脚本的 Mypy 覆盖 282 文件并通过；
  全仓 Ruff、api:check、执行资产 manifest --check、git diff --check 均通过。
- Java 门禁只使用隔离 Testcontainers，结束后测试容器清单为空；没有访问或迁移真实开发库/正式库。

Catalog 仍为 7/21，执行资产、Web、CLI 源码和已安装 Skills 没有变化；没有部署、推送或更新安装 JAR。
下一步仍须完成：初始最小索引/目标解析及 Evidence 扩展、候选与 Diff 物化、先 filter 再按所选项复验的
事务适配、生成/复审/返工及显式/自然入口，最后补齐 Web/CLI 消费与业务 E2E。上述基础门禁不能替代这些验收。

## 后续本地进展：严格执行输出与不可变候选（2026-09-05）

执行输出 Registry 新增 output.agent_updates.v2，机械派生自 AgentUpdatesOutput；仅包含 summary/updates，
不让 Provider 生成 updatesSha256。新输出 Schema 哈希为
`1ebda5ea441d2f421199725ebdad05f9add5abc44875e040252e2b41810a3467`，执行 manifest 指纹为
`8ee66362cf8d8547ac25fa3a5372a54c4924a3321e95f5f437338bb67f0c508f`。原 output.agent_updates.v1
空占位及哈希原样保留，五项 Operation 仍未切到新输出资产，也未启用。

DurableAgentUpdatesArtifact 已提供原始候选的 create/output/reconstruct：冻结 Provider Schema、确定性语义、
updates 哈希、五项 operation、小说、bundle/manifest 和生成 Step/result 身份会复验；嵌套 updates 深冻结且
保留缺省、显式 null、空串和原文。reconstruct 的生成 Step 身份期望值由调用方显式传入，合法格式但不匹配的
身份同样拒绝。该类没有正式 writer 元数据、完整 Diff 或数据库调用，不能称为作者采用事务已实现。

Python 与 Java 共用 `apps/core-api-java/src/test/resources/protocol-fixtures/agent-updates-semantics.v1.json`
中的 50 个固定用例，覆盖既有 ID/名称优先级、空白文本差异、整型范围、可空字段、业务字段存在性、
parentKey/parentId、patch 重复 key/动态父类型及 replace 限制；并补全嵌套深冻结、长文、结果字段/哈希和
合法格式身份替换的 Core 用例。通用 WorkflowOutputValidator 没有修改，也未改造 Java DTO 生成器。

最终门禁：

- `./mvnw verify`：服务身份 11、服务契约 5、Core 941（含 3 skipped）、CLI 127，五个 reactor 全部成功；
  日志 `/tmp/inkforge-agent-updates-candidate-maven-full.log`。
- `uv run pytest -q`：4793 passed、3 skipped，仅保留既有 Starlette 弃用警告；日志
  `/tmp/inkforge-agent-updates-candidate-python-full.log`。
- 定向 Python 253 passed；最终全量包含 Core 候选 59 项。Ruff、Python 格式检查、覆盖 282 源码文件的
  Mypy、api:check、执行 manifest --check 和 git diff --check 均通过。测试容器已自动清理。

Catalog 仍为 7/21，Profile/Deployment、公共 API、CLI 和 Web 未变化；未推送、部署、更新安装包或调用真实模型。
后续事务适配必须保留原数组索引来派生稳定 create 请求键，不能按过滤后的新下标重编号；大纲中引用同一
候选前面新建的节点也不能被误当成缺失的历史数据库节点。仍须先复用现有 filter，再只读取所选动作的必要
冻结来源来构造采用门禁，不将未选资料的 Head 变化或独立值对象校验当作完整业务闭环。

## 所选建议的事务适配

本轮复用 AgentUpdatesExecutor.filter 和现有领域写入器，不新增公共采用参数、整小说来源 CAS 或发布设施。
冻结来源索引按真实业务 ID 收录完整目标和直接引用；Reader 的十二种具名集合均可按名称取出，只有
character_experiences、outline_children 的完整行允许额外作为目标来源，删除依赖的结构投影不能冒充完整行。
仅整树替换另冻结 outline_tree_membership（按 ID 排序的成员列表），包括显式空集；不能从“没有节点
Evidence”推断“已冻结空树”。它不参与普通节点 patch、人物或其他资料的采用门禁。

采用适配输入为 Core 已物化、已解析历史目标 ID 的建议，不直接接受 Provider 输出；名称解析和完整 Diff
仍属于采用前的物化步骤。先按作者原 section/index 过滤，仅核验实际写入目标及明确依赖；目标完整快照
（含时间）必须一致，不能仅凭 updatedAt。使用既有 Novel 行锁、advisory 锁顺序，全部写入加入同一
CoreDatabase 事务。连续修改同一目标时，只在写入前核验一次冻结来源，后续 writer CAS 使用本事务前项
写入产生的时间，不能把外部新版本当成原始来源。大纲调整仍整组交给现有 writer，保留 parentKey 和合法
replace 子集语义。稳定新建请求键绑定 Artifact/revision/原始 section/index，不使用过滤后的数组位置。

隔离 PostgreSQL 验证必须包含：未选目标变化不阻塞、所选目标同时间异内容冲突、只读引用无关字段变化不
阻塞、重复修改、后项失败回滚前项、外层审核事务回滚、单例缺席竞争和 replace 子集。基础类通过不代表
五个业务入口已启用；生成、复审、返工、物化、采用与消费者仍须逐项接通后才能改变 Catalog。

实现已落在 AgentUpdatesFrozenSources、JooqAgentUpdatesApplier 和现有 AgentUpdatesExecutor 的显式
applyMaterialized 路径。旧 apply 路径保持原行为；物化路径的无 ID 大纲名称只在本组刚新建的节点内解析，
不按当前数据库名称重新定位历史目标。普通历史目标及经历所属人物未解析成 ID 时不能绕过冻结来源。
同一真实行在多个目标/直接引用中完全一致时去重，只有冲突快照拒绝。整树来源只读取每个节点一次完整行
及显式成员清单，不为每个节点重复展开整组兄弟信息。所选目标冻结后被删除明确报告 SOURCE_CHANGED。

在 8a23d0d 检查点，此适配仍由测试直接构造，尚未装配进 JooqDurableReviewDecisionStore。调用方必须从权威候选及其冻结
Evidence 物化输入并在同一审核事务记录 Artifact/Run 终态；不能让调用方自报 updates/来源代替这条链。
该检查点的名称唯一解析、默认 order 的冻结派生、同候选新建人物与经历等跨项身份映射、完整 Diff 以及生成
Step 来源链当时尚待完成；本节基础适配验证不单独代表原始 Provider 建议已能直接采用，后续进展见下节。

本轮验证结果：

- 新增来源索引 8 项和隔离 PostgreSQL 采用测试 18 项全部通过；包括只采用原下标、未选来源变化、
  同时间字段/FK 改变、只读引用变化、人物/参考资料连续修改、单例缺席、稳定创建键、replace 合法子集、
  缺父项回滚旧树、显式空树、批内同名节点和已删除来源。跨领域回滚测试在第二次真实仓储调用前读取到
  第一次写入，再验证后项失败后第一项恢复；外层审核事务失败和锁生命周期另有独立测试。
- `./mvnw verify` 五个 reactor 全部成功：服务身份 11、服务契约 5、Core 967（3 skipped）、CLI 127，
  无失败或错误。日志 `/tmp/inkforge-agent-updates-applier-maven-full.log`。
- `uv run pytest -q`：4793 passed、3 skipped，仅既有 Starlette 弃用警告；日志
  `/tmp/inkforge-agent-updates-applier-python-full.log`。全仓 Ruff、四个服务/共享目录 Mypy（281 文件）、
  api:check、执行 manifest --check 和 git diff --check 通过。
- 未修改 Web 源码，未重复 Web 构建；测试仅使用隔离 PostgreSQL/Redis，Testcontainers 清单已为空。
  公共接口、CLI 命令和执行资产未变化，Catalog 仍为 7/21，无须更新活动 Skills；没有推送、部署、
  真实库变更、真实模型调用或安装包更新。

## 建议物化与审核读取接线

下一步把冻结候选转换为现有 agent_updates payload 和 Web 已支持的数组 Diff，不新增公共 DTO、CLI 参数
或选择协议。Diff 使用 `{section,action,name,fields:[{field,label,oldValue?,newValue?}]}`；旧链路没有可直接
复用的完整 builder，不能复活依赖可变 workspace 或信任模型 fieldChanges 的历史实现。

Core 冻结一份 agent_updates_index 最小名录，仅含同小说资料身份/名称及必要的父级、类型和顺序，不含
无关正文。名称唯一解析以该名录为准；实际被修改的历史资料仍须取得完整冻结来源，不能把名录当作 before。
按现有 writer 的分区顺序和每个分区原顺序模拟临时状态，保留同候选先新建再更新、重命名后定位、删除、
patch 临时 key 覆盖及 replace 部分采用。未提供的经历/大纲顺序从冻结名录和本候选前序动作派生。

稳定创建身份统一绑定 Artifact/revision/原 section/index，复用现有 CommandResourceId。V2 内部 writer
为大纲和伏笔补上确定性创建身份，以便跨项引用刚创建的资源；旧公共创建入口及 V1 writer 原行为不改。
这些 Core 元数据不进入 Provider 输出契约。采用时只有真正选中的创建动作可以建立批内身份，引用未选
创建项必须按旧写入规则失败并整单回滚，不自动补选。

审核详情和决定必须复验精确修订、冻结 Evidence item 哈希和 bundle 归属，以及对应生成 Step 的 Run、
Artifact/revision、结果哈希与完整输出；期望身份来自权威 Step，而不是候选自报。读取重建不得访问当前
业务 Head。全部接线完成且端到端验证前，五项 Catalog 继续关闭；本轮不部署、不修改真实库或活动 Skills。

本轮 Core 实现：

- AgentUpdatesMaterializer 按原分区/数组顺序从冻结名录及完整 before 派生 writer payload 和数组 Diff，
  支持重命名后的唯一名称定位、批内创建/修改/引用、缺省顺序、删除完整旧值和 replace 旧树隐式删除。
  空串、null、未提供字段和原始 Unicode 文本不混同；Diff 不作为写入权威。
- AgentUpdatesIdentity 与既有 CommandResourceId 统一创建身份；V2 大纲/伏笔创建补上稳定请求，旧入口
  不变。所选集合不含依赖的创建动作时，不自动补选，不伪造历史来源，整个采用事务失败。
- 生成回调注册五个结构化结果处理器，先在同一事务存候选并经审核域端口核验来源及物化，再写终报和安排
  Reviewer。Step output 只保存 artifactId/revision/updatesSha256 指针，原始候选仍由精确修订保管。
- 审核详情复验完整 manifest 与逐 item 哈希，按同 Run 生成 Step 的产出指针定位权威生成记录，并用原始
  output、真实 resolvedModel/usage 重算结果哈希；摘要和 updates 都参与。历史详情不依赖当前作品 Head。
  公共详情直接返回既有 Web 支持的 Diff 数组，且精确修订的 summary 不取可变 head 摘要。
- 用户 approve/discard/revise 接入同一 Run；仅 agent_updates 的 approve 接受 selectedUpdateRefs，采用
  调用前序事务适配，Run/Artifact/决定 Step 同事务提交。人工返工携带原始 summary/updates，不把物化元数据
  回灌 Provider，也不按已过滤的数组重建原候选。

本地回归已真实贯通生成回调 → Reviewer 回调 → 精确详情 → 作者采用 → Run completed；另以五种 operation
的内存冻结计划覆盖部分采用、冲突时决定/状态回滚、幂等重放、原始候选返工和结果摘要不匹配拒绝。
这些计划复用已注册测试模型/预算，仅证明 Core 接线，不是五项真实 Profile、Agent 执行或生产开放证明。
尚须完成正式 Profile/Prompt/StepBudget、Agent 生成和专用复审、EvidenceExpansionRequest 新 bundle/Step、
最多一次自动完整返工、显式/自然 planner 及对应 Web/CLI 业务 E2E；Catalog 继续保持 7/21。

本次接线后的最终验证记录：

- `./mvnw verify`：五个 reactor 全部成功，服务身份 11、服务契约 5、Core 987（3 skipped）、
  CLI 129，无失败或错误；日志 `/tmp/inkforge-agent-updates-materialization-final-maven.log`。
- `uv run pytest -q`：4805 passed、3 skipped，仅既有 Starlette 弃用警告；日志
  `/tmp/inkforge-agent-updates-materialization-final-python.log`。这是 CLI 修正后的全仓重跑结果。
- 全仓 Ruff 通过；四个服务/共享目录及 CLI 的 Mypy 覆盖 322 个源码文件并通过，日志
  `/tmp/inkforge-agent-updates-materialization-final-mypy.log`。
- `npm run test:web`、`npm run typecheck`、`npm run lint`、`npm run api:check` 和 `npm run build`
  全部通过，日志分别为 `/tmp/inkforge-agent-updates-materialization-web-tests.log`、
  `-typecheck.log`、`-lint.log`、`-api-check.log`、`-web-build.log`（相同文件名前缀）。
- 所有 Java 数据库测试只使用隔离 Testcontainers；最终测试容器清单为空，没有执行真实库 DDL、
  生产部署、远程写或真实供应商调用。

消费者复核发现并修正两端 CLI 原先一律拒绝 V2 部分采用的漏接：仅 verified 的精确 agent_updates
候选批准透传现有 selectedUpdateRefs，其余 V2 类型及返工/放弃语义不变，没有新增命令或参数。
Java/Python 共享成功 fixture 31 例、V2 错误 fixture 19 例均已验证；Python CLI 全目录另有 641 项通过。
源码候选 JAR 已构建，但没有安装到固定入口或改动活动 Skills。更新要求见
`2026-09-01-durable-agent-v2-operator-skill-update.md` 的“结构化资料 V2 部分采用”。
