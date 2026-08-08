# Beat Plan 场景字段契约修复实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复 `submit_beat_plan` 与 Core 正式写入之间的场景字段错位，使当前生产 Artifact 可批准，并阻止未来生成不可应用的 Beat Plan。

**Architecture:** Agent 工具入口使用严格嵌套 Pydantic 模型生成规范场景；Core 的 ReviewArtifact 应用边界对当前生产中已经持久化的旧场景形态做有限归一化，再把规范对象交给现有 `FormalWriteRepository`。不修改数据库、公共 API、前端和状态机。

**Tech Stack:** Python 3.13、Pydantic v2、FastAPI、pytest、Ruff、Mypy、GitHub Actions、InkForge 生产 CLI。

---

## 文件结构

- 修改 `apps/agent-service/src/inkforge_agents/tools/control.py`：定义并应用严格 Beat Plan 场景参数模型。
- 修改 `apps/agent-service/tests/tools/test_control.py`：覆盖规范输入、旧字段拒绝、必填字段和节拍数量一致性。
- 修改 `apps/core-api/src/inkforge_core/reviews/apply.py`：在正式写入前完成有限旧字段归一化。
- 修改 `apps/core-api/tests/reviews/test_artifact_apply.py`：精确复现生产 revision 4，并验证规范字段不被改写。
- 修改 `docs/plans/2026-08-07-beat-plan-contract-alignment.md`：执行时更新任务勾选状态。

### Task 1: 收紧 Agent 的 Beat Plan 工具契约

**Files:**
- Modify: `apps/agent-service/tests/tools/test_control.py`
- Modify: `apps/agent-service/src/inkforge_agents/tools/control.py`

- [x] **Step 1: 写 Agent 失败测试**

在 `test_control.py` 增加测试，要求规范场景能精确序列化，旧字段和字符串角色被拒绝，顶层必填字段缺失被拒绝，`beatCount` 与场景数量不一致被拒绝：

```python
import pytest
from pydantic import ValidationError

from inkforge_agents.tools.control import BeatPlanArgs, QualityReportArgs


def canonical_beat_plan() -> dict[str, object]:
    return {
        "title": "第一章",
        "beatCount": 1,
        "summary": "章节计划",
        "chapterGoal": "让主角被困洞天",
        "sceneBeats": [
            {
                "order": 1,
                "goal": "完成内部复评并立即撤离",
                "conflict": "报酬与安全冲突",
                "characters": ["纪寻", "栾城"],
                "foreshadowingRefs": ["维护数据异常"],
                "estimatedWords": 640,
                "acceptanceCriteria": "撤离决定无降智",
            }
        ],
    }


def test_beat_plan_args_accepts_only_canonical_scene_contract() -> None:
    value = BeatPlanArgs.model_validate(canonical_beat_plan())
    assert value.model_dump()["sceneBeats"] == canonical_beat_plan()["sceneBeats"]


@pytest.mark.parametrize(
    "change",
    [
        {"sceneBeats": [{"sceneGoal": "旧目标", "characters": "纪寻、栾城"}]},
        {"chapterGoal": None},
        {"sceneBeats": None},
        {"beatCount": 2},
    ],
)
def test_beat_plan_args_rejects_unapplicable_contract(change: dict[str, object]) -> None:
    payload = canonical_beat_plan()
    payload.update(change)
    with pytest.raises(ValidationError):
        BeatPlanArgs.model_validate(payload)
```

- [x] **Step 2: 运行测试并确认 RED**

Run:

```powershell
uv run pytest apps/agent-service/tests/tools/test_control.py -q
```

Expected: 新测试失败；旧形态仍被宽松 `sceneBeats` 接受，且顶层字段仍可为空。

- [x] **Step 3: 实现最小严格模型**

在 `control.py` 中加入并应用以下模型：

```python
class BeatPlanSceneArgs(StrictArgs):
    order: int | None = Field(default=None, ge=1)
    goal: str = Field(min_length=1, max_length=1000)
    conflict: str | None = Field(default=None, max_length=1000)
    characters: list[Annotated[str, Field(min_length=1, max_length=100)]] = Field(
        default_factory=list,
        max_length=50,
    )
    foreshadowingRefs: list[
        Annotated[str, Field(min_length=1, max_length=200)]
    ] | None = Field(default=None, max_length=50)
    estimatedWords: int | None = Field(default=None, ge=0)
    acceptanceCriteria: str | None = Field(default=None, min_length=1, max_length=1000)


class BeatPlanArgs(StrictArgs):
    title: str = Field(min_length=1, max_length=200)
    beatCount: int = Field(ge=1, le=50)
    summary: str = Field(min_length=1, max_length=2000)
    artifactKey: str | None = Field(default=None, min_length=1, max_length=200)
    reviewerAgent: AgentId | None = None
    submitForReview: bool | None = None
    chapterGoal: str = Field(min_length=1, max_length=1000)
    mainPlotConnection: str | None = Field(default=None, max_length=1000)
    chapterAcceptanceCriteria: str | None = Field(default=None, max_length=1000)
    totalEstimatedWords: int | None = Field(default=None, ge=0)
    sceneBeats: list[BeatPlanSceneArgs] = Field(min_length=1, max_length=50)

    @model_validator(mode="after")
    def require_matching_beat_count(self) -> Self:
        if self.beatCount != len(self.sceneBeats):
            raise ValueError("beatCount 必须等于 sceneBeats 数量")
        return self
```

