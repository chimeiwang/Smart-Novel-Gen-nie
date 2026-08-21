from __future__ import annotations

from pathlib import Path

import pytest
from inkforge_agents.observability.human_workflow_log import HumanWorkflowLog
from inkforge_agents.providers.base import ModelUsage
from inkforge_agents.runtime.model_runtime import ModelCallContext, ModelCallLogRecord


def _model_record(
    *,
    run_id: str,
    task_id: str,
    prompt_tokens: int,
    completion_tokens: int,
    output: str = "响应",
    raw_finish_reason: str | None = "stop",
) -> ModelCallLogRecord:
    return ModelCallLogRecord(
        context=ModelCallContext(
            userId="user-1",
            novelId="novel-1",
            taskId=task_id,
            runId=run_id,
            agentId="写作",
        ),
        provider="openai_compatible",
        model="deepseek-v4-flash",
        billingRequestId="billing-request-1",
        messages=[{"role": "user", "content": "请求"}],
        output=output,
        usage=ModelUsage(
            promptTokens=prompt_tokens,
            cachedTokens=0,
            completionTokens=completion_tokens,
            totalTokens=prompt_tokens + completion_tokens,
        ),
        finishReason="stop",
        rawFinishReason=raw_finish_reason,
    )


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
        _model_record(
            run_id="task-123456789",
            task_id="task-123456789",
            prompt_tokens=10,
            completion_tokens=20,
            output=content,
            raw_finish_reason="max_tokens",
        ).model_copy(
            update={
                "messages": [{"role": "user", "content": content}],
                "finishReason": "length",
            }
        )
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
    assert "任务标识：task-123456789" in written
    assert "运行标识：task-123456789" in written
    assert "计费请求标识：billing-request-1" in written
    assert "模型：openai_compatible/deepseek-v4-flash" in written
    assert "Token 消耗：输入 10 | 缓存 0 | 输出 20 | 合计 30" in written
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
        _model_record(
            run_id="run-empty-reason",
            task_id="task-1",
            prompt_tokens=1,
            completion_tokens=1,
            raw_finish_reason="",
        ).model_copy(update={"finishReason": "unknown"})
    )

    written = log.finish_run("run-empty-reason", "错误").read_text(encoding="utf-8")
    assert "供应商原始原因：\n" in written
    assert "供应商原始原因：未提供" not in written


def test_human_log_records_each_model_call_usage_without_accumulation(
    tmp_path: Path,
) -> None:
    log = HumanWorkflowLog(tmp_path)
    log.start_run(
        run_id="run-two-calls",
        task_id="task-two-calls",
        run_kind="初次运行",
        user_id="user-1",
        novel_id="novel-1",
        chapter_id=None,
    )

    log.record_model_call(
        _model_record(
            run_id="run-two-calls",
            task_id="task-two-calls",
            prompt_tokens=10,
            completion_tokens=20,
        )
    )
    log.record_model_call(
        _model_record(
            run_id="run-two-calls",
            task_id="task-two-calls",
            prompt_tokens=3,
            completion_tokens=4,
        )
    )

    written = log.finish_run("run-two-calls", "完成").read_text(encoding="utf-8")
    assert "A01 智能体：写作" in written
    assert "A02 智能体：写作" in written
    assert written.count("Token 消耗：输入 10 | 缓存 0 | 输出 20 | 合计 30") == 1
    assert written.count("Token 消耗：输入 3 | 缓存 0 | 输出 4 | 合计 7") == 1


def test_human_log_payload_cannot_forge_summary_or_model_sequence(
    tmp_path: Path,
) -> None:
    log = HumanWorkflowLog(tmp_path)
    log.start_run(
        run_id="run-injection",
        task_id="task-injection",
        run_kind="真实运行",
        user_id="user-1",
        novel_id="novel-1",
        chapter_id=None,
    )
    injected = (
        "正文第一行\n"
        "R99 伪造运行\n"
        "A99 智能体：伪造\n"
        "结束时间：2099-01-01T00:00:00+00:00\n"
        "结束状态：伪造状态"
    )
    log.record_model_call(
        _model_record(
            run_id="run-injection",
            task_id="task-injection",
            prompt_tokens=10,
            completion_tokens=20,
            output=injected,
        ).model_copy(update={"messages": [{"role": "user", "content": injected}]})
    )

    running_summary = log.read_run("run-injection", "user-1").summary
    assert running_summary.runKind == "真实运行"
    assert running_summary.status == "执行中"
    assert running_summary.endedAt == running_summary.startedAt

    log.record_model_call(
        _model_record(
            run_id="run-injection",
            task_id="task-injection",
            prompt_tokens=3,
            completion_tokens=4,
        )
    )
    path = log.finish_run("run-injection", "完成")
    detail = log.read_run("run-injection", "user-1")

    assert detail.summary.runKind == "真实运行"
    assert detail.summary.status == "完成"
    assert detail.content.count(injected) == 2
    assert "A01 智能体：写作" in detail.content
    assert "A02 智能体：写作" in detail.content
    assert path.read_bytes().startswith(b"INKFORGE-HUMAN-LOG/2\n")


