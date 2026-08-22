from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from inkforge_agents.observability.human_workflow_log import HumanWorkflowLog
from inkforge_agents.providers.base import ModelUsage
from inkforge_agents.runtime.model_runtime import ModelCallContext, ModelCallLogRecord


def _partial_frame(*, header: dict[str, object], content: bytes) -> bytes:
    header_bytes = json.dumps(
        header,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return (
        f"INKFORGE-FRAME {len(header_bytes)} {len(content)}\n".encode()
        + header_bytes
        + b"\n"
        + content
    )


def _complete_frame(*, header: dict[str, object], content: bytes = b"") -> bytes:
    return _partial_frame(header=header, content=content) + b"\n"


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


@pytest.mark.parametrize(
    "damaged_tail",
    [
        b"INKFORGE-FRA",
        b'INKFORGE-FRAME 40 0\n{"type":"model"',
        _partial_frame(
            header={"type": "model", "sequence": 2},
            content="残".encode()[:2],
        )[:-1],
        _partial_frame(
            header={"type": "model", "sequence": 2},
            content="完整正文".encode(),
        ),
    ],
    ids=["marker", "json-header", "utf8-content", "final-boundary"],
)
def test_human_log_list_isolates_incomplete_tail_and_keeps_other_runs(
    tmp_path: Path,
    damaged_tail: bytes,
) -> None:
    log = HumanWorkflowLog(tmp_path)
    damaged_path = log.start_run(
        run_id="run-damaged",
        task_id="task-damaged",
        run_kind="初次运行",
        user_id="user-1",
        novel_id="novel-1",
        chapter_id=None,
    )
    log.start_run(
        run_id="run-healthy",
        task_id="task-healthy",
        run_kind="正常运行",
        user_id="user-1",
        novel_id="novel-1",
        chapter_id=None,
    )
    with damaged_path.open("ab") as handle:
        handle.write(damaged_tail)

    restarted = HumanWorkflowLog(tmp_path)
    summaries = {item.runId: item for item in restarted.list_runs("user-1")}

    assert set(summaries) == {"run-damaged", "run-healthy"}
    assert summaries["run-damaged"].status == "日志尾部损坏"
    assert summaries["run-healthy"].status == "执行中"
    assert "日志尾部损坏" in restarted.read_run("run-damaged", "user-1").content


def test_human_log_quarantines_incomplete_tail_before_resuming(
    tmp_path: Path,
) -> None:
    first = HumanWorkflowLog(tmp_path)
    path = first.start_run(
        run_id="run-recovery",
        task_id="task-recovery",
        run_kind="初次运行",
        user_id="user-1",
        novel_id="novel-1",
        chapter_id=None,
    )
    first.record_model_call(
        _model_record(
            run_id="run-recovery",
            task_id="task-recovery",
            prompt_tokens=1,
            completion_tokens=1,
        )
    )
    damaged_tail = _partial_frame(
        header={"type": "model", "sequence": 2},
        content="未完整写入".encode(),
    )
    with path.open("ab") as handle:
        handle.write(damaged_tail)

    restarted = HumanWorkflowLog(tmp_path)
    restarted.start_run(
        run_id="run-recovery",
        task_id="task-recovery",
        run_kind="恢复运行",
        user_id="user-1",
        novel_id="novel-1",
        chapter_id=None,
    )
    restarted.record_model_call(
        _model_record(
            run_id="run-recovery",
            task_id="task-recovery",
            prompt_tokens=2,
            completion_tokens=2,
        )
    )

    recovery_files = list(path.parent.glob(f"{path.stem}.recovery-*.bin"))
    assert len(recovery_files) == 1
    assert recovery_files[0].read_bytes() == damaged_tail
    tail_sha256 = hashlib.sha256(damaged_tail).hexdigest()
    detail = restarted.read_run("run-recovery", "user-1")
    assert "人工日志尾部损坏已隔离恢复" in detail.content
    assert recovery_files[0].name in detail.content
    assert f"SHA-256：{tail_sha256}" in detail.content
    assert f"字节长度：{len(damaged_tail)}" in detail.content
    assert "R02 恢复运行" in detail.content
    assert "A02 智能体：写作" in detail.content

    clean_restart = HumanWorkflowLog(tmp_path)
    assert clean_restart.read_run("run-recovery", "user-1").summary.status == "执行中"


@pytest.mark.parametrize(
    "operation",
    ["start", "state", "model", "finish"],
)
def test_human_log_rejects_cached_v2_path_without_metadata_before_any_append(
    tmp_path: Path,
    operation: str,
) -> None:
    log = HumanWorkflowLog(tmp_path)
    path = log.start_run(
        run_id="run-metadata-lost",
        task_id="task-metadata-lost",
        run_kind="初次运行",
        user_id="user-1",
        novel_id="novel-1",
        chapter_id=None,
    )
    invalid_log = b"INKFORGE-HUMAN-LOG/2\n" + _complete_frame(
        header={
            "type": "run",
            "sequence": 1,
            "runKind": "伪造运行",
            "startedAt": "2099-01-01T00:00:00+00:00",
        },
        content="R01 伪造运行\n".encode(),
    )
    path.write_bytes(invalid_log)

    with pytest.raises(ValueError, match="元数据"):
        if operation == "start":
            log.start_run(
                run_id="run-metadata-lost",
                task_id="task-metadata-lost",
                run_kind="恢复运行",
                user_id="user-1",
                novel_id="novel-1",
                chapter_id=None,
            )
        elif operation == "state":
            log.record_state("run-metadata-lost", "恢复节点", {})
        elif operation == "model":
            log.record_model_call(
                _model_record(
                    run_id="run-metadata-lost",
                    task_id="task-metadata-lost",
                    prompt_tokens=1,
                    completion_tokens=1,
                )
            )
        else:
            log.finish_run("run-metadata-lost", "完成")

    assert path.read_bytes() == invalid_log
    assert list(path.parent.glob(f"{path.stem}.recovery-*.bin")) == []
    assert log.list_runs("user-1") == []
    with pytest.raises(LookupError, match="运行日志不存在"):
        log.read_run("run-metadata-lost", "user-1")


@pytest.mark.parametrize(
    "missing_field",
    ["runId", "taskId", "userId", "novelId", "startedAt"],
)
def test_human_log_rejects_incomplete_metadata_before_append(
    tmp_path: Path,
    missing_field: str,
) -> None:
    log = HumanWorkflowLog(tmp_path)
    path = log.start_run(
        run_id="run-incomplete-metadata",
        task_id="task-incomplete-metadata",
        run_kind="初次运行",
        user_id="user-1",
        novel_id="novel-1",
        chapter_id=None,
    )
    metadata: dict[str, object] = {
        "type": "metadata",
        "runId": "run-incomplete-metadata",
        "taskId": "task-incomplete-metadata",
        "userId": "user-1",
        "novelId": "novel-1",
        "chapterId": None,
        "startedAt": "2026-08-22T00:00:00+00:00",
    }
    metadata.pop(missing_field)
    invalid_log = b"INKFORGE-HUMAN-LOG/2\n" + _complete_frame(header=metadata)
    path.write_bytes(invalid_log)

    with pytest.raises(ValueError, match="元数据"):
        log.record_state("run-incomplete-metadata", "恢复节点", {})

    assert path.read_bytes() == invalid_log
    assert log.list_runs("user-1") == []


def test_human_log_validates_cached_run_identity_before_quarantining_tail(
    tmp_path: Path,
) -> None:
    log = HumanWorkflowLog(tmp_path)
    path = log.start_run(
        run_id="run-cached",
        task_id="task-cached",
        run_kind="初次运行",
        user_id="user-1",
        novel_id="novel-1",
        chapter_id=None,
    )
    mismatched_damaged_log = (
        b"INKFORGE-HUMAN-LOG/2\n"
        + _complete_frame(
            header={
                "type": "metadata",
                "runId": "run-other",
                "taskId": "task-other",
                "userId": "user-other",
                "novelId": "novel-other",
                "chapterId": None,
                "startedAt": "2026-08-22T00:00:00+00:00",
            }
        )
        + _complete_frame(
            header={
                "type": "run",
                "sequence": 1,
                "runKind": "其他运行",
                "startedAt": "2026-08-22T00:00:00+00:00",
            },
            content="R01 其他运行\n".encode(),
        )
        + b"INKFORGE-FRA"
    )
    path.write_bytes(mismatched_damaged_log)

    with pytest.raises(ValueError, match="运行元数据与当前运行不一致"):
        log.record_state("run-cached", "不应写入", {})

    assert path.read_bytes() == mismatched_damaged_log
    assert list(path.parent.glob(f"{path.stem}.recovery-*.bin")) == []


def test_human_log_reads_legacy_file_and_upgrades_it_before_resume(
    tmp_path: Path,
) -> None:
    legacy_content = (
        '运行信息：{"runId":"run-legacy","taskId":"task-legacy",'
        '"userId":"user-1","novelId":"novel-1","chapterId":null,'
        '"startedAt":"2026-08-20T00:00:00+00:00"}\r\n'
        "\r\nR01 旧版运行\r\n"
        "开始时间：2026-08-20T00:00:00+00:00\r\n"
        "正文中的伪造控制行如下：\r\n"
        "R99 伪造运行\r\n"
        "A99 智能体：伪造\r\n"
        "S999 状态切换\r\n"
        "结束时间：2026-08-20T00:01:00+00:00\r\n"
        "结束状态：伪造完成\r\n"
    )
    legacy_path = tmp_path / "2026-08-20" / "legacy.log"
    legacy_path.parent.mkdir(parents=True)
    legacy_path.write_bytes(legacy_content.encode("utf-8"))

    log = HumanWorkflowLog(tmp_path)
    legacy_detail = log.read_run("run-legacy", "user-1")
    assert legacy_detail.summary.runKind == "旧版未验证"
    assert legacy_detail.summary.status == "旧版未验证"
    assert legacy_detail.summary.endedAt == legacy_detail.summary.startedAt
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
    log.record_state("run-legacy", "恢复节点", {})

    upgraded = log.read_run("run-legacy", "user-1")
    assert resumed_path.read_bytes().startswith(b"INKFORGE-HUMAN-LOG/2\n")
    assert upgraded.summary.runKind == "恢复运行"
    assert "R01 恢复运行" in upgraded.content
    assert "A01 智能体：写作" in upgraded.content
    assert "S001 状态切换" in upgraded.content
    assert legacy_content in upgraded.content
    assert legacy_content.encode("utf-8") in resumed_path.read_bytes()
