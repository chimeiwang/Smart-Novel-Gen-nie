from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Self, cast

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    StrictInt,
    StringConstraints,
    model_validator,
)
from pydantic.config import JsonDict

NonBlankClaim = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=256),
]
BodySha256 = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
HttpMethod = Annotated[str, StringConstraints(pattern=r"^[A-Z]+$", min_length=3, max_length=16)]
HttpPath = Annotated[str, StringConstraints(pattern=r"^/", min_length=1, max_length=2048)]


class ServiceScope(StrEnum):
    AGENT_RUN = "agent:run"
    AGENT_CANCEL = "agent:cancel"
    AGENT_DEBUG_READ = "agent:debug:read"
    CALLBACK_EVENT = "callback:event"
    CALLBACK_CHECKPOINT = "callback:checkpoint"
    CALLBACK_COMPLETE = "callback:complete"
    CALLBACK_FAIL = "callback:fail"
    TOOL_READ = "tool:read"
    TOOL_WRITE = "tool:write"
    RAG_INDEX_WRITE = "rag:index:write"
    PORTRAIT_WRITE = "portrait:write"
    QUALITY_WRITE = "quality:write"
    VIDEO_WRITE = "video:write"
    VIDEO_RENDER = "video:render"
    EXECUTION_SUBMIT = "execution:submit"
    EXECUTION_CANCEL = "execution:cancel"
    EXECUTION_PROGRESS = "execution:progress"
    EXECUTION_RESULT = "execution:result"
    BILLING_AUTHORIZE = "billing:authorize"
    BILLING_USAGE_WRITE = "billing:usage:write"
    BILLING_RECONCILE = "billing:reconcile"


EXECUTION_SERVICE_SCOPES = frozenset(
    {
        ServiceScope.EXECUTION_SUBMIT,
        ServiceScope.EXECUTION_CANCEL,
        ServiceScope.EXECUTION_PROGRESS,
        ServiceScope.EXECUTION_RESULT,
        ServiceScope.BILLING_RECONCILE,
    }
)
_EXECUTION_SCOPE_JSON_VALUES = cast(
    list[JsonValue],
    sorted(scope.value for scope in EXECUTION_SERVICE_SCOPES),
)

_SERVICE_JWT_JSON_SCHEMA_EXTRA: JsonDict = {
    "allOf": [
        {
            "if": {
                "properties": {"novel_id": {"type": "null"}},
                "required": ["novel_id"],
            },
            "then": {
                "properties": {
                    "scope": {"items": {"enum": _EXECUTION_SCOPE_JSON_VALUES}}
                }
            },
        }
    ]
}


WRITE_SERVICE_SCOPES = frozenset(
    {
        ServiceScope.AGENT_RUN,
        ServiceScope.AGENT_CANCEL,
        ServiceScope.CALLBACK_EVENT,
        ServiceScope.CALLBACK_CHECKPOINT,
        ServiceScope.CALLBACK_COMPLETE,
        ServiceScope.CALLBACK_FAIL,
        ServiceScope.TOOL_WRITE,
        ServiceScope.RAG_INDEX_WRITE,
        ServiceScope.PORTRAIT_WRITE,
        ServiceScope.QUALITY_WRITE,
        ServiceScope.VIDEO_WRITE,
        ServiceScope.VIDEO_RENDER,
        ServiceScope.EXECUTION_SUBMIT,
        ServiceScope.EXECUTION_CANCEL,
        ServiceScope.EXECUTION_PROGRESS,
        ServiceScope.EXECUTION_RESULT,
        ServiceScope.BILLING_USAGE_WRITE,
        ServiceScope.BILLING_RECONCILE,
    }
)


class ServiceJwtClaims(BaseModel):
    """服务 JWT；V2 execution 固定 task_id=stepId、run_id=runId、novel_id=novelId。"""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        json_schema_extra=_SERVICE_JWT_JSON_SCHEMA_EXTRA,
    )

    iss: NonBlankClaim
    sub: NonBlankClaim
    aud: NonBlankClaim
    scope: tuple[ServiceScope, ...] = Field(min_length=1)
    task_id: NonBlankClaim
    run_id: NonBlankClaim
    novel_id: NonBlankClaim | None
    jti: NonBlankClaim
    iat: StrictInt
    exp: StrictInt
    body_sha256: BodySha256
    query_sha256: BodySha256
    idempotency_key: NonBlankClaim
    request_timestamp: StrictInt
    http_method: HttpMethod
    http_path: HttpPath

    @model_validator(mode="after")
    def validate_lifetime_and_scope(self) -> Self:
        lifetime = self.exp - self.iat
        if lifetime <= 0:
            raise ValueError("服务令牌有效期必须大于 0 秒")
        if lifetime > 300:
            raise ValueError("服务令牌有效期不能超过 300 秒")
        if self.request_timestamp != self.iat:
            raise ValueError("request_timestamp 必须与 iat 相同")
        if len(set(self.scope)) != len(self.scope):
            raise ValueError("服务令牌权限范围不能重复")
        if self.novel_id is None and not set(self.scope) <= EXECUTION_SERVICE_SCOPES:
            raise ValueError("只有纯 execution scope 服务令牌允许 novel_id 为 null")
        return self
