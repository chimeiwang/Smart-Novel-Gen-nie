from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from inkforge_contracts.jwt_claims import ServiceScope
from inkforge_service_auth import (
    ReplayPolicy as _ReplayPolicy,
)
from inkforge_service_auth import (
    ReplayStore as _ReplayStore,
)
from inkforge_service_auth import (
    ServiceAuthError as _ServiceAuthError,
)
from inkforge_service_auth import (
    ServiceTokenSigner as _ServiceTokenSigner,
)
from inkforge_service_auth import (
    ServiceTokenVerifier as _ServiceTokenVerifier,
)

__all__ = [
    "create_agent_callback_signer",
    "create_core_request_verifier",
    "install_service_auth_error_handler",
]

_CORE_TO_AGENT_SCOPES = frozenset(
    {
        ServiceScope.AGENT_RUN,
        ServiceScope.AGENT_CANCEL,
    }
)
_AGENT_TO_CORE_SCOPES = frozenset(
    {
        ServiceScope.CALLBACK_EVENT,
        ServiceScope.CALLBACK_CHECKPOINT,
        ServiceScope.CALLBACK_COMPLETE,
        ServiceScope.CALLBACK_FAIL,
        ServiceScope.TOOL_READ,
        ServiceScope.TOOL_WRITE,
        ServiceScope.RAG_INDEX_WRITE,
        ServiceScope.PORTRAIT_WRITE,
        ServiceScope.BILLING_AUTHORIZE,
        ServiceScope.BILLING_USAGE_WRITE,
    }
)
_PUBLIC_MESSAGES = {
    401: "服务身份认证失败",
    403: "服务调用权限不足",
    409: "服务令牌已被使用",
    503: "服务请求重放保护暂不可用",
}


def create_agent_callback_signer(
    *,
    private_key_path: str | Path,
    kid: str,
) -> _ServiceTokenSigner:
    return _ServiceTokenSigner.from_pkcs8_file(
        private_key_path,
        issuer="agent-service",
        subject="agent-service",
        audience="core-api",
        kid=kid,
        allowed_scopes=_AGENT_TO_CORE_SCOPES,
    )


def create_core_request_verifier(
    *,
    jwks_path: str | Path,
    replay_store: _ReplayStore,
    replay_policy: _ReplayPolicy = _ReplayPolicy.ALL_SCOPES,
) -> _ServiceTokenVerifier:
    return _ServiceTokenVerifier.from_jwks_file(
        jwks_path,
        expected_issuer="core-api",
        expected_subject="core-api",
        audience="agent-service",
        replay_store=replay_store,
        replay_policy=replay_policy,
        allowed_scopes=_CORE_TO_AGENT_SCOPES,
    )


def install_service_auth_error_handler(app: FastAPI) -> None:
    app.add_exception_handler(_ServiceAuthError, _handle_service_auth_error)


async def _handle_service_auth_error(request: Request, exc: Exception) -> JSONResponse:
    del request
    if not isinstance(exc, _ServiceAuthError):
        return JSONResponse(
            status_code=500,
            content={"code": "INTERNAL_SERVER_ERROR", "message": "服务器内部错误", "details": None},
        )
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "code": exc.code,
            "message": _PUBLIC_MESSAGES.get(exc.status_code, "服务身份校验失败"),
            "details": None,
        },
    )
