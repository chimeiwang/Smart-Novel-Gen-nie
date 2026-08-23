"""视频耐久 dispatcher 的投递与故障分类测试。"""

from __future__ import annotations

import httpx
import pytest
from inkforge_contracts.video import LongSerialSettingSnapshot, VideoPlanJobPayload
from inkforge_core.db.models import VideoGenerationTask, VideoScene
from inkforge_core.video.dispatcher import VideoTaskDispatcher
from inkforge_core.video.repository import VideoRepository, VideoTaskDispatch


def _record() -> VideoTaskDispatch:
    return VideoTaskDispatch(
        user_id="user-1",
        novel_id="novel-1",
        task_id="task-1",
        job_id="video-plan-task-1",
        payload=VideoPlanJobPayload(
            projectId="project-1",
            sceneId="scene-1",
            chapterId="chapter-1",
            title="雨夜异响",
            sourceText="沈砚听见门外异响。",
            durationSeconds=15,
            ratio="16:9",
            settingSnapshot=LongSerialSettingSnapshot.from_entries([]),
        ),
    )


class _Repository:
    def __init__(self) -> None:
        self.records = [_record()]
        self.submitted: list[str] = []
        self.failures: list[tuple[str, str, bool]] = []
        self.terminals: list[tuple[str, str]] = []

    async def claim_due_plan_tasks(self, limit: int) -> list[VideoTaskDispatch]:
        assert limit == 20
        return self.records

    async def mark_submitted(self, task_id: str) -> None:
        self.submitted.append(task_id)

    async def record_dispatch_failure(
        self,
        task_id: str,
        error_code: str,
        *,
        transient: bool,
    ) -> None:
        self.failures.append((task_id, error_code, transient))

    async def settle_dispatch_terminal(self, task_id: str, agent_status: str) -> None:
        self.terminals.append((task_id, agent_status))


class _Submitter:
    def __init__(self, result: str | Exception) -> None:
        self.result = result
        self.calls = 0

    async def submit(self, **kwargs: object) -> str:
        assert kwargs["job_id"] == "video-plan-task-1"
        self.calls += 1
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


class _Transaction:
    async def __aenter__(self) -> None:
        return None

    async def __aexit__(self, *args: object) -> None:
        del args


class _FailureSession:
    def __init__(self, task: VideoGenerationTask, scene: VideoScene) -> None:
        self.task = task
        self.scene = scene

    async def __aenter__(self) -> _FailureSession:
        return self

    async def __aexit__(self, *args: object) -> None:
        del args

    def begin(self) -> _Transaction:
        return _Transaction()

    async def get(
        self,
        model: type[object],
        object_id: str,
        *,
        with_for_update: bool,
    ) -> object | None:
        assert with_for_update is True
        if model is VideoGenerationTask and object_id == self.task.id:
            return self.task
        if model is VideoScene and object_id == self.scene.id:
            return self.scene
        return None


class _FailureSessionFactory:
    def __init__(self, session: _FailureSession) -> None:
        self.session = session

    def __call__(self) -> _FailureSession:
        return self.session


class _EmptyRows:
    def all(self) -> list[object]:
        return []


class _ClaimSession:
    def __init__(self) -> None:
        self.statement: object | None = None

    async def __aenter__(self) -> _ClaimSession:
        return self

    async def __aexit__(self, *args: object) -> None:
        del args

    def begin(self) -> _Transaction:
        return _Transaction()

    async def execute(self, statement: object) -> _EmptyRows:
        self.statement = statement
        return _EmptyRows()


class _ClaimSessionFactory:
    def __init__(self, session: _ClaimSession) -> None:
        self.session = session

    def __call__(self) -> _ClaimSession:
        return self.session


@pytest.mark.asyncio
async def test_dispatcher_marks_accepted_job_submitted() -> None:
    repository = _Repository()
    submitter = _Submitter("queued")
    dispatcher = VideoTaskDispatcher(repository, submitter)  # type: ignore[arg-type]

    assert await dispatcher.run_once() == 1
    assert repository.submitted == ["task-1"]
    assert repository.failures == []


