from __future__ import annotations

from typing import Annotated, cast

from fastapi import Cookie, Depends, Request

from ..errors import ApiError
from .repository import AuthUser
from .service import COOKIE_NAME, AuthService


def get_auth_service(request: Request) -> AuthService:
    service = cast(AuthService | None, getattr(request.app.state, "auth_service", None))
    if service is None:
        raise ApiError(
            status_code=503,
            code="AUTH_UNAVAILABLE",
            message="认证服务暂时不可用",
        )
    return service


async def get_current_user(
    service: Annotated[AuthService, Depends(get_auth_service)],
    token: Annotated[str | None, Cookie(alias=COOKIE_NAME)] = None,
) -> AuthUser:
    """只信任 Cookie 主体，并从数据库重新读取当前用户。"""

    return await service.get_current_user(token)
