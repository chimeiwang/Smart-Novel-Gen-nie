from __future__ import annotations

from typing import Any, Protocol

from ..errors import ApiError
from ..novels.schemas import QualityCheckDto
from .dispatcher import QualityDispatchRecord
from .schemas import RunQualityCheckRequest, RunQualityCheckResponse, UpdateQualityCheckRequest


class QualityRecordPort(Protocol):
    @property
    def id(self) -> str: ...

    @property
    def chapter_id(self) -> str: ...

    @property
    def novel_id(self) -> str: ...

    @property
    def type(self) -> str: ...

    @property
    def status(self) -> str: ...


class QualityRepositoryPort(Protocol):
    async def require_check(self, check_id: str, user_id: str) -> QualityRecordPort: ...
    async def get_check(self, check_id: str, user_id: str) -> QualityCheckDto: ...
    async def update_public_status(
        self, check_id: str, user_id: str, status: str, reset_result: bool
    ) -> QualityCheckDto: ...
    async def authorize_run(
        self, check_id: str, user_id: str, task_id: str | None
    ) -> QualityRecordPort: ...
    async def create_run(
        self,
        check_id: str,
        user_id: str,
        task_id: str | None,
        message: str | None,
    ) -> QualityDispatchRecord: ...
    async def get_run_context(
        self,
        check_id: str,
        user_id: str,
        task_id: str | None,
        message: str | None,
        run_id: str | None = None,
    ) -> dict[str, Any]: ...
    async def complete_run(
        self,
        check_id: str,
        user_id: str,
        result: dict[str, Any],
        *,
        run_id: str | None = None,
        novel_id: str | None = None,
    ) -> None: ...
    async def fail_run(
        self,
        check_id: str,
        user_id: str,
        *,
        run_id: str | None = None,
        novel_id: str | None = None,
    ) -> None: ...


class QualityRunDispatcherPort(Protocol):
    async def dispatch(self, record: QualityDispatchRecord) -> bool: ...


class QualityService:
    def __init__(
        self,
        repository: QualityRepositoryPort,
        dispatcher: QualityRunDispatcherPort | None = None,
        *,
        submitter: QualityRunDispatcherPort | None = None,
    ) -> None:
        self._repository = repository
        self._dispatcher = dispatcher if dispatcher is not None else submitter

    async def get_check(self, user_id: str, check_id: str) -> QualityCheckDto:
        return await self._repository.get_check(check_id, user_id)

    async def update_status(
        self, user_id: str, check_id: str, request: UpdateQualityCheckRequest
    ) -> QualityCheckDto:
        return await self._repository.update_public_status(
            check_id, user_id, request.status, request.resetResult
        )

    async def run(
        self, user_id: str, check_id: str, request: RunQualityCheckRequest
    ) -> RunQualityCheckResponse:
        check = await self._repository.authorize_run(check_id, user_id, request.taskId)
        if check.type != "consistency":
            raise ApiError(
                status_code=400,
                code="UNSUPPORTED_QUALITY_CHECK",
                message="当前只支持一致性终检",
            )
        if self._dispatcher is None:
            raise ApiError(
                status_code=503,
                code="QUALITY_RUN_UNAVAILABLE",
                message="质量检查运行服务暂时不可用",
            )
        run = await self._repository.create_run(
            check_id,
            user_id,
            request.taskId,
            request.message,
        )
        await self._dispatcher.dispatch(run)
        return RunQualityCheckResponse(accepted=True, checkId=check_id, taskId=run.run_id)

    async def get_run_context(
        self,
        user_id: str,
        check_id: str,
        task_id: str | None,
        message: str | None,
        run_id: str | None = None,
    ) -> dict[str, Any]:
        if run_id is None:
            return await self._repository.get_run_context(
                check_id,
                user_id,
                task_id,
                message,
            )
        return await self._repository.get_run_context(
            check_id, user_id, task_id, message, run_id
        )

    async def complete_run(
        self,
        user_id: str,
        check_id: str,
        result: dict[str, Any],
        *,
        run_id: str | None = None,
        novel_id: str | None = None,
    ) -> None:
        if run_id is None:
            await self._repository.complete_run(check_id, user_id, result)
            return
        await self._repository.complete_run(
            check_id,
            user_id,
            result,
            run_id=run_id,
            novel_id=novel_id,
        )

    async def fail_run(
        self,
        user_id: str,
        check_id: str,
        *,
        run_id: str | None = None,
        novel_id: str | None = None,
    ) -> None:
        if run_id is None:
            await self._repository.fail_run(check_id, user_id)
            return
        await self._repository.fail_run(
            check_id,
            user_id,
            run_id=run_id,
            novel_id=novel_id,
        )
