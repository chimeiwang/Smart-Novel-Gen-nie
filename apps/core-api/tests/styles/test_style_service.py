from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path

import pytest
from inkforge_core.errors import ApiError
from inkforge_core.styles.schemas import (
    ApplyStyleRequest,
    PortraitFailureRequest,
    PortraitProcessingRequest,
    PortraitSection,
    PortraitSuccessRequest,
    UpdatePortraitSectionRequest,
)
from inkforge_core.styles.service import StyleService
from inkforge_core.styles.storage import StyleStorage
from pydantic import ValidationError
from starlette.datastructures import Headers, UploadFile

NOW = datetime(2026, 7, 11, tzinfo=UTC)
SECTIONS = {
    "creativeMethodology": "方法",
    "uniqueMarkers": "标记",
    "generationStyle": "生成",
    "expressionFeatures": "表达",
    "styleTraits": "特质",
}


class MemoryRepository:
    def __init__(self) -> None:
        self.styles: dict[str, dict[str, object]] = {
            "style-1": {
                "id": "style-1",
                "name": "共享文风",
                "sourceType": "agent",
                **{key: None for key in SECTIONS},
                "portraitMarkdown": None,
                "originalCharCount": 0,
                "usedCharCount": 0,
                "truncated": False,
                "errorMessage": None,
                "createdAt": NOW,
                "updatedAt": NOW,
                "references": [],
                "tasks": [],
            }
        }
        self.owners = {"style-1": "user-1"}
        self.tasks: dict[str, dict[str, object]] = {}
        self.applied: tuple[str, str, str | None] | None = None
        self.deleted_paths: list[str] = []
        self.fail_reference_create = False

    def require_owned(self, user_id, style_id):
        if self.owners.get(style_id) != user_id:
            raise ApiError(status_code=404, code="STYLE_NOT_FOUND", message="文风不存在")
        return self.styles[style_id]

    async def list_styles(self, user_id):
        return [
            style
            for style_id, style in self.styles.items()
            if self.owners.get(style_id) == user_id
        ]

    async def create_style(self, user_id, name):
        del name
        self.owners["style-1"] = user_id
        return self.styles["style-1"]

    async def reserve_reference(self, user_id, style_id):
        self.require_owned(user_id, style_id)
        return "ref-1"

    async def create_reference(self, user_id, style_id, reference_id, fields):
        self.require_owned(user_id, style_id)
        if self.fail_reference_create:
            raise RuntimeError("数据库失败")
        value = {
            "id": reference_id,
            "styleId": style_id,
            **fields,
            "createdAt": NOW,
        }
        self.styles[style_id]["references"].append(value)
        return {key: item for key, item in value.items() if key != "filepath"}

    async def delete_reference(self, user_id, style_id, reference_id):
        self.require_owned(user_id, style_id)
        references = self.styles[style_id]["references"]
        for index, value in enumerate(references):
            if value["id"] == reference_id:
                return references.pop(index)["filepath"]
        raise ApiError(status_code=404, code="STYLE_REFERENCE_NOT_FOUND", message="参考资料不存在")

    async def delete_style(self, user_id, style_id):
        style = self.require_owned(user_id, style_id)
        self.styles.pop(style_id)
        self.owners.pop(style_id)
        return [value["filepath"] for value in style["references"]]

    async def create_portrait_task(self, user_id, style_id):
        style = self.require_owned(user_id, style_id)
        if not any(value["status"] == "ready" for value in style["references"]):
            raise ApiError(
                status_code=409, code="STYLE_REFERENCE_REQUIRED", message="请先上传参考资料"
            )
        if any(value["status"] in {"pending", "processing"} for value in self.tasks.values()):
            raise ApiError(status_code=409, code="PORTRAIT_TASK_ACTIVE", message="画像任务正在执行")
        task = {
            "id": "task-1",
            "styleId": style_id,
            "status": "pending",
            "errorMessage": None,
            "createdAt": NOW,
            "updatedAt": NOW,
        }
        self.tasks["task-1"] = task
        style["tasks"].append(task)
        return task

    async def get_portrait_task(self, user_id, task_id):
        if task_id not in self.tasks:
            raise ApiError(
                status_code=404, code="PORTRAIT_TASK_NOT_FOUND", message="画像任务不存在"
            )
        task = self.tasks[task_id]
        self.require_owned(user_id, task["styleId"])
        return task

    async def transition_portrait_task(self, style_id, task_id, target, fields=None):
        task = self.tasks[task_id]
        if task["styleId"] != style_id:
            raise ApiError(status_code=409, code="PORTRAIT_TASK_MISMATCH", message="画像任务不匹配")
        current = task["status"]
        allowed = (
            current == "pending"
            and target == "processing"
            or current == "processing"
            and target in {"success", "error"}
        )
        if current == target and target in {"processing", "success", "error"}:
            return task
        if not allowed:
            raise ApiError(
                status_code=409, code="PORTRAIT_TASK_STATE_CONFLICT", message="画像任务状态冲突"
            )
        task["status"] = target
        if target == "success":
            self.styles[style_id].update(fields or {})
        elif target == "error":
            task["errorMessage"] = "画像生成失败"
            self.styles[style_id]["errorMessage"] = "画像生成失败"
        return task

    async def get_portrait_sources(self, style_id, task_id):
        assert self.tasks[task_id]["styleId"] == style_id
        return [
            value
            for value in self.styles[style_id]["references"]
            if value["status"] == "ready"
        ]

    async def update_section(self, user_id, style_id, section, content):
        style = self.require_owned(user_id, style_id)
        style[section] = content
        from inkforge_core.styles.service import build_portrait_markdown

        style["portraitMarkdown"] = build_portrait_markdown(
            {key: style[key] for key in SECTIONS}
        )
        return style

    async def apply_style(self, novel_id, user_id, style_id):
        if user_id != "user-1":
            raise ApiError(status_code=404, code="NOVEL_NOT_FOUND", message="小说不存在")
        if style_id is not None:
            style = self.require_owned(user_id, style_id)
        if style_id is not None and not style["portraitMarkdown"]:
            raise ApiError(
                status_code=409, code="STYLE_PORTRAIT_INCOMPLETE", message="文风画像不完整"
            )
        self.applied = (novel_id, user_id, style_id)


