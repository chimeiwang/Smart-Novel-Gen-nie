from __future__ import annotations

import argparse
import base64
import inspect
import json
import os
import tempfile
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from inkforge_contracts.jwt_claims import ServiceScope
from inkforge_core.app import create_app
from inkforge_core.auth.service import COOKIE_NAME, SESSION_MAX_AGE_SECONDS
from inkforge_core.http.cursor import encode_run_cursor
from inkforge_core.writing.schemas import (
    WritingRunOutcome,
    WritingRunOutcomeCommand,
    WritingRunOutcomeResult,
)
from inkforge_core.writing.sse import (
    WritingEvent,
    format_heartbeat,
    format_run_outcome,
    format_sse_event,
)
from inkforge_service_auth import ServiceTokenSigner
from starlette.responses import FileResponse

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_ROOT = ROOT / "contracts" / "core"
HTTP_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE"}


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()


def _full_path(prefix: str, route_path: str) -> str:
    if not prefix:
        return route_path
    return f"{prefix.rstrip('/')}{route_path}"


def _product_module(endpoint_module: str) -> str:
    mappings = (
        (".video.adaptation.post_production", "video"),
        (".video.adaptation", "video"),
        (".video", "video"),
        (".short_medium", "shortmedium"),
        (".auth", "identity"),
        (".novels", "novels"),
        (".chapters", "chapters"),
        (".lore", "lore"),
        (".outlines", "outlines"),
        (".references", "references"),
        (".styles", "styles"),
        (".billing", "billing"),
        (".reviews", "reviews"),
        (".writing", "writing"),
        (".quality", "quality"),
        (".debug", "debug"),
        (".operations", "operations"),
    )
    for marker, product_module in mappings:
        if marker in endpoint_module:
            return product_module
    raise RuntimeError(f"未登记的 Core 路由模块：{endpoint_module}")


def _python_tests(product_module: str) -> list[str]:
    directory = "short_medium" if product_module == "shortmedium" else product_module
    return [f"apps/core-api/tests/{directory}/**/test_*.py"]


def _authentication(exposure: str, path: str) -> str:
    if exposure == "internal":
        return "direct_peer_and_ed25519"
    if exposure == "provider_media":
        return "provider_media_hmac_token"
    if path in {
        "/api/v1/auth/register",
        "/api/v1/auth/login",
        "/api/v1/auth/logout",
        "/api/v1/health/live",
        "/api/v1/health/ready",
    }:
        return "public"
    return "browser_cookie"


def _response_kind(route: Any, path: str) -> str:
    if path.endswith("/events"):
        return "sse"
    response_class = getattr(route, "response_class", None)
    response_name = getattr(response_class, "__name__", "")
    if response_name == "FileResponse" or "provider-assets" in path:
        return "file"
    if getattr(route, "status_code", None) == 204:
        return "empty"
    return "json"


def _side_effects(product_module: str, method: str, path: str) -> list[str]:
    if method == "GET":
        return ["redis_stream_subscription"] if path.endswith("/events") else []
    effects = ["postgresql_transaction"]
    if product_module in {"writing", "quality", "references", "styles", "video"}:
        effects.append("background_dispatch_or_reconciliation")
    if product_module in {"styles", "video"} and (
        "assets" in path or "references" in path or "frames" in path or "exports" in path
    ):
        effects.append("controlled_file_storage")
    if product_module in {"writing", "quality", "reviews"}:
        effects.append("redis_event_or_queue")
    if product_module == "billing":
        effects.append("credit_ledger_or_usage")
    return sorted(set(effects))


def _source(endpoint: Any) -> tuple[str, int]:
    source_file = inspect.getsourcefile(endpoint)
    if source_file is None:
        raise RuntimeError(f"无法定位路由源码：{endpoint}")
    path = Path(source_file).resolve().relative_to(ROOT)
    line = inspect.getsourcelines(endpoint)[1]
    return path.as_posix(), line


