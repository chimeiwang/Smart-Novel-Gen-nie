from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StringConstraints, model_validator

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
    CALLBACK_EVENT = "callback:event"
    CALLBACK_CHECKPOINT = "callback:checkpoint"
    CALLBACK_COMPLETE = "callback:complete"
    CALLBACK_FAIL = "callback:fail"
    TOOL_READ = "tool:read"
    TOOL_WRITE = "tool:write"
    RAG_INDEX_WRITE = "rag:index:write"
    PORTRAIT_WRITE = "portrait:write"


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
    }
)


class ServiceJwtClaims(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    iss: NonBlankClaim
    sub: NonBlankClaim
    aud: NonBlankClaim
    scope: tuple[ServiceScope, ...] = Field(min_length=1)
    task_id: NonBlankClaim
    run_id: NonBlankClaim
    novel_id: NonBlankClaim
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
        return self
