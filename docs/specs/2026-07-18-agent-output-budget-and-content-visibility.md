# Agent 输出预算与内容可见性规格

## 状态

- 日期：2026-07-18
- 状态：已实现
- 范围：模型输出预算、计费授权收缩、画像完成原因、最近章节按需读取、生成正文预览

## 背景

当前普通 Agent 的每轮模型输出被 `AgentRuntime` 固定为 `8192` tokens，画像生成则固定为 `1200` tokens。两个数字都会一路进入 Core 模型预授权和 OpenAI-compatible Provider 的 `max_tokens`，因此它们不是提示词建议，而是会真实截断模型响应的传输层上限。

当前默认模型 `deepseek-v4-flash` 的上下文窗口和单次最大输出能力均显著高于 `8192`。应用继续使用固定 `8192` 会让较长章节、深入评审和长文本返工过早得到 `finishReason=length`。Runtime 会正确拒绝截断响应，因而不会静默提交半截正文，但用户得到的是整轮失败，已经生成的内容也不能作为完整草案交付。

同一轮审计还发现两个不同性质的限制：

- `get_recent_chapters` 最多读取 5 章，限制的是 Agent 按需读取历史正文的工具参数，不是模型自动上下文；
- 写作界面的正文预览完整保留在 DOM 中，但 CSS 用 `150px + overflow:hidden` 遮住尾部，属于显示裁切，不是数据截断。

这三类边界必须分别处理，不能因为模型拥有大上下文就无差别放大 RAG 索引、基础上下文或所有接口载荷。

## 当前项目事实

- `AgentRuntime.run()` 的 `max_output_tokens` 默认值是 `8192`，`AgentRunner` 没有覆盖它。
- `ModelTurnRequest.maxOutputTokens` 是必填正整数；OpenAI-compatible Provider 始终把它传成 `max_tokens`。
- Core 预授权会根据余额把 `requestedMaxOutputTokens` 收缩为较小的 `maxOutputTokens`，但 `ModelRuntime` 当前把任何小于请求值的合法授权都当成错误。
- Core grant 和结算会校验实际 `completionTokens` 不得超过授权上限，因此不能简单省略 Provider 上限或把授权改成无界。
- `AgentRuntime` 已在正文、控制事件和工具副作用产生前拒绝 `finishReason=length`；该安全边界必须保留。
- `ModelPortraitGenerator` 只检查响应正文是否非空，没有拒绝 `length`，存在把截断画像当成完整结果的风险。
- 最近章节读取契约默认不主动指定数量，Core 当前默认读取 3 章；共享参数契约仅允许最大 5 章，Core 服务会原样返回所选章节完整正文。
- 生成正文预览在组件中使用完整 `generatedContent` 和统一 `countTextLength()`，但两个样式文件都对 `.preview-content` 设置了相同的隐藏裁切规则。
- 当前 RAG 每份资料最多 64 块是索引、回调体和事务容量边界；它不是本规格要修改的模型上下文边界。
- PostgreSQL schema、ReviewArtifact 审核与正式应用事务均不需要改变。

## 目标

- 删除普通 Agent 的固定 `8192` 和画像生成的固定 `1200` 输出上限。
- 用单一、显式、可配置的模型最大输出能力驱动所有文本模型调用；当前默认值为 `384000`，允许部署者随实际模型调整。
- Core 因余额返回较小合法授权时，让 Provider 使用准确的授权值，而不是在 Provider 调用前无条件失败。
- 保持计费 grant 为有限整数，实际输出不得超过授权值，不允许以“无限输出”为由绕过预授权和结算。
- 保持所有 `length` 响应为明确失败；半截正文、评审、画像和报告不得成为成功结果。
- 允许 Agent 按需读取最多 20 个最近章节，默认读取行为仍保持 3 章，且不把历史章节自动注入基础上下文。
- 让正文预览在有限桌面高度内可滚动查看完整内容，不再用渐变和 `overflow:hidden` 遮住尾部。
- 用超过旧 `8192` 边界的成功回归测试证明长内容没有被应用层截断。

## 非目标