def _route_inventory(app: Any, openapi: dict[str, Any]) -> list[dict[str, Any]]:
    operation_ids = {
        (method.upper(), path): operation["operationId"]
        for path, path_item in openapi["paths"].items()
        for method, operation in path_item.items()
        if method.upper() in HTTP_METHODS
    }
    routes: list[dict[str, Any]] = []
    for included in app.routes:
        if type(included).__name__ != "_IncludedRouter":
            continue
        context = included.include_context
        for route in included.original_router.routes:
            methods = sorted(set(getattr(route, "methods", set())) & HTTP_METHODS)
            if not methods:
                continue
            path = _full_path(context.prefix, route.path)
            effective_schema = bool(context.include_in_schema and route.include_in_schema)
            if effective_schema:
                exposure = "public"
            elif path.startswith("/internal/v1/"):
                exposure = "internal"
            elif "provider-assets" in path:
                exposure = "provider_media"
            else:
                raise RuntimeError(f"未分类的隐藏路由：{path}")
            endpoint_module = route.endpoint.__module__
            product_module = _product_module(endpoint_module)
            source_file, source_line = _source(route.endpoint)
            for method in methods:
                routes.append(
                    {
                        "authentication": _authentication(exposure, path),
                        "deprecated": bool(getattr(route, "deprecated", False)),
                        "endpointFunction": route.name,
                        "endpointModule": endpoint_module,
                        "exposure": exposure,
                        "includeInOpenApi": effective_schema,
                        "method": method,
                        "mutation": method != "GET",
                        "operationId": operation_ids.get((method, path)),
                        "path": path,
                        "productModule": product_module,
                        "pythonTests": _python_tests(product_module),
                        "responseKind": _response_kind(route, path),
                        "sideEffects": _side_effects(product_module, method, path),
                        "sourceFile": source_file,
                        "sourceLine": source_line,
                        "statusCode": getattr(route, "status_code", None),
                        "transaction": (
                            "stream"
                            if path.endswith("/events")
                            else "write"
                            if method != "GET"
                            else "read_only"
                        ),
                    }
                )
    return sorted(routes, key=lambda item: (item["path"], item["method"]))


def _full_openapi(app: Any) -> dict[str, Any]:
    """仅在迁移基线导出进程中临时公开隐藏路由，供 Java 生成完整服务契约。"""

    restored: list[tuple[Any, bool, Any, bool]] = []
    try:
        for included in app.routes:
            if type(included).__name__ != "_IncludedRouter":
                continue
            context = included.include_context
            for route in included.original_router.routes:
                restored.append(
                    (context, bool(context.include_in_schema), route, bool(route.include_in_schema))
                )
                context.include_in_schema = True
                route.include_in_schema = True
        app.openapi_schema = None
        return app.openapi()
    finally:
        for context, context_value, route, route_value in restored:
            context.include_in_schema = context_value
            route.include_in_schema = route_value
        app.openapi_schema = None


