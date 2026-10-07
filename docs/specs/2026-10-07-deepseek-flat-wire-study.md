# DeepSeek 工具参数包装简化规格

状态：实现及本地验证完成，完整 Linux CI、生产发布和真实任务验收待完成。本文取代
[默认 strict 规格](2026-10-01-deepseek-default-strict.md)和[空对象兼容规格](2026-10-07-deepseek-strict-empty-object.md)
中普通字段固定采用多层 value/variant 的表示规则；原业务校验、质量专用映射和安全边界继续有效。


## 本轮实施契约

用户于本轮明确同意实施上述调研方案，沿用本会话已经明确的提交、部署授权。实施在供应商适配层完成，
不迁移业务 Schema、数据库或正式内容。

- 普通标量、数组及业务对象直接传输正常值；可选缺省用闭合标记 `{"_inkforgeState":"omitted"}`，
  null 用 `{"_inkforgeState":"null"}`，无参/真实空对象保留非空独立标记。
- 正常分支接受某个状态标记或多分支不能证明解码一致时，使用明确的最小判别包装，不能把业务同名
  标记误解成缺省/null。JSON 字符串转换保持完整，字符串与 JSON 字符串的重叠联合不得猜解。
- 处理现有 5 个条件根联合，尽可能直接表达字段和现有业务判别值。模型可见 Schema 仍须表达原条件；
  根对象必须有 properties、字段全必填和 additionalProperties=false，不能为去根包装删除条件。
- 编码、解码、原业务验证、进程内历史重编码使用同一编译结果；解码歧义或不合法参数明确拒绝，不能
  自动把不合新 wire 的旧坏响应解释为业务参数绕过校验。已有历史业务输入仍无损重编码。
- 描述及合法形状提示从实际 codec 生成，说明标记含义。`ModelTurnResult.toolSchemaHints` 为排除序列化与 repr 的进程内字段；每次至多 10 个已暴露失败工具、每工具至多 10 个字段提示，只使用模型已见 wire Schema 的类型、状态说明和经字段 Schema 验证的标量示例。完整失败诊断和原参数不进入纠正消息，不新增纠正次数或计费调用。
- 两个 DeepSeek 传输入口均在原 arguments JSON 上拒绝重复键及非有限数，不能只校验 SDK 已经覆盖键后的字典；正常 JSON 的确定性闭合恢复仍受原有范围限制。
- 保留两个 DeepSeek Provider、非 DeepSeek/显式 strict=false、质量工具专用投影和冻结 V2 身份；
  更新 45 注册工具、12 Operation、24 写作工具及原故障样例的离线/传输回归。
- 完成专项、全仓 Ruff/Mypy 及完整 Linux CI 后发布，同轮清单身份、容量、schema、健康和回滚门禁
  按原流程验证。真实任务只经生产 Operator 或用户 Web 重试，不能绕过 Core 身份与计费。

## 问题与结论

用户要求盘点简化包装的改动范围，并判断是否可以适当平铺。调查基线为
`24761da4247258727d206b792a1e15b0f62c4b66`，生产代码为 `f16eb344`。
最新任务 `cmuy2h2m3z5s29bp82u2eejc4` 的两轮响应分别把可选字段的外层 `value` 或 nullable 联合的
内层 `variant/value` 漏掉，完整诊断已确认 wire 校验失败。本文提出减少这种人为包装的方案，不把它
等同于已经解释或解决供应商 strict 未约束住该响应的问题。

大部分额外包装可以减少。优先让正常值保持业务形状，在省略、null、真实空对象等情况下使用可区分的
状态标记；保留原本有意义的对象和数组。不能统一填默认值、丢字段、把空串/零/false 当缺省，或删除
条件分支约束。目标是可逆表示，不是改变工具的业务参数契约。

## 当前范围

以下数量来自当前注册表和编译器的离线运行，不是历史文档数量。全集使用工具默认模型 Schema，
Operation 另按 Agent 能力、Operation、执行模式权限及产物 Schema 收窄；两种口径不能混用。

| 注册工具分类 | 数量 | 建议 |
| --- | ---: | --- |
| 含可选/联合包装的工具 | 21 | 简单字段优先平铺，复杂根联合另审查 |
| 无参或空对象工具 | 11 | 保留非空传输标记，解码为业务空对象 |
| 已保持自然业务形状 | 10 | 不需要包装改造 |
| 仅含动态 JSON 字符串转换 | 2 | 保留完整 JSON 表示 |
| 质量报告专用映射 | 1 | 保持独立兼容协议 |

上述为互斥分组，共 45 个工具。21 个包装候选中另有 3 个包含动态 JSON 字符串字段，简化可选字段
不意味着可以移除这些字段的保真编码。共有 5 个根对象联合需独立设计。

