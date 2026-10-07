from __future__ import annotations

import json

import httpx
from inkforge_agents.providers.base import ProviderProtocolError, ProviderTransportError
from inkforge_agents.providers.error_details import capture_provider_error_details


def test完整长正文和嵌套凭据脱敏() -> None:
    secret = "test-private-key"  # noqa: S105 - 测试凭据脱敏。
    message = "完整错误说明" * 20_000
    response = httpx.Response(
        400,
        json={
            "error": {"message": message, "param": "tools", "api_key": secret},
            "extra": [{"password": "password-value", "grantToken": "grant-value"}],
            "echo": "Bearer unknown-private-value",
        },
        headers={"set-cookie": "session=private-session", "x-diagnostic": secret},
        request=httpx.Request("POST", "https://user:pass@provider.test/api?api_key=query-key"),
    )
    details = capture_provider_error_details(response=response, secrets=(secret,))
    assert details.responseBody is not None
    assert json.loads(details.responseBody)["error"]["message"] == message
    serialized = json.dumps(details.model_dump(mode="json"), ensure_ascii=False)
    for value in (
        secret,
        "password-value",
        "grant-value",
        "unknown-private-value",
        "private-session",
        "query-key",
        "user:pass",
    ):
        assert value not in serialized
    assert details.requestMethod == "POST"
    assert details.statusCode == 400


def test非JSON正文完整且不保存成功正文() -> None:
    body = "供应商错误\n" * 20_000
    failed = httpx.Response(400, text=body)
    assert capture_provider_error_details(response=failed).responseBody == body
    successful = httpx.Response(200, text="不复制正常模型输出")
    assert capture_provider_error_details(response=successful).responseBody is None


def test异常因果链无局部变量并脱敏地址与凭据() -> None:
    local_private_value = "局部变量不得采集"
    try:
        try:
            raise ValueError("底层错误 Bearer private-bearer")
        except ValueError as cause:
            raise httpx.ConnectError(
                "无法连接 https://username:password@provider.test/api?token=private-query",
                request=httpx.Request("POST", "https://provider.test/api"),
            ) from cause
    except httpx.ConnectError as error:
        details = capture_provider_error_details(error=error)
    assert [entry.type for entry in details.exceptionChain] == ["ConnectError", "ValueError"]
    serialized = json.dumps(details.model_dump(mode="json"), ensure_ascii=False)
    for value in (local_private_value, "private-bearer", "private-query", "username:password"):
        assert value not in serialized
    assert "test_error_details.py" in details.exceptionChain[0].traceback


def test旧异常构造兼容且详情不进入错误文本() -> None:
    details = capture_provider_error_details(response=httpx.Response(400, text="私有错误详情"))
    for kind, code in (
        (ProviderTransportError, "http_error"),
        (ProviderProtocolError, "invalid_usage"),
    ):
        legacy = kind(code=code, statusCode=400, requestId="request-id")
        assert legacy.details is None
        error = kind(code=code, statusCode=400, requestId="request-id", details=details)
        assert "私有错误详情" not in str(error)
        assert "私有错误详情" not in repr(error)


def test普通token诊断值完整保留而凭据后缀脱敏() -> None:
    response = httpx.Response(
        400,
        json={
            "max_tokens": 384000,
            "total_tokens": 123,
            "token_count": 12,
            "token_limit": 393216,
            "refreshToken": "private-refresh",
            "session_token": "private-session",
        },
    )
    details = capture_provider_error_details(response=response)
    assert details.responseBody is not None
    parsed = json.loads(details.responseBody)
    assert parsed["max_tokens"] == 384000
    assert parsed["total_tokens"] == 123
    assert parsed["token_count"] == 12
    assert parsed["token_limit"] == 393216
    assert "private-" not in details.responseBody


def test重复JSON键完整保留并分别脱敏() -> None:
    response = httpx.Response(
        400, content=(b'{"message":"first","message":"second","api_key":"one","api_key":"two"}')
    )
    details = capture_provider_error_details(response=response)
    assert details.responseBody is not None
    pairs = json.loads(details.responseBody, object_pairs_hook=list)
    assert pairs[:2] == [("message", "first"), ("message", "second")]
    assert pairs[2:] == [("api_key", "[已脱敏]"), ("api_key", "[已脱敏]")]


def test非法UTF8错误字节显式保留() -> None:
    details = capture_provider_error_details(
        response=httpx.Response(400, content=b"error:\xff\xfe")
    )
    assert details.responseBody == r"error:\xff\xfe"


def test深层JSON及异常字符串失败不覆盖原始错误() -> None:
    body = "[" * 2000 + "0" + "]" * 2000
    details = capture_provider_error_details(response=httpx.Response(400, text=body))
    assert details.responseBody == body

    class BrokenMessageError(Exception):
        def __str__(self) -> str:
            raise RuntimeError("不应传播的格式化错误")

    details = capture_provider_error_details(error=BrokenMessageError())
    assert details.exceptionChain[0].type == "BrokenMessageError"
    assert "无法格式化" in details.exceptionChain[0].message


def test自由文本多段Cookie带逗号密码和token后缀完整脱敏() -> None:
    message = (
        "Cookie: session=private-one; auth=private-two\n"
        'password="private-left,private-right"; param="max_tokens"\n'
        "Error: session_token=private-session; token_count=12; token_limit=393216\n"
        'api_key="private-quoted\\"part,tail"; max_tokens=384000'
    )
    for details in (
        capture_provider_error_details(error=ValueError(message)),
        capture_provider_error_details(response=httpx.Response(400, text=message)),
    ):
        body = details.responseBody or details.exceptionChain[0].message
        assert "private-" not in body
        assert 'param="max_tokens"' in body
        assert "token_count=12" in body
        assert "token_limit=393216" in body
        assert "max_tokens=384000" in body


def test带引号Cookie不抹去同行诊断() -> None:
    details = capture_provider_error_details(
        error=ValueError('cookie="a=one; b=two"; param="tools"')
    )
    assert details.exceptionChain[0].message == 'cookie=[已脱敏]; param="tools"'