class RecordingSubmitter:
    def __init__(self, *, failure: bool = False) -> None:
        self.calls: list[dict[str, str]] = []
        self.failure = failure

    async def submit(self, **kwargs: str) -> None:
        self.calls.append(kwargs)
        if self.failure:
            raise RuntimeError("智能体不可用")


def upload(content: str = "正文", filename: str = "作品.txt") -> UploadFile:
    return UploadFile(BytesIO(content.encode()), filename=filename, headers=Headers())


def service(tmp_path: Path, repository=None, submitter=None) -> StyleService:
    return StyleService(repository or MemoryRepository(), StyleStorage(tmp_path), submitter)


def test_section_and_callback_models_are_strict() -> None:
    with pytest.raises(ValidationError):
        UpdatePortraitSectionRequest.model_validate({"content": "内容", "userId": "攻击者"})
    with pytest.raises(ValidationError):
        ApplyStyleRequest.model_validate({"styleId": 1})
    with pytest.raises(ValidationError):
        PortraitProcessingRequest.model_validate({"runId": "run", "status": "done"})
    with pytest.raises(ValidationError):
        PortraitSuccessRequest.model_validate(
            {
                "runId": "run",
                **SECTIONS,
                "originalCharCount": 5,
                "usedCharCount": 5,
                "truncated": True,
            }
        )
    assert set(PortraitSection.__args__) == set(SECTIONS)


@pytest.mark.parametrize(
    ("model", "body"),
    [
        (PortraitProcessingRequest, {"runId": 1}),
        (PortraitProcessingRequest, {"runId": ""}),
        (PortraitFailureRequest, {"runId": "task-1", "message": ""}),
        (ApplyStyleRequest, {}),
        (UpdatePortraitSectionRequest, {"content": 1}),
    ],
)
def test_style_requests_reject_invalid_strict_values(model, body) -> None:
    with pytest.raises(ValidationError):
        model.model_validate(body)


@pytest.mark.asyncio
async def test_upload_db_failure_removes_written_file(tmp_path: Path) -> None:
    repository = MemoryRepository()
    repository.fail_reference_create = True
    with pytest.raises(RuntimeError):
        await service(tmp_path, repository).upload_reference("user-1", "style-1", upload())
    assert not await asyncio.to_thread(lambda: list(tmp_path.rglob("*.txt")))


@pytest.mark.asyncio
async def test_delete_commits_repository_before_best_effort_file_cleanup(tmp_path: Path) -> None:
    repository = MemoryRepository()
    await service(tmp_path, repository).upload_reference("user-1", "style-1", upload())
    stored_path = repository.styles["style-1"]["references"][0]["filepath"]
    target = StyleStorage(tmp_path).resolve(stored_path)
    assert target.exists()
    await service(tmp_path, repository).delete_reference("user-1", "style-1", "ref-1")
    assert repository.styles["style-1"]["references"] == []
    assert not target.exists()