def _java_openapi(
    source_openapi: dict[str, Any],
    routes: list[dict[str, Any]],
    *,
    source_contract: str,
) -> dict[str, Any]:
    """机械降级 JSON Schema 2020-12 语法，规避 Java 生成器尚未稳定支持的 3.1 表达。"""

    def normalize(value: object) -> object:
        if isinstance(value, list):
            return [normalize(item) for item in value]
        if not isinstance(value, dict):
            return value

        normalized = {key: normalize(item) for key, item in value.items()}
        if (
            normalized.get("type") == "string"
            and normalized.get("contentMediaType") == "application/octet-stream"
        ):
            # OpenAPI 3.0 用 format=binary 表示 multipart 文件。只把 3.1 关键字
            # 搬到扩展会让 Spring 接口错误生成 String，无法接收真实上传流。
            normalized["format"] = "binary"
        for unsupported_keyword in ("contentEncoding", "contentMediaType"):
            if unsupported_keyword in normalized:
                normalized[f"x-inkforge-{unsupported_keyword}"] = normalized.pop(
                    unsupported_keyword
                )
        if "const" in normalized:
            # Java 生成器 7.24 会把 boolean const 生成成无法编译的字符串枚举，并让
            # discriminator 子类返回枚举而父接口返回 String。运行时仍由原始 3.1 Schema 校验常量。
            normalized["x-inkforge-const"] = normalized.pop("const")
        any_of = normalized.get("anyOf")
        if isinstance(any_of, list):
            non_null = [item for item in any_of if item != {"type": "null"}]
            if len(non_null) + 1 == len(any_of) and len(non_null) == 1:
                replacement = dict(non_null[0]) if isinstance(non_null[0], dict) else {}
                for key in ("default", "description", "title"):
                    if key in normalized and key not in replacement:
                        replacement[key] = normalized[key]
                replacement["nullable"] = True
                return replacement
        return normalized

    java_openapi = normalize(deepcopy(source_openapi))
    if not isinstance(java_openapi, dict):
        raise TypeError("完整 OpenAPI 顶层必须是对象")

    def schema_references(value: object) -> set[str]:
        if isinstance(value, list):
            return set().union(*(schema_references(item) for item in value))
        if not isinstance(value, dict):
            return set()
        result: set[str] = set()
        reference = value.get("$ref")
        prefix = "#/components/schemas/"
        if isinstance(reference, str) and reference.startswith(prefix):
            result.add(reference.removeprefix(prefix))
        for item in value.values():
            result.update(schema_references(item))
        return result

    # JsonNullable 只用于请求图中需要区分“缺失”和“显式 null”的字段。响应 DTO 继续用
    # 普通可空引用，避免把 263 个响应字段泄漏成 Java 包装器；原始可空事实保留在扩展中。
    request_schemas: set[str] = set()
    for path_item in java_openapi.get("paths", {}).values():
        for operation in path_item.values():
            if isinstance(operation, dict) and "requestBody" in operation:
                request_schemas.update(schema_references(operation["requestBody"]))
    schemas = java_openapi.get("components", {}).get("schemas", {})

    # PostgreSQL VideoAsset.byteSize 是 BIGINT，受控整集导出又允许接近 2 GiB；
    # Java 生成器在没有 format 时默认使用 Integer，会在合法文件边界发生溢出。
    # 这里只把 Java 表示提升为 Long，线上 JSON 数字字段和 Python/TypeScript 契约不变。
    video_asset_schema = schemas.get("VideoAssetResponse")
    if not isinstance(video_asset_schema, dict):
        raise RuntimeError("Java 迁移契约缺少 VideoAssetResponse")
    byte_size_schema = video_asset_schema.get("properties", {}).get("byteSize")
    if not isinstance(byte_size_schema, dict) or byte_size_schema.get("type") != "integer":
        raise RuntimeError("Java 迁移契约缺少 VideoAssetResponse.byteSize 整数字段")
    byte_size_schema["format"] = "int64"
    byte_size_schema["x-inkforge-java-bigint-projection"] = True

    pending = list(request_schemas)
    while pending:
        schema_name = pending.pop()
        schema = schemas.get(schema_name)
        if not isinstance(schema, dict):
            continue
        for dependency in schema_references(schema) - request_schemas:
            request_schemas.add(dependency)
            pending.append(dependency)

    def use_plain_response_nulls(value: object) -> None:
        if isinstance(value, list):
            for item in value:
                use_plain_response_nulls(item)
            return
        if not isinstance(value, dict):
            return
        if value.get("nullable") is True:
            # OpenAPI Generator 会在解析带同级扩展的 $ref 时丢失属性扩展。先用
            # allOf 包住引用，确保“响应必显但值可空”的标记能进入 CodegenProperty，
            # 同时仍保持普通 Java 引用而不是 JsonNullable 包装器。
            reference = value.pop("$ref", None)
            if isinstance(reference, str):
                value["allOf"] = [{"$ref": reference}]
            value.pop("nullable")
            value["x-inkforge-source-nullable"] = True
        for item in value.values():
            use_plain_response_nulls(item)

    for schema_name, schema in schemas.items():
        if schema_name not in request_schemas:
            use_plain_response_nulls(schema)

    # FastAPI 对 StreamingResponse 的 OpenAPI 只保留无正文的 200，Java 生成器因此会
    # 错误地产生 ResponseEntity<Void> 和 application/json。这里只修正 Java 迁移投影，
    # 浏览器 URL、Last-Event-ID 和线上 SSE 帧格式均不改变。
    stream_path = java_openapi.get("paths", {}).get(
        "/api/v1/writing/runs/{task_id}/events", {}
    )
    stream_operation = stream_path.get("get") if isinstance(stream_path, dict) else None
    if not isinstance(stream_operation, dict):
        raise RuntimeError("Java 迁移契约缺少写作 SSE 路由")
    stream_response = stream_operation.get("responses", {}).get("200")
    if not isinstance(stream_response, dict):
        raise RuntimeError("Java 迁移契约缺少写作 SSE 200 响应")
    schemas["WritingEventStream"] = {
        "description": "持续输出写作运行事件的 SSE 字节流",
        "format": "binary",
        "type": "string",
    }
    stream_response["content"] = {
        "text/event-stream": {
            "schema": {"$ref": "#/components/schemas/WritingEventStream"}
        }
    }

    # FastAPI 的 FileResponse 默认不把动态媒体正文写入 OpenAPI，Java 生成器会错误产生
    # ResponseEntity<Void>。route inventory 已经从真实 response_class 标出全部文件路由，
    # 因此只修正 Java 投影，实际 MIME 与 Content-Disposition 仍由控制器按文件事实设置。
    schemas["BinaryFileStream"] = {
        "description": "经过归属或供应商令牌校验后流式输出的受控媒体文件",
        "format": "binary",
        "type": "string",
    }
    file_routes = {
        (str(item["path"]), str(item["method"]).lower())
        for item in routes
        if item["responseKind"] == "file"
    }
    for path, method in file_routes:
        operation = java_openapi.get("paths", {}).get(path, {}).get(method)
        if not isinstance(operation, dict):
            raise RuntimeError(f"Java 迁移契约缺少文件路由：{method.upper()} {path}")
        response = operation.get("responses", {}).get("200")
        if not isinstance(response, dict):
            raise RuntimeError(f"Java 迁移契约缺少文件 200 响应：{method.upper()} {path}")
        response["content"] = {
            "application/octet-stream": {
                "schema": {"$ref": "#/components/schemas/BinaryFileStream"}
            }
        }

    java_openapi["openapi"] = "3.0.3"
    java_openapi["x-inkforge-source-contract"] = source_contract
    java_openapi["x-inkforge-json-nullable-scope"] = "request-schema-graph"
    route_modules = {
        (str(item["path"]), str(item["method"]).lower()): str(item["productModule"])
        for item in routes
    }
    for path, path_item in java_openapi["paths"].items():
        for method, operation in path_item.items():
            product_module = route_modules.get((path, method))
            if product_module is not None:
                operation["tags"] = [product_module]
    product_modules = sorted(set(route_modules.values()))
    java_openapi["tags"] = [{"name": name} for name in product_modules]
    return java_openapi


