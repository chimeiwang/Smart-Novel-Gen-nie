"""独立分集分镜的冻结上下文、局部提案与有限复审契约。"""

from __future__ import annotations

from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .video_episode import VideoEpisodeScriptDocument

Identifier = Annotated[str, Field(min_length=1, max_length=128)]
NodeKey = Annotated[str, Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")]
Sha256 = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class VideoStoryboardContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class VideoStoryboardLineage(VideoStoryboardContractModel):
    sourceShotId: Identifier
    relation: Literal["replacement", "copy", "split", "merge"]


class VideoStoryboardReferenceEvidence(VideoStoryboardContractModel):
    """Core 冻结的已批准视觉版本与已核验图片事实。"""

    canonVersionId: Identifier
    canonContentHash: Sha256
    assetId: Identifier
    sha256: Sha256
    mimeType: Literal["image/jpeg", "image/png", "image/webp"]
    duty: Literal["identity", "costume", "scene", "prop"]
    defaultStrength: int = Field(ge=1, le=100)
    settingName: str = Field(min_length=1, max_length=240)
    label: str = Field(min_length=1, max_length=240)
    includeFeatures: list[str] = Field(default_factory=list, max_length=50)
    excludeFeatures: list[str] = Field(default_factory=list, max_length=50)


class VideoStoryboardReferenceChoice(VideoStoryboardContractModel):
    """模型只选择已冻结版本及强度，其余不可变事实由 Core 回填。"""

    canonVersionId: Identifier
    strength: int | None = Field(default=None, ge=1, le=100)


class VideoStoryboardReferenceSnapshot(VideoStoryboardContractModel):
    ordinal: int = Field(ge=1, le=20)
    canonVersionId: Identifier
    canonContentHash: Sha256
    assetId: Identifier
    sha256: Sha256
    mimeType: Literal["image/jpeg", "image/png", "image/webp"]
    duty: Literal["identity", "costume", "scene", "prop"]
    strength: int = Field(ge=1, le=100)


class VideoStoryboardProductionDefaults(VideoStoryboardContractModel):
    """AI 候选固定为模拟制作输入，不能代表用户确认真实供应商费用。"""

    provider: Literal["seedance"] = "seedance"
    model: str = Field(min_length=1, max_length=200)
    generationMode: Literal["reference"] = "reference"
    executionMode: Literal["simulated"] = "simulated"
    feeConfirmed: Literal[False] = False
    ratio: Literal["16:9", "4:3", "1:1", "3:4", "9:16", "21:9", "adaptive"]
    resolution: Literal["720p"] = "720p"
    generateAudio: bool = True
    watermark: bool = False
    outputFormat: Literal["mp4"] = "mp4"


class VideoStoryboardProductionIntentProposal(VideoStoryboardProductionDefaults):
    prompt: str = Field(min_length=1, max_length=2_500)
    durationSeconds: int = Field(ge=4, le=12)
    references: list[VideoStoryboardReferenceChoice] = Field(min_length=1, max_length=20)

    @model_validator(mode="after")
    def validate_references(self) -> Self:
        versions = [item.canonVersionId for item in self.references]
        if len(versions) != len(set(versions)):
            raise ValueError("同一视觉版本不能在一个镜头中重复选择")
        return self


class VideoStoryboardProductionIntent(VideoStoryboardProductionDefaults):
    prompt: str = Field(min_length=1, max_length=2_500)
    durationSeconds: int = Field(ge=4, le=12)
    references: list[VideoStoryboardReferenceSnapshot] = Field(min_length=1, max_length=20)


class _StoryboardShotIdentity(VideoStoryboardContractModel):
    id: Identifier | None = None
    tempKey: NodeKey | None = None
    lineage: list[VideoStoryboardLineage] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def validate_identity_and_lineage(self) -> Self:
        if (self.id is None) == (self.tempKey is None):
            raise ValueError("镜头必须且只能提供稳定 id 或 tempKey")
        sources = [item.sourceShotId for item in self.lineage]
        relations = {item.relation for item in self.lineage}
        if len(sources) != len(set(sources)):
            raise ValueError("镜头沿袭来源不能重复")
        if len(relations) > 1:
            raise ValueError("一个新镜头不能混用多种沿袭关系")
        if "merge" in relations and len(sources) < 2:
            raise ValueError("合并镜头必须包含至少两个有序来源")
        if relations and "merge" not in relations and len(sources) != 1:
            raise ValueError("替换、复制和拆分镜头必须各有一个来源")
        if self.id is not None and self.lineage:
            # 稳定镜头的既有 lineage 会在合并时与冻结稿精确比较。
            return self
        return self

    @property
    def identity(self) -> str:
        return self.id if self.id is not None else str(self.tempKey)


class VideoStoryboardShotProposal(_StoryboardShotIdentity):
    scriptSceneId: Identifier
    scriptLineIds: list[Identifier] = Field(default_factory=list, max_length=100)
    title: str = Field(min_length=1, max_length=240)
    action: str = Field(min_length=1, max_length=4_000)
    framing: Literal[
        "extreme_wide", "wide", "medium", "close_up", "detail", "over_shoulder", "pov"
    ]
    cameraMovement: Literal[
        "static", "pan", "tilt", "dolly", "truck", "crane", "handheld", "orbit", "zoom"
    ]
    durationMs: int = Field(ge=4_000, le=12_000)
    productionIntent: VideoStoryboardProductionIntentProposal

    @model_validator(mode="after")
    def validate_duration_and_lines(self) -> Self:
        if self.durationMs != self.productionIntent.durationSeconds * 1_000:
            raise ValueError("镜头预计时长必须与生成秒数一致")
        if len(self.scriptLineIds) != len(set(self.scriptLineIds)):
            raise ValueError("镜头绑定的台词身份不能重复")
        return self


class VideoStoryboardShot(_StoryboardShotIdentity):
    scriptSceneId: Identifier
    scriptLineIds: list[Identifier] = Field(default_factory=list, max_length=100)
    title: str = Field(min_length=1, max_length=240)
    action: str = Field(min_length=1, max_length=4_000)
    framing: Literal[
        "extreme_wide", "wide", "medium", "close_up", "detail", "over_shoulder", "pov"
    ]
    cameraMovement: Literal[
        "static", "pan", "tilt", "dolly", "truck", "crane", "handheld", "orbit", "zoom"
    ]
    durationMs: int = Field(ge=4_000, le=12_000)
    productionIntent: VideoStoryboardProductionIntent

    @model_validator(mode="after")
    def validate_duration_and_lines(self) -> Self:
        if self.durationMs != self.productionIntent.durationSeconds * 1_000:
            raise ValueError("镜头预计时长必须与生成秒数一致")
        if len(self.scriptLineIds) != len(set(self.scriptLineIds)):
            raise ValueError("镜头绑定的台词身份不能重复")
        return self


class VideoStoryboardDocument(VideoStoryboardContractModel):
    schemaVersion: Literal["video-episode-storyboard/1.0"] = "video-episode-storyboard/1.0"
    shots: list[VideoStoryboardShot] = Field(default_factory=list, max_length=300)

    @model_validator(mode="after")
    def validate_identities(self) -> Self:
        identities = [shot.identity for shot in self.shots]
        if len(identities) != len(set(identities)):
            raise ValueError("同一分镜不能重复使用镜头身份")
        return self


class VideoStoryboardProposal(VideoStoryboardContractModel):
    """起草返回完整镜头清单；局部修订只返回明确选择的稳定镜头。"""

    shots: list[VideoStoryboardShotProposal] = Field(min_length=1, max_length=300)


class VideoStoryboardContext(VideoStoryboardContractModel):
    schemaVersion: Literal["video-episode-storyboard-context/1.0"] = (
        "video-episode-storyboard-context/1.0"
    )
    episodeId: Identifier
    projectId: Identifier
    novelId: Identifier
    episodeTitle: str = Field(min_length=1, max_length=240)
    operation: Literal["episode_storyboard_generate", "episode_storyboard_revise"]
    draftRevision: int = Field(ge=1)
    draftContentHash: Sha256
    scriptVersionId: Identifier
    scriptContentHash: Sha256
    baseStoryboardVersionId: Identifier | None
    script: VideoEpisodeScriptDocument
    draft: VideoStoryboardDocument
    stableShotIds: list[Identifier] = Field(max_length=300)
    selectedShotIds: list[Identifier] = Field(max_length=300)
    productionDefaults: VideoStoryboardProductionDefaults
    availableReferences: list[VideoStoryboardReferenceEvidence] = Field(
        min_length=1, max_length=200
    )
    instruction: str = Field(min_length=1, max_length=8_000)

    @model_validator(mode="after")
    def validate_scope_and_frozen_identities(self) -> Self:
        script_scenes: set[str] = set()
        for scene in self.script.scenes:
            if scene.id is None or scene.tempKey is not None:
                raise ValueError("正式剧本场次必须使用稳定身份")
            script_scenes.add(scene.id)
            if any(line.id is None or line.tempKey is not None for line in scene.lines):
                raise ValueError("正式剧本台词必须使用稳定身份")
        if not script_scenes:
            raise ValueError("分镜必须绑定至少一个正式剧本场次")
        draft_ids: list[str] = []
        for shot in self.draft.shots:
            if shot.id is None or shot.tempKey is not None:
                raise ValueError("冻结分镜工作稿必须只包含 Core 分配的稳定镜头身份")
            draft_ids.append(shot.id)
        if draft_ids != self.stableShotIds or len(draft_ids) != len(set(draft_ids)):
            raise ValueError("稳定镜头清单必须与冻结工作稿的身份及顺序完全一致")
        if len(self.selectedShotIds) != len(set(self.selectedShotIds)):
            raise ValueError("分镜修订范围不能重复")
        if set(self.selectedShotIds) - set(self.stableShotIds):
            raise ValueError("分镜修订范围必须引用冻结工作稿中的稳定镜头")
        if self.operation == "episode_storyboard_generate" and self.selectedShotIds:
            raise ValueError("分镜起草不能携带局部修订范围")
        if self.operation == "episode_storyboard_revise" and not self.selectedShotIds:
            raise ValueError("分镜修订必须明确选择至少一个稳定镜头")
        reference_ids = [item.canonVersionId for item in self.availableReferences]
        if len(reference_ids) != len(set(reference_ids)):
            raise ValueError("冻结视觉参考版本不能重复")
        return self


class VideoStoryboardReviewFinding(VideoStoryboardContractModel):
    code: Literal[
        "script_coverage", "continuity", "shot_clarity", "feasibility", "reference", "duration"
    ]
    shotId: str | None
    scriptSceneId: str | None
    message: str = Field(min_length=1, max_length=2_000)


class VideoStoryboardReview(VideoStoryboardContractModel):
    decision: Literal["pass", "revise"]
    summary: str = Field(min_length=1, max_length=2_000)
    requiredChanges: list[str] = Field(max_length=30)
    findings: list[VideoStoryboardReviewFinding] = Field(max_length=200)

    @model_validator(mode="after")
    def validate_decision(self) -> Self:
        if (self.decision == "revise") != bool(self.requiredChanges):
            raise ValueError("分镜审阅决定与必须修改项不一致")
        return self


class VideoStoryboardStageDependency(VideoStoryboardContractModel):
    stepId: Identifier
    resultHash: Sha256


class VideoStoryboardStageInput(VideoStoryboardContractModel):
    stageKey: Literal["episode_storyboard", "episode_storyboard_review"]
    cycle: Literal[0, 1]
    candidate: VideoStoryboardProposal | None
    requiredChanges: list[str] = Field(max_length=30)
    dependencies: list[VideoStoryboardStageDependency] = Field(max_length=3)

    @model_validator(mode="after")
    def validate_stage(self) -> Self:
        if len({item.stepId for item in self.dependencies}) != len(self.dependencies):
            raise ValueError("分镜阶段不能重复引用前序结果")
        if self.stageKey == "episode_storyboard_review":
            if self.candidate is None or self.requiredChanges or not self.dependencies:
                raise ValueError("分镜审阅必须精确引用前序完整候选")
        elif self.cycle == 0:
            if self.candidate is not None or self.requiredChanges or self.dependencies:
                raise ValueError("首轮分镜输入不能伪造前序结果")
        elif self.candidate is None or not self.requiredChanges or len(self.dependencies) != 2:
            raise ValueError("分镜返工必须引用候选及其审阅要求")
        return self


class VideoStoryboardStageOutput(VideoStoryboardContractModel):
    stageKey: Literal["episode_storyboard", "episode_storyboard_review"]
    candidate: VideoStoryboardProposal | None
    review: VideoStoryboardReview | None

    @model_validator(mode="after")
    def validate_output(self) -> Self:
        if self.stageKey == "episode_storyboard":
            if self.candidate is None or self.review is not None:
                raise ValueError("分镜阶段必须只返回候选")
        elif self.review is None or self.candidate is not None:
            raise ValueError("分镜审阅阶段必须只返回审阅结论")
        return self


def merge_video_storyboard_proposal(
    context: VideoStoryboardContext, proposal: VideoStoryboardProposal
) -> VideoStoryboardDocument:
    """Core/Agent 同构校验局部权限，并把不可变参考事实写回完整工作稿候选。"""

    stable = set(context.stableShotIds)
    frozen = {shot.id: shot for shot in context.draft.shots if shot.id is not None}
    script_lines = {
        scene.id: {line.id for line in scene.lines if line.id is not None}
        for scene in context.script.scenes
        if scene.id is not None
    }
    references = {item.canonVersionId: item for item in context.availableReferences}

    if context.selectedShotIds:
        if any(shot.id is None or shot.tempKey is not None for shot in proposal.shots):
            raise ValueError("局部分镜修订只能返回明确选择的稳定镜头")
        replacements = {shot.id: shot for shot in proposal.shots}
        if len(replacements) != len(proposal.shots) or set(replacements) != set(
            context.selectedShotIds
        ):
            raise ValueError("局部分镜候选必须恰好包含所有选中镜头")
        proposals = [
            replacements[shot.id] if shot.id in replacements else _proposal_from_shot(shot)
            for shot in context.draft.shots
        ]
    else:
        proposals = proposal.shots

    identities = [shot.identity for shot in proposals]
    if len(identities) != len(set(identities)):
        raise ValueError("分镜候选的镜头身份不能重复")

    normalized: list[VideoStoryboardShot] = []
    for shot in proposals:
        if shot.id is not None:
            if shot.id not in stable:
                raise ValueError("模型不能分配新的稳定镜头身份")
            if frozen[shot.id].lineage != shot.lineage:
                raise ValueError("模型不能修改稳定镜头的沿袭事实")
        elif any(item.sourceShotId not in stable for item in shot.lineage):
            raise ValueError("新镜头沿袭只能引用冻结工作稿中的稳定镜头")

        allowed_lines = script_lines.get(shot.scriptSceneId)
        if allowed_lines is None or set(shot.scriptLineIds) - allowed_lines:
            raise ValueError("镜头必须绑定正式剧本中的确切场次和台词")
        defaults = context.productionDefaults
        intent = shot.productionIntent
        if any(
            (
                intent.provider != defaults.provider,
                intent.model != defaults.model,
                intent.generationMode != defaults.generationMode,
                intent.executionMode != defaults.executionMode,
                intent.feeConfirmed != defaults.feeConfirmed,
                intent.ratio != defaults.ratio,
                intent.resolution != defaults.resolution,
                intent.generateAudio != defaults.generateAudio,
                intent.watermark != defaults.watermark,
                intent.outputFormat != defaults.outputFormat,
            )
        ):
            raise ValueError("模型不能改变 Core 冻结的供应商执行参数或费用语义")
        reference_snapshots: list[VideoStoryboardReferenceSnapshot] = []
        for ordinal, choice in enumerate(intent.references, start=1):
            evidence = references.get(choice.canonVersionId)
            if evidence is None:
                raise ValueError("分镜候选引用了未冻结的视觉版本")
            reference_snapshots.append(
                VideoStoryboardReferenceSnapshot(
                    ordinal=ordinal,
                    canonVersionId=evidence.canonVersionId,
                    canonContentHash=evidence.canonContentHash,
                    assetId=evidence.assetId,
                    sha256=evidence.sha256,
                    mimeType=evidence.mimeType,
                    duty=evidence.duty,
                    strength=choice.strength or evidence.defaultStrength,
                )
            )
        normalized.append(
            VideoStoryboardShot(
                id=shot.id,
                tempKey=shot.tempKey,
                lineage=shot.lineage,
                scriptSceneId=shot.scriptSceneId,
                scriptLineIds=shot.scriptLineIds,
                title=shot.title,
                action=shot.action,
                framing=shot.framing,
                cameraMovement=shot.cameraMovement,
                durationMs=shot.durationMs,
                productionIntent=VideoStoryboardProductionIntent(
                    **defaults.model_dump(mode="python"),
                    prompt=intent.prompt,
                    durationSeconds=intent.durationSeconds,
                    references=reference_snapshots,
                ),
            )
        )
    return VideoStoryboardDocument(shots=normalized)


def _proposal_from_shot(shot: VideoStoryboardShot) -> VideoStoryboardShotProposal:
    """范围外镜头只做无损形状转换，随后仍经过同一冻结事实校验。"""

    intent = shot.productionIntent
    return VideoStoryboardShotProposal(
        id=shot.id,
        tempKey=shot.tempKey,
        lineage=shot.lineage,
        scriptSceneId=shot.scriptSceneId,
        scriptLineIds=shot.scriptLineIds,
        title=shot.title,
        action=shot.action,
        framing=shot.framing,
        cameraMovement=shot.cameraMovement,
        durationMs=shot.durationMs,
        productionIntent=VideoStoryboardProductionIntentProposal(
            provider=intent.provider,
            model=intent.model,
            generationMode=intent.generationMode,
            executionMode=intent.executionMode,
            feeConfirmed=intent.feeConfirmed,
            prompt=intent.prompt,
            ratio=intent.ratio,
            durationSeconds=intent.durationSeconds,
            resolution=intent.resolution,
            generateAudio=intent.generateAudio,
            watermark=intent.watermark,
            outputFormat=intent.outputFormat,
            references=[
                VideoStoryboardReferenceChoice(
                    canonVersionId=item.canonVersionId, strength=item.strength
                )
                for item in intent.references
            ],
        ),
    )