@pytest.mark.asyncio
async def test_delete_style_commits_cascade_before_refusing_outside_cleanup(
    tmp_path: Path,
) -> None:
    repository = MemoryRepository()
    style_service = service(tmp_path, repository)
    await style_service.upload_reference("user-1", "style-1", upload())
    outside = tmp_path.parent / f"{tmp_path.name}-outside.txt"
    outside.write_text("keep", encoding="utf-8")
    repository.styles["style-1"]["references"].append(
        {"filepath": str(outside), "status": "ready"}
    )
    await style_service.delete_style("user-1", "style-1")
    assert "style-1" not in repository.styles
    assert outside.exists()


@pytest.mark.asyncio
async def test_second_user_cannot_read_or_mutate_private_style(tmp_path: Path) -> None:
    repository = MemoryRepository()
    repository.tasks["task-1"] = {
        "id": "task-1",
        "styleId": "style-1",
        "status": "pending",
        "errorMessage": None,
        "createdAt": NOW,
        "updatedAt": NOW,
    }
    style_service = service(tmp_path, repository, RecordingSubmitter())

    assert await style_service.list_styles("user-2") == []
    operations = (
        style_service.upload_reference("user-2", "style-1", upload()),
        style_service.delete_reference("user-2", "style-1", "ref-1"),
        style_service.delete_style("user-2", "style-1"),
        style_service.create_portrait("user-2", "style-1"),
        style_service.get_portrait_task("user-2", "task-1"),
        style_service.update_section(
            "user-2",
            "style-1",
            "styleTraits",
            UpdatePortraitSectionRequest(content="越权修改"),
        ),
    )
    for operation in operations:
        with pytest.raises(ApiError) as caught:
            await operation
        assert caught.value.status_code == 404

    assert "style-1" in repository.styles
    assert repository.styles["style-1"]["styleTraits"] is None


@pytest.mark.asyncio
async def test_create_portrait_requires_submitter_without_creating_task(tmp_path: Path) -> None:
    repository = MemoryRepository()
    await service(tmp_path, repository).upload_reference("user-1", "style-1", upload())
    with pytest.raises(ApiError) as caught:
        await service(tmp_path, repository, None).create_portrait("user-1", "style-1")
    assert caught.value.status_code == 503
    assert repository.tasks == {}


@pytest.mark.asyncio
async def test_portrait_requires_ready_reference(tmp_path: Path) -> None:
    repository = MemoryRepository()
    with pytest.raises(ApiError) as caught:
        await service(tmp_path, repository, RecordingSubmitter()).create_portrait(
            "user-1", "style-1"
        )
    assert caught.value.code == "STYLE_REFERENCE_REQUIRED"


@pytest.mark.asyncio
@pytest.mark.parametrize("active_status", ["pending", "processing"])
async def test_portrait_rejects_existing_active_task(tmp_path: Path, active_status: str) -> None:
    repository = MemoryRepository()
    style_service = service(tmp_path, repository, RecordingSubmitter())
    await style_service.upload_reference("user-1", "style-1", upload())
    repository.tasks["old-task"] = {
        "id": "old-task",
        "styleId": "style-1",
        "status": active_status,
        "errorMessage": None,
        "createdAt": NOW,
        "updatedAt": NOW,
    }
    with pytest.raises(ApiError) as caught:
        await style_service.create_portrait("user-1", "style-1")
    assert caught.value.code == "PORTRAIT_TASK_ACTIVE"


@pytest.mark.asyncio
async def test_submit_failure_keeps_pending_task_and_returns_reconcilable_id(
    tmp_path: Path,
) -> None:
    repository = MemoryRepository()
    failing = RecordingSubmitter(failure=True)
    style_service = service(tmp_path, repository, failing)
    await style_service.upload_reference("user-1", "style-1", upload())
    result = await style_service.create_portrait("user-1", "style-1")
    assert result.taskId == "task-1"
    assert result.status == "pending"
    assert repository.tasks["task-1"]["status"] == "pending"
    assert failing.calls == [
        {
            "user_id": "user-1",
            "style_id": "style-1",
            "task_id": "task-1",
            "run_id": "task-1",
        }
    ]


