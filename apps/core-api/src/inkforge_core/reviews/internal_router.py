from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from inkforge_contracts.jwt_claims import ServiceScope

from ..errors import ApiError
from ..references.internal_router import RagCallbackVerifier, get_rag_callback_verifier
from ..writing.callbacks import get_task_repository
from ..writing.tasks import WritingTaskRepository
from .repository import ReviewRepository
from .router import get_review_repository
from .schemas import (
    CreateArtifactRequest,
    ReviewArtifactResponse,
    SubmitArtifactEvaluationRequest,
)

router = APIRouter(
    prefix="/internal/v1/review-artifacts",
    tags=["内部待审核草案"],
    include_in_schema=False,
)

Verifier = Annotated[RagCallbackVerifier, Depends(get_rag_callback_verifier)]
Repository = Annotated[ReviewRepository, Depends(get_review_repository)]
TaskRepository = Annotated[WritingTaskRepository, Depends(get_task_repository)]


async def _verify(
    request: Request,
    verifier: RagCallbackVerifier,
    *,
    run_id: str,
    task_id: str,
    novel_id: str,
) -> None:
    authorization = request.headers.get("Authorization", "")
    token = authorization.removeprefix("Bearer ") if authorization.startswith("Bearer ") else ""
    await verifier.verify_request(
        token=token,
        body=await request.body(),
        http_method=request.method,
        http_path=request.url.path,
        query_string=request.scope.get("query_string", b""),
        idempotency_key=request.headers.get("Idempotency-Key", ""),
        request_timestamp=request.headers.get("X-InkForge-Timestamp", ""),
        body_sha256=request.headers.get("X-InkForge-Body-SHA256", ""),
        required_scope=ServiceScope.TOOL_WRITE,
        task_id=task_id,
        run_id=run_id,
        novel_id=novel_id,
    )


def _require_authorization_header(request: Request) -> None:
    if not request.headers.get("Authorization", "").startswith("Bearer "):
        raise ApiError(
            status_code=401,
            code="SERVICE_AUTHENTICATION_FAILED",
            message="服务身份认证失败",
        )


@router.post("", response_model=ReviewArtifactResponse)
async def create_or_revise_artifact(
    body: CreateArtifactRequest,
    request: Request,
    verifier: Verifier,
    repository: Repository,
    task_repository: TaskRepository,
) -> ReviewArtifactResponse:
    _require_authorization_header(request)
    actual_novel_id, user_id = await task_repository.get_task_resources(body.taskId)
    if actual_novel_id != body.novelId:
        raise ApiError(
            status_code=403,
            code="ARTIFACT_TASK_MISMATCH",
            message="待审核草案与任务小说不匹配",
        )
    await _verify(
        request,
        verifier,
        run_id=body.runId,
        task_id=body.taskId,
        novel_id=body.novelId,
    )
    return await repository.create_or_revise(user_id, body)


@router.post("/{artifact_id}/evaluations", response_model=ReviewArtifactResponse)
async def submit_artifact_evaluation(
    artifact_id: str,
    body: SubmitArtifactEvaluationRequest,
    request: Request,
    verifier: Verifier,
    repository: Repository,
    task_repository: TaskRepository,
) -> ReviewArtifactResponse:
    _require_authorization_header(request)
    actual_novel_id, user_id = await task_repository.get_task_resources(body.taskId)
    if actual_novel_id != body.novelId:
        raise ApiError(
            status_code=403,
            code="ARTIFACT_TASK_MISMATCH",
            message="复审结论与任务小说不匹配",
        )
    await _verify(
        request,
        verifier,
        run_id=body.runId,
        task_id=body.taskId,
        novel_id=body.novelId,
    )
    return await repository.submit_evaluation(user_id, artifact_id, body)
