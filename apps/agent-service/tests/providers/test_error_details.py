from __future__ import annotations

import json
import logging

import httpx
import pytest
from inkforge_agents.providers.base import ProviderProtocolError, ProviderTransportError
from inkforge_agents.providers.error_details import (
    capture_failure_diagnostic,
    capture_provider_error_details,
    log_failure_diagnostic,
)
from pydantic import BaseModel, ConfigDict, ValidationError, field_validator


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


def test完整失败payload容忍异常ctx并排除reasoning() -> None:
    payload = {
        "arguments": "正文" * 40_000,
        "validationErrors": [{"ctx": {"error": ValueError("完整校验异常")}}],
        "reasoningTokens": 123,
        "reasoning_content": "不得记录思考",
        "output": [{"type": "reasoning", "summary": "不得记录摘要"}],
        "api_key": "private-key",
    }
    diagnostic = capture_failure_diagnostic(
        stage="tool.wire_schema", code="invalid", payload=payload
    )
    assert diagnostic.captureFailure is None
    assert diagnostic.payloadJson is not None
    result = json.loads(diagnostic.payloadJson)
    assert result["arguments"] == payload["arguments"]
    assert result["validationErrors"][0]["ctx"]["error"] == "完整校验异常"
    assert result["reasoningTokens"] == 123
    assert "不得记录" not in diagnostic.payloadJson
    assert "private-key" not in diagnostic.payloadJson


def testHTTP200协议失败可显式保存去除推理正文() -> None:
    response = httpx.Response(200, json={"error": "无效usage", "reasoning_content": "隐藏推理"})
    details = capture_provider_error_details(response=response, include_success_body=True)
    assert details.responseBody is not None
    assert json.loads(details.responseBody) == {"error": "无效usage"}


def test坏JSON也排除Chat推理与Responses推理对象() -> None:
    body = (
        '{"error":"可查说明", "reasoning_content":"隐藏Chat思考", '
        '"output":[{"type":"reasoning","summary":"隐藏Responses思考"}, '
        '{"type":"message","content":"失败输出"}'
    )
    details = capture_provider_error_details(
        response=httpx.Response(200, text=body), include_success_body=True
    )
    assert details.responseBody is not None
    assert "隐藏" not in details.responseBody
    assert "可查说明" in details.responseBody
    assert "失败输出" in details.responseBody


def testURI凭据脱敏及ExceptionGroup子异常完整采集() -> None:
    error = ExceptionGroup(
        "并行失败",
        [
            ValueError("postgresql://user:pass@db/x?token=private"),
            RuntimeError("redis://user:pass@redis/0"),
        ],
    )
    details = capture_provider_error_details(error=error)
    assert [item.type for item in details.exceptionChain] == [
        "ExceptionGroup",
        "ValueError",
        "RuntimeError",
    ]
    assert "user:pass" not in details.model_dump_json()
    assert "private" not in details.model_dump_json()


def test日志使用单行JSON并隔离sink错误(caplog) -> None:
    diagnostic = capture_failure_diagnostic(
        stage="tool", code="invalid", payload={"args": "\n伪造日志\n"}
    )
    logger = logging.getLogger("test.failure.diagnostics")
    with caplog.at_level(logging.WARNING):
        log_failure_diagnostic(logger, diagnostic, runId="run")
    assert len(caplog.records) == 1
    assert "\n" not in caplog.records[0].getMessage()

    class BrokenLogger:
        def warning(self, *args, **kwargs):
            raise OSError("sink失败")

    log_failure_diagnostic(BrokenLogger(), diagnostic)


def test校验input和异常文本中的敏感字段值全局脱敏且不污染Schema() -> None:
    class Input(BaseModel):
        model_config = ConfigDict(extra="forbid")
        count: int

    arguments = {"count": "bad-count", "password": "private-validation-password"}
    try:
        Input.model_validate(arguments)
    except ValidationError as error:
        diagnostic = capture_failure_diagnostic(
            stage="tool.pydantic",
            code="invalid",
            error=error,
            payload={
                "arguments": arguments,
                "validationErrors": error.errors(),
                "wireSchema": {"properties": {"password": {"type": "string"}}},
            },
        )
    assert "private-validation-password" not in diagnostic.model_dump_json()
    assert diagnostic.payloadJson is not None
    payload = json.loads(diagnostic.payloadJson)
    assert payload["arguments"]["count"] == "bad-count"
    assert payload["wireSchema"]["properties"]["password"] == {"type": "string"}
    assert "bad-count" in diagnostic.model_dump_json()


def test原参数JSON重复敏感键可遮盖无键异常回显() -> None:
    diagnostic = capture_failure_diagnostic(
        stage="tool.json_parse",
        code="invalid",
        payload={
            "rawArguments": '{"password":"private-one","password":"private-two"}',
            "validationErrors": [{"input": "private-one private-two"}],
        },
        error=ValueError("input_value=private-one private-two"),
    )
    assert "private-one" not in diagnostic.model_dump_json()
    assert "private-two" not in diagnostic.model_dump_json()


