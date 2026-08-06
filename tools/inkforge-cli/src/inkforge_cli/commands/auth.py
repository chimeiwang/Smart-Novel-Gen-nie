from __future__ import annotations

import argparse
from typing import Never

from ..config import ProfileConfig
from ..credentials import validate_core_origin
from ..json_types import JsonObject
from ..runtime import (
    CliInputError,
    CliRuntime,
    ensure_command_json_result,
)


class _SilentArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> Never:
        raise CliInputError("INVALID_ARGUMENTS", "auth.login 参数无效")


def login(runtime: CliRuntime, payload: JsonObject) -> JsonObject:
    del payload
    parser = _SilentArgumentParser(prog="inkforge auth.login", add_help=False)
    parser.add_argument("--origin", required=True)
    parser.add_argument("--username", required=True)
    parser.add_argument("--profile", default="default")
    arguments = parser.parse_args(runtime.argv)

    dependencies = runtime.dependencies
    if not dependencies.stdin_isatty():
        raise CliInputError(
            "TTY_REQUIRED",
            "auth.login 必须由用户在真实终端中交互执行",
        )
    origin = validate_core_origin(arguments.origin)
    password = dependencies.getpass_fn("InkForge 密码：")
    client = dependencies.api_factory(origin, None)
    user, token = client.login(arguments.username, password)
    dependencies.credential_store.set(arguments.profile, origin, token)
    dependencies.config_store.save(
        arguments.profile,
        ProfileConfig(origin=origin, username=arguments.username),
    )
    return ensure_command_json_result(user)


def logout(runtime: CliRuntime, payload: JsonObject) -> JsonObject:
    del payload
    api = runtime.require_api()
    profile, origin = runtime.require_identity()
    try:
        result = api.request("POST", "/api/v1/auth/logout")
    finally:
        runtime.dependencies.credential_store.delete(profile, origin)
    return ensure_command_json_result(result)


def whoami(runtime: CliRuntime, payload: JsonObject) -> JsonObject:
    response = runtime.require_api().request("GET", "/api/v1/auth/me")
    expected_username = payload.get("expectedUsername")
    if expected_username is not None:
        if not isinstance(expected_username, str) or not expected_username:
            raise CliInputError(
                "INVALID_EXPECTED_USERNAME",
                "expectedUsername 必须是非空字符串",
            )
        actual_username = (
            response.get("username") if isinstance(response, dict) else None
        )
        if actual_username != expected_username:
            raise CliInputError(
                "IDENTITY_MISMATCH",
                "当前登录身份与 expectedUsername 不一致",
                exit_code=3,
            )
    return ensure_command_json_result(response)
