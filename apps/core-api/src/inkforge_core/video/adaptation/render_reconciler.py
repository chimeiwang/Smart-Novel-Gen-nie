"""逐镜 Seedance 耐久任务的短提交、短查询与结果归档协调器。"""

from __future__ import annotations

import asyncio
import logging
from typing import Literal, Protocol, cast

from inkforge_contracts.video_render import (
    SeedanceRenderQueryRequest,
    SeedanceRenderQueryResponse,
    SeedanceRenderSubmitRequest,
    SeedanceRenderSubmitResponse,
    SeedanceRuntimeReference,
    ShotRenderKeyframeManifest,
    ShotRenderReferenceManifest,
)

from ...agent_client import (
    SeedanceGatewayQueryError,
    SeedanceGatewayRejectedError,
    SeedanceSubmissionUnknownError,
)
from ...operations.transient_errors import is_transient_infrastructure_error
from ..storage import VideoAssetStorage
from .render_repository import (
    CompletedTakeInput,
    ShotRenderClaim,
    VideoShotRenderRepository,
)
from .render_security import ProviderAssetTokenCodec
from .render_storage import SeedanceResultArchiver

logger = logging.getLogger(__name__)


class SeedanceGateway(Protocol):
    async def submit_seedance_render(
        self,
        request: SeedanceRenderSubmitRequest,
    ) -> SeedanceRenderSubmitResponse: ...

    async def query_seedance_render(
        self,
        request: SeedanceRenderQueryRequest,
    ) -> SeedanceRenderQueryResponse: ...


