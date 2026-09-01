#!/usr/bin/env python3
"""把 Agent/Core 共享 Pydantic 模型导出为稳定、语言中立的 JSON Schema。"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import inspect
import json
from pathlib import Path

from pydantic import BaseModel

CONTRACT_MODULES = (
    "events",
    "execution",
    "identity",
    "jobs",
    "jwt_claims",
    "long_serial",
    "operations",
    "quality",
    "read_tools",
    "runs",
    "short_medium",
    "tools",
    "video",
    "video_adaptation",
    "video_render",
    "workflow_events",
)
ABSTRACT_MODELS = {
    "_StrictModel",
    "StrictModel",
    "VideoContractModel",
    "VideoAdaptationContractModel",
    "VideoRenderContractModel",
}
MODULE_SCHEMA_VERSIONS = {"execution": "2.0", "workflow_events": "2.0"}


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()


def export_contracts(output: Path) -> dict[str, object]:
    output.mkdir(parents=True, exist_ok=True)
    entries: list[dict[str, str]] = []
    for module_name in CONTRACT_MODULES:
        module = importlib.import_module(f"inkforge_contracts.{module_name}")
        model_types = sorted(
            (
                value
                for value in vars(module).values()
                if inspect.isclass(value)
                and issubclass(value, BaseModel)
                and value.__module__ == module.__name__
                and value.__name__ not in ABSTRACT_MODELS
            ),
            key=lambda model: model.__name__,
        )
        for model_type in model_types:
            relative_path = Path(module_name) / f"{model_type.__name__}.schema.json"
            schema = model_type.model_json_schema(mode="validation")
            schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
            schema["$id"] = (
                "https://inkforge.local/contracts/agent/"
                f"{module_name}/{model_type.__name__}/"
                f"{MODULE_SCHEMA_VERSIONS.get(module_name, '1.0')}"
            )
            schema["x-inkforge-python-type"] = (
                f"inkforge_contracts.{module_name}.{model_type.__name__}"
            )
            serialized = _json_bytes(schema)
            destination = output / relative_path
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(serialized)
            entries.append(
                {
                    "module": module_name,
                    "model": model_type.__name__,
                    "path": relative_path.as_posix(),
                    "sha256": hashlib.sha256(serialized).hexdigest(),
                }
            )

    manifest: dict[str, object] = {
        "schemaVersion": "inkforge-agent-contract-manifest/1.0",
        "generator": "scripts/export_agent_contract_schemas.py",
        "modelCount": len(entries),
        "models": entries,
    }
    (output / "manifest.json").write_bytes(_json_bytes(manifest))
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("contracts/core/agent"),
        help="输出目录",
    )
    arguments = parser.parse_args()
    manifest = export_contracts(arguments.output)
    print(f"已导出 {manifest['modelCount']} 个 Agent JSON Schema。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
