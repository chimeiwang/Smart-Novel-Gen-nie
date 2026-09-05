"""耐久 Agent V2 结构化资料候选的严格共享协议。"""

from __future__ import annotations

from typing import Annotated, Any, Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    SerializerFunctionWrapHandler,
    model_serializer,
    model_validator,
)

from .execution import (
    ExecutionId,
    Sha256,
    StrictPositiveInt,
    canonical_execution_sha256,
    count_chapter_text_length,
)

CharacterStatus = Literal["active", "missing", "dead", "imprisoned", "unknown"]
OutlineKind = Literal["stage", "plot_unit", "chapter_group"]
OutlineStatus = Literal["planned", "in_progress", "completed", "skipped"]
OutlineTreeMode = Literal["patch", "replace"]
ReferenceType = Literal["note", "web", "book", "image", "custom"]

# 与 Java 21 Character.isWhitespace 一致；只用于判断，不修改候选原文。
_JAVA_WHITESPACE = (
    "\u0009\u000a\u000b\u000c\u000d\u001c\u001d\u001e\u001f\u0020\u1680"
    "\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2008\u2009\u200a"
    "\u2028\u2029\u205f\u3000"
)
_DbInt32 = Annotated[int, Field(ge=-(2**31), le=2**31 - 1)]


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    @model_serializer(mode="wrap")
    def serialize_present_fields(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        """默认序列化也只保留实际输入字段，显式 null/空串仍原样存在。"""

        serialized: dict[str, Any] = handler(self)
        return {
            field: value for field, value in serialized.items() if field in self.model_fields_set
        }


def _provided(value: BaseModel, *fields: str) -> set[str]:
    return value.model_fields_set.intersection(fields)


def _require_nonempty_if_provided(value: BaseModel, *fields: str) -> None:
    for field in _provided(value, *fields):
        candidate = getattr(value, field)
        if not isinstance(candidate, str) or not candidate:
            raise ValueError(f"{field} 必须是非空字符串")


def _require_nonblank_if_provided(value: BaseModel, *fields: str) -> None:
    for field in _provided(value, *fields):
        candidate = getattr(value, field)
        if not isinstance(candidate, str) or not candidate.strip(_JAVA_WHITESPACE):
            raise ValueError(f"{field} 不能为空白文本")


def _require_locator(value: BaseModel, *fields: str) -> None:
    if not any(
        isinstance(getattr(value, field), str) and getattr(value, field) for field in fields
    ):
        raise ValueError("更新项缺少可解析目标")


def _require_business_field(value: BaseModel, fields: set[str]) -> None:
    if not value.model_fields_set.intersection(fields):
        raise ValueError("update 至少需要一个业务字段")


def _require_nullable_id_if_provided(value: BaseModel, *fields: str) -> None:
    for field in _provided(value, *fields):
        candidate = getattr(value, field)
        if candidate is not None and (not isinstance(candidate, str) or not candidate):
            raise ValueError(f"{field} 必须为 null 或非空字符串")


class _CharacterOptionalFields(_StrictModel):
    aliases: str | None = None
    gender: str | None = None
    age: str | None = None
    identity: str | None = None
    appearance: str | None = None
    personality: str | None = None
    background: str | None = None
    factionId: str | None = None
    combatAbility: str | None = None
    powerLevel: str | None = None
    specialSkills: str | None = None
    coreDesire: str | None = None
    shortTermGoal: str | None = None
    behaviorBoundaries: str | None = None
    speechStyle: str | None = None
    relationshipPrinciples: str | None = None
    statusNote: str | None = None

    @model_validator(mode="after")
    def validate_link_ids(self) -> Self:
        _require_nullable_id_if_provided(self, "factionId")
        return self


class CharacterCreate(_CharacterOptionalFields):
    action: Literal["create"]
    name: str
    currentStatus: CharacterStatus = "active"


class CharacterUpdate(_CharacterOptionalFields):
    action: Literal["update"]
    id: str = ""
    characterId: str = ""
    name: str = ""
    currentStatus: CharacterStatus = "active"

    @model_validator(mode="after")
    def validate_update(self) -> Self:
        _require_locator(self, "id", "characterId", "name")
        _require_business_field(
            self,
            set(_CharacterOptionalFields.model_fields) | {"name", "currentStatus"},
        )
        return self


class CharacterDelete(_StrictModel):
    action: Literal["delete"]
    id: str = ""
    characterId: str = ""
    name: str = ""

    @model_validator(mode="after")
    def validate_target(self) -> Self:
        _require_locator(self, "id", "characterId", "name")
        return self


type CharacterMutation = CharacterCreate | CharacterUpdate | CharacterDelete


class _LocationFields(_StrictModel):
    aliases: str | None = None
    type: str | None = None
    parentId: str | None = None
    description: str | None = None
    climate: str | None = None
    culture: str | None = None

    @model_validator(mode="after")
    def validate_link_ids(self) -> Self:
        _require_nullable_id_if_provided(self, "parentId")
        return self


class LocationCreate(_LocationFields):
    action: Literal["create"]
    name: str


class LocationUpdate(_LocationFields):
    action: Literal["update"]
    id: str = ""
    locationId: str = ""
    name: str = ""

    @model_validator(mode="after")
    def validate_update(self) -> Self:
        _require_locator(self, "id", "locationId", "name")
        _require_business_field(self, set(_LocationFields.model_fields) | {"name"})
        return self


class LocationDelete(_StrictModel):
    action: Literal["delete"]
    id: str = ""
    locationId: str = ""
    name: str = ""

    @model_validator(mode="after")
    def validate_target(self) -> Self:
        _require_locator(self, "id", "locationId", "name")
        return self


type LocationMutation = LocationCreate | LocationUpdate | LocationDelete


class _ItemFields(_StrictModel):
    aliases: str | None = None
    type: str | None = None
    rarity: str | None = None
    ownerId: str | None = None
    description: str | None = None
    effect: str | None = None
    origin: str | None = None

    @model_validator(mode="after")
    def validate_link_ids(self) -> Self:
        _require_nullable_id_if_provided(self, "ownerId")
        return self


class ItemCreate(_ItemFields):
    action: Literal["create"]
    name: str


class ItemUpdate(_ItemFields):
    action: Literal["update"]
    id: str = ""
    itemId: str = ""
    name: str = ""

    @model_validator(mode="after")
    def validate_update(self) -> Self:
        _require_locator(self, "id", "itemId", "name")
        _require_business_field(self, set(_ItemFields.model_fields) | {"name"})
        return self


class ItemDelete(_StrictModel):
    action: Literal["delete"]
    id: str = ""
    itemId: str = ""
    name: str = ""

    @model_validator(mode="after")
    def validate_target(self) -> Self:
        _require_locator(self, "id", "itemId", "name")
        return self


type ItemMutation = ItemCreate | ItemUpdate | ItemDelete


class _FactionFields(_StrictModel):
    aliases: str | None = None
    type: str | None = None
    baseId: str | None = None
    description: str | None = None

    @model_validator(mode="after")
    def validate_link_ids(self) -> Self:
        _require_nullable_id_if_provided(self, "baseId")
        return self


class FactionCreate(_FactionFields):
    action: Literal["create"]
    name: str


class FactionUpdate(_FactionFields):
    action: Literal["update"]
    id: str = ""
    factionId: str = ""
    name: str = ""

    @model_validator(mode="after")
    def validate_update(self) -> Self:
        _require_locator(self, "id", "factionId", "name")
        _require_business_field(self, set(_FactionFields.model_fields) | {"name"})
        return self


class FactionDelete(_StrictModel):
    action: Literal["delete"]
    id: str = ""
    factionId: str = ""
    name: str = ""

    @model_validator(mode="after")
    def validate_target(self) -> Self:
        _require_locator(self, "id", "factionId", "name")
        return self


type FactionMutation = FactionCreate | FactionUpdate | FactionDelete


class GlossaryCreate(_StrictModel):
    action: Literal["create"]
    term: str
    definition: str
    category: str | None = None


class GlossaryUpdate(_StrictModel):
    action: Literal["update"]
    id: str = ""
    glossaryId: str = ""
    term: str = ""
    definition: str = ""
    category: str | None = None

    @model_validator(mode="after")
    def validate_update(self) -> Self:
        _require_locator(self, "id", "glossaryId", "term")
        _require_business_field(self, {"term", "definition", "category"})
        return self


class GlossaryDelete(_StrictModel):
    action: Literal["delete"]
    id: str = ""
    glossaryId: str = ""
    term: str = ""

    @model_validator(mode="after")
    def validate_target(self) -> Self:
        _require_locator(self, "id", "glossaryId", "term")
        return self


type GlossaryMutation = GlossaryCreate | GlossaryUpdate | GlossaryDelete


class CharacterExperienceCreate(_StrictModel):
    action: Literal["create"]
    characterId: str = ""
    characterName: str = ""
    chapterId: str | None = None
    content: str
    order: _DbInt32 | None = None

    @model_validator(mode="after")
    def validate_target(self) -> Self:
        _require_nullable_id_if_provided(self, "chapterId")
        _require_locator(self, "characterId", "characterName")
        return self


class CharacterExperienceUpdate(_StrictModel):
    action: Literal["update"]
    id: str
    chapterId: str | None = None
    content: str = ""
    order: _DbInt32 = 0

    @model_validator(mode="after")
    def validate_update(self) -> Self:
        _require_nonempty_if_provided(self, "id")
        _require_nullable_id_if_provided(self, "chapterId")
        _require_business_field(self, {"chapterId", "content", "order"})
        return self


class CharacterExperienceDelete(_StrictModel):
    action: Literal["delete"]
    id: str

    @model_validator(mode="after")
    def validate_target(self) -> Self:
        _require_nonempty_if_provided(self, "id")
        return self


type CharacterExperienceMutation = (
    CharacterExperienceCreate | CharacterExperienceUpdate | CharacterExperienceDelete
)


class OutlineUpdate(_StrictModel):
    nodeId: str
    status: OutlineStatus = "planned"
    actualWordCount: _DbInt32 | None = None

    @model_validator(mode="after")
    def validate_target(self) -> Self:
        _require_nonempty_if_provided(self, "nodeId")
        _require_business_field(self, {"status", "actualWordCount"})
        return self


def _validate_outline_range(value: BaseModel, *, require_pair: bool) -> None:
    start_present = "chapterStartOrder" in value.model_fields_set
    end_present = "chapterEndOrder" in value.model_fields_set
    if not start_present and not end_present:
        return
    start = value.__dict__.get("chapterStartOrder")
    end = value.__dict__.get("chapterEndOrder")
    if require_pair and (start is None) != (end is None):
        raise ValueError("章节范围必须同时提供起止序号")
    if not require_pair and start_present and end_present and (start is None) != (end is None):
        raise ValueError("章节范围必须同时提供起止序号")
    if start_present and start is not None and start <= 0:
        raise ValueError("章节范围必须是有效正整数闭区间")
    if end_present and end is not None and end <= 0:
        raise ValueError("章节范围必须是有效正整数闭区间")
    if start is not None and end is not None and start > end:
        raise ValueError("章节范围必须是有效正整数闭区间")


class _OutlineBusinessFields(_StrictModel):
    content: str | None = None
    parentId: str | None = None
    linkedChapterId: str | None = None
    estimatedWordCount: _DbInt32 | None = None
    actualWordCount: _DbInt32 | None = None
    chapterStartOrder: _DbInt32 | None = None
    chapterEndOrder: _DbInt32 | None = None

    @model_validator(mode="after")
    def validate_link_ids(self) -> Self:
        _require_nullable_id_if_provided(self, "linkedChapterId")
        if not getattr(self, "parentKey", ""):
            _require_nullable_id_if_provided(self, "parentId")
        return self


class OutlineAdjustmentCreate(_OutlineBusinessFields):
    action: Literal["create"]
    title: str = ""
    nodeTitle: str = ""
    clientKey: str = ""
    parentKey: str = ""
    kind: OutlineKind
    status: OutlineStatus = "planned"
    order: _DbInt32 = 0

    @model_validator(mode="after")
    def validate_create(self) -> Self:
        title_field = "title" if "title" in self.model_fields_set else "nodeTitle"
        _require_nonblank_if_provided(self, title_field)
        if not self.title and not self.nodeTitle:
            raise ValueError("创建大纲节点必须提供 title 或 nodeTitle")
        if self.kind == "stage" and (self.parentId is not None or self.parentKey):
            raise ValueError("stage 必须位于顶层")
        if self.kind != "stage" and self.parentId is None and not self.parentKey:
            raise ValueError("非 stage 节点必须提供 parentId 或 parentKey")
        _validate_outline_range(self, require_pair=True)
        return self


class OutlineAdjustmentUpdate(_OutlineBusinessFields):
    action: Literal["update"]
    nodeId: str = ""
    nodeTitle: str = ""
    parentKey: str = ""
    title: str = ""
    kind: OutlineKind = "stage"
    status: OutlineStatus = "planned"
    order: _DbInt32 = 0

    @model_validator(mode="after")
    def validate_update(self) -> Self:
        title_field = "title" if "title" in self.model_fields_set else "nodeTitle"
        _require_nonblank_if_provided(self, title_field)
        _require_locator(self, "nodeId", "nodeTitle", "title")
        _require_business_field(
            self,
            set(_OutlineBusinessFields.model_fields)
            | {"title", "kind", "status", "order", "parentKey"},
        )
        _validate_outline_range(self, require_pair=False)
        return self


class OutlineAdjustmentDelete(_StrictModel):
    action: Literal["delete"]
    nodeId: str = ""
    nodeTitle: str = ""
    title: str = ""

    @model_validator(mode="after")
    def validate_target(self) -> Self:
        if not self.nodeId:
            title_field = "title" if "title" in self.model_fields_set else "nodeTitle"
            _require_locator(self, title_field)
        return self


type OutlineAdjustment = OutlineAdjustmentCreate | OutlineAdjustmentUpdate | OutlineAdjustmentDelete


class _ForeshadowingFields(_StrictModel):
    plantedAt: str | None = None
    plantedContent: str | None = None
    expectedPayoff: str | None = None
    payoffAt: str | None = None


class ForeshadowingCreate(_ForeshadowingFields):
    action: Literal["create"]
    name: str

    @model_validator(mode="after")
    def validate_name(self) -> Self:
        _require_nonempty_if_provided(self, "name")
        return self


class ForeshadowingUpdate(_ForeshadowingFields):
    action: Literal["update"]
    id: str = ""
    name: str = ""

    @model_validator(mode="after")
    def validate_update(self) -> Self:
        _require_locator(self, "id", "name")
        _require_business_field(self, set(_ForeshadowingFields.model_fields) | {"name"})
        return self


class ForeshadowingPayoff(_ForeshadowingFields):
    action: Literal["payoff"]
    id: str = ""
    name: str = ""

    @model_validator(mode="after")
    def validate_target(self) -> Self:
        _require_locator(self, "id", "name")
        return self


class ForeshadowingAbandon(_ForeshadowingFields):
    action: Literal["abandon"]
    id: str = ""
    name: str = ""

    @model_validator(mode="after")
    def validate_target(self) -> Self:
        _require_locator(self, "id", "name")
        return self


type ForeshadowingMutation = (
    ForeshadowingCreate | ForeshadowingUpdate | ForeshadowingPayoff | ForeshadowingAbandon
)


class ReferenceCreate(_StrictModel):
    action: Literal["create"]
    title: str
    type: ReferenceType
    content: str
    sourceUrl: str | None = None

    @model_validator(mode="after")
    def validate_title(self) -> Self:
        _require_nonblank_if_provided(self, "title")
        return self


class ReferenceUpdate(_StrictModel):
    action: Literal["update"]
    id: str = ""
    referenceId: str = ""
    title: str = ""
    type: ReferenceType = "note"
    content: str = ""
    sourceUrl: str | None = None

    @model_validator(mode="after")
    def validate_update(self) -> Self:
        _require_locator(self, "id", "referenceId")
        if self.id and self.referenceId and self.id != self.referenceId:
            raise ValueError("references id 与 referenceId 不一致")
        _require_business_field(self, {"title", "type", "content", "sourceUrl"})
        return self


class ReferenceDelete(_StrictModel):
    action: Literal["delete"]
    id: str = ""
    referenceId: str = ""

    @model_validator(mode="after")
    def validate_target(self) -> Self:
        _require_locator(self, "id", "referenceId")
        if self.id and self.referenceId and self.id != self.referenceId:
            raise ValueError("references id 与 referenceId 不一致")
        return self


type ReferenceMutation = ReferenceCreate | ReferenceUpdate | ReferenceDelete


class AgentUpdates(_StrictModel):
    """一个可跨分区聚合、按字段存在性解释的结构化候选。"""

    outlineTreeMode: OutlineTreeMode = "patch"
    characters: list[CharacterMutation] = Field(default_factory=list)
    locations: list[LocationMutation] = Field(default_factory=list)
    items: list[ItemMutation] = Field(default_factory=list)
    factions: list[FactionMutation] = Field(default_factory=list)
    glossaries: list[GlossaryMutation] = Field(default_factory=list)
    characterExperiences: list[CharacterExperienceMutation] = Field(default_factory=list)
    outline: list[OutlineUpdate] = Field(default_factory=list)
    outlineAdjustments: list[OutlineAdjustment] = Field(default_factory=list)
    foreshadowing: list[ForeshadowingMutation] = Field(default_factory=list)
    references: list[ReferenceMutation] = Field(default_factory=list)
    outlineContent: str = ""
    worldSetting: str = ""
    storyBackground: str = ""

    @model_validator(mode="after")
    def validate_sections(self) -> Self:
        arrays = (
            "characters",
            "locations",
            "items",
            "factions",
            "glossaries",
            "characterExperiences",
            "outline",
            "outlineAdjustments",
            "foreshadowing",
            "references",
        )
        texts = {"outlineContent", "worldSetting", "storyBackground"}
        if not any(getattr(self, name) for name in arrays) and not (self.model_fields_set & texts):
            raise ValueError("updates 至少需要一个非空数组或实际提供的全文")
        if "outlineTreeMode" in self.model_fields_set and not self.outlineAdjustments:
            raise ValueError("outlineTreeMode 只能控制非空 outlineAdjustments")
        if self.outlineTreeMode == "replace" and any(
            adjustment.action != "create" for adjustment in self.outlineAdjustments
        ):
            raise ValueError("整树替换只能包含 create")
        if self.outlineTreeMode == "replace" and any(
            adjustment.parentId is not None and not adjustment.parentKey
            for adjustment in self.outlineAdjustments
            if isinstance(adjustment, OutlineAdjustmentCreate)
        ):
            raise ValueError("整树替换不能引用删除前的 parentId")
        self._validate_outline_client_keys()
        return self

    def _validate_outline_client_keys(self) -> None:
        seen: dict[str, OutlineAdjustmentCreate] = {}
        for adjustment in self.outlineAdjustments:
            parent_key = getattr(adjustment, "parentKey", "")
            if parent_key:
                parent = seen.get(parent_key)
                if parent is None:
                    raise ValueError("outlineAdjustments parentKey 必须引用更早的 create")
                # patch 中父节点可能已被中间的 update 改型，由 Core 顺序验证。
                kind = (
                    adjustment.kind
                    if isinstance(
                        adjustment,
                        (OutlineAdjustmentCreate, OutlineAdjustmentUpdate),
                    )
                    and "kind" in adjustment.model_fields_set
                    else None
                )
                expected_kind = (
                    {"plot_unit": "stage", "chapter_group": "plot_unit"}.get(kind)
                    if kind is not None
                    else None
                )
                if (
                    self.outlineTreeMode == "replace"
                    and expected_kind is not None
                    and parent.kind != expected_kind
                ):
                    raise ValueError("outlineAdjustments parentKey 的节点层级不兼容")
            if not isinstance(adjustment, OutlineAdjustmentCreate) or not adjustment.clientKey:
                continue
            if self.outlineTreeMode == "replace" and adjustment.clientKey in seen:
                raise ValueError("outlineAdjustments clientKey 不能重复")
            seen[adjustment.clientKey] = adjustment


class AgentUpdatesOutput(_StrictModel):
    """Provider 只生成原始说明和业务更新，不生成 Core 控制字段。"""

    summary: str = Field(min_length=1, max_length=1000)
    updates: AgentUpdates


class AgentUpdatesResult(AgentUpdatesOutput):
    """Agent 校验 Provider 输出后只派生 presence-aware updates 哈希。"""

    updatesSha256: Sha256

    @model_validator(mode="after")
    def validate_updates_hash(self) -> Self:
        material = self.updates.model_dump(mode="json", exclude_unset=True)
        if self.updatesSha256 != canonical_execution_sha256(material):
            raise ValueError("updatesSha256 与完整 updates 不一致")
        return self


class AgentUpdatesPreviousCandidate(_StrictModel):
    artifactId: ExecutionId
    artifactRevision: StrictPositiveInt
    summary: str = Field(min_length=1, max_length=1000)
    updates: AgentUpdates


class AgentUpdatesInput(_StrictModel):
    """初次生成和绑定精确上一候选的返工输入。"""

    userInstruction: str = Field(min_length=1)
    originalUserInstruction: str | None = Field(default=None, min_length=1)
    previousCandidate: AgentUpdatesPreviousCandidate | None = None

    @model_validator(mode="after")
    def validate_revision_pair(self) -> Self:
        if count_chapter_text_length(self.userInstruction) == 0:
            raise ValueError("结构化资料指令不能为空白文本")
        if (
            self.originalUserInstruction is not None
            and count_chapter_text_length(self.originalUserInstruction) == 0
        ):
            raise ValueError("结构化资料原始指令不能为空白文本")
        revision_fields = self.model_fields_set.intersection(
            {"originalUserInstruction", "previousCandidate"}
        )
        if revision_fields and (
            len(revision_fields) != 2
            or self.originalUserInstruction is None
            or self.previousCandidate is None
        ):
            raise ValueError("结构化资料返工必须同时绑定原指令和精确上一候选")
        return self


def materialize_agent_updates_output(value: object) -> dict[str, JsonValue]:
    """保留字段存在性与原文，仅派生 updates canonical SHA-256。"""

    output = AgentUpdatesOutput.model_validate(value)
    material = output.model_dump(mode="json", exclude_unset=True)
    updates = material["updates"]
    if not isinstance(updates, dict):  # pragma: no cover - Pydantic 已保证
        raise TypeError("updates 必须是 JSON 对象")
    material["updatesSha256"] = canonical_execution_sha256(updates)
    return AgentUpdatesResult.model_validate(material).model_dump(mode="json", exclude_unset=True)
