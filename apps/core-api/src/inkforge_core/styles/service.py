from __future__ import annotations

import asyncio
import logging
from collections.abc import Mapping
from typing import Any, Protocol

from fastapi import UploadFile
from inkforge_contracts.jobs import AgentJobStatus

from ..errors import ApiError
from .schemas import (
    ApplyStyleRequest,
    CreateStyleRequest,
    FullPortraitSuccessRequest,
    PortraitAcceptedResponse,
    PortraitFailureRequest,
    PortraitProcessingRequest,
    PortraitSection,
    PortraitSuccessRequest,
    PortraitTaskResponse,
    StyleReferenceResponse,
    StyleResponse,
    UpdatePortraitSectionRequest,
)
from .storage import StyleStorage

logger = logging.getLogger(__name__)


class StyleRepositoryPort(Protocol):
    async def list_styles(self, user_id: str) -> list[dict[str, Any]]: ...
    async def create_style(self, user_id: str, name: str) -> dict[str, Any]: ...
    async def reserve_reference(self, user_id: str, style_id: str) -> str: ...
    async def create_reference(
        self, user_id: str, style_id: str, reference_id: str, fields: dict[str, Any]
    ) -> dict[str, Any]: ...
    async def delete_reference(self, user_id: str, style_id: str, reference_id: str) -> str: ...
    async def delete_style(self, user_id: str, style_id: str) -> list[str]: ...
    async def create_portrait_task(
        self,
        user_id: str,
        style_id: str,
        section: PortraitSection | None,
    ) -> dict[str, Any]: ...
    async def get_portrait_sources(
        self, style_id: str, task_id: str
    ) -> list[dict[str, Any]]: ...
    async def get_portrait_task(self, user_id: str, task_id: str) -> dict[str, Any]: ...
    async def transition_portrait_task(
        self,
        style_id: str,
        task_id: str,
        target: str,
        fields: dict[str, Any] | None = None,
        *,
        expected_section: PortraitSection | None = None,
        validate_section: bool = False,
    ) -> dict[str, Any]: ...
    async def update_section(
        self, user_id: str, style_id: str, section: PortraitSection, content: str
    ) -> dict[str, Any]: ...
    async def apply_style(self, novel_id: str, user_id: str, style_id: str | None) -> None: ...


class PortraitRunSubmitter(Protocol):
    async def submit(
        self,
        *,
        user_id: str,
        style_id: str,
        task_id: str,
        run_id: str,
        section: PortraitSection | None,
    ) -> AgentJobStatus: ...


