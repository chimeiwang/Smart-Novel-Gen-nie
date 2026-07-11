from __future__ import annotations

import runpy
from pathlib import Path
from typing import Any

ROOT = Path(__file__).parents[4]
MODULE = ROOT / "apps" / "core-api" / "src" / "inkforge_core" / "ops" / "recovery_audit.py"


def _load_module() -> dict[str, Any]:
    assert MODULE.is_file(), "缺少恢复演练只读审计模块"
    return runpy.run_path(str(MODULE), run_name="inkforge_recovery_audit_test")


def _snapshot(module: dict[str, Any], **overrides: object) -> object:
    values: dict[str, object] = {
        "task_id": "task-1",
        "novel_id": "novel-1",
        "phase": "active",
        "graph_state_sha256": "before",
        "updated_at": "2026-07-11T00:00:00",
        "artifact_keys": (),
        "artifact_count": 0,
        "duplicate_billing_request_ids": (),
    }
    values.update(overrides)
    return module["RecoverySnapshot"](**values)


def test_recovery_audit_accepts_progress_without_duplicates() -> None:
    module = _load_module()
    before = _snapshot(module)
    after = _snapshot(
        module,
        phase="awaiting_user_review",
        graph_state_sha256="after",
        updated_at="2026-07-11T00:00:10",
        artifact_keys=("task-1:write_chapter",),
        artifact_count=1,
    )

    decision = module["evaluate_recovery"](before, after)

    assert decision.status == "pass"
    assert decision.reasons == ()


def test_recovery_audit_waits_while_task_is_still_running() -> None:
    module = _load_module()
    before = _snapshot(module)
    after = _snapshot(module, updated_at="2026-07-11T00:00:05")

    decision = module["evaluate_recovery"](before, after)

    assert decision.status == "pending"


def test_recovery_audit_rejects_error_duplicate_artifact_and_duplicate_billing() -> None:
    module = _load_module()
    before = _snapshot(module)
    after = _snapshot(
        module,
        phase="error",
        graph_state_sha256="after",
        updated_at="2026-07-11T00:00:10",
        artifact_keys=("same-key", "same-key"),
        artifact_count=2,
        duplicate_billing_request_ids=("model-duplicate",),
    )

    decision = module["evaluate_recovery"](before, after)

    assert decision.status == "fail"
    assert "任务进入错误阶段" in decision.reasons
    assert "产生重复草案键" in decision.reasons
    assert "产生重复计费请求" in decision.reasons


def test_recovery_audit_database_collection_is_read_only() -> None:
    source = MODULE.read_text(encoding="utf-8") if MODULE.is_file() else ""

    assert "SET TRANSACTION READ ONLY" in source
    assert "INSERT " not in source
    assert "UPDATE " not in source
    assert "DELETE " not in source


def test_recovery_drill_uses_machine_verification() -> None:
    source = (ROOT / "scripts" / "recovery_drill.sh").read_text(encoding="utf-8")

    assert "inkforge_core.ops.recovery_audit" in source
    assert "请在 Core 调试接口确认" not in source
    assert '[ "$status" -eq 2 ]' in source
    assert "else\n    status=$?\n  fi" in source