def _error_fixtures() -> dict[Path, bytes]:
    request_id = "migration-baseline-request-1"
    return {
        CONTRACT_ROOT / "error-fixtures" / "api-error.json": _json_bytes(
            {
                "code": "NOVEL_VERSION_CONFLICT",
                "details": {"currentUpdatedAt": "2026-08-24T12:00:00Z"},
                "message": "小说已在其他位置更新，请刷新后重试",
                "requestId": request_id,
            }
        ),
        CONTRACT_ROOT / "error-fixtures" / "validation-error.json": _json_bytes(
            {
                "code": "VALIDATION_ERROR",
                "details": [
                    {
                        "message": "缺少必需字段",
                        "path": ["body", "clientRequestId"],
                        "type": "missing",
                    },
                    {
                        "message": "包含不允许的字段",
                        "path": ["body", "unknown"],
                        "type": "extra_forbidden",
                    },
                ],
                "message": "请求参数校验失败",
                "requestId": request_id,
            }
        ),
        CONTRACT_ROOT / "error-fixtures" / "not-found.json": _json_bytes(
            {
                "code": "NOT_FOUND",
                "details": None,
                "message": "请求的资源不存在",
                "requestId": request_id,
            }
        ),
    }


def _sse_fixtures() -> dict[Path, bytes]:
    observed_at = datetime(2026, 8, 24, 12, 0, tzinfo=UTC)
    event = WritingEvent(
        id="1735123456789-0",
        event="artifact_awaiting_user_approval",
        data={"artifactId": "artifact-fixture", "revision": 2},
        occurred_at=observed_at,
        source_event_id="source-fixture",
        sequence=7,
    )
    outcome = WritingRunOutcome(
        state="waiting_user",
        code="ARTIFACT_AWAITING_USER",
        taskTerminal=False,
        streamShouldClose=True,
        reconciliationRequired=False,
        currentCommand=WritingRunOutcomeCommand(
            id="command-fixture",
            kind="start",
            status="succeeded",
            updatedAt=observed_at,
        ),
        result=WritingRunOutcomeResult(
            kind="review_artifact",
            ready=True,
            id="artifact-fixture",
        ),
        observedAt=observed_at,
    )
    return {
        CONTRACT_ROOT / "sse-fixtures" / "event.txt": format_sse_event(event).encode(),
        CONTRACT_ROOT / "sse-fixtures" / "heartbeat.txt": format_heartbeat().encode(),
        CONTRACT_ROOT / "sse-fixtures" / "run-outcome.txt": format_run_outcome(outcome).encode(),
    }


