"""独立剧集的完整剧本、来源锚点与 V2 单阶段提案契约。"""

from __future__ import annotations

import hashlib
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

Identifier = Annotated[str, Field(min_length=1, max_length=128)]
NodeKey = Annotated[str, Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")]
Sha256 = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class VideoEpisodeContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class VideoEpisodeSourceRef(VideoEpisodeContractModel):
    sourceSnapshotId: Identifier
    start: int = Field(ge=0)
    end: int = Field(ge=1)

    @model_validator(mode="after")
    def validate_range(self) -> Self:
        if self.end <= self.start:
            raise ValueError("来源范围必须是非空 Unicode 码点半开区间")
        return self


class VideoEpisodeScriptNode(VideoEpisodeContractModel):
    """已有节点使用 id；新增节点只使用临时 key，稳定身份由 Core 分配。"""

    id: Identifier | None = None
    tempKey: NodeKey | None = None

    @model_validator(mode="after")
    def validate_identity(self) -> Self:
        if (self.id is None) == (self.tempKey is None):
            raise ValueError("节点必须且只能提供 id 或 tempKey")
        return self

    @property
    def identity(self) -> str:
        return self.id if self.id is not None else str(self.tempKey)


class VideoEpisodeScriptLine(VideoEpisodeScriptNode):
    kind: Literal["action", "dialogue", "narration"]
    speakerId: Identifier | None = None
    text: str = Field(max_length=8_000)
    sourceRefs: list[VideoEpisodeSourceRef] = Field(default_factory=list, max_length=40)

    @model_validator(mode="after")
    def validate_speaker(self) -> Self:
        if self.kind == "dialogue" and self.speakerId is None:
            raise ValueError("对白必须绑定明确的小说角色身份")
        if self.kind == "action" and self.speakerId is not None:
            raise ValueError("行动节点不能冒充有说话人的对白")
        return self


class VideoEpisodeScriptScene(VideoEpisodeScriptNode):
    title: str = Field(max_length=160)
    locationLabel: str = Field(max_length=240)
    timeLabel: str = Field(max_length=160)
    narrativeTime: str = Field(max_length=400)
    characterIds: list[Identifier] = Field(default_factory=list, max_length=40)
    lines: list[VideoEpisodeScriptLine] = Field(default_factory=list, max_length=500)

    @model_validator(mode="after")
    def validate_characters(self) -> Self:
        if len(self.characterIds) != len(set(self.characterIds)):
            raise ValueError("同一场次的出场角色不能重复")
        return self


class VideoEpisodeScriptOverview(VideoEpisodeContractModel):
    summary: str = Field(default="", max_length=4_000)
    creativeIntent: str = Field(default="", max_length=4_000)
    targetDurationSeconds: int | None = Field(default=None, ge=1, le=86_400)


class VideoEpisodeEndingState(VideoEpisodeContractModel):
    key: NodeKey
    description: str = Field(min_length=1, max_length=2_000)
    entityIds: list[Identifier] = Field(default_factory=list, max_length=40)
    narrativeTime: str = Field(default="", max_length=400)


class VideoEpisodeDependencyInput(VideoEpisodeContractModel):
    producerEpisodeId: Identifier
    producerScriptVersionId: Identifier
    producerStateKey: NodeKey
    consumerSceneId: Identifier
    consumerLineId: Identifier | None = None
    narrativeTime: str = Field(min_length=1, max_length=400)
    description: str = Field(min_length=1, max_length=2_000)


class VideoEpisodeScriptDocument(VideoEpisodeContractModel):
    """工作稿和正式版共用完整结构；空工作稿不冒充已经确认的剧本。"""

    schemaVersion: Literal["video-episode-script/1.0"] = "video-episode-script/1.0"
    overview: VideoEpisodeScriptOverview = Field(default_factory=VideoEpisodeScriptOverview)
    scenes: list[VideoEpisodeScriptScene] = Field(default_factory=list, max_length=60)
    endingStates: list[VideoEpisodeEndingState] = Field(default_factory=list, max_length=100)
    dependencies: list[VideoEpisodeDependencyInput] = Field(default_factory=list, max_length=200)

    @model_validator(mode="after")
    def validate_nodes(self) -> Self:
        node_keys = [scene.identity for scene in self.scenes]
        node_keys.extend(line.identity for scene in self.scenes for line in scene.lines)
        if len(node_keys) != len(set(node_keys)):
            raise ValueError("剧本场次、台词和行动节点身份不能重复")
        state_keys = [state.key for state in self.endingStates]
        if len(state_keys) != len(set(state_keys)):
            raise ValueError("结尾状态 key 不能重复")
        scene_by_id = {scene.identity: scene for scene in self.scenes}
        for dependency in self.dependencies:
            scene = scene_by_id.get(dependency.consumerSceneId)
            if scene is None or (
                dependency.consumerLineId is not None
                and dependency.consumerLineId not in {line.identity for line in scene.lines}
            ):
                raise ValueError("承接关系必须绑定本剧本内的确切场次或台词")
        return self


class VideoEpisodeSelectedSourceEvidence(VideoEpisodeSourceRef):
    """只把明确选中的片段交给模型；偏移仍引用完整不可变章节快照。"""

    text: str
    textHash: Sha256

    @model_validator(mode="after")
    def validate_text(self) -> Self:
        if len(self.text) != self.end - self.start:
            raise ValueError("选中片段必须精确覆盖 Unicode 码点范围")
        if hashlib.sha256(self.text.encode()).hexdigest() != self.textHash:
            raise ValueError("选中片段哈希不一致")
        return self


class VideoEpisodeSourceEvidence(VideoEpisodeContractModel):
    sourceSnapshotId: Identifier
    chapterId: Identifier
    chapterTitle: str = Field(max_length=240)
    sourceHash: Sha256
    selectedRanges: list[VideoEpisodeSelectedSourceEvidence] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def validate_snapshot(self) -> Self:
        if any(
            selected.sourceSnapshotId != self.sourceSnapshotId for selected in self.selectedRanges
        ):
            raise ValueError("来源选区必须属于当前完整快照")
        return self


class VideoEpisodeCharacterEvidence(VideoEpisodeContractModel):
    id: Identifier
    name: str = Field(min_length=1, max_length=240)
    description: str = Field(default="", max_length=20_000)


class VideoEpisodeDependencyEvidence(VideoEpisodeContractModel):
    episodeId: Identifier
    scriptVersionId: Identifier
    state: VideoEpisodeEndingState
    contentHash: Sha256


class VideoEpisodeScriptContext(VideoEpisodeContractModel):
    """模型只读取 Core 已冻结的完整输入，不查询当前章节或工作稿。"""

    schemaVersion: Literal["video-episode-script-context/1.0"] = "video-episode-script-context/1.0"
    episodeId: Identifier
    projectId: Identifier
    novelId: Identifier
    episodeTitle: str = Field(min_length=1, max_length=240)
    operation: Literal["episode_script_generate", "episode_script_revise"]
    draftRevision: int = Field(ge=1)
    sourceSetVersionId: Identifier | None
    baseScriptVersionId: Identifier | None
    draft: VideoEpisodeScriptDocument
    sources: list[VideoEpisodeSourceEvidence] = Field(max_length=40)
    characters: list[VideoEpisodeCharacterEvidence] = Field(max_length=200)
    inheritedStates: list[VideoEpisodeDependencyEvidence] = Field(max_length=200)
    selectedSceneIds: list[Identifier] = Field(max_length=60)
    instruction: str = Field(min_length=1, max_length=8_000)

    @model_validator(mode="after")
    def validate_scope(self) -> Self:
        if len(self.selectedSceneIds) != len(set(self.selectedSceneIds)):
            raise ValueError("剧本修订场次不能重复")
        existing = {scene.id for scene in self.draft.scenes if scene.id is not None}
        if set(self.selectedSceneIds) - existing:
            raise ValueError("修订范围必须引用冻结工作稿中的稳定场次身份")
        if self.operation == "episode_script_generate" and self.selectedSceneIds:
            raise ValueError("剧本起草不能携带局部修订范围")
        if self.operation == "episode_script_revise" and not self.selectedSceneIds:
            raise ValueError("剧本修订必须明确选择至少一个稳定场次")
        return self


class VideoEpisodeScriptProposal(VideoEpisodeContractModel):
    """局部修订仅返回选中场次；其他内容由 Core 按冻结工作稿合并。"""

    overview: VideoEpisodeScriptOverview | None
    scenes: list[VideoEpisodeScriptScene] = Field(min_length=1, max_length=60)
    endingStates: list[VideoEpisodeEndingState] | None
    dependencies: list[VideoEpisodeDependencyInput] | None


class VideoEpisodeScriptReviewFinding(VideoEpisodeContractModel):
    code: Literal["source", "continuity", "dialogue", "clarity"]
    sceneId: str | None
    lineId: str | None
    message: str = Field(min_length=1, max_length=2_000)


class VideoEpisodeScriptReview(VideoEpisodeContractModel):
    decision: Literal["pass", "revise"]
    summary: str = Field(min_length=1, max_length=2_000)
    requiredChanges: list[str] = Field(max_length=20)
    findings: list[VideoEpisodeScriptReviewFinding] = Field(max_length=100)

    @model_validator(mode="after")
    def validate_decision(self) -> Self:
        if (self.decision == "revise") != bool(self.requiredChanges):
            raise ValueError("审阅决定与必须修改项不一致")
        return self


class VideoEpisodeScriptStageDependency(VideoEpisodeContractModel):
    stepId: Identifier
    resultHash: Sha256


class VideoEpisodeScriptStageInput(VideoEpisodeContractModel):
    stageKey: Literal["episode_script", "episode_script_review"]
    cycle: Literal[0, 1]
    candidate: VideoEpisodeScriptProposal | None
    requiredChanges: list[str] = Field(max_length=20)
    dependencies: list[VideoEpisodeScriptStageDependency] = Field(max_length=3)

    @model_validator(mode="after")
    def validate_stage(self) -> Self:
        if len({item.stepId for item in self.dependencies}) != len(self.dependencies):
            raise ValueError("剧本阶段不能重复引用前序结果")
        if self.stageKey == "episode_script_review":
            if self.candidate is None or self.requiredChanges or not self.dependencies:
                raise ValueError("审阅必须精确引用前序完整候选")
        elif self.cycle == 0:
            if self.candidate is not None or self.requiredChanges or self.dependencies:
                raise ValueError("首轮剧本输入不能伪造前序结果")
        elif self.candidate is None or not self.requiredChanges or len(self.dependencies) != 2:
            raise ValueError("返工必须引用候选及其审阅要求")
        return self


class VideoEpisodeScriptStageOutput(VideoEpisodeContractModel):
    stageKey: Literal["episode_script", "episode_script_review"]
    candidate: VideoEpisodeScriptProposal | None
    review: VideoEpisodeScriptReview | None

    @model_validator(mode="after")
    def validate_output(self) -> Self:
        if self.stageKey == "episode_script":
            if self.candidate is None or self.review is not None:
                raise ValueError("剧本阶段必须只返回候选")
        elif self.review is None or self.candidate is not None:
            raise ValueError("剧本审阅阶段必须只返回审阅结论")
        return self


def merge_video_episode_proposal(
    context: VideoEpisodeScriptContext, proposal: VideoEpisodeScriptProposal
) -> VideoEpisodeScriptDocument:
    """只合并被授权的场次，禁止候选隐式修改范围外的内容。"""

    if context.selectedSceneIds:
        if (
            proposal.overview is not None
            or proposal.endingStates is not None
            or proposal.dependencies is not None
        ):
            raise ValueError("局部修订不能修改本集概览、结尾状态或承接关系")
        replacements = {scene.id: scene for scene in proposal.scenes}
        if len(replacements) != len(proposal.scenes) or set(replacements) != set(
            context.selectedSceneIds
        ):
            raise ValueError("局部候选必须恰好包含所有选中场次")
        payload = context.draft.model_dump(mode="json")
        payload["scenes"] = [
            replacements[scene.id].model_dump(mode="json")
            if scene.id in replacements
            else scene.model_dump(mode="json")
            for scene in context.draft.scenes
        ]
        document = VideoEpisodeScriptDocument.model_validate(payload)
    else:
        if (
            proposal.overview is None
            or proposal.endingStates is None
            or proposal.dependencies is None
        ):
            raise ValueError("完整剧本候选必须包含概览、结尾状态及承接依据")
        document = VideoEpisodeScriptDocument(
            overview=proposal.overview,
            scenes=proposal.scenes,
            endingStates=proposal.endingStates,
            dependencies=proposal.dependencies,
        )
    scene_ids = {scene.id for scene in context.draft.scenes if scene.id is not None}
    line_parents = {
        line.id: scene.id
        for scene in context.draft.scenes
        for line in scene.lines
        if line.id is not None
    }
    character_ids = {character.id for character in context.characters}
    snapshots = {source.sourceSnapshotId: source for source in context.sources}
    for scene in document.scenes:
        if scene.id is not None and scene.id not in scene_ids:
            raise ValueError("模型不能分配新的稳定场次身份")
        if set(scene.characterIds) - character_ids:
            raise ValueError("候选引用了未冻结的角色")
        for line in scene.lines:
            if line.id is not None and (
                line.id not in line_parents or line_parents[line.id] != scene.id
            ):
                raise ValueError("模型不能分配新的稳定台词身份")
            if line.speakerId is not None and line.speakerId not in character_ids:
                raise ValueError("对白说话人不属于冻结角色")
            for source_ref in line.sourceRefs:
                snapshot = snapshots.get(source_ref.sourceSnapshotId)
                if snapshot is None or not any(
                    selected.start <= source_ref.start < source_ref.end <= selected.end
                    for selected in snapshot.selectedRanges
                ):
                    raise ValueError("候选来源锚点超出明确选择的取材范围")
    allowed_dependencies = {
        (state.episodeId, state.scriptVersionId, state.state.key)
        for state in context.inheritedStates
    }
    if any(
        (item.producerEpisodeId, item.producerScriptVersionId, item.producerStateKey)
        not in allowed_dependencies
        for item in document.dependencies
    ):
        raise ValueError("候选承接关系超出冻结的已确认前集状态")
    return document
