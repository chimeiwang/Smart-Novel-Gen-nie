# Agent 输出预算与内容可见性实施计划

> 对应规格：`docs/specs/2026-07-18-agent-output-budget-and-content-visibility.md`

## 目标

移除应用层固定 `8192/1200` 模型输出预算，正确使用 Core 授权值调用 Provider；把最近章节按需读取上限提升到 20；让生成正文预览可以查看完整尾部，同时保持截断失败、计费和 ReviewArtifact 安全边界。

## 实施原则

- 严格执行测试驱动：每个任务先增加会失败的断言，确认红灯后再改生产代码。
- 不修改 PostgreSQL schema、公共 OpenAPI 或 ReviewArtifact 工作流。
- 不实现自动续写，不扩大 RAG 容量。
- 所有新增注释、文档和测试名称使用简体中文。
- 保留当前 `finishReason=length` 的失败语义。

## 任务 1：模型输出预算与计费授权

涉及文件：

- `.env.example`
- `infra/compose.yaml`
- `apps/agent-service/src/inkforge_agents/config.py`
- `apps/agent-service/src/inkforge_agents/app.py`
- `apps/agent-service/src/inkforge_agents/runtime/agent_runtime.py`
- `apps/agent-service/src/inkforge_agents/runtime/model_runtime.py`
- `apps/agent-service/src/inkforge_agents/jobs/portrait.py`
- 对应 Agent/Core 测试

步骤：

1. 在配置、装配、计费 Runtime、Agent Runtime 和画像测试中增加以下失败断言：默认 384000、配置边界、装配透传、较小 grant 精确传给 Provider、非法 grant 零调用、长于旧边界的完整正文通过、画像截断失败。
2. 运行定向测试，确认失败原因来自缺失的新行为，而非测试语法或夹具错误。
3. 新增 `MODEL_MAX_OUTPUT_TOKENS` 配置并显式注入两个运行入口。
4. 删除业务运行时 `8192/1200` 默认值。
5. 在 `ModelRuntime` 中复制请求并使用合法授权额度调用 Provider；保留签名和 usage 结算。
6. 让画像生成校验完成原因，不接受截断或过滤响应。
7. 运行定向测试、Ruff 和 Mypy。

定向命令：

```powershell
uv run --frozen pytest -p no:cacheprovider apps/agent-service/tests/test_config.py apps/agent-service/tests/test_health.py apps/agent-service/tests/runtime/test_agent_runtime.py apps/agent-service/tests/runtime/test_agent_runner.py apps/agent-service/tests/runtime/test_billing_runtime.py apps/agent-service/tests/jobs/test_portrait.py apps/core-api/tests/billing -q
```

## 任务 2：最近章节读取上限

涉及文件：

- `packages/service-contracts/src/inkforge_contracts/read_tools.py`
- `packages/service-contracts/tests/test_read_tools.py`
- `apps/core-api/tests/writing/test_read_tools.py`
- `apps/core-api/tests/writing/test_read_tool_service.py`

步骤：

1. 增加 `count=20` 成功、`count=21` 拒绝、默认 3 章和完整顺序的失败测试。
2. 确认现有契约因 `le=5` 出现预期红灯。
3. 仅把共享参数上限改为 20，不改变默认值和 Core 正文返回逻辑。
4. 运行共享契约、Core 工具与 Mypy 回归。

定向命令：

```powershell
uv run --frozen pytest -p no:cacheprovider packages/service-contracts/tests/test_read_tools.py apps/core-api/tests/writing/test_read_tools.py apps/core-api/tests/writing/test_read_tool_service.py -q
```

## 任务 3：正文预览完整可见

涉及文件：

- `apps/web/src/features/writing/writing-conversation.css`
- `apps/web/src/app/globals.css`
- `apps/web/src/features/writing/__tests__/generated-content-preview.test.ts`

步骤：

1. 增加静态契约测试，验证组件继续传递完整正文，两份 CSS 都提供纵向滚动且不含预览尾部渐变/隐藏溢出。
2. 运行该测试并确认旧样式触发红灯。
3. 同步修改两份重复样式，使用较大桌面最大高度和 `overflow-y:auto`，移除 `::after`。
4. 运行 Web 测试、TypeScript 类型检查和 ESLint。

定向命令：

```powershell
npx tsx --test apps/web/src/features/writing/__tests__/generated-content-preview.test.ts
npm run test:web
npm run typecheck
npm run lint
```

## 任务 4：权威文档同步与总体验收

涉及文件：

- `apps/agent-service/AGENTS.md`
- `docs/requirements/03-ai-writing-and-agents.md`
- `docs/requirements/04-review-quality-and-workflow.md`
- 本规格状态与验收清单

步骤：

1. 同步模型输出预算、授权收缩、画像完成原因和最近章节按需读取规则。
2. 明确“取消固定 8192”不等于无限输出或自动续写。
3. 运行规格中的全量回归命令。
4. 对照规格逐项复核差异，完成规格审查和代码质量审查。
5. 仅在所有新鲜验证通过后把规格状态改为“已实现”。