class VideoShotRenderReconciler:
    """PostgreSQL 是权威状态；每次循环最多对供应商执行一次短操作。"""

    def __init__(
        self,
        repository: VideoShotRenderRepository,
        gateway: SeedanceGateway,
        archiver: SeedanceResultArchiver,
        storage: VideoAssetStorage,
        *,
        provider_media_base_url: str | None,
        provider_asset_token_codec: ProviderAssetTokenCodec | None,
        batch_size: int = 3,
        interval_seconds: float = 3.0,
    ) -> None:
        if batch_size < 1 or interval_seconds <= 0:
            raise ValueError("逐镜视频任务协调器配置无效")
        self._repository = repository
        self._gateway = gateway
        self._archiver = archiver
        self._storage = storage
        self._provider_media_base_url = provider_media_base_url
        self._provider_asset_token_codec = provider_asset_token_codec
        self._batch_size = batch_size
        self._interval_seconds = interval_seconds
        self._stop = asyncio.Event()

    def request_stop(self) -> None:
        self._stop.set()

    async def run_once(self) -> int:
        claims = await self._repository.claim_due_tasks(self._batch_size)
        # 不同镜头任务可以并发执行短 I/O；避免批量领取后排队时间超过数据库租约。
        await asyncio.gather(*(self._process(claim) for claim in claims))
        return len(claims)

    async def run(self) -> None:
        while not self._stop.is_set():
            try:
                await self.run_once()
            except Exception as exc:
                if not is_transient_infrastructure_error(exc):
                    raise
                logger.warning(
                    "逐镜视频任务后台协调暂时失败",
                    extra={"errorCode": type(exc).__name__},
                )
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self._interval_seconds)
            except TimeoutError:
                pass

    async def _process(self, claim: ShotRenderClaim) -> None:
        if claim.operation == "submit":
            await self._submit(claim)
        else:
            await self._query(claim)

    async def _submit(self, claim: ShotRenderClaim) -> None:
        try:
            references = self._runtime_references(claim)
            response = await self._gateway.submit_seedance_render(
                SeedanceRenderSubmitRequest(
                    taskId=claim.task_id,
                    novelId=claim.novel_id,
                    inputHash=_claim_hash(claim),
                    model=claim.manifest.model,
                    promptText=(
                        claim.manifest.providerPromptText or claim.manifest.promptText
                    ),
                    ratio=claim.manifest.ratio,
                    durationSeconds=claim.manifest.durationSeconds,
                    resolution=claim.manifest.resolution,
                    generateAudio=claim.manifest.generateAudio,
                    watermark=claim.manifest.watermark,
                    references=references,
                )
            )
        except SeedanceSubmissionUnknownError:
            await self._repository.mark_submission_unknown(
                claim.task_id,
                "Seedance 创建请求返回前连接中断；未自动重提，以免重复计费",
            )
            return
        except SeedanceGatewayRejectedError as exc:
            await self._repository.mark_submission_rejected(
                claim.task_id,
                "SEEDANCE_SUBMIT_REJECTED",
                exc.detail,
            )
            return
        except Exception as exc:
            await self._repository.mark_submission_rejected(
                claim.task_id,
                "SEEDANCE_SUBMIT_INPUT_INVALID",
                str(exc) or type(exc).__name__,
            )
            return
        await self._repository.mark_submitted(claim.task_id, response.providerTaskId)

    async def _query(self, claim: ShotRenderClaim) -> None:
        if claim.provider_task_id is None:
            await self._repository.mark_provider_terminal(
                claim.task_id,
                status="failed",
                code="SEEDANCE_PROVIDER_TASK_ID_MISSING",
                message="耐久任务缺少供应商任务标识",
            )
            return
        try:
            response = await self._gateway.query_seedance_render(
                SeedanceRenderQueryRequest(
                    taskId=claim.task_id,
                    novelId=claim.novel_id,
                    providerTaskId=claim.provider_task_id,
                    pollCount=max(claim.poll_count, 1),
                )
            )
        except SeedanceGatewayQueryError:
            await self._repository.mark_query_error(
                claim.task_id,
                "Seedance 状态查询暂时失败，稍后继续查询同一任务",
            )
            return
        if response.status in {"queued", "running"}:
            await self._repository.mark_query_progress(
                claim.task_id,
                cast(Literal["queued", "running"], response.status),
            )
            return
        if response.status in {"failed", "expired", "cancelled"}:
            error = response.error
            await self._repository.mark_provider_terminal(
                claim.task_id,
                status=cast(
                    Literal["failed", "expired", "cancelled"],
                    response.status,
                ),
                code=error.code if error is not None else f"SEEDANCE_{response.status.upper()}",
                message=(
                    error.message
                    if error is not None
                    else f"Seedance 任务状态为 {response.status}"
                ),
            )
            return
        if response.output is None:
            await self._repository.mark_query_error(
                claim.task_id,
                "Seedance 成功响应缺少视频结果",
            )
            return
        if not await self._repository.begin_archiving(claim.task_id):
            return
        # taskId 在该表内唯一，用作确定性素材 ID；崩溃恢复时可清理同一精确文件再归档。
        asset_id = claim.task_id
        stale_storage_key = f"{claim.project_id}/{asset_id}.mp4"
        self._storage.delete(stale_storage_key)
        try:
            archived = await self._archiver.archive(
                project_id=claim.project_id,
                asset_id=asset_id,
                video_url=response.output.videoUrl,
            )
            metadata = response.output.model_dump(mode="json", exclude={"videoUrl"})
            duration_ms = (
                round(response.output.durationSeconds * 1_000)
                if response.output.durationSeconds is not None
                else claim.manifest.durationSeconds * 1_000
            )
            await self._repository.complete_take(
                claim.task_id,
                CompletedTakeInput(
                    asset_id=archived.asset_id,
                    stored=archived.stored,
                    provider_metadata=metadata,
                    duration_ms=duration_ms,
                ),
            )
        except Exception as exc:
            # complete_take 可能已经提交，只是提交响应在网络中断时丢失。只有数据库仍把
            # archiving 原子改成 failed，才能确认文件没有被成功 Take 引用并执行补偿删除。
            transitioned_to_failed = await self._repository.fail_archiving(
                claim.task_id,
                f"Seedance 结果归档失败：{type(exc).__name__}",
            )
            if transitioned_to_failed:
                self._storage.delete(stale_storage_key)

    def _runtime_references(
        self,
        claim: ShotRenderClaim,
    ) -> list[SeedanceRuntimeReference]:
        if not claim.manifest.references and not claim.manifest.keyframes:
            return []
        if (
            self._provider_media_base_url is None
            or self._provider_asset_token_codec is None
        ):
            raise ValueError("VIDEO_RENDER_REFERENCE_TRANSPORT_NOT_CONFIGURED")
        by_role = {frame.role: frame for frame in claim.manifest.keyframes}
        ordered: list[
            tuple[
                ShotRenderKeyframeManifest | ShotRenderReferenceManifest,
                Literal[
                    "visual_reference",
                    "initial_state",
                    "transition_anchor",
                    "end_state",
                ],
            ]
        ] = []
        initial = by_role.get("initial_state")
        if initial is not None:
            ordered.append((initial, "initial_state"))
        ordered.extend((reference, "visual_reference") for reference in claim.manifest.references)
        transition = by_role.get("transition_anchor")
        if transition is not None:
            ordered.append((transition, "transition_anchor"))
        ending = by_role.get("end_state")
        if ending is not None:
            ordered.append((ending, "end_state"))
        result: list[SeedanceRuntimeReference] = []
        for ordinal, (reference, usage_role) in enumerate(ordered, start=1):
            asset_id = reference.assetId
            sha256 = reference.sha256
            mime_type = reference.mimeType
            result.append(
                SeedanceRuntimeReference(
                    ordinal=ordinal,
                    assetId=asset_id,
                    mimeType=mime_type,
                    url=(
                        f"{self._provider_media_base_url}/api/v1/video/provider-assets/"
                        + self._provider_asset_token_codec.encode(
                            asset_id=asset_id,
                            sha256=sha256,
                        )
                    ),
                    usageRole=usage_role,
                )
            )
        return result


def _claim_hash(claim: ShotRenderClaim) -> str:
    # 仓储已经在解析 manifest 时验证 inputHash；共享请求仍需携带同一稳定值。
    import hashlib
    import json

    payload = json.dumps(
        claim.manifest.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(payload).hexdigest()
