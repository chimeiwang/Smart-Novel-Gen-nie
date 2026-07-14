from __future__ import annotations

from typing import Any, Protocol

from ..clients.core import RunResource
from ..providers.base import ModelMessage, ModelTurnRequest
from ..queue.repository import QueueJob
from ..runtime.model_runtime import ModelCallContext, ModelRuntime
from .workflow_log import WorkflowLogPort


class PortraitCorePort(Protocol):
    async def get_portrait_context(
        self, resource: RunResource, style_id: str
    ) -> dict[str, Any]: ...

    async def mark_portrait_processing(
        self, resource: RunResource, style_id: str
    ) -> None: ...

    async def complete_portrait(
        self,
        resource: RunResource,
        style_id: str,
        result: dict[str, Any],
    ) -> None: ...

    async def fail_portrait(
        self,
        resource: RunResource,
        style_id: str,
        message: str,
    ) -> None: ...


class PortraitGeneratorPort(Protocol):
    async def generate(
        self,
        resource: RunResource,
        source_text: str,
        section: str | None = None,
    ) -> dict[str, str]: ...


class PortraitJobHandler:
    def __init__(
        self,
        core: PortraitCorePort,
        generator: PortraitGeneratorPort,
        *,
        workflow_log: WorkflowLogPort | None = None,
    ) -> None:
        self._core = core
        self._generator = generator
        self._workflow_log = workflow_log

    async def __call__(self, job: QueueJob) -> None:
        if job.kind != "portrait":
            raise ValueError("画像处理器收到错误任务类型")
        style_id = job.payload.get("styleId")
        if not isinstance(style_id, str) or not style_id:
            raise ValueError("画像任务缺少文风标识")
        section = job.payload.get("section")
        if section is not None and section not in ModelPortraitGenerator._SECTIONS:
            raise ValueError("画像任务分节无效")
        resource = RunResource(
            userId=job.userId,
            novelId=job.novelId,
            taskId=job.taskId,
            runId=job.runId,
        )
        if self._workflow_log is not None:
            self._workflow_log.start_run(
                run_id=job.runId,
                task_id=job.taskId,
                run_kind="文风画像",
                user_id=job.userId,
                novel_id=job.novelId,
                chapter_id=None,
            )
        try:
            await self._core.mark_portrait_processing(resource, style_id)
            context = await self._core.get_portrait_context(resource, style_id)
            source_text = context.get("sourceText")
            original_count = context.get("originalCharCount")
            if not isinstance(source_text, str) or not source_text:
                raise ValueError("画像上下文缺少完整参考正文")
            if isinstance(original_count, bool) or not isinstance(original_count, int):
                raise ValueError("画像上下文字数无效")
            sections = await self._generator.generate(resource, source_text, section)
            if section is None:
                result: dict[str, Any] = {
                    "mode": "full",
                    **sections,
                    "originalCharCount": original_count,
                    "usedCharCount": original_count,
                    "truncated": False,
                }
            else:
                result = {
                    "mode": "section",
                    "section": section,
                    "content": sections[section],
                    "originalCharCount": original_count,
                    "usedCharCount": original_count,
                    "truncated": False,
                }
            await self._core.complete_portrait(resource, style_id, result)
        except Exception as exc:
            try:
                await self._core.fail_portrait(resource, style_id, str(exc))
            finally:
                self._finish_log(job.runId, "错误")
            raise
        self._finish_log(job.runId, "完成")

    def _finish_log(self, run_id: str, status: str) -> None:
        if self._workflow_log is not None:
            self._workflow_log.finish_run(run_id, status)


class ModelPortraitGenerator:
    _SECTIONS = {
        "creativeMethodology": "分析作者组织素材、推进叙事和构造场景的创作方法论。",
        "uniqueMarkers": "分析可辨识的语言习惯、意象、句式和独特标记。",
        "generationStyle": "总结可直接指导后续正文生成的文风规则。",
        "expressionFeatures": "分析叙述视角、节奏、对白和描写的表达特征。",
        "styleTraits": "概括整体文风特质，并为每项结论指出文本证据。",
    }

    def __init__(self, runtime: ModelRuntime) -> None:
        self._runtime = runtime

    async def generate(
        self,
        resource: RunResource,
        source_text: str,
        section: str | None = None,
    ) -> dict[str, str]:
        result: dict[str, str] = {}
        selected = (
            self._SECTIONS.items()
            if section is None
            else ((section, self._SECTIONS[section]),)
        )
        for section_name, instruction in selected:
            response = await self._runtime.run_turn(
                ModelTurnRequest(
                    messages=[
                        ModelMessage(
                            role="system",
                            content=(
                                "你是中文小说文风分析师。只依据用户提供的完整参考资料分析，"
                                "证据不足时明确说明，不得编造。只输出本维度正文。"
                            ),
                        ),
                        ModelMessage(
                            role="user",
                            content=f"任务：{instruction}\n\n完整参考资料：\n{source_text}",
                        ),
                    ],
                    tools=[],
                    maxOutputTokens=1200,
                ),
                context=ModelCallContext(
                    userId=resource.userId,
                    novelId=resource.novelId,
                    taskId=resource.taskId,
                    runId=resource.runId,
                    agentId="编辑",
                ),
            )
            content = response.content.strip()
            if not content:
                raise RuntimeError("画像模型返回空内容")
            result[section_name] = content
        return result
