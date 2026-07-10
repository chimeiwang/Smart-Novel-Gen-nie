from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status

from .dependencies import get_auth_service, get_current_user
from .repository import AuthUser
from .schemas import LoginRequest, RegisterRequest, UserResponse
from .service import COOKIE_NAME, SESSION_MAX_AGE_SECONDS, AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(
    payload: RegisterRequest,
    request: Request,
    response: Response,
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> UserResponse:
    user = await service.register(
        payload.username,
        payload.password,
        payload.confirmPassword,
        client_identity=_client_identity(request),
    )
    _set_session_cookie(response, service, user.id)
    return _user_response(user)


@router.post("/login", response_model=UserResponse)
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> UserResponse:
    user = await service.login(
        payload.username,
        payload.password,
        client_identity=_client_identity(request),
    )
    _set_session_cookie(response, service, user.id)
    return _user_response(user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    response: Response,
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> None:
    response.delete_cookie(
        key=COOKIE_NAME,
        path="/",
        secure=service.environment == "production",
        httponly=True,
        samesite="lax",
    )


@router.get("/me", response_model=UserResponse)
async def me(user: Annotated[AuthUser, Depends(get_current_user)]) -> UserResponse:
    return _user_response(user)


def _set_session_cookie(response: Response, service: AuthService, user_id: str) -> None:
    response.set_cookie(
        key=COOKIE_NAME,
        value=service.create_session_token(user_id),
        max_age=SESSION_MAX_AGE_SECONDS,
        httponly=True,
        secure=service.environment == "production",
        samesite="lax",
        path="/",
    )


def _user_response(user: AuthUser) -> UserResponse:
    return UserResponse(
        id=user.id,
        username=user.username,
        creditBalanceMicros=str(user.credit_balance_micros),
    )


def _client_identity(request: Request) -> str:
    return request.client.host if request.client is not None else "unknown"
