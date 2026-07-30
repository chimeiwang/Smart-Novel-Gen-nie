# 中短篇正文通用创作契约 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让中短篇正文首次生成与基于当前版本的全文修订使用同一套通用、可验证的创作契约，并保持一次任务只产生一个完整候选版本。

**Architecture:** 保留现有 `generate_manuscript`、不可变 `baseContent`、来源蓝图和 `userInstruction` 契约；仅在 Agent Service 的消息装配阶段根据是否存在基础正文区分“首次创作”和“全文修订”。通用约束集中在正文 Operation brief，不增加 API、数据库字段、Agent 或模型调用。

**Tech Stack:** Python 3.12、Pydantic、pytest、Ruff、Mypy

---

### Task 1: 收敛正文提示词并验证生成与修订语义

**Files:**
- Modify: `docs/specs/2026-07-30-short-medium-writing-workflow.md`
- Modify: `apps/agent-service/src/inkforge_agents/jobs/short_medium.py`
- Test: `apps/agent-service/tests/short_medium/test_graph.py`

- [ ] **Step 1: 写首次生成和全文修订的失败测试**

在 `apps/agent-service/tests/short_medium/test_graph.py` 增加两个测试。首次生成测试解析第二条模型消息的 JSON，验证单次正文任务要求一次性输出完整正文，并包含统一的结构、重复、篇幅和输出边界；全文修订测试为任务补充匹配的 `baseVersionId/baseContent/baseContentHash` 和 `userInstruction`，验证 Operation brief 明确把基础正文作为底稿并保留有效内容。

```python
@pytest.mark.asyncio
async def test_single_call_manuscript_prompt_uses_general_creation_contract() -> None:
    core = Core()
    generator = Generator(["甲" * 6_000])
    await ShortMediumWritingJobHandler(core, generator)(manuscript_job(8_000))

    context = json.loads(generator.requests[0].messages[1].content)
    brief = context["operationBrief"]
    assert "一次性输出完整正文" in brief
    assert "同一事件只完整叙述一次" in brief
    assert "目标字数和蓝图局部估算只用于控制结构比例" in brief
    assert "只输出作品正文" in brief


@pytest.mark.asyncio
async def test_existing_manuscript_prompt_treats_base_content_as_revision_draft() -> None:
    base_content = "需要保留的正文底稿"
    job = manuscript_job(8_000)
    job.payload.update(
        baseVersionId="manuscript-version-1",
        baseContent=base_content,
        baseContentHash=hashlib.sha256(base_content.encode("utf-8")).hexdigest(),
        userInstruction="压缩重复并修复时间线",
    )
    core = Core()
    generator = Generator(["乙" * 6_000])
    await ShortMediumWritingJobHandler(core, generator)(job)

    context = json.loads(generator.requests[0].messages[1].content)
    assert "全文修订" in context["operationBrief"]
    assert "保留仍然有效的内容" in context["operationBrief"]
    assert context["request"]["baseContent"] == base_content
    assert context["request"]["userInstruction"] == "压缩重复并修复时间线"
```

- [ ] **Step 2: 运行目标测试并确认按预期失败**

Run:

```powershell
uv run pytest apps/agent-service/tests/short_medium/test_graph.py -k "general_creation_contract or revision_draft" -q
```

Expected: 两个测试因当前 brief 仍包含“第 1/1 段”且没有全文修订契约而失败。

- [ ] **Step 3: 用单一正文 brief 实现最小改动**

在 `apps/agent-service/src/inkforge_agents/jobs/short_medium.py` 中缩短 `_STATIC_PROMPT`，并增加只负责正文语义的 `_manuscript_operation_brief()`。它根据 `payload.baseContent` 和 `segment_count` 选择首次创作/全文修订、完整正文/连续单元措辞，同时集中以下通用规则：

```python
def _manuscript_operation_brief(
    payload: ShortMediumRunPayload,
    *,
    index: int,
    segment_count: int,
    fixed_source_brief: str,
) -> str:
    task_mode = (
        "以 request.baseContent 为正文底稿执行全文修订；保留仍然有效的内容，"
        "只为符合本轮要求和已确认蓝图作必要改动；"
        if payload.baseContent is not None
        else "依据已确认蓝图完成首次创作；"
    )
    output_scope = (
        "一次性输出完整正文；"
        if segment_count == 1
        else f"只输出第 {index + 1}/{segment_count} 个连续正文单元；"
    )
    return (
        output_scope
        + task_mode
        + fixed_source_brief
        + "本轮用户要求高于已确认蓝图的可调整表达，蓝图高于正文底稿和通用写法；"
        + "下笔前在内部映射蓝图节点、场景职责和先后关系，同一事件只完整叙述一次，"
        + "确保时间、空间和因果成立；"
        + "目标字数和蓝图局部估算只用于控制结构比例，不重复说明凑字，不截断未完成场景；"
        + "除非用户或蓝图明确要求结构标题，只输出作品正文；"
        + "完成蓝图指定的核心兑现和结尾动作后立即停止，不追加总结性尾声；"
        + "与 completedContent 自然衔接，不总结、不重复已完成内容。"
    )
```

`generate_outline`、`replace_selection` 和 `full_check` 的 Operation brief 保持原有职责边界。

- [ ] **Step 4: 运行目标测试并确认通过**

Run:

```powershell
uv run pytest apps/agent-service/tests/short_medium/test_graph.py -k "general_creation_contract or revision_draft" -q
```

Expected: `2 passed`。

- [ ] **Step 5: 运行中短篇测试和静态检查**

Run:

```powershell
uv run pytest apps/agent-service/tests/short_medium -q
uv run ruff check apps/agent-service/src/inkforge_agents/jobs/short_medium.py apps/agent-service/tests/short_medium/test_graph.py
uv run mypy apps/agent-service/src
```

Expected: 全部退出码为 `0`，无失败、Ruff 错误或 Mypy 错误。

- [ ] **Step 6: 做一次真实版本化修订测试**

先使用 `inkforge-short-story-operator` 重新拉取作品并展示当前正文候选相对空正文的完整 Diff、`confirmationHash` 和字数变化。只有用户确认该摘要后才采用为正文 v1；随后以正文 v1、当前大纲版本和本轮评审意见启动一次 `manuscript` 任务，等待同一 taskId 的持久终态，读取完整候选 v2 并报告字数、结构、时间线、重复和结尾结果，不自动采用 v2。

