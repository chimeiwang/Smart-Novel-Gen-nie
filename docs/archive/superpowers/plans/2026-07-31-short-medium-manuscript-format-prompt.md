# 中短篇正文格式提示词实施计划

> **面向执行 Agent：** 必须按测试驱动开发逐步实施，并在完成前执行验证技能要求的全部检查。

**目标：** 让中短篇首次生成和全文修订共用同一正文格式契约，使后续 Agent 正文保持相对统一的纯文本格式。

**架构：** 只修改 `generate_manuscript` 的共享 Operation brief，不增加正文后处理、格式化器或持久化改写。契约明确普通段落、场景转换和标题的输出规则，因此首次创作、全文修订及内部连续分段会自然继承同一约束。

**技术栈：** Python 3.12、Pydantic、pytest、Ruff、Mypy。

---

## 文件边界

- 修改 `docs/specs/2026-07-30-short-medium-writing-workflow.md`：记录正文格式契约及验收标准。
- 修改 `apps/agent-service/tests/short_medium/test_graph.py`：锁定首次生成和全文修订的共享格式约束。
- 修改 `apps/agent-service/src/inkforge_agents/jobs/short_medium.py`：替换现有重复度较高的正文输出说明。
- 不修改已有正文版本，不增加输出后处理，不修改 PostgreSQL schema、公共 API 或 Agent 状态机。

### 任务一：更新正文格式规格

- [x] **步骤 1：补充共享格式契约**

在正文生成的统一创作契约中明确：

```text
普通段落之间只使用一个换行符，不额外插入空白行；
仅在明确的场景或时间跳转处保留一个空行；
除非用户或蓝图明确要求，不输出作品标题、Markdown 标题、分幕标题或结构编号。
```

- [x] **步骤 2：补充验收项**

要求首次创作和全文修订的 `operationBrief` 都包含上述契约。

### 任务二：用失败测试锁定提示词契约

- [x] **步骤 1：补充首次生成断言**

在 `test_single_call_manuscript_prompt_uses_complete_creation_contract` 中断言共享 brief 包含：

```python
assert "普通段落之间只使用一个换行符" in operation_brief
assert "仅在明确的场景或时间跳转处保留一个空行" in operation_brief
assert "不输出作品标题、Markdown 标题、分幕标题或结构编号" in operation_brief
```

- [x] **步骤 2：补充全文修订断言**

在 `test_manuscript_prompt_uses_base_content_as_revision_draft` 中加入相同三项断言，证明全文修订没有走另一套格式提示。

- [x] **步骤 3：运行测试并确认失败**

```powershell
uv run pytest apps/agent-service/tests/short_medium/test_graph.py -k "single_call_manuscript_prompt_uses_complete_creation_contract or manuscript_prompt_uses_base_content_as_revision_draft" -q
```

预期：两项测试因当前 brief 缺少正文换行和标题格式契约而失败。

### 任务三：最小化修改共享 Operation brief

- [x] **步骤 1：替换旧输出说明**

在 `generate_manuscript` 共享 brief 中保留“只输出作品正文”的边界，并把标题、段落和场景转换规则合并为一条通用格式契约；不新增新的提示层。

- [x] **步骤 2：运行针对性测试**

```powershell
uv run pytest apps/agent-service/tests/short_medium/test_graph.py -k "single_call_manuscript_prompt_uses_complete_creation_contract or manuscript_prompt_uses_base_content_as_revision_draft" -q
```

预期：`2 passed`。

### 任务四：完整验证

- [x] **步骤 1：运行中短篇 Agent 测试**

```powershell
uv run pytest apps/agent-service/tests/short_medium
```

- [x] **步骤 2：运行静态检查**

```powershell
uv run ruff check apps/agent-service/src/inkforge_agents/jobs/short_medium.py apps/agent-service/tests/short_medium/test_graph.py
uv run mypy apps/core-api/src apps/agent-service/src packages/service-contracts/src packages/service-auth/src
```

- [x] **步骤 3：审查最终差异**

```powershell
git diff --check
git status --short
git diff -- docs/specs/2026-07-30-short-medium-writing-workflow.md apps/agent-service/src/inkforge_agents/jobs/short_medium.py apps/agent-service/tests/short_medium/test_graph.py
```

确认未触碰 `apps/web/next-env.d.ts`，并明确现有正文版本不会被自动重排。