当前 `write_chapter` 的 24 个工具中，7 个包装候选为：
`get_novel_info`、`find_similar_lore`、`semantic_search_references`、`list_outline_summary`、
`get_outline_node`、`get_recent_chapters`、`begin_artifact_output`。
其余为 10 个无参标记工具和 7 个自然参数工具。若把无参标记也计入任何表示转换，则为 17 个；
不能把这 17 个全部称为需要去除多层包装。

## 表示设计

### 正常值直接表达，特殊状态保留区别

当前 `count=6`：

```json
{"count":{"value":{"variant":"0","value":6}}}
```

建议的正常参数：

```json
{"count":6}
```

大纲索引同样可表达为：

```json
{"scope":"tree_index","include_full_summary":true}
```

为满足字段全必填，同时保留业务字段省略和显式 null，可以研究下列不同取值：

| 输入意图 | 候选 wire 值 | 解码后的业务参数 |
| --- | --- | --- |
| 提供数量 | `{"count":6}` | `{"count":6}` |
| 使用既有缺省逻辑 | `{"count":{"_inkforgeState":"omitted"}}` | `{}` |
| 显式 null | `{"count":{"_inkforgeState":"null"}}` | `{"count":null}` |

`_inkforgeState` 已选定为本轮状态标记；生产上线状态以本规格的验收记录为准。正常值与状态对象通过 `anyOf` 表达；对象闭合且
有必填属性。当前计数类正常值与标记对象类型不同，容易无歧义区分。通用编码器还必须检测真实业务
同名字段、同形对象及分支重叠，不能仅按出现某个键就把业务值当标记；无法证明可逆时保留最小判别包装。

调研阶段离线验证了上述三个 count 例子的候选 wire Schema 和解码后原业务 Schema，并确认越界数量、
布尔、空串、非法标记等仍被拒绝。没有改变生产实现，也没有证明供应商已接受候选 Schema。

### 简单联合与复杂对象分别处理

- 普通标量/数组与 null 的联合：可优先移除人工数字 `variant`；正常值直接表达，null 单独标记。
  全集有 71 个此类联合节点，按展开分支位置计数，包含重复字段；不是 71 个唯一业务字段。
  当前其中 55 个字符串、8 个布尔、5 个整数、2 个数字、1 个数组。
- 业务本身的对象/数组：如 `sceneBeats` 继续保留数组，每个节拍保留其业务字段；只去掉字段外的
  人工包装，不拆成没有关联的全局平铺字段。
- 根对象联合：`get_outline_node`、`put_update_item_text_block`、`show_review_artifact`、
  `begin_artifact_output`、`submit_evaluation`。优先利用现有 `kind/verdict/revisionMode` 或定位约束，
  研究直接业务对象的联合，不能把各分支字段简单取并集。`get_outline_node` 的 ID/标题是至少一个，
  允许同时提供，不能改成互斥二选一；多分支同时匹配时须证明解码结果相同，否则保留判别信息。
- 开放字典/任意 JSON：`updates`、`stages`、`blocks`、`conflicts` 仍需完整表示。第一阶段保留已有
  JSON 字符串转换；改为新的结构化对象属于额外契约设计，不能把动态键闭合后静默删除。
- 无参根和真正的空对象：生产曾明确拒绝无属性 object，不能直接退回 wire `{}`。保留小型非空标记。
- `submit_quality_report`：已有专用字段映射，不随普通工具重构改变。

### 业务语义不得改变

读工具当前默认值由 Core 执行：count 为 3、threshold 为 0.3、topK 为 5、scope 为 current_chapter，
两个 include 布尔为 false。可以在描述中说明，但不应为了省包装在通用编码器中复制或统一填充默认值。
普通工具顶层 null 在注册表校验中通常被省略，这不意味着所有嵌套字段也可合并。

两个必须回归的例子：

- `finish_update_builder.submitForReview` 省略时继承已有设置，显式 false 会覆盖它。不能把省略统一
  编码/解码为 false；对应实现为 `artifacts/builder.py` 的 finish 分支。
- 资料更新的字段缺席与显式 null/空串具有不同意义。共享 `AgentUpdates` 按 `model_fields_set`
  保留实际输入，Core 用 `containsKey` 构建 PatchField；默认补入 `currentStatus=active` 可能把未要求
  修改的人物状态改掉。开放更新字典的原始键和值必须完整保留。

## 改动文件与职责

