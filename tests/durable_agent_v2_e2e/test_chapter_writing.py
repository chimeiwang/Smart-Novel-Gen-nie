"""写作验收断言本身也必须拒绝缺失、重复及错误状态证据。"""

import json
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest

from .chapter_writing import _facts, _other_layers, assert_completed_writing
from .run_e2e import Acceptance


def writing_facts() -> dict[str, object]:
    return {
        "engineVersion": 2,
        "operation": "write_chapter",
        "status": "completed",
        "legacyTaskCount": 0,
        "legacyCommandCount": 0,
        "artifactCount": 1,
        "artifactKind": "chapter_draft",
        "artifactStatus": "applied",
        "revisionCount": 2,
        "evaluationCount": 4,
        "reviewVerdicts": ["issues_found", "issues_found", "pass", "pass"],
        "modelStepCount": 5,
        "badModelStepCount": 0,
        "patchStepCount": 1,
        "badPatchStepCount": 0,
        "matchedBillingCount": 5,
        "reservationCount": 5,
        "tokenUsageCount": 5,
        "creditLedgerCount": 0,
        "balanceDeltaMicros": 0,
        "completedEventCount": 1,
        "chapterSha256": "a" * 64,
        "otherLayersSha256": "b" * 64,
        "chapterStatus": "drafting",
        "chapterCompletedAt": None,
        "qualityCheckCount": 1,
        "qualityStatus": "pending",
        "qualityResult": None,
        "qualityGate": None,
        "qualityScoreOverall": None,
    }


def assert_patch(facts: dict[str, object]) -> None:
    assert_completed_writing(
        facts,
        model_steps=5,
        revisions=2,
        patch_steps=1,
        applied=True,
        chapter_sha256="a" * 64,
        other_layers_sha256="b" * 64,
        verdicts=["issues_found", "issues_found", "pass", "pass"],
    )


def test_writing_acceptance_requires_two_reviews_after_zero_model_patch() -> None:
    assert_patch(writing_facts())


@pytest.mark.parametrize(
    "field,value",
    [
        ("operation", "plan_chapter"),
        ("engineVersion", 1),
        ("status", "waiting_user"),
        ("legacyTaskCount", 1),
        ("legacyCommandCount", 1),
        ("artifactKind", "beat_plan"),
        ("modelStepCount", 6),
        ("badModelStepCount", 1),
        ("patchStepCount", 0),
        ("badPatchStepCount", 1),
        ("evaluationCount", 2),
        ("reviewVerdicts", ["issues_found", "pass"]),
        ("matchedBillingCount", 4),
        ("reservationCount", 6),
        ("tokenUsageCount", 6),
        ("creditLedgerCount", 1),
        ("balanceDeltaMicros", -1),
        ("completedEventCount", 2),
        ("chapterSha256", "c" * 64),
        ("otherLayersSha256", "c" * 64),
        ("chapterStatus", "completed"),
        ("chapterCompletedAt", "2026-09-04"),
        ("qualityCheckCount", 0),
        ("qualityStatus", "completed"),
        ("qualityResult", "旧终检"),
        ("qualityGate", "pass"),
        ("qualityScoreOverall", 90),
    ],
)
def test_writing_acceptance_rejects_wrong_or_partial_evidence(field: str, value: object) -> None:
    facts = deepcopy(writing_facts())
    facts[field] = value
    with pytest.raises(AssertionError):
        assert_patch(facts)


@pytest.mark.parametrize("field", ["qualityGate", "qualityScoreOverall"])
def test_writing_acceptance_requires_explicit_cleared_quality_fields(field: str) -> None:
    facts = writing_facts()
    facts.pop(field)
    with pytest.raises(AssertionError):
        assert_patch(facts)


def test_other_layers_sql_covers_real_independent_tables_and_hashes_changed_rows() -> None:
    contract = json.loads(
        (
            Path(__file__).resolve().parents[2]
            / "apps/core-api/src/inkforge_core/db/schema-contract.json"
        ).read_text(encoding="utf-8")
    )
    tables = {
        table["name"]: {column["name"] for column in table["columns"]}
        for table in contract["tables"]
    }
    protected = {
        "WorldSetting",
        "StoryBackground",
        "WritingBible",
        "Outline",
        "Faction",
        "Location",
        "Item",
        "Glossary",
    }
    rows = {table: [{"id": table + "-1", "content": "保持独立的数据层"}] for table in protected}
    queries: list[str] = []

    def psql(sql: str, **_kwargs: object) -> str:
        queries.append(sql)
        for table in protected:
            assert "novelId" in tables[table]
            assert f'public."{table}"' in sql
        assert 'n."worldSetting"' not in sql
        assert 'n."storyBackground"' not in sql
        return json.dumps(rows, ensure_ascii=False)

    acceptance = cast(
        Acceptance, SimpleNamespace(novel_id="novel-1", stack=SimpleNamespace(psql=psql))
    )
    original = _other_layers(acceptance)
    rows["Outline"][0]["content"] = "文本总纲被错误覆盖"
    assert _other_layers(acceptance) != original
    assert len(queries) == 2


def test_writing_facts_reads_quality_gate_and_score_without_recording_body() -> None:
    raw = writing_facts() | {"chapterContent": "保留完整正文😀\r\n", "userBalanceMicros": 100}

    def psql(sql: str, **_kwargs: object) -> str:
        if 'FROM public."WorkflowRun" r' in sql:
            assert "'qualityGate', q.\"qualityGate\"" in sql
            assert "'qualityScoreOverall', q.\"scoreOverall\"" in sql
            return json.dumps(raw, ensure_ascii=False)
        return "{}"

    acceptance = cast(
        Acceptance,
        SimpleNamespace(
            novel_id="novel-1",
            stack=SimpleNamespace(psql=psql),
            initial_credit_balance_micros=100,
            safe_diagnostics={},
        ),
    )
    facts = _facts(acceptance, "run-1")
    assert facts["qualityGate"] is None
    assert facts["qualityScoreOverall"] is None
    assert "chapterContent" not in facts
    assert "保留完整正文" not in json.dumps(acceptance.safe_diagnostics, ensure_ascii=False)
