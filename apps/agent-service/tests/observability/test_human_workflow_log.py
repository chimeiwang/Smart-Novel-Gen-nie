from __future__ import annotations

from pathlib import Path

import pytest
from inkforge_agents.observability.human_workflow_log import HumanWorkflowLog


def test_human_log_keeps_complete_messages_and_resume_in_same_file(tmp_path: Path) -> None:
    log = HumanWorkflowLog(tmp_path)
    content = "完整正文" * 5000

    log.start_run(
        run_id="task-123456789",
        task_id="task-123456789",
        run_kind="初次运行",
        user_id="user-1",
        novel_id="novel-1",
        chapter_id="chapter-1",
    )
    log.record_state("task-123456789", "准备操作上下文", {"阶段": "执行中"})
    log.record_model_call(
        "task-123456789",
        "写作",
        [{"role": "user", "content": content}],
        content,
        "length",
        "max_tokens",
    )
    first_path = log.finish_run("task-123456789", "等待用户确认")

    log.start_run(
        run_id="task-123456789",
        task_id="task-123456789",
        run_kind="恢复运行",
        user_id="user-1",
        novel_id="novel-1",
        chapter_id="chapter-1",
    )
    second_path = log.finish_run("task-123456789", "完成")

    assert first_path == second_path
    written = first_path.read_text(encoding="utf-8")
    assert written.count(content) == 2
    assert "R01 初次运行" in written
    assert "R02 恢复运行" in written
    assert "S001 状态切换" in written
    assert "A01 智能体：写作" in written
    assert "完成原因：length" in written
    assert "供应商原始原因：max_tokens" in written
    assert "结束状态：完成" in written


def test_human_log_lists_only_owned_runs_and_rejects_unknown_run(tmp_path: Path) -> None:
    log = HumanWorkflowLog(tmp_path)
    log.start_run(
        run_id="../../other-run",
        task_id="task-1",
        run_kind="初次运行",
        user_id="user-1",
        novel_id="novel-1",
        chapter_id=None,
    )
    path = log.finish_run("../../other-run", "错误")

    assert path.resolve().is_relative_to(tmp_path.resolve())
    assert [item.runId for item in log.list_runs("user-1")] == ["../../other-run"]
    assert log.list_runs("user-2") == []
    assert "结束状态：错误" in log.read_run("../../other-run", "user-1").content
    with pytest.raises(LookupError, match="运行日志不存在"):
        log.read_run("../../other-run", "user-2")


def test_human_log_preserves_empty_raw_finish_reason(tmp_path: Path) -> None:
    log = HumanWorkflowLog(tmp_path)
    log.start_run(
        run_id="run-empty-reason",
        task_id="task-1",
        run_kind="初次运行",
        user_id="user-1",
        novel_id="novel-1",
        chapter_id=None,
    )

    log.record_model_call(
        "run-empty-reason",
        "写作",
        [{"role": "user", "content": "请求"}],
        "响应",
        "unknown",
        "",
    )

    written = log.finish_run("run-empty-reason", "错误").read_text(encoding="utf-8")
    assert "供应商原始原因：\n" in written
    assert "供应商原始原因：未提供" not in written