def _http_fixtures() -> dict[Path, bytes]:
    cursor_time = datetime(2026, 8, 24, 12, 34, 56, 789000, tzinfo=UTC)
    cursor = encode_run_cursor(created_at=cursor_time, task_id="task-cursor-fixture")
    file_response = FileResponse(
        "fixture.mp4",
        media_type="video/mp4",
        filename="成片 v1.mp4",
    )
    return {
        CONTRACT_ROOT / "http-fixtures" / "pagination-cursor.json": _json_bytes(
            {
                "createdAt": cursor_time.isoformat(),
                "decodedTaskId": "task-cursor-fixture",
                "encoded": cursor,
                "paddingAllowed": False,
                "schemaVersion": "run-cursor-fixture/1.0",
            }
        ),
        CONTRACT_ROOT / "http-fixtures" / "request-id.json": _json_bytes(
            {
                "acceptedExamples": ["migration-request-1", "甲-request-2"],
                "generatedFormat": "uuid-v4",
                "header": "X-Request-ID",
                "maxLength": 128,
                "minLength": 1,
                "rejectedExamples": ["", "has\\ncontrol", "x" * 129],
                "schemaVersion": "request-id-fixture/1.0",
                "trimBeforeValidation": True,
            }
        ),
        CONTRACT_ROOT / "http-fixtures" / "session-cookie.json": _json_bytes(
            {
                "cookieName": COOKIE_NAME,
                "httpOnly": True,
                "jwt": {
                    "algorithm": "HS256",
                    "requiredClaims": ["sub", "iat", "exp"],
                },
                "maxAgeSeconds": SESSION_MAX_AGE_SECONDS,
                "path": "/",
                "sameSite": "lax",
                "schemaVersion": "session-cookie-fixture/1.0",
                "secure": {"dev": False, "production": True, "test": False},
            }
        ),
        CONTRACT_ROOT / "http-fixtures" / "file-download.json": _json_bytes(
            {
                "headers": {
                    key.lower(): value
                    for key, value in sorted(file_response.headers.items())
                },
                "inputFilename": "成片 v1.mp4",
                "mediaType": "video/mp4",
                "schemaVersion": "file-download-fixture/1.0",
            }
        ),
        CONTRACT_ROOT / "http-fixtures" / "trailing-slash-redirect.json": _json_bytes(
            {
                "canonicalPath": "/api/v1/novels",
                "locationTemplate": "{scheme}://{host}/api/v1/novels",
                "preserveRequestIdHeader": True,
                "requestPath": "/api/v1/novels/",
                "schemaVersion": "trailing-slash-redirect-fixture/1.0",
                "statusCode": 307,
            }
        ),
    }


