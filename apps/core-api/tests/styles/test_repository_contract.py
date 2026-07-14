from __future__ import annotations

import inspect
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path

import pytest
from inkforge_core.db.models import StylePortraitTask, WritingStyle
from inkforge_core.errors import ApiError
from inkforge_core.styles.repository import StyleRepository

ROOT = Path(__file__).parents[2] / "src" / "inkforge_core"


def test_private_style_repository_requires_owner_scope() -> None:
    signatures = {
        name: inspect.signature(getattr(StyleRepository, name))
        for name in (
            "list_styles",
            "create_style",
            "create_reference",
            "delete_reference",
            "delete_style",
            "create_portrait_task",
            "get_portrait_task",
            "update_section",
        )
    }
    assert all("user_id" in signature.parameters for signature in signatures.values())
    assert "user_id" in inspect.signature(StyleRepository.apply_style).parameters


def test_style_source_contains_no_schema_mutation_or_agent_path_payload() -> None:
    source = "\n".join(
        path.read_text(encoding="utf-8") for path in (ROOT / "styles").glob("*.py")
    ).lower()
    for forbidden in (
        "create_all(",
        "drop_all(",
        "alembic",
        "create table",
        "alter table",
        "backgroundtasks",
    ):
        assert forbidden not in source
    submit_block = inspect.getsource(
        __import__(
            "inkforge_core.styles.service", fromlist=["StyleService"]
        ).StyleService.create_portrait
    )
    assert "filepath" not in submit_block
    assert "database_path" not in submit_block


class Transaction:
    def __init__(self) -> None:
        self.committed = False
        self.rolled_back = False

    @asynccontextmanager
    async def begin(self):
        try:
            yield
        except Exception:
            self.rolled_back = True
            raise
        else:
            self.committed = True


class TransitionSession(Transaction):
    def __init__(self, task: StylePortraitTask, style: WritingStyle) -> None:
        super().__init__()
        self.task = task
        self.style = style
        self.queries: list[str] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        del exc_type, exc, traceback

    async def scalar(self, statement):
        rendered = str(statement)
        self.queries.append(rendered)
        return self.task if '"StylePortraitTask"' in rendered else self.style

    async def flush(self) -> None:
        return None


def task_and_style(status: str = "processing") -> tuple[StylePortraitTask, WritingStyle]:
    now = datetime(2026, 7, 11, tzinfo=UTC).replace(tzinfo=None)
    task = StylePortraitTask(
        id="task-1",
        styleId="style-1",
        status=status,
        errorMessage=None,
        createdAt=now,
        updatedAt=now,
    )
    style = WritingStyle(
        id="style-1",
        name="共享文风",
        sourceType="agent",
        originalCharCount=0,
        usedCharCount=0,
        truncated=False,
        createdAt=now,
        updatedAt=now,
    )
    return task, style


@pytest.mark.asyncio
async def test_success_callback_locks_task_and_style_in_one_transaction() -> None:
    task, style = task_and_style()
    session = TransitionSession(task, style)
    repository = StyleRepository(lambda: session)  # type: ignore[arg-type]
    result = await repository.transition_portrait_task(
        "style-1",
        "task-1",
        "success",
        {
            "creativeMethodology": "完整方法",
            "portraitMarkdown": "完整画像",
            "originalCharCount": 20,
            "usedCharCount": 20,
            "truncated": False,
            "errorMessage": None,
        },
    )
    assert session.committed is True
    assert all("FOR UPDATE" in query for query in session.queries)
    assert result["status"] == "success"
    assert style.portraitMarkdown == "完整画像"
    assert style.truncated is False


@pytest.mark.asyncio
async def test_old_terminal_callback_cannot_overwrite_success() -> None:
    task, style = task_and_style("success")
    session = TransitionSession(task, style)
    repository = StyleRepository(lambda: session)  # type: ignore[arg-type]
    with pytest.raises(ApiError) as caught:
        await repository.transition_portrait_task("style-1", "task-1", "error")
    assert caught.value.code == "PORTRAIT_TASK_STATE_CONFLICT"
    assert task.status == "success"
    assert style.errorMessage is None


@pytest.mark.asyncio
async def test_dispatch_terminal_does_not_overwrite_successful_portrait() -> None:
    task, style = task_and_style("success")
    session = TransitionSession(task, style)
    repository = StyleRepository(lambda: session)  # type: ignore[arg-type]

    await repository.mark_portrait_dispatch_terminal(
        "style-1", "task-1", "failed"
    )

    assert task.status == "success"
    assert task.errorMessage is None
    assert style.errorMessage is None


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["pending", "processing"])
async def test_dispatch_terminal_ends_active_portrait(status: str) -> None:
    task, style = task_and_style(status)
    session = TransitionSession(task, style)
    repository = StyleRepository(lambda: session)  # type: ignore[arg-type]

    await repository.mark_portrait_dispatch_terminal(
        "style-1", "task-1", "cancelled"
    )

    assert task.status == "error"
    assert task.errorMessage == "智能体画像任务已终止：cancelled"
    assert style.errorMessage == task.errorMessage


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("current", "target"),
    [
        ("pending", "success"),
        ("pending", "error"),
        ("processing", "pending"),
        ("success", "processing"),
        ("success", "error"),
        ("error", "processing"),
        ("error", "success"),
    ],
)
async def test_repository_rejects_invalid_portrait_transition(current: str, target: str) -> None:
    task, style = task_and_style(current)
    session = TransitionSession(task, style)
    repository = StyleRepository(lambda: session)  # type: ignore[arg-type]
    with pytest.raises(ApiError) as caught:
        await repository.transition_portrait_task("style-1", "task-1", target)
    assert caught.value.code == "PORTRAIT_TASK_STATE_CONFLICT"
    assert session.rolled_back is True


def test_database_foreign_keys_preserve_delete_cascade_and_set_null() -> None:
    from inkforge_core.db.models import Novel, StyleReference

    reference_fk = next(iter(StyleReference.__table__.c.styleId.foreign_keys))
    task_fk = next(iter(StylePortraitTask.__table__.c.styleId.foreign_keys))
    novel_fk = next(iter(Novel.__table__.c.appliedStyleId.foreign_keys))
    assert reference_fk.ondelete == "CASCADE"
    assert task_fk.ondelete == "CASCADE"
    assert novel_fk.ondelete == "SET NULL"