| 文件 | 预计改动 |
| --- | --- |
| `apps/agent-service/src/inkforge_agents/providers/deepseek_strict.py` | 核心：重做 optional/null/union 编译及对应 encode/decode；处理碰撞和联合重叠；保留历史参数重编码、质量专用分支、wire→解码→业务完整校验及失败诊断 |
| `apps/agent-service/src/inkforge_agents/providers/deepseek_v4.py` | 复核实际下发与响应校验使用同一新 wire；共享编解码入口可保持，按实际需要调整错误路径映射 |
| `apps/agent-service/src/inkforge_agents/providers/openai_compatible.py` | 与原始适配器做相同兼容复核，避免 generic 下 DeepSeek 行为分叉；非 DeepSeek 行为不变 |
| `apps/agent-service/src/inkforge_agents/providers/base.py`、`providers/tool_schema_hints.py` | 排除序列化的 Schema 提示字段及提示生成器，只生成模型已见类型/状态和合法字段格式示例 |
| `apps/agent-service/src/inkforge_agents/runtime/agent_runtime.py` | 纠正：使用受约束的字段路径、预期类型、固定合法示例；保持坏参数不回放、完整诊断不进提示、原纠正预算及计费 |
| `apps/agent-service/src/inkforge_agents/tools/read.py`、`tools/control.py` | 按需补业务字段描述与 Operation 收窄说明；优先由适配器生成正确 wire 示例，避免人工写两套可漂移格式 |
| `packages/service-contracts/src/inkforge_contracts/read_tools.py` | 字段语义和原业务 Schema 的核对依据；仅改变 wire 时不必改业务契约 |
| `apps/agent-service/tests/providers/test_deepseek_default_strict.py` | 更新明确依赖旧包装的断言，覆盖全注册工具、缺省/null/空值、动态 JSON、根联合和历史往返 |
| `apps/agent-service/tests/providers/test_deepseek_v4.py`、`test_openai_compatible.py` | 两种适配器的真实请求替身与操作收窄后的 24 工具回归、新旧语义等价、失败诊断 |
| `apps/agent-service/tests/runtime/test_agent_runtime.py` | 纠正提示、非法整轮拒绝、无副作用、计费调用次数；如改提示需相应更新 |
| Agent 指导、03/04 号需求、相关 strict/诊断规格 | 实施前补正式规格，明确取代的 wire 规则及安全纠正边界；验证结果另入审计 |

条件根对象的业务限制定义在共享 `read_tools.py` 与 `tools/control.py`；不应为了生成更平的 Schema
删除这些限制。必要时增加仅供模型使用的投影，仍解码回原工具契约，并保留注册身份和权限。

## 历史与 V2 兼容

V1 会话和快照保存解码后的业务参数，`prepare_deepseek_tools` 在发送前先按原业务 Schema 验证，
再用本轮 codec 复制编码。因此在业务契约不变的前提下，无需重写旧业务历史/快照，wire 在调用时重建。
必须验证旧 checkpoint 恢复、连续工具轮次和原消息不被修改。

当前 V2 的普通文本/JSON/Responses Step 不使用这套普通工具列表；quality strict 路由使用独立
`submit_quality_report`。保持其专用 Schema、路由和能力标识不变时，无需修改 execution manifest、
journal 或冻结依赖。若将质量工具也纳入修改，则要单独设计能力版本与旧 Step 恢复，不能静默替换。

本方案正常情况下不涉及 Web、Core 公共 OpenAPI、生成客户端或 PostgreSQL 结构变更。没有理由新增
DDL、改变任务重试预算、修改计费、自动采用草案或开放生产视频。

## 实施顺序与验收

1. 先处理简单字段包装，并自动生成与实际 wire 一致的描述/示例；优先覆盖本次失败两个工具，回归
   全部 21 个包装候选及实际 Operation 集合。5 个复杂根联合可以暂留根判别，只简化内部字段。
2. 单独处理 5 个根联合，保留至少一个定位字段、普通正文/选区互斥、复审结论/patch 组合等约束，
   逐分支验证原业务合法输入的往返等价及非法组合拒绝。
3. JSON 字符串与质量专用映射保持独立；原递归表示的进一步优化另列后续研究。
4. 全覆盖 omitted/null/0/false/空串/空数组/空对象、业务同名标记、嵌套数组、开放字典、历史编码，
   全对象闭合/全必填/无空 properties，原业务 Schema/Pydantic 限制继续有效。
5. 运行 Provider/Runtime 相关测试、质量 Executor/registry/journal 兼容回归、全仓 Ruff 和共享范围
   Mypy；用受控真实调用核对供应商接受、实际参数遵循与任务终态。离线 Schema 成功不代替真实验收。

## 外部依据与未确定项