def _b64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _service_auth_fixtures() -> dict[Path, bytes]:
    seed = bytes(range(1, 33))
    private_key = Ed25519PrivateKey.from_private_bytes(seed)
    public_raw = private_key.public_key().public_bytes(
        serialization.Encoding.Raw,
        serialization.PublicFormat.Raw,
    )
    kid = "migration-fixture-v1"
    jwks = {
        "keys": [
            {
                "alg": "EdDSA",
                "crv": "Ed25519",
                "kid": kid,
                "kty": "OKP",
                "use": "sig",
                "x": _b64url(public_raw),
            }
        ]
    }
    body = '{"message":"开始","count":2}'.encode()
    query = b"cursor=abc%2F1"
    with tempfile.TemporaryDirectory(prefix="inkforge-service-auth-fixture-") as directory:
        private_path = Path(directory) / "test-only-private.pem"
        private_path.write_bytes(
            private_key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            )
        )
        os.chmod(private_path, 0o600)
        signer = ServiceTokenSigner(
            private_key_path=private_path,
            issuer="inkforge-core-fixture",
            subject="core-api",
            audience="inkforge-agent-fixture",
            kid=kid,
        )
        signed = signer.sign_request(
            body=body,
            http_method="POST",
            http_path="/internal/v1/tools/get_novel_summary",
            query_string=query,
            idempotency_key="migration-fixture-request-0001",
            scope=[ServiceScope.TOOL_READ],
            task_id="task-fixture",
            run_id="run-fixture",
            novel_id="novel-fixture",
            now=1_800_000_000,
            ttl_seconds=120,
            jti="jti-migration-fixture-0001",
        )
    claims = jwt.decode(signed.token, options={"verify_signature": False})
    golden = {
        "bodyBase64": base64.b64encode(body).decode("ascii"),
        "claims": claims,
        "expectedFailures": {
            "expired": "SERVICE_AUTHENTICATION_FAILED",
            "replay": "SERVICE_TOKEN_REPLAYED",
            "wrongAudience": "SERVICE_AUTHENTICATION_FAILED",
            "wrongBody": "SERVICE_REQUEST_BINDING_INVALID",
            "wrongScope": "SERVICE_SCOPE_FORBIDDEN",
        },
        "headers": dict(signed.headers),
        "httpMethod": "POST",
        "httpPath": "/internal/v1/tools/get_novel_summary",
        "queryStringBase64": base64.b64encode(query).decode("ascii"),
        "schemaVersion": "service-auth-golden-request/1.0",
        "testOnlyPrivateKeySeedHex": seed.hex(),
        "token": signed.token,
    }
    return {
        CONTRACT_ROOT / "service-auth-fixtures" / "golden-request.json": _json_bytes(golden),
        CONTRACT_ROOT / "service-auth-fixtures" / "public-jwks.json": _json_bytes(jwks),
    }


def build_outputs() -> dict[Path, bytes]:
    app = create_app(testing=True)
    openapi = app.openapi()
    routes = _route_inventory(app, openapi)
    internal = [item for item in routes if item["exposure"] == "internal"]
    # FastAPI 首次生成 OpenAPI 时会固化延迟 include 的结果，因此完整契约必须使用独立应用实例。
    full_openapi = _full_openapi(create_app(testing=True))
    public_routes = [item for item in routes if item["exposure"] == "public"]
    public_java_openapi = _java_openapi(
        openapi,
        public_routes,
        source_contract="public-openapi-python-baseline.json",
    )
    java_openapi = _java_openapi(
        full_openapi,
        routes,
        source_contract="full-openapi-python-baseline.json",
    )
    outputs = {
        CONTRACT_ROOT / "public-openapi-python-baseline.json": _json_bytes(openapi),
        CONTRACT_ROOT / "public-openapi-java-baseline.json": _json_bytes(
            public_java_openapi
        ),
        CONTRACT_ROOT / "full-openapi-python-baseline.json": _json_bytes(full_openapi),
        CONTRACT_ROOT / "full-openapi-java-baseline.json": _json_bytes(java_openapi),
        CONTRACT_ROOT / "internal-endpoints.json": _json_bytes(
            {
                "endpoints": internal,
                "schemaVersion": "core-internal-endpoints/1.0",
            }
        ),
        CONTRACT_ROOT / "route-inventory.json": _json_bytes(
            {
                "baselineCommit": "c9afc95",
                "routes": routes,
                "schemaVersion": "core-route-inventory/1.0",
            }
        ),
    }
    outputs.update(_error_fixtures())
    outputs.update(_sse_fixtures())
    outputs.update(_http_fixtures())
    outputs.update(_service_auth_fixtures())
    return outputs


def _check(outputs: dict[Path, bytes]) -> int:
    drift: list[str] = []
    for path, expected in outputs.items():
        if not path.exists():
            drift.append(f"缺少 {path.relative_to(ROOT)}")
        elif path.read_bytes() != expected:
            drift.append(f"内容漂移 {path.relative_to(ROOT)}")
    if drift:
        print("Core 迁移基线不一致：")
        for item in drift:
            print(f"- {item}")
        return 1
    print(f"Core 迁移基线一致，共 {len(outputs)} 个文件")
    return 0


def _write(outputs: dict[Path, bytes]) -> None:
    for path, payload in outputs.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
    print(f"已导出 Core 迁移基线，共 {len(outputs)} 个文件")


def main() -> int:
    parser = argparse.ArgumentParser(description="导出或核对 Python Core Java 迁移基线")
    parser.add_argument("--check", action="store_true", help="只核对，不修改文件")
    args = parser.parse_args()
    outputs = build_outputs()
    if args.check:
        return _check(outputs)
    _write(outputs)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