- 不实现跨模型调用的自动续写、片段去重、断点标记或多轮拼接。
- 不承诺真正无限输出；供应商单次输出能力、上下文窗口、内容过滤、余额和计费授权仍是有效边界。
- 不把整部作品、全部章节或全部 RAG 块自动塞入每次模型请求。
- 不修改 RAG 的 64 块索引容量和 `topK`，也不改变 embedding 回调协议。
- 不修改中短篇/长篇产品分类、目标总字数范围、章节规划或故事合同；这些属于独立产品规格。
- 不修改公共浏览器 API、PostgreSQL schema、ReviewArtifact 状态机或正式内容应用流程。
- 不通过静默截断、截取前缀、丢弃尾部或缩短日志来规避任何容量问题。

## 设计方案

### 1. 统一模型输出能力配置

Agent Service 的 `Settings` 新增：

```text
model_max_output_tokens: 1..1_000_000，默认 384000
```

环境变量名为 `MODEL_MAX_OUTPUT_TOKENS`。该值表达当前部署所选模型允许的单次最大输出能力，不表达目标篇幅，也不要求模型必须生成到该长度。

应用装配时把该值显式传给：

- `AgentRuntime`：普通回答、策划、写作、复审、返工和质量 Agent；
- `ModelPortraitGenerator`：五个画像维度。

业务运行时不再保留 `8192` 或 `1200` 默认值。测试中若直接构造上述对象，必须显式给出测试预算，避免隐藏回退重新出现。

OpenAI-compatible Provider 继续收到一个有限的 token 上限。不能只删除 `max_tokens`，因为计费 grant 必须约束实际可消费额度。

### 2. 授权额度决定 Provider 实际上限

计费调用保持以下顺序：

```text
配置的模型能力上限
  -> requestedMaxOutputTokens
  -> Core 按模型请求和可用余额签发有限 grant
  -> ModelRuntime 校验 grant
  -> Provider 使用 grant.maxOutputTokens
  -> 按实际 usage 结算
```

`ModelRuntime` 对授权结果执行确定性校验：

- `maxOutputTokens` 必须是正整数；
- 不得大于原始请求值；
- `grantToken` 和 `requestId` 必须完整；
- 校验失败时不得调用 Provider。

授权值小于请求值时，不再直接报“授权低于请求值”，而是复制本轮请求并把 `maxOutputTokens` 替换为授权值后调用 Provider。原始请求对象不被原地修改，模型请求幂等标识仍按原始意图生成。

非计费 Provider 继续使用调用方给出的配置上限。

### 3. 完成原因与不完整内容

`AgentRuntime` 继续在接受可见正文、控制事件和工具副作用前校验完成原因：

- `length`：抛出稳定的 `MODEL_OUTPUT_TRUNCATED`，本轮不产生成功结果；
- `content_filter`：明确失败；
- `stop/tool_calls/unknown`：继续遵循现有一致性契约。

本规格不把 `length` 改造成自动续写信号。对于当前目标的 6000～80000 字中短篇和按章生成路径，默认 384K 单次输出能力已经移除了应用层主要瓶颈；自动续写需要另行定义逐字拼接、重复处理、续写轮数和多轮计费。

`ModelPortraitGenerator` 必须同样拒绝 `length`、`content_filter` 和不符合无工具文本响应语义的完成原因。截断画像不得写入任一画像维度；内部模型日志继续保留供应商原始内容和原始完成原因。

### 4. 最近章节按需读取

共享 `RecentChapterArgs.count` 的最大值从 5 调整为 20：

```text
count: 1..20，可选
```

规则保持不变：

- 未指定时仍由 Core 默认读取最近 3 章；
- 只返回目标章节之前的章节；
- 返回顺序和章节正文保持完整；
- Agent 必须显式调用工具，基础上下文不自动扩张；
- 超过 20 的请求在共享契约入口拒绝，不进入 Core 业务服务。

### 5. 正文预览完整可见

正文预览继续使用完整 `generatedContent`，不复制、不裁剪正文。显示层采用有限高度的可滚动阅读区域：

- 移除 `max-height:150px + overflow:hidden`；
- 移除遮挡尾部的 `::after` 渐变；
- 使用适合桌面阅读的较大最大高度和 `overflow-y:auto`；
- 保留完整字数统计、采纳和继续修改动作；
- 两份现存重复样式必须同步修改，避免全局样式重新覆盖组件样式。

