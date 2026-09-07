"""静态旧候选不等于运行活动，迁移前后均按真实归属和命令验证。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.architecture.durable_agent_execution_fixtures import BASE_SCHEMA, _psql, _scalar

ROOT = Path(__file__).parents[2]
HELPER = ROOT / "scripts" / "durable-agent-execution-migration.sh"
FORWARD = ROOT / "scripts" / "migrations" / "20260831_durable_agent_execution.sql"


def _drain_query(migrated: bool) -> str:
    source = HELPER.read_text(encoding="utf-8")
    function = "query_joint_drain_postgres" if migrated else "query_pre_contract_drain_postgres"
    function_start = source.index(function + "() {")
    start = source.index("WITH\nobserved AS MATERIALIZED (", function_start)
    end = source.index("\nCOMMIT;", start)
    return source[start:end].replace(":'expected_database'", "'novelwriterdev'")


@pytest.mark.parametrize("migrated", [False, True], ids=["pre-contract", "post-contract"])
def test_static_candidate_exemption_keeps_exact_owner_terminal_task_and_no_active_command(
    migrated: bool,
) -> None:
    query = _drain_query(migrated)
    for required in (
        'task.id = artifact."taskId"',
        'task."novelId" = artifact."novelId"',
        '(artifact."chapterId" IS NULL OR EXISTS (',
        'artifact_chapter.id = artifact."chapterId"',
        'artifact_chapter."novelId" = artifact."novelId"',
        'chapter."novelId" = task."novelId"',
        "task.phase::text IN ('completed', 'error')",
        'command."taskId" = task.id',
        "command.status IN ('pending', 'submitted', 'processing')",
    ):
        assert query.count(required) == 2
    assert query.count('artifact."taskId" IS NOT NULL AND artifact."workflowRunId" IS NULL') == 2
    assert "artifact.status::text = 'applying' OR NOT EXISTS" in query
    assert 'task."chapterId" = artifact."chapterId"' not in query


@pytest.mark.parametrize("migrated", [False, True], ids=["pre-contract", "post-contract"])
def test_real_postgres14_drain_preserves_only_terminal_owned_static_v1_candidates(
    isolated_postgres: tuple[str, str], migrated: bool
) -> None:
    docker, container = isolated_postgres
    query = _drain_query(migrated)
    _psql(docker, container, "DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
    _psql(docker, container, BASE_SCHEMA.read_text(encoding="utf-8"))
    if migrated:
        _psql(docker, container, FORWARD.read_text(encoding="utf-8"))
    _psql(
        docker,
        container,
        """
        INSERT INTO public."User" (id, username, "passwordHash", "updatedAt")
        VALUES ('preserve-user', 'preserve-user', 'test', CURRENT_TIMESTAMP);
        INSERT INTO public."Novel" (id, name, "userId", "updatedAt")
        VALUES ('preserve-novel', '保全作品', 'preserve-user', CURRENT_TIMESTAMP),
               ('other-novel', '其他作品', 'preserve-user', CURRENT_TIMESTAMP);
        INSERT INTO public."Chapter" (id, "novelId", title, content, "order", "updatedAt")
        VALUES ('preserve-chapter', 'preserve-novel', '正文', '完整正文不改', 1, CURRENT_TIMESTAMP),
               ('other-chapter', 'preserve-novel', '另一章', '另一章原文', 2, CURRENT_TIMESTAMP),
               ('foreign-chapter', 'other-novel', '他作章节', '他作正文', 1, CURRENT_TIMESTAMP);
        """,
    )
    expected: dict[str, set[str]] = {
        "v1ArtifactsAwaitingUser": set(),
        "v1ArtifactsRecoverable": set(),
    }
    commands: set[str] = set()
    rows = []
    cases = [
        (phase, status, None, None)
        for phase in (
            "completed",
            "error",
            "idle",
            "active",
            "waiting_call",
            "awaiting_user_review",
        )
        for status in ("draft", "under_review", "awaiting_user", "applying")
    ]
    cases += [
        ("error", status, command, None)
        for status in ("draft", "under_review", "awaiting_user")
        for command in ("pending", "submitted", "processing", "succeeded", "failed")
    ]
    cases += [
        ("completed", status, None, mismatch)
        for status in ("draft", "under_review", "awaiting_user")
        for mismatch in (
            "novel",
            "same-novel-other-chapter",
            "null-chapter",
            "missing-task",
            "task-chapter-novel",
            "artifact-chapter-novel",
            "missing-artifact-chapter",
            "missing-task-chapter",
        )
    ]
    for index, (phase, status, command, mismatch) in enumerate(cases):
        task_id = f"preserve-task-{index}"
        artifact_id = f"preserve-artifact-{index}"
        active_command = command in {"pending", "submitted", "processing"}
        blocked = (
            phase not in {"completed", "error"}
            or status == "applying"
            or active_command
            or mismatch not in {None, "null-chapter", "same-novel-other-chapter"}
        )
        if blocked:
            metric = (
                "v1ArtifactsAwaitingUser" if status == "awaiting_user" else "v1ArtifactsRecoverable"
            )
            expected[metric].add(artifact_id)
        if mismatch != "missing-task":
            task_novel = "other-novel" if mismatch == "task-chapter-novel" else "preserve-novel"
            task_chapter = (
                "missing-chapter" if mismatch == "missing-task-chapter" else "preserve-chapter"
            )
            if mismatch == "missing-task-chapter":
                rows.append("SET session_replication_role = replica;")
            rows.append(f"""
                INSERT INTO public."WritingTask" (
                  id, "novelId", "chapterId", "targetWordCount", "selectedAgents",
                  phase, "updatedAt"
                ) VALUES ('{task_id}', '{task_novel}', '{task_chapter}', 1000, '写作',
                          '{phase}', CURRENT_TIMESTAMP);
            """)  # noqa: S608 - 插值只来自本测试固定枚举和编号，不接收外部输入。
            if mismatch == "missing-task-chapter":
                rows.append("SET session_replication_role = origin;")
        novel_id = (
            "other-novel" if mismatch in {"novel", "task-chapter-novel"} else "preserve-novel"
        )
        # 对应真实 6 月旧数据：Task 已 completed，draft 绑定同作品另一章节，无任何命令。
        # 只用于 drain 分类，不能据此放宽新建、采用或恢复业务规则。
        chapter_id = {
            "same-novel-other-chapter": "other-chapter",
            "artifact-chapter-novel": "foreign-chapter",
            "missing-artifact-chapter": "missing-chapter",
        }.get(mismatch, "preserve-chapter")
        chapter_sql = "NULL" if mismatch == "null-chapter" else f"'{chapter_id}'"
        # 原创建协议允许作品级候选不绑定章节，中短篇大纲正是这个合法来源。
        artifact_kind = "outline_draft" if mismatch == "null-chapter" else "chapter_draft"
        # 只在本 module 的隔离夹具构造缺失来源的损坏行，生产约束和迁移文件不变。
        if mismatch in {"missing-task", "missing-artifact-chapter"}:
            rows.append("SET session_replication_role = replica;")
        rows.append(f"""
            INSERT INTO public."ReviewArtifact" (
              id, "novelId", "chapterId", "taskId", kind, status, "payloadJson", "updatedAt"
            ) VALUES ('{artifact_id}', '{novel_id}', {chapter_sql}, '{task_id}',
                      '{artifact_kind}', '{status}', '{{"content":"完整候选不改"}}',
                      CURRENT_TIMESTAMP);
        """)  # noqa: S608 - 插值只来自本测试固定枚举和编号，不接收外部输入。
        if mismatch in {"missing-task", "missing-artifact-chapter"}:
            rows.append("SET session_replication_role = origin;")
        if command is not None:
            command_id = f"preserve-command-{index}"
            if active_command:
                commands.add(command_id)
            rows.append(f"""
                INSERT INTO public."WritingRunCommand" (
                  id, "taskId", kind, "payloadJson", "idempotencyKey", status, "updatedAt"
                ) VALUES ('{command_id}', '{task_id}', 'start', '{{}}', '{command_id}',
                          '{command}', CURRENT_TIMESTAMP);
            """)  # noqa: S608 - 插值只来自本测试固定枚举和编号，不接收外部输入。
    # 无 WritingTask 的手工候选不扩入旧写作分类；V2 仍交给原 Run/Step 指标。
    rows.append("""
        INSERT INTO public."ReviewArtifact" (
          id, "novelId", kind, status, "payloadJson", "updatedAt"
        ) VALUES ('manual-candidate', 'preserve-novel', 'outline_draft', 'awaiting_user',
                  '{"content":"手工版本"}', CURRENT_TIMESTAMP);
    """)
    _psql(docker, container, "\n".join(rows))
    before = _scalar(
        docker,
        container,
        """
        SELECT jsonb_build_object(
          'artifacts', (SELECT jsonb_agg(to_jsonb(a) ORDER BY id) FROM public."ReviewArtifact" a),
          'chapters', (SELECT jsonb_agg(to_jsonb(c) ORDER BY id) FROM public."Chapter" c)
        )::text;
    """,
    )
    metrics = json.loads(_scalar(docker, container, query))["metrics"]
    for metric, identifiers in expected.items():
        assert {item["id"] for item in metrics[metric]} == identifiers
    assert {item["id"] for item in metrics["v1CommandsActive"]} == commands
    assert any(item["id"].startswith("preserve-task-") for item in metrics["v1WritingTasksActive"])
    assert "v2RunsActive" in metrics if migrated else "v2RunsActive" not in metrics
    after = _scalar(
        docker,
        container,
        """
        SELECT jsonb_build_object(
          'artifacts', (SELECT jsonb_agg(to_jsonb(a) ORDER BY id) FROM public."ReviewArtifact" a),
          'chapters', (SELECT jsonb_agg(to_jsonb(c) ORDER BY id) FROM public."Chapter" c)
        )::text;
    """,
    )
    assert after == before
