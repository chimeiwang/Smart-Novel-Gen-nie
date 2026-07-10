from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class AuthSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RegisterRequest(AuthSchema):
    username: str
    password: str
    confirmPassword: str


class LoginRequest(AuthSchema):
    username: str
    password: str


class UserResponse(AuthSchema):
    id: str
    username: str
    creditBalanceMicros: str
