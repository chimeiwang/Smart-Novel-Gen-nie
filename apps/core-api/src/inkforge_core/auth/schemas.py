from __future__ import annotations

from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field


def _validate_input_length(value: str) -> str:
    if len(value) > 4096:
        raise ValueError("输入文本不能超过 4096 个字符")
    return value


BoundedUsername = Annotated[
    str,
    AfterValidator(_validate_input_length),
    Field(json_schema_extra={"maxLength": 4096}),
]
BoundedPassword = Annotated[
    str,
    AfterValidator(_validate_input_length),
    Field(
        json_schema_extra={
            "format": "password",
            "maxLength": 4096,
            "writeOnly": True,
        },
    ),
]


class AuthSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RegisterRequest(AuthSchema):
    username: BoundedUsername
    password: BoundedPassword
    confirmPassword: BoundedPassword


class LoginRequest(AuthSchema):
    username: BoundedUsername
    password: BoundedPassword


class UserResponse(AuthSchema):
    id: str
    username: str
    creditBalanceMicros: str
