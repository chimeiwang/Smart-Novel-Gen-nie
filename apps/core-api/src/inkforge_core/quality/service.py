from __future__ import annotations

from typing import Protocol

from ..errors import ApiError
from ..novels.schemas import QualityCheckDto
from .schemas import RunQualityCheckRequest, RunQualityCheckResponse, UpdateQualityCheckRequest


class QualityRecordPort(Protocol):
    @property
    def id(self) -> str: ...

    @property
    def chapter_id(self) -> str: ...

    @property
    def type(self) -> str: ...

    @property
    def status(self) -> str: ...


class QualityRepositoryPort(Protocol):
    async def require_check(self, check_id: str, user_id: str) -> QualityRecordPort: ...
    async def get_check(self, check_id: str, user_id: str) -> QualityCheckDto: ...
    async def update_public_status(
        self, check_id: str, user_id: str, status: str, reset_result: bool
    ) -> QualityRecordPort: ...


class QualityRunSubmitter(Protocol):
    async def submit(
        self,
        *,
        user_id: str,
        check_id: str,
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
        await self._repository.require_check(check_id, user_id)
        await self._repository.update_public_status(
            check_id, user_id, request.status, request.resetResult
        )
        return await self._repository.get_check(check_id, user_id)

    async def run(
        self, user_id: str, check_id: str, request: RunQualityCheckRequest
    ) -> RunQualityCheckResponse:
        check = await self._repository.require_check(check_id, user_id)
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
            task_id=request.taskId,
            message=request.message,
        )
        return RunQualityCheckResponse(accepted=True, checkId=check_id, taskId=task_id)
