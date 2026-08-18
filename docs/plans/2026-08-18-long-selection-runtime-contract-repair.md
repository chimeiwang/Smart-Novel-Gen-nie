# 长篇选区改写运行契约修复 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复长篇选区 Artifact 产物校验、稳定快照恢复和公共任务投影之间的契约遗漏。

**Architecture:** `replacement` 继续作为选区产物的唯一权威内容，Agent 只放宽真实工具调用的空可见正文。Core 从共享 `PUBLIC_LONG_SERIAL_OPERATIONS` 派生恢复与查询集合，减少重复白名单漂移；公共响应枚举同步补齐选区 Operation。

**Tech Stack:** Python 3.12、Pydantic、FastAPI、Pytest、Ruff、Mypy

---

### Task 1: 修复 Agent 选区产物契约

**Files:**
- Modify: `apps/agent-service/tests/operations/test_artifact_contract.py`
- Modify: `apps/agent-service/src/inkforge_agents/operations/artifact_contract.py`

- [ ] **Step 1: 写入空可见正文通过、非空不一致正文失败的测试**

```python
def test_selection_submission_accepts_empty_visible_content() -> None:
    result = validate_artifact_submission(
        definition=OPERATION_DEFINITIONS["rewrite_chapter_selection"],
        events=[selection_event()],
        visible_content="",
        authoritative_artifact=None,
        task_id="task-1",
        operation_kind="rewrite_chapter_selection",
        selection_snapshot=selection_snapshot(),
    )
    assert result.content == "新文"


def test_selection_submission_rejects_nonempty_visible_content_mismatch() -> None:
    with pytest.raises(ValueError, match="ARTIFACT_CONTRACT_MISMATCH"):
        validate_artifact_submission(
            definition=OPERATION_DEFINITIONS["rewrite_chapter_selection"],
            events=[selection_event()],
            visible_content="另一份正文",
            authoritative_artifact=None,
            task_id="task-1",
            operation_kind="rewrite_chapter_selection",
            selection_snapshot=selection_snapshot(),
        )
```

- [ ] **Step 2: 运行测试并确认空可见正文用例失败**

Run: `uv run pytest apps/agent-service/tests/operations/test_artifact_contract.py -q`

Expected: 空可见正文用例因现有 `replacement != visible_content` 校验失败。

- [ ] **Step 3: 最小修改选区可见正文规则**

```python
if "content" in event or (
    visible_content != "" and replacement != visible_content
):
    raise ValueError(
        "ARTIFACT_CONTRACT_MISMATCH：选区产物只能返回 replacement，"
        "且非空可见正文必须与 replacement 完全一致"
    )
```

- [ ] **Step 4: 重新运行 Agent 产物契约测试并确认通过**

Run: `uv run pytest apps/agent-service/tests/operations/test_artifact_contract.py -q`

Expected: 全部通过。

### Task 2: 修复 Core 快照与任务投影

**Files:**
- Modify: `apps/core-api/tests/writing/test_recovery.py`
- Modify: `apps/core-api/tests/writing/test_run_queries.py`
- Modify: `apps/core-api/src/inkforge_core/writing/recovery.py`
- Modify: `apps/core-api/src/inkforge_core/writing/run_queries.py`
- Modify: `apps/core-api/src/inkforge_core/writing/schemas.py`

- [ ] **Step 1: 写入两个选区 Operation 的快照恢复测试**

```python
@pytest.mark.parametrize(
    "operation",
    ["rewrite_chapter_selection", "rewrite_outline_selection"],
)
def test_snapshot_accepts_public_selection_operations(operation: str) -> None:
    snapshot = deserialize_graph_snapshot(
        _snapshot(currentOperation={"kind": operation})
    )
    assert snapshot.current_operation == {"kind": operation}
```

- [ ] **Step 2: 写入选区任务查询投影测试**

