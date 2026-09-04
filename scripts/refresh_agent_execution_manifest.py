#!/usr/bin/env python3
"""从共享模型机械生成指定输出 Schema，并刷新执行资产的派生哈希。"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from inkforge_contracts.execution import (
    ChapterPlanOutput,
    canonical_execution_sha256,
)


def _bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def chapter_plan_schema() -> dict[str, Any]:
    """内联模型引用并去掉展示注解，保持 Core 已实现的严格 Schema 子集。"""

    source = ChapterPlanOutput.model_json_schema(mode="validation")
    definitions = source.pop("$defs", {})

    def simplify(node: dict[str, Any]) -> dict[str, Any]:
        if "$ref" in node:
            reference = node["$ref"]
            if not reference.startswith("#/$defs/"):
                raise ValueError("输出 Schema 只能引用当前模型的本地定义")
            node = definitions[reference.removeprefix("#/$defs/")] | {
                key: value for key, value in node.items() if key != "$ref"
            }
        result: dict[str, Any] = {}
        for key, value in node.items():
            if key in {"title", "description", "default"}:
                continue
            if key == "properties":
                result[key] = {name: simplify(schema) for name, schema in value.items()}
            elif isinstance(value, dict):
                result[key] = simplify(value)
            elif key in {"anyOf", "allOf", "oneOf"}:
                result[key] = [simplify(schema) for schema in value]
            else:
                result[key] = value
        return result

    return {"$schema": "https://json-schema.org/draft/2020-12/schema"} | simplify(source)


def refresh(root: Path, *, check: bool) -> list[str]:
    changes: dict[Path, bytes] = {}
    prompt_path = root / "prompt-profile-registry.v1.json"
    prompts = json.loads(prompt_path.read_bytes())
    for prompt in prompts["prompts"]:
        prompt["sha256"] = hashlib.sha256(prompt["systemPrompt"].encode("utf-8")).hexdigest()
    changes[prompt_path] = _bytes(prompts)

    output_path = root / "output-schema-registry.v1.json"
    outputs = json.loads(output_path.read_bytes())
    for output in outputs["schemas"]:
        if output["key"] == "output.beat_plan.v1":
            output["supported"] = True
            output["jsonSchema"] = chapter_plan_schema()
        output["sha256"] = canonical_execution_sha256(output["jsonSchema"])
    changes[output_path] = _bytes(outputs)

    manifest_path = root / "manifest.json"
    manifest = json.loads(manifest_path.read_bytes())
    for entry in manifest.values():
        if isinstance(entry, dict) and "path" in entry:
            path = root / entry["path"]
            entry["sha256"] = hashlib.sha256(changes.get(path, path.read_bytes())).hexdigest()
    changes[manifest_path] = _bytes(manifest)
    changed = [path.name for path, content in changes.items() if path.read_bytes() != content]
    if not check:
        for path, content in changes.items():
            if path.name in changed:
                path.write_bytes(content)
    return changed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="仅检查派生内容是否需要更新")
    parser.add_argument("--root", type=Path, default=Path("contracts/agent-execution"))
    arguments = parser.parse_args()
    changed = refresh(arguments.root, check=arguments.check)
    print(
        "需更新：" + "、".join(changed)
        if arguments.check and changed
        else "执行资产派生内容已一致。"
    )
    return 1 if arguments.check and changed else 0


if __name__ == "__main__":
    raise SystemExit(main())