@pytest.mark.asyncio
async def test_portrait_state_machine_and_success_are_idempotent(tmp_path: Path) -> None:
    repository = MemoryRepository()
    submitter = RecordingSubmitter()
    style_service = service(tmp_path, repository, submitter)
    await style_service.upload_reference("user-1", "style-1", upload("甲 乙"))
    await style_service.create_portrait("user-1", "style-1")
    processing = PortraitProcessingRequest(runId="task-1")
    await style_service.mark_processing("style-1", "task-1", processing)
    await style_service.mark_processing("style-1", "task-1", processing)
    success = PortraitSuccessRequest(
        runId="task-1",
        **SECTIONS,
        originalCharCount=2,
        usedCharCount=2,
        truncated=False,
    )
    await style_service.complete_portrait("style-1", "task-1", success)
    await style_service.complete_portrait("style-1", "task-1", success)
    style = repository.styles["style-1"]
    assert (
        style["portraitMarkdown"] == "创作方法论\n方法\n\n独特标记\n标记\n\n生成风格\n生成\n\n"
        "表达特征\n表达\n\n风格特质\n特质"
    )
    assert style["truncated"] is False
    with pytest.raises(ApiError):
        await style_service.fail_portrait(
            "style-1", "task-1", PortraitFailureRequest(runId="task-1", message="供应商密钥泄漏")
        )


@pytest.mark.asyncio
async def test_portrait_context_reads_all_reference_files_without_truncation(
    tmp_path: Path,
) -> None:
    repository = MemoryRepository()
    style_service = service(tmp_path, repository, RecordingSubmitter())
    source = "甲" * 5000
    await style_service.upload_reference("user-1", "style-1", upload(source, "长篇.txt"))
    await style_service.create_portrait("user-1", "style-1")

    context = await style_service.get_portrait_context("style-1", "task-1")

    assert context["sourceText"].endswith(source)
    assert context["originalCharCount"] == 5000


@pytest.mark.asyncio
async def test_callback_rejects_run_that_is_not_task_id(tmp_path: Path) -> None:
    with pytest.raises(ApiError) as caught:
        await service(tmp_path, MemoryRepository()).mark_processing(
            "style-1", "task-1", PortraitProcessingRequest(runId="other-run")
        )
    assert caught.value.code == "PORTRAIT_RUN_MISMATCH"


@pytest.mark.asyncio
@pytest.mark.parametrize("run_id", ["other-run", "task-1 ", "style:task-1"])
async def test_all_callback_types_reject_mismatched_run(tmp_path: Path, run_id: str) -> None:
    style_service = service(tmp_path, MemoryRepository())
    with pytest.raises(ApiError) as caught:
        await style_service.fail_portrait(
            "style-1",
            "task-1",
            PortraitFailureRequest(runId=run_id, message="失败"),
        )
    assert caught.value.code == "PORTRAIT_RUN_MISMATCH"


@pytest.mark.asyncio
async def test_failure_stores_controlled_message_not_provider_text(tmp_path: Path) -> None:
    repository = MemoryRepository()
    repository.tasks["task-1"] = {
        "id": "task-1",
        "styleId": "style-1",
        "status": "processing",
        "errorMessage": None,
        "createdAt": NOW,
        "updatedAt": NOW,
    }
    await service(tmp_path, repository).fail_portrait(
        "style-1", "task-1", PortraitFailureRequest(runId="task-1", message="sk-secret 供应商原文")
    )
    assert repository.tasks["task-1"]["errorMessage"] == "画像生成失败"
    assert repository.styles["style-1"]["errorMessage"] == "画像生成失败"


@pytest.mark.asyncio
async def test_manual_section_rebuilds_only_when_all_five_are_present(tmp_path: Path) -> None:
    repository = MemoryRepository()
    style_service = service(tmp_path, repository)
    for section, content in list(SECTIONS.items())[:-1]:
        response = await style_service.update_section(
            "user-1", "style-1", section, UpdatePortraitSectionRequest(content=content)
        )
        assert response.portraitMarkdown is None
    response = await style_service.update_section(
        "user-1",
        "style-1",
        "styleTraits",
        UpdatePortraitSectionRequest(content="特质" * 5000),
    )
    assert response.portraitMarkdown is not None
    assert response.portraitMarkdown.endswith("特质" * 5000)


@pytest.mark.asyncio
async def test_apply_rechecks_novel_owner_and_requires_complete_portrait(tmp_path: Path) -> None:
    repository = MemoryRepository()
    style_service = service(tmp_path, repository)
    with pytest.raises(ApiError):
        await style_service.apply_style("attacker", "novel-1", ApplyStyleRequest(styleId=None))
    with pytest.raises(ApiError) as caught:
        await style_service.apply_style("user-1", "novel-1", ApplyStyleRequest(styleId="style-1"))
    assert caught.value.code == "STYLE_PORTRAIT_INCOMPLETE"
    repository.styles["style-1"]["portraitMarkdown"] = "完整画像"
    await style_service.apply_style("user-1", "novel-1", ApplyStyleRequest(styleId="style-1"))
    await style_service.apply_style("user-1", "novel-1", ApplyStyleRequest(styleId=None))
    assert repository.applied == ("novel-1", "user-1", None)
