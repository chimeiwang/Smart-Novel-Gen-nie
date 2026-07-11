from __future__ import annotations

from typing import Any, Literal, Protocol

from ..errors import ApiError
from .apply import resolve_apply_target
from .schemas import ArtifactDecisionResponse, assert_status_transition


class ArtifactPort(Protocol):
    @property
    def id(self) -> str: ...

    @property
    def status(self) -> str: ...

    @property
    def payload(self) -> dict[str, Any]: ...

    @property
    def novel_id(self) -> str: ...

    @property
    def chapter_id(self) -> str | None: ...


class ReviewRepositoryPort(Protocol):
    async def require_artifact(self, user_id: str, artifact_id: str) -> ArtifactPort: ...

    async def transition(self, artifact_id: str, current: str, target: str) -> None: ...

    async def discard(self, user_id: str, artifact_id: str) -> None: ...


class ArtifactApplierPort(Protocol):
    async def apply(
        self,
        artifact: ArtifactPort,
        *,
        user_id: str,
        edited_content: str | None,
        selected_update_refs: list[dict[str, object]] | None,
    ) -> int: ...


class ReviewService:
    def __init__(self, repository: ReviewRepositoryPort, applier: ArtifactApplierPort) -> None:
        self._repository = repository
        self._applier = applier

    async def decide(
        self,
        user_id: str,
        artifact_id: str,
        decision: Literal["approve", "discard", "revise"],
        *,
        edited_content: str | None = None,
        selected_update_refs: list[dict[str, object]] | None = None,
    ) -> ArtifactDecisionResponse:
        artifact = await self._repository.require_artifact(user_id, artifact_id)
        if decision == "discard":
            await self._repository.discard(user_id, artifact_id)
            return ArtifactDecisionResponse(
                artifactId=artifact_id,
                decision=decision,
                deleted=True,
            )
        if decision == "revise":
            await self._transition(artifact_id, artifact.status, "draft")
            return ArtifactDecisionResponse(artifactId=artifact_id, decision=decision)

        if artifact.status != "awaiting_user":
            raise ApiError(
                status_code=409,
                code="ARTIFACT_NOT_AWAITING_USER",
                message="当前草案状态不能批准",
            )
        if resolve_apply_target(artifact.payload) is None:
            raise ApiError(
                status_code=400,
                code="ARTIFACT_NOT_APPLICABLE",
                message="该草案类型不能写入正式数据",
            )
        await self._transition(artifact_id, "awaiting_user", "applying")
        try:
            saved_count = await self._applier.apply(
                artifact,
                user_id=user_id,
                edited_content=edited_content,
                selected_update_refs=selected_update_refs,
            )
        except Exception:
            await self._transition(artifact_id, "applying", "awaiting_user")
            raise ApiError(
                status_code=409,
                code="ARTIFACT_APPLY_FAILED",
                message="草案正式写入失败，已恢复为等待确认",
            ) from None
        await self._transition(artifact_id, "applying", "applied")
        return ArtifactDecisionResponse(
            artifactId=artifact_id,
            decision=decision,
            savedCount=saved_count,
        )

    async def _transition(self, artifact_id: str, current: str, target: str) -> None:
        try:
            assert_status_transition(current, target)
        except ValueError as exc:
            raise ApiError(
                status_code=409,
                code="ARTIFACT_STATUS_CONFLICT",
                message=str(exc),
            ) from exc
        await self._repository.transition(artifact_id, current, target)