@pytest.mark.asyncio
async def test_repository_claims_only_current_dispatch_namespace() -> None:
    session = _ClaimSession()
    repository = VideoRepository(  # type: ignore[arg-type]
        _ClaimSessionFactory(session),
        dispatch_namespace="developer-a",
    )

    assert await repository.claim_due_plan_tasks(20) == []

    assert session.statement is not None
    compiled = session.statement.compile()  # type: ignore[union-attr]
    assert "jobId" in str(compiled) and "LIKE" in str(compiled)
    assert "video-plan-developer-a-%" in compiled.params.values()


@pytest.mark.asyncio
async def test_dispatcher_keeps_transport_failure_retryable() -> None:
    repository = _Repository()
    request = httpx.Request("POST", "http://agent-service/internal/v1/jobs")
    submitter = _Submitter(httpx.ConnectError("暂时不可连接", request=request))
    dispatcher = VideoTaskDispatcher(repository, submitter)  # type: ignore[arg-type]

    assert await dispatcher.dispatch(_record()) is False
    assert repository.submitted == []
    assert repository.failures == [("task-1", "ConnectError", True)]


@pytest.mark.asyncio
async def test_dispatcher_surfaces_programming_error_after_settling_task() -> None:
    repository = _Repository()
    submitter = _Submitter(TypeError("错误载荷"))
    dispatcher = VideoTaskDispatcher(repository, submitter)  # type: ignore[arg-type]

    with pytest.raises(TypeError, match="错误载荷"):
        await dispatcher.dispatch(_record())
    assert repository.failures == [("task-1", "TypeError", False)]


@pytest.mark.asyncio
async def test_dispatcher_settles_agent_terminal_without_callback() -> None:
    repository = _Repository()
    submitter = _Submitter("failed")
    dispatcher = VideoTaskDispatcher(repository, submitter)  # type: ignore[arg-type]

    assert await dispatcher.dispatch(_record()) is True
    assert repository.terminals == [("task-1", "failed")]


@pytest.mark.asyncio
async def test_repository_keeps_transient_dispatch_failure_pending() -> None:
    task = VideoGenerationTask(
        id="task-1",
        sceneId="scene-1",
        status="submitted",
        attemptCount=0,
    )
    scene = VideoScene(id="scene-1", status="generating")
    repository = VideoRepository(  # type: ignore[arg-type]
        _FailureSessionFactory(_FailureSession(task, scene))
    )

    await repository.record_dispatch_failure(
        task.id,
        "ConnectError",
        transient=True,
    )

    assert task.status == "pending"
    assert task.attemptCount == 1
    assert task.completedAt is None
    assert task.lastErrorCode == "VIDEO_AGENT_SUBMIT_RETRY"
    assert task.nextAttemptAt is not None
    assert scene.status == "generating"


@pytest.mark.asyncio
async def test_repository_ends_non_transient_dispatch_failure() -> None:
    task = VideoGenerationTask(
        id="task-1",
        sceneId="scene-1",
        status="pending",
        attemptCount=0,
    )
    scene = VideoScene(id="scene-1", status="generating")
    repository = VideoRepository(  # type: ignore[arg-type]
        _FailureSessionFactory(_FailureSession(task, scene))
    )

    await repository.record_dispatch_failure(
        task.id,
        "TypeError",
        transient=False,
    )

    assert task.status == "failed"
    assert task.completedAt is not None
    assert task.lastErrorCode == "VIDEO_AGENT_SUBMIT_FAILED"
    assert scene.status == "failed"


@pytest.mark.asyncio
async def test_repository_does_not_overwrite_existing_terminal_failure() -> None:
    task = VideoGenerationTask(
        id="task-1",
        sceneId="scene-1",
        status="failed",
        attemptCount=2,
        lastErrorCode="VIDEO_RENDER_FAILED",
        lastErrorMessage="渲染器返回失败",
    )
    scene = VideoScene(id="scene-1", status="failed")
    repository = VideoRepository(  # type: ignore[arg-type]
        _FailureSessionFactory(_FailureSession(task, scene))
    )

    await repository.record_dispatch_failure(
        task.id,
        "ConnectError",
        transient=True,
    )

    assert task.status == "failed"
    assert task.attemptCount == 2
    assert task.lastErrorCode == "VIDEO_RENDER_FAILED"
    assert task.lastErrorMessage == "渲染器返回失败"
    assert scene.status == "failed"
