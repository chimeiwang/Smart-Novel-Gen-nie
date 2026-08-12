# Beat Plan 骨架职责与复审事实一致性实施计划

## 目标

压缩 `plan_chapter` 的职责，并消除主 Agent 与复审/返工 Agent 之间的权威事实不对称。

## 步骤

1. 先修改消息协议测试，要求 Beat Plan 提示包含“剧情骨架、一句可观察结果、不复制全局规则”，并移除对逐项列举转折、代价、结果、余波的断言。
2. 先修改执行器测试，要求 `plan_chapter` reviewer/reviser 同时收到冻结作品事实和草案，其他 Operation 仍只收到草案。
3. 运行定向测试，确认测试因现有行为而失败。
4. 修改剧情 Agent 与 `plan_chapter` 专用执行提示。
5. 修改 `CoreGraphAgentExecutor`，只为 `plan_chapter` 注入冻结事实。
6. 同步 Agent 架构文档和 03、04 号需求文档。
7. 运行定向 pytest、Agent Service 全量 pytest、Ruff 和 Mypy。

## 影响文件

- `apps/agent-service/src/inkforge_agents/prompts/plot.py`
- `apps/agent-service/src/inkforge_agents/runtime/execution.py`
- `apps/agent-service/src/inkforge_agents/jobs/adapters.py`
- `apps/agent-service/tests/runtime/test_messages.py`
- `apps/agent-service/tests/jobs/test_adapters.py`
- `apps/agent-service/AGENTS.md`
- `docs/requirements/03-ai-writing-and-agents.md`
- `docs/requirements/04-review-quality-and-workflow.md`