- [x] **Step 4: 运行 Agent 测试并确认 GREEN**

Run:

```powershell
uv run pytest apps/agent-service/tests/tools/test_control.py apps/agent-service/tests/operations/test_artifact_contract.py apps/agent-service/tests/graph/test_operation_graph.py -q
```

Expected: 全部通过。

### Task 2: 兼容当前生产 Artifact 的旧场景形态

**Files:**
- Modify: `apps/core-api/tests/reviews/test_artifact_apply.py`
- Modify: `apps/core-api/src/inkforge_core/reviews/apply.py`

- [x] **Step 1: 扩展测试替身并写 Core 失败测试**

让 `FakeFormalWrites` 保存完整 `beat_plan`，再加入 revision 4 精确形态测试：

```python
class FakeFormalWrites:
    def __init__(self) -> None:
        self.content: str | None = None
        self.beat_plan: dict[str, object] | None = None

    async def apply_beat_plan(
        self, artifact: object, user_id: str, beat_plan: dict[str, object]
    ) -> int:
        del artifact, user_id
        self.beat_plan = beat_plan
        self.content = str(beat_plan["chapterGoal"])
        return 1


@pytest.mark.asyncio
async def test_formal_applier_normalizes_current_legacy_beat_plan() -> None:
    writes = FakeFormalWrites()
    artifact = Artifact(
        kind="beat_plan",
        payload={
            "kind": "beat_plan",
            "beatPlan": {
                "chapterGoal": "完成撤离失败行动链",
                "sceneBeats": [
                    {
                        "sceneName": "复评：压差超限，无倒计时",
                        "sceneGoal": "完成专业复评并立即撤离",
                        "conflict": "报酬与安全冲突",
                        "characters": "纪寻、栾城",
                        "foreshadowingReferences": "【新埋】维护数据异常",
                        "estimatedWords": 640,
                        "acceptanceCriteria": "撤离决定无降智",
                    }
                ],
            },
        },
    )
    artifact.novel_id = "novel-1"
    artifact.chapter_id = "chapter-1"

    await FormalArtifactApplier(writes, FakeUpdatesExecutor()).apply(
        artifact,
        user_id="user-1",
        edited_content=None,
        selected_update_refs=None,
    )

    assert writes.beat_plan == {
        "chapterGoal": "完成撤离失败行动链",
        "sceneBeats": [
            {
                "order": 1,
                "goal": "复评：压差超限，无倒计时：完成专业复评并立即撤离",
                "conflict": "报酬与安全冲突",
                "characters": ["纪寻", "栾城"],
                "foreshadowingRefs": ["【新埋】维护数据异常"],
                "estimatedWords": 640,
                "acceptanceCriteria": "撤离决定无降智",
            }
        ],
    }
```

再增加一个规范场景测试，断言输入与传给正式写入端口的对象相等。

- [x] **Step 2: 运行测试并确认 RED**

Run:

```powershell
uv run pytest apps/core-api/tests/reviews/test_artifact_apply.py -q
```

Expected: 旧场景仍原样传递，断言失败。

- [x] **Step 3: 实现有限归一化**

在 `apply.py` 中引入 `re`，增加 `_normalize_beat_plan()`、`_normalize_scene_beat()`、
`_normalize_string_list()`，只接受规范字段与规格列出的旧字段：