class StyleService:
    def __init__(
        self,
        repository: StyleRepositoryPort,
        storage: StyleStorage,
        submitter: PortraitRunSubmitter | None,
    ) -> None:
        self._repository = repository
        self._storage = storage
        self._submitter = submitter

    async def list_styles(self, user_id: str) -> list[StyleResponse]:
        return [
            StyleResponse.model_validate(value)
            for value in await self._repository.list_styles(user_id)
        ]

    async def create_style(self, user_id: str, request: CreateStyleRequest) -> StyleResponse:
        name = request.name.strip()
        if not name:
            raise ApiError(status_code=422, code="STYLE_NAME_REQUIRED", message="文风名称不能为空")
        return StyleResponse.model_validate(await self._repository.create_style(user_id, name))

    async def upload_reference(
        self, user_id: str, style_id: str, upload: UploadFile
    ) -> StyleReferenceResponse:
        reference_id = await self._repository.reserve_reference(user_id, style_id)
        stored = await self._storage.save(style_id, reference_id, upload)
        try:
            value = await self._repository.create_reference(
                user_id,
                style_id,
                reference_id,
                {
                    "filename": stored.filename,
                    "filepath": stored.database_path,
                    "charCount": stored.char_count,
                    "status": "ready",
                    "errorMessage": None,
                },
            )
        except Exception:
            self._storage.delete(stored.database_path)
            raise
        return StyleReferenceResponse.model_validate(value)

    async def delete_reference(self, user_id: str, style_id: str, reference_id: str) -> None:
        path = await self._repository.delete_reference(user_id, style_id, reference_id)
        self._storage.delete(path)

    async def delete_style(self, user_id: str, style_id: str) -> None:
        paths = await self._repository.delete_style(user_id, style_id)
        for path in paths:
            self._storage.delete(path)

    async def create_portrait(
        self,
        user_id: str,
        style_id: str,
        section: PortraitSection | None = None,
    ) -> PortraitAcceptedResponse:
        if self._submitter is None:
            raise ApiError(
                status_code=503,
                code="PORTRAIT_SERVICE_UNAVAILABLE",
                message="画像生成服务暂时不可用",
            )
        task = await self._repository.create_portrait_task(user_id, style_id, section)
        task_id = str(task["id"])
        try:
            await self._submitter.submit(
                user_id=user_id,
                style_id=style_id,
                task_id=task_id,
                run_id=task_id,
                section=section,
            )
        except Exception:
            logger.warning(
                "画像任务提交失败，保留待处理任务供后续对账",
                extra={"code": "PORTRAIT_SUBMIT_FAILED", "taskId": task_id},
            )
        return PortraitAcceptedResponse(taskId=task_id, status="pending")

    async def get_portrait_context(self, style_id: str, task_id: str) -> dict[str, Any]:
        sources = await self._repository.get_portrait_sources(style_id, task_id)
        if not sources:
            raise ApiError(
                status_code=409,
                code="STYLE_REFERENCE_REQUIRED",
                message="没有可用的文风参考资料",
            )
        parts: list[str] = []
        original_count = 0
        for source in sources:
            path = source.get("filepath")
            filename = source.get("filename")
            char_count = source.get("charCount")
            if not isinstance(path, str) or not isinstance(filename, str):
                raise ApiError(
                    status_code=409,
                    code="STYLE_REFERENCE_INVALID",
                    message="文风参考资料元数据无效",
                )
            resolved = self._storage.resolve(path)
            content = await asyncio.to_thread(resolved.read_text, encoding="utf-8")
            parts.append(f"参考资料：{filename}\n\n{content}")
            original_count += (
                char_count
                if isinstance(char_count, int) and not isinstance(char_count, bool)
                else sum(not character.isspace() for character in content)
            )
        return {
            "sourceText": "\n\n".join(parts),
            "originalCharCount": original_count,
        }

    async def get_portrait_task(self, user_id: str, task_id: str) -> PortraitTaskResponse:
        return PortraitTaskResponse.model_validate(
            await self._repository.get_portrait_task(user_id, task_id)
        )

    async def mark_processing(
        self, style_id: str, task_id: str, request: PortraitProcessingRequest
    ) -> PortraitTaskResponse:
        self._require_run(task_id, request.runId)
        return PortraitTaskResponse.model_validate(
            await self._repository.transition_portrait_task(style_id, task_id, "processing")
        )

    async def complete_portrait(
        self, style_id: str, task_id: str, request: PortraitSuccessRequest
    ) -> PortraitTaskResponse:
        self._require_run(task_id, request.runId)
        if isinstance(request, FullPortraitSuccessRequest):
            sections = {
                "creativeMethodology": request.creativeMethodology,
                "uniqueMarkers": request.uniqueMarkers,
                "generationStyle": request.generationStyle,
                "expressionFeatures": request.expressionFeatures,
                "styleTraits": request.styleTraits,
            }
            expected_section: PortraitSection | None = None
            fields: dict[str, Any] = {
                **sections,
                "portraitMarkdown": build_portrait_markdown(sections),
                "originalCharCount": request.originalCharCount,
                "usedCharCount": request.usedCharCount,
                "truncated": False,
                "errorMessage": None,
            }
        else:
            expected_section = request.section
            fields = {
                request.section: request.content,
                "originalCharCount": request.originalCharCount,
                "usedCharCount": request.usedCharCount,
                "truncated": False,
                "errorMessage": None,
            }
        return PortraitTaskResponse.model_validate(
            await self._repository.transition_portrait_task(
                style_id,
                task_id,
                "success",
                fields,
                expected_section=expected_section,
                validate_section=True,
            )
        )

    async def fail_portrait(
        self, style_id: str, task_id: str, request: PortraitFailureRequest
    ) -> PortraitTaskResponse:
        self._require_run(task_id, request.runId)
        return PortraitTaskResponse.model_validate(
            await self._repository.transition_portrait_task(style_id, task_id, "error")
        )

    async def update_section(
        self,
        user_id: str,
        style_id: str,
        section: PortraitSection,
        request: UpdatePortraitSectionRequest,
    ) -> StyleResponse:
        content = request.content.strip()
        if not content:
            raise ApiError(
                status_code=422,
                code="PORTRAIT_SECTION_REQUIRED",
                message="画像分节内容不能为空",
            )
        return StyleResponse.model_validate(
            await self._repository.update_section(user_id, style_id, section, content)
        )

    async def apply_style(self, user_id: str, novel_id: str, request: ApplyStyleRequest) -> None:
        await self._repository.apply_style(novel_id, user_id, request.styleId)

    @staticmethod
    def _require_run(task_id: str, run_id: str) -> None:
        if run_id != task_id:
            raise ApiError(
                status_code=409,
                code="PORTRAIT_RUN_MISMATCH",
                message="画像运行与任务不匹配",
            )


def build_portrait_markdown(sections: Mapping[str, str | None]) -> str | None:
    ordered = (
        ("创作方法论", sections.get("creativeMethodology")),
        ("独特标记", sections.get("uniqueMarkers")),
        ("生成风格", sections.get("generationStyle")),
        ("表达特征", sections.get("expressionFeatures")),
        ("风格特质", sections.get("styleTraits")),
    )
    if any(not value for _, value in ordered):
        return None
    return "\n\n".join(f"{title}\n{value}" for title, value in ordered)
