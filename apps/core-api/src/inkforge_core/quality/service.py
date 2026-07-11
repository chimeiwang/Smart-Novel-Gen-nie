from __future__ import annotations

from typing import Any, Protocol

from ..errors import ApiError
from ..novels.schemas import QualityCheckDto
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
    async def get_run_context(
        self,
        check_id: str,
        user_id: str,
        task_id: str | None,
        message: str | None,
    ) -> dict[str, Any]: ...
    async def complete_run(
        self, check_id: str, user_id: str, result: dict[str, Any]
    ) -> None: ...
    async def fail_run(self, check_id: str, user_id: str) -> None: ...


class QualityRunSubmitter(Protocol):
    async def submit(
        self,
        *,
        user_id: str,
        check_id: str,
        novel_id: str,
        chapter_id: str,
        task_id: str | None,
        message: str | None,
    ) -> str: ...


class QualityService:
    def __init__(
        self,
        repository: QualityRepositoryPort,
        submitter: QualityRunSubmitter | None,
    ) -> None:
        self._repository = repository
        self._submitter = submitter

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
        if self._submitter is None:
            raise ApiError(
                status_code=503,
                code="QUALITY_RUN_UNAVAILABLE",
                message="质量检查运行服务暂时不可用",
            )
        task_id = await self._submitter.submit(
            user_id=user_id,
            check_id=check_id,
            novel_id=check.novel_id,
            chapter_id=check.chapter_id,
            task_id=request.taskId,
            message=request.message,
        )
        return RunQualityCheckResponse(accepted=True, checkId=check_id, taskId=task_id)

    async def get_run_context(
        self,
        user_id: str,
        check_id: str,
        task_id: str | None,
        message: str | None,
    ) -> dict[str, Any]:
        return await self._repository.get_run_context(
            check_id, user_id, task_id, message
        )

    async def complete_run(
        self,
        user_id: str,
        check_id: str,
        result: dict[str, Any],
    ) -> None:
        await self._repository.complete_run(check_id, user_id, result)

    async def fail_run(self, user_id: str, check_id: str) -> None:
        await self._repository.fail_run(check_id, user_id)