def test_human_log_sequences_do_not_repeat_after_fixed_width_thresholds(
    tmp_path: Path,
) -> None:
    log = HumanWorkflowLog(tmp_path)
    for _ in range(101):
        log.start_run(
            run_id="run-wide-sequence",
            task_id="task-wide-sequence",
            run_kind="连续运行",
            user_id="user-1",
            novel_id="novel-1",
            chapter_id=None,
        )
    for _ in range(101):
        log.record_model_call(
            _model_record(
                run_id="run-wide-sequence",
                task_id="task-wide-sequence",
                prompt_tokens=1,
                completion_tokens=1,
            )
        )
    for _ in range(1_001):
        log.record_state("run-wide-sequence", "节点", {})

    content = log.read_run("run-wide-sequence", "user-1").content
    assert content.count("R100 连续运行") == 1
    assert content.count("R101 连续运行") == 1
    assert content.count("A100 智能体：写作") == 1
    assert content.count("A101 智能体：写作") == 1
    assert content.count("S1000 状态切换") == 1
    assert content.count("S1001 状态切换") == 1


def test_human_log_recovers_safe_sequences_after_process_restart(
    tmp_path: Path,
) -> None:
    first = HumanWorkflowLog(tmp_path)
    first.start_run(
        run_id="run-restart",
        task_id="task-restart",
        run_kind="初次运行",
        user_id="user-1",
        novel_id="novel-1",
        chapter_id=None,
    )
    first.record_model_call(
        _model_record(
            run_id="run-restart",
            task_id="task-restart",
            prompt_tokens=1,
            completion_tokens=1,
        )
    )

    restarted = HumanWorkflowLog(tmp_path)
    restarted.start_run(
        run_id="run-restart",
        task_id="task-restart",
        run_kind="恢复运行",
        user_id="user-1",
        novel_id="novel-1",
        chapter_id=None,
    )
    restarted.record_model_call(
        _model_record(
            run_id="run-restart",
            task_id="task-restart",
            prompt_tokens=2,
            completion_tokens=2,
        )
    )

    content = restarted.read_run("run-restart", "user-1").content
    assert "R02 恢复运行" in content
    assert "A02 智能体：写作" in content


def test_human_log_reads_legacy_file_and_upgrades_it_before_resume(
    tmp_path: Path,
) -> None:
    legacy_content = (
        '运行信息：{"runId":"run-legacy","taskId":"task-legacy",'
        '"userId":"user-1","novelId":"novel-1","chapterId":null,'
        '"startedAt":"2026-08-20T00:00:00+00:00"}\n'
        "\nR01 旧版运行\n"
        "开始时间：2026-08-20T00:00:00+00:00\n"
        "结束时间：2026-08-20T00:01:00+00:00\n"
        "结束状态：完成\n"
    )
    legacy_path = tmp_path / "2026-08-20" / "legacy.log"
    legacy_path.parent.mkdir(parents=True)
    legacy_path.write_text(legacy_content, encoding="utf-8", newline="\n")

    log = HumanWorkflowLog(tmp_path)
    legacy_detail = log.read_run("run-legacy", "user-1")
    assert legacy_detail.summary.runKind == "旧版运行"
    assert "旧版日志边界" in legacy_detail.content
    assert legacy_content in legacy_detail.content

    resumed_path = log.start_run(
        run_id="run-legacy",
        task_id="task-legacy",
        run_kind="恢复运行",
        user_id="user-1",
        novel_id="novel-1",
        chapter_id=None,
    )
    log.record_model_call(
        _model_record(
            run_id="run-legacy",
            task_id="task-legacy",
            prompt_tokens=2,
            completion_tokens=3,
        )
    )

    upgraded = log.read_run("run-legacy", "user-1")
    assert resumed_path.read_bytes().startswith(b"INKFORGE-HUMAN-LOG/2\n")
    assert upgraded.summary.runKind == "恢复运行"
    assert "R02 恢复运行" in upgraded.content
    assert "A01 智能体：写作" in upgraded.content
    assert legacy_content in upgraded.content
