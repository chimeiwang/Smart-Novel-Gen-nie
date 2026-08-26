from __future__ import annotations

import argparse
import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from inkforge_agents.app import create_app

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_ROOT = ROOT / "contracts" / "agent-service"


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()


def _full_openapi() -> dict[str, Any]:
    app = create_app(testing=True)
    for included in app.routes:
        if type(included).__name__ == "_IncludedRouter":
            included.include_context.include_in_schema = True
            for route in included.original_router.routes:
                route.include_in_schema = True
        elif hasattr(included, "include_in_schema"):
            included.include_in_schema = True
    app.openapi_schema = None
    return app.openapi()


def _java_openapi(source: dict[str, Any]) -> dict[str, Any]:
    def normalize(value: object) -> object:
        if isinstance(value, list):
            return [normalize(item) for item in value]
        if not isinstance(value, dict):
            return value
        normalized = {key: normalize(item) for key, item in value.items()}
        for unsupported_keyword in ("contentEncoding", "contentMediaType"):
            if unsupported_keyword in normalized:
                normalized[f"x-inkforge-{unsupported_keyword}"] = normalized.pop(
                    unsupported_keyword
                )
        if "const" in normalized:
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

    result = normalize(deepcopy(source))
    if not isinstance(result, dict):
        raise TypeError("Agent OpenAPI 顶层必须是对象")
    result["openapi"] = "3.0.3"
    result["x-inkforge-source-contract"] = "openapi-python-baseline.json"
    for path_item in result["paths"].values():
        for method, operation in path_item.items():
            if method in {"get", "post", "put", "patch", "delete"}:
                operation["tags"] = ["agent-service"]
    result["tags"] = [{"name": "agent-service"}]
    return result


def build_outputs() -> dict[Path, bytes]:
    source = _full_openapi()
    return {
        CONTRACT_ROOT / "openapi-python-baseline.json": _json_bytes(source),
        CONTRACT_ROOT / "openapi-java-baseline.json": _json_bytes(_java_openapi(source)),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="导出 Agent Service Java 迁移契约")
    parser.add_argument("--check", action="store_true", help="只检查，不写文件")
    arguments = parser.parse_args()
    outputs = build_outputs()
    if arguments.check:
        drift = [
            path
            for path, content in outputs.items()
            if not path.exists() or path.read_bytes() != content
        ]
        if drift:
            print("Agent Service 迁移契约不一致：")
            for path in drift:
                print(f"- {path.relative_to(ROOT)}")
            return 1
        print("Agent Service 迁移契约一致")
        return 0
    for path, content in outputs.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    print(f"已导出 Agent Service 迁移契约，共 {len(outputs)} 个文件")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