```python
def _normalize_beat_plan(beat_plan: dict[str, object]) -> dict[str, object]:
    scenes = beat_plan.get("sceneBeats")
    if not isinstance(scenes, list) or not scenes:
        raise ValueError("章节计划草案结构无效")
    normalized = dict(beat_plan)
    normalized["sceneBeats"] = [
        _normalize_scene_beat(scene, index=index)
        for index, scene in enumerate(scenes, start=1)
    ]
    return normalized


def _normalize_scene_beat(value: object, *, index: int) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError("章节计划场景结构无效")
    goal = value.get("goal")
    if not isinstance(goal, str) or not goal.strip():
        legacy_goal = value.get("sceneGoal")
        legacy_name = value.get("sceneName")
        if not isinstance(legacy_goal, str) or not legacy_goal.strip():
            raise ValueError("章节计划场景结构无效")
        goal = legacy_goal.strip()
        if isinstance(legacy_name, str) and legacy_name.strip():
            goal = f"{legacy_name.strip()}：{goal}"

    order = value.get("order", index)
    if type(order) is not int or order < 1:
        raise ValueError("章节计划场景顺序无效")
    estimated_words = value.get("estimatedWords", 0)
    if type(estimated_words) is not int or estimated_words < 0:
        raise ValueError("章节计划场景字数无效")

    result: dict[str, object] = {
        "order": order,
        "goal": goal,
        "characters": _normalize_string_list(
            value.get("characters"),
            field="characters",
            split_legacy=True,
        ),
        "estimatedWords": estimated_words,
    }
    conflict = value.get("conflict")
    if conflict is not None:
        if not isinstance(conflict, str):
            raise ValueError("章节计划场景冲突无效")
        result["conflict"] = conflict

    refs = value.get("foreshadowingRefs")
    if refs is None and "foreshadowingReferences" in value:
        legacy_refs = value.get("foreshadowingReferences")
        if not isinstance(legacy_refs, str):
            raise ValueError("章节计划场景伏笔引用无效")
        refs = [] if legacy_refs.strip() in {"", "无"} else [legacy_refs]
    elif refs is not None:
        refs = _normalize_string_list(
            refs,
            field="foreshadowingRefs",
            split_legacy=False,
        )
    if refs is not None:
        result["foreshadowingRefs"] = refs

    criteria = value.get("acceptanceCriteria")
    if criteria is not None:
        if not isinstance(criteria, str) or not criteria:
            raise ValueError("章节计划场景验收标准无效")
        result["acceptanceCriteria"] = criteria
    return result


def _normalize_string_list(
    value: object,
    *,
    field: str,
    split_legacy: bool,
) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        if not all(isinstance(item, str) and item for item in value):
            raise ValueError(f"章节计划场景 {field} 无效")
        return list(value)
    if split_legacy and isinstance(value, str):
        return [item.strip() for item in re.split(r"[、，,]", value) if item.strip()]
    raise ValueError(f"章节计划场景 {field} 无效")
```

`FormalArtifactApplier.apply()` 在调用 `apply_beat_plan()` 前执行：

```python
return await self._formal_writes.apply_beat_plan(
    artifact,
    user_id,
    _normalize_beat_plan(beat_plan),
)
```

- [x] **Step 4: 运行 Core 测试并确认 GREEN**

Run:

```powershell
uv run pytest apps/core-api/tests/reviews/test_artifact_apply.py apps/core-api/tests/reviews/test_decision_orchestrator.py -q
```

Expected: 全部通过。

### Task 3: 完整验证、提交与发布

**Files:**
- Modify: `docs/plans/2026-08-07-beat-plan-contract-alignment.md`

- [x] **Step 1: 运行相关回归测试**

```powershell
uv run pytest `
  apps/core-api/tests/reviews/test_artifact_apply.py `
  apps/core-api/tests/reviews/test_decision_orchestrator.py `
  apps/agent-service/tests/tools/test_control.py `
  apps/agent-service/tests/operations/test_artifact_contract.py `
  apps/agent-service/tests/graph/test_operation_graph.py -q
```

Expected: 全部通过，0 failures。

- [x] **Step 2: 运行 Python 静态检查和完整测试**

```powershell
uv run ruff check apps/core-api/src apps/core-api/tests apps/agent-service/src apps/agent-service/tests
uv run mypy apps/core-api/src apps/agent-service/src packages/service-contracts/src packages/service-auth/src
uv run pytest -q
git diff --check
```

Expected: 所有命令退出码为 0。

- [x] **Step 3: 显式暂存并提交实现**

```powershell
git add -- `
  apps/agent-service/src/inkforge_agents/tools/control.py `
  apps/agent-service/tests/tools/test_control.py `
  apps/core-api/src/inkforge_core/reviews/apply.py `
  apps/core-api/tests/reviews/test_artifact_apply.py `
  docs/plans/2026-08-07-beat-plan-contract-alignment.md
git diff --cached --name-only
git diff --cached --check
git commit -m "修复：统一章节计划场景字段契约"
```

Expected: 暂存区只包含以上文件，提交成功。

- [ ] **Step 4: 推送 main 并确认生产部署**

```powershell
git push origin main
$commit = git rev-parse HEAD
$run = gh run list --workflow "CI and Deploy" --branch main --commit $commit --event push --limit 1 `
  --json databaseId,headSha,status,conclusion,url | ConvertFrom-Json
gh run watch $run.databaseId --exit-status
gh run view $run.databaseId --json headSha,status,conclusion,jobs,url
```

Expected: `ci` 与 `deploy` job 均为 `success`，部署日志中的 Core 与 Agent 镜像标签均为本次完整提交 SHA，schema 指纹与编排冒烟检查通过。

- [ ] **Step 5: 重新批准生产 Artifact 并回拉验证**

通过生产 Skill wrapper 依次执行 `auth.whoami`、`long.artifact.get`、复用
`clientRequestId=long-plan-ch1-approve-20260807-01` 的 `long.artifact.approve`、`long.task.watch`、
`long.artifact.get` 和 `long.chapter.get`。

Expected:

- Artifact `cmsiww264wb28sojqtwo6nyst` 从 `revision 4 / awaiting_user / verified` 收敛为 `applied`；
- 任务 `cmsiwshluwb1usojqrgz8292x` 收敛成功；
- 第一章 `cmshau1xv75e9ndii58yjeb6k` 的 `approvedBeatPlan` 非空；
- 五个 SceneBeat 顺序、目标、角色、伏笔、字数和验收标准与用户批准内容一致。
