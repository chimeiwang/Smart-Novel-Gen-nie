from __future__ import annotations

from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StringConstraints


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
MainlandPhone = Annotated[
    str,
    StringConstraints(pattern=r"^1[3-9][0-9]{9}$"),
    Field(json_schema_extra={"minLength": 11, "maxLength": 11}),
]
SmsVerifyCode = Annotated[
    str,
    StringConstraints(pattern=r"^[0-9]{6}$"),
    Field(json_schema_extra={"minLength": 6, "maxLength": 6}),
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


class CreatePhoneChallengeRequest(AuthSchema):
    phone: MainlandPhone
    captchaVerifyParam: str = Field(min_length=1, max_length=16_384)
    consentVersion: str = Field(min_length=1, max_length=64)
    acceptedTerms: Literal[True]
    clientRequestId: str = Field(min_length=16, max_length=128)


class PhoneChallengeResponse(AuthSchema):
    challengeId: str
    expiresInSeconds: int
    resendAfterSeconds: int


class VerifyPhoneChallengeRequest(AuthSchema):
    phone: MainlandPhone
    code: SmsVerifyCode
    clientRequestId: str = Field(min_length=16, max_length=128)


class PhoneLoginResponse(AuthSchema):
    id: str
    username: str
    creditBalanceMicros: str
    maskedPhone: str
    isNewUser: bool


class UserResponse(AuthSchema):
    id: str
    username: str
    creditBalanceMicros: str
    maskedPhone: str | None = Field(
        default=None,
        pattern=r"^1[3-9][0-9]\*{4}[0-9]{4}$",
    )