[DeepSeek 官方 Tool Calls](https://api-docs.deepseek.com/zh-cn/guides/tool_calls/)当前要求 Beta 端点、
所有函数 strict，object 字段全必填且 additionalProperties=false；支持 anyOf。文档未要求每个字段
添加 `value/variant`，这些是现有通用适配器为可逆性添加的表示。候选正常值与标记对象的联合是依据
这些能力提出的设计推导，尚未真实调用验证；当前文档也未将 type:null 列入支持类型，不直接假设可用。

官方文档另列引用与递归能力，说明现有“递归转 JSON 字符串”可能还有优化空间；但这涉及生产兼容
验证，不能在本次字段包装简化中无条件取消。供应商为何对上次严格 Schema 返回无效参数仍未确定，
保留相同 Schema/新 Schema 的受控对照有助于区分输入复杂度和 strict 实际生效问题。

## 21 个候选的字段清单

以下使用默认注册 Schema 的业务路径，重复联合分支去重。操作专用产物投影可进一步缩小字段集合。

| 包装受影响工具 | 去重业务字段路径 | 根对象联合 |
| --- | --- | --- |
| get_novel_info | $/include_full_sections | 否 |
| find_similar_lore | $/threshold | 否 |
| semantic_search_references | $/topK | 否 |
| list_outline_summary | $/include_full_summary、$/scope | 否 |
| get_outline_node | $、$/node_id、$/node_title | 是 |
| get_recent_chapters | $/count | 否 |
| list_review_artifacts | $/kind、$/status | 否 |
| propose_update_outline | $/action、$/client_key、$/content_summary、$/estimated_word_count、$/kind、$/parent_key、$/status | 否 |
| propose_add_foreshadowing | $/expected_payoff_summary、$/planted_content_summary | 否 |
| propose_resolve_foreshadowing | $/payoff_note_summary | 否 |
| submit_evaluation | $、$/artifactId、$/artifactKey、$/patches、$/requiredChanges、$/revisionMode | 是 |
| propose_updates | $/artifactKey、$/reviewerAgent、$/submitForReview | 否 |
| start_update_builder | $/reviewerAgent、$/submitForReview | 否 |
| append_update_batch | $/summary | 否 |
| append_outline_tree | $/summary | 否 |
| put_update_text_block | $/summary | 否 |
| put_update_item_text_block | $、$/summary、$/targetId、$/targetKey、$/targetName | 是 |
| finish_update_builder | $/reviewerAgent、$/submitForReview | 否 |
| begin_artifact_output | $、$/artifactKey、$/baseContentHash、$/baseUpdatedAt、$/content、$/operation、$/replacement、$/resourceId、$/resourceType、$/reviewerAgent、$/selectedTextHash、$/selectionEnd、$/selectionStart、$/submitForReview | 是 |
| show_review_artifact | $、$/artifactId、$/artifactKey、$/reason | 是 |
| submit_beat_plan | $/artifactKey、$/chapterAcceptanceCriteria、$/mainPlotConnection、$/reviewerAgent、$/sceneBeats/[]/acceptanceCriteria、$/sceneBeats/[]/characters、$/sceneBeats/[]/conflict、$/sceneBeats/[]/estimatedWords、$/sceneBeats/[]/foreshadowingRefs、$/sceneBeats/[]/order、$/submitForReview、$/totalEstimatedWords | 否 |


## 本轮实现与专项验证

- 普通可选/nullable 值与 5 个根对象联合均已实施平铺。`get_recent_chapters` 的正常调用为
  `{"count":6}`，`list_outline_summary` 为直接 scope/布尔；旧的半包装错误仍明确拒绝。
- 联合交集的解码兼容性采用保守结构证明；不能证明时保留判别。运行时若多个匹配分支得到不同业务值，
  继续拒绝。根联合保留完整条件，并修复 nullable 分支父 const/enum 未投影的问题，非法复审模式在
  wire 阶段即拒绝；供应商不支持的数组最小长度仍由原业务 Schema 复验。
- 重复键与非有限数在原始 JSON 和确定性闭合后的 JSON 中均拒绝。当前锁定 LangChain 的 Chat
  解析不保留原 arguments 字符串，因此 generic 的 DeepSeek 路径使用专用小型 ChatOpenAI 子类，
  在原解析前仅为本轮保存工具原 JSON；非 DeepSeek 沿用原类，正常结果、历史及日志不新增原始副本。
- 字段描述中的形状示例经实际 wire 验证，根联合的重复条件描述移除以减少重复文本；条件本身不移除。
  安全纠正说明通过独立排除字段送入模型，完整错误载荷不回放，调用次数及原 usage 不变。
- 核心新测试 22 项通过；两 Provider 与默认 strict 集成 345 项通过；Runtime/字段提示 65 项通过。
  全仓 Ruff、Agent/共享协议/鉴权 Mypy（134 源文件）通过。另有独立 912 个合法输入往返样例检查。
- 本机沿用已有 `.venv/bin`，未变更依赖。macOS 缺少部署测试要求的 `/usr/bin/dd`，本地全仓运行
  排除 `tests/architecture/test_deploy_scripts.py`；完整 Linux CI 必须包含该套件，不能算作本机已通过。

- 本地最终全仓验证（仅排除上述部署脚本套件）为 3860 passed、1 warning，耗时 289.35 秒。