def test已脱敏异常证据在上层无凭据时复用并可继续加严() -> None:
    original = ValueError("裸供应商凭据 fixture-sdk-key 和额外值 fixture-grant-value")
    first = capture_provider_error_details(error=original, secrets=("fixture-sdk-key",))
    assert "fixture-sdk-key" not in first.model_dump_json()
    wrapper = RuntimeError("上层包装失败")
    wrapper.__cause__ = original
    second = capture_provider_error_details(error=wrapper, secrets=("fixture-grant-value",))
    assert "fixture-sdk-key" not in second.model_dump_json()
    assert "fixture-grant-value" not in second.model_dump_json()
    third = capture_provider_error_details(error=wrapper)
    assert "fixture-sdk-key" not in third.model_dump_json()
    assert "fixture-grant-value" not in third.model_dump_json()
    diagnostic = capture_failure_diagnostic(
        stage="runtime",
        code="failed",
        payload={"validationErrors": [{"ctx": {"error": original}}]},
        error=wrapper,
    )
    assert "fixture-sdk-key" not in diagnostic.model_dump_json()
    assert "fixture-grant-value" not in diagnostic.model_dump_json()
    assert "fixture-sdk-key" in str(original)
    assert wrapper.__cause__ is original


def test嵌套JSON字符串推理完全排除且Schema定义保留() -> None:
    raw = json.dumps({"nested": json.dumps({"reasoning_content": "隐藏多层思考"})})
    diagnostic = capture_failure_diagnostic(
        stage="tool",
        code="invalid",
        payload={"rawArguments": raw, "schema": {"properties": {"password": {"type": "string"}}}},
    )
    assert "隐藏多层思考" not in diagnostic.model_dump_json()
    assert diagnostic.payloadJson is not None
    assert json.loads(diagnostic.payloadJson)["schema"]["properties"]["password"] == {
        "type": "string"
    }


def test敏感数字PIN在参数校验input与异常消息中均脱敏() -> None:
    diagnostic = capture_failure_diagnostic(
        stage="tool.pydantic",
        code="invalid",
        payload={
            "arguments": {"password": 123456},
            "validationErrors": [{"loc": ["password"], "input": 123456}],
        },
        error=ValueError("input_value=123456"),
    )
    assert "123456" not in diagnostic.model_dump_json()
    assert diagnostic.payloadJson is not None
    assert json.loads(diagnostic.payloadJson)["validationErrors"][0]["input"] == "[已脱敏]"


def test请求URL安全元数据缓存后无凭据复采不会泄密() -> None:
    original = httpx.ConnectError(
        "连接失败",
        request=httpx.Request(
            "POST",
            "https://test.invalid/api?key=fixture-sdk-key",
        ),
    )
    first = capture_provider_error_details(error=original, secrets=("fixture-sdk-key",))
    wrapper = RuntimeError("上层失败")
    wrapper.__cause__ = original
    second = capture_provider_error_details(error=wrapper)
    assert first.requestUrl == second.requestUrl
    assert second.requestMethod == "POST"
    assert "fixture-sdk-key" not in second.model_dump_json()
    assert "fixture-sdk-key" not in repr(original._inkforgeRequestMetadata)


@pytest.mark.parametrize("evidence", [{"requestId": "diagnostic-request"}, ["已有证据"]])
def test普通ValidationError自动保存完整输入敏感输入及ctx异常(evidence) -> None:
    class Input(BaseModel):
        text: int
        password: int
        info: str

        @field_validator("info")
        @classmethod
        def reject_info(cls, value: str) -> str:
            raise ValueError("完整ctx异常")

    large_input = "非法整数" * 30_000
    try:
        Input.model_validate(
            {"text": large_input, "password": "fixture-private-password", "info": "普通输入"}
        )
    except ValidationError as error:
        diagnostic = capture_failure_diagnostic(
            stage="unknown", code="invalid", payload=evidence, error=error
        )
        preserved = capture_failure_diagnostic(
            stage="unknown",
            code="invalid",
            error=error,
            payload={"validationErrors": [{"original": True}]},
        )
    assert diagnostic.payloadJson is not None
    payload = json.loads(diagnostic.payloadJson)
    assert len(payload["validationErrors"]) == 3
    assert payload["validationErrors"][0]["input"] == large_input
    assert payload["validationErrors"][1]["input"] == "[已脱敏]"
    assert payload["validationErrors"][2]["ctx"]["error"] == "完整ctx异常"
    assert "fixture-private-password" not in diagnostic.model_dump_json()
    if isinstance(evidence, dict):
        assert payload["requestId"] == evidence["requestId"]
        assert "evidence" not in payload
    else:
        assert payload["evidence"] == evidence
    assert json.loads(preserved.payloadJson)["validationErrors"] == [{"original": True}]