键盘和滚轮用户都必须能够到达正文尾部；正文内容不因视觉容器高度发生字符串变更。

## 影响范围

- `apps/agent-service/src/inkforge_agents/config.py`
- `apps/agent-service/src/inkforge_agents/app.py`
- `apps/agent-service/src/inkforge_agents/runtime/agent_runtime.py`
- `apps/agent-service/src/inkforge_agents/runtime/model_runtime.py`
- `apps/agent-service/src/inkforge_agents/jobs/portrait.py`
- `apps/agent-service/tests/**` 对应配置、运行时、计费、画像和装配测试
- `.env.example`、`infra/compose.yaml` 中 Agent Service 模型能力配置
- `packages/service-contracts/src/inkforge_contracts/read_tools.py`
- 共享契约与 Core 读取工具测试
- `apps/web/src/features/writing/writing-conversation.css`
- `apps/web/src/app/globals.css`
- `apps/web/src/features/writing/__tests__/generated-content-preview.test.ts`
- `apps/agent-service/AGENTS.md`
- `docs/requirements/03-ai-writing-and-agents.md`
- `docs/requirements/04-review-quality-and-workflow.md`

不修改 PostgreSQL schema，不生成数据库迁移，不修改公共 OpenAPI 客户端。

## 验收标准

### 模型输出与计费

- [x] 默认配置为 `384000`，配置小于 1 或大于 `1000000` 时启动配置校验失败。
- [x] 应用装配把统一配置同时传给 `AgentRuntime` 和 `ModelPortraitGenerator`。
- [x] 普通 Agent 和画像生产代码中不再存在固定 `8192` 或 `1200` 输出预算。
- [x] 余额充足时，大于 `8192` 的请求和 grant 不被 Core 隐式压回旧上限。
- [x] Core 返回较小合法 grant 时，Provider 收到的 `maxOutputTokens` 精确等于 grant。
- [x] grant 非正、超过请求值或缺少签名字段时，Provider 不被调用。
- [x] 超过旧 `8192` 边界且 `finishReason=stop` 的完整正文原样通过，尾部哨兵存在。
- [x] `finishReason=length` 仍在正文、控制事件和工具副作用产生前失败。
- [x] 画像的 `length/content_filter` 响应不会成为成功画像维度。

### 章节读取

- [x] `count=20` 通过共享契约校验，`count=21` 被拒绝。
- [x] Core 工具网关接受 20 章边界并拒绝越界输入。
- [x] 默认读取数量仍为 3，读取结果保持目标章之前、顺序正确和正文完整。

### 正文预览

- [x] 预览使用完整 `generatedContent` 和统一字数统计。
- [x] 两份样式均不再使用隐藏溢出和尾部渐变。
- [x] 长正文区域可以纵向滚动到尾部，采纳与修改按钮保持可用。

### 回归命令

```powershell
uv run --frozen pytest -p no:cacheprovider apps/agent-service/tests -q
uv run --frozen pytest -p no:cacheprovider packages/service-contracts/tests apps/core-api/tests/writing/test_read_tools.py apps/core-api/tests/writing/test_read_tool_service.py apps/core-api/tests/billing -q
uv run --frozen ruff check apps/agent-service/src apps/agent-service/tests apps/core-api/src apps/core-api/tests packages/service-contracts/src packages/service-contracts/tests
uv run --frozen mypy apps/agent-service/src apps/core-api/src packages/service-contracts/src packages/service-auth/src
npm run test:web
npm run typecheck
npm run lint
```

### 实际验收结果（2026-07-18）

- Agent Service 全量测试：294 passed，1 warning，退出码 0。
- 共享契约、service-auth、Core billing 与 Core 读取工具测试：158 passed，1 skipped，退出码 0。
- Compose 架构测试：11 passed。
- Web 测试：187 passed；api-client 测试：3 passed。
- Ruff：All checks passed。
- Mypy：193 个源文件无问题。
- `npm run typecheck`、`npm run lint`：退出码均为 0。
- 非失败提示：存在 Starlette 既有弃用 warning；Windows pytest 临时目录清理阶段出现 atexit `PermissionError`。相关命令均退出码 0，未声称这两项已修复。