```python
@pytest.mark.parametrize(
    ("operation", "artifact_kind"),
    [
        ("rewrite_chapter_selection", "chapter_draft"),
        ("rewrite_outline_selection", "outline_draft"),
    ],
)
def test_selection_projection_exposes_operation_and_waiting_artifact(
    operation: str,
    artifact_kind: str,
) -> None:
    status = project_run_status(
        _task(
            phase="awaiting_user_review",
            graph={"activeArtifactId": "artifact-1"},
        ),
        commands=[_command("start-1", operation=operation)],
        artifacts=[_artifact(kind=artifact_kind)],
    )
    assert status.operation == operation
    assert status.outcome.state == "waiting_user"
    assert status.activeArtifactId == "artifact-1"
```

- [ ] **Step 3: 运行测试并确认白名单与投影测试失败**

Run: `uv run pytest apps/core-api/tests/writing/test_recovery.py apps/core-api/tests/writing/test_run_queries.py -q`

Expected: 快照报 Operation 无效，任务投影的 `operation` 为 `None`。

- [ ] **Step 4: 从共享公共长篇契约派生集合并补齐响应枚举**

```python
from inkforge_contracts.long_serial import PUBLIC_LONG_SERIAL_OPERATIONS

OPERATION_KINDS = frozenset({...}) | frozenset(PUBLIC_LONG_SERIAL_OPERATIONS)

_PUBLIC_OPERATIONS = frozenset(
    {"generate_outline", "generate_manuscript", "replace_selection", "full_check"}
) | frozenset(PUBLIC_LONG_SERIAL_OPERATIONS)

_LONG_ARTIFACT_KINDS = {
    operation: definition.artifactKind
    for operation, definition in PUBLIC_LONG_SERIAL_OPERATIONS.items()
    if definition.artifactKind is not None
}
```

`WritingRunStatusResponse.operation` 的 Literal 同步加入 `rewrite_scene`、`rewrite_chapter_selection` 和 `rewrite_outline_selection`。

- [ ] **Step 5: 重新运行 Core 定向测试并确认通过**

Run: `uv run pytest apps/core-api/tests/writing/test_recovery.py apps/core-api/tests/writing/test_run_queries.py -q`

Expected: 全部通过。

### Task 3: 验证与提交

**Files:**
- Verify: `apps/agent-service/src`
- Verify: `apps/core-api/src`
- Verify: `packages/service-contracts/src`

- [ ] **Step 1: 运行相关完整测试集**

Run: `uv run pytest apps/agent-service/tests/operations/test_artifact_contract.py apps/agent-service/tests/graph/test_operation_graph.py apps/agent-service/tests/jobs/test_writing.py apps/core-api/tests/writing/test_recovery.py apps/core-api/tests/writing/test_run_queries.py apps/core-api/tests/writing/test_long_serial_runs.py packages/service-contracts/tests/test_long_serial_contracts.py packages/service-contracts/tests/test_public_operation_contracts.py -q`

Expected: 全部通过。

- [ ] **Step 2: 运行静态检查**

Run: `uv run ruff check apps/agent-service/src apps/agent-service/tests/operations/test_artifact_contract.py apps/core-api/src apps/core-api/tests/writing/test_recovery.py apps/core-api/tests/writing/test_run_queries.py packages/service-contracts/src`

Run: `uv run mypy apps/core-api/src apps/agent-service/src packages/service-contracts/src packages/service-auth/src`

Expected: 两条命令均通过。

- [ ] **Step 3: 复核变更范围与文档一致性**

Run: `git diff --check && git diff --stat && git status --short`

Expected: 无空白错误，只包含本 spec、计划、测试和对应实现。

- [ ] **Step 4: 提交修复**

```bash
git add docs/specs/2026-08-18-long-selection-runtime-contract-repair.md \
  docs/plans/2026-08-18-long-selection-runtime-contract-repair.md \
  apps/agent-service/src/inkforge_agents/operations/artifact_contract.py \
  apps/agent-service/tests/operations/test_artifact_contract.py \
  apps/core-api/src/inkforge_core/writing/recovery.py \
  apps/core-api/src/inkforge_core/writing/run_queries.py \
  apps/core-api/src/inkforge_core/writing/schemas.py \
  apps/core-api/tests/writing/test_recovery.py \
  apps/core-api/tests/writing/test_run_queries.py
git commit -m "修复：长篇选区改写运行契约"
```

