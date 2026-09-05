#!/usr/bin/env python3
"""从共享模型机械生成指定输出 Schema，并刷新执行资产的派生哈希。"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from inkforge_contracts.agent_updates import AgentUpdatesEvidenceRequestOutput, AgentUpdatesOutput
from inkforge_contracts.execution import (
    CandidateTextPatch,
    ChapterDraftOutput,
    ChapterPlanOutput,
    ChapterReviewOutput,
    IntentResolutionOutput,
    OutlineSelectionOutput,
    canonical_execution_sha256,
)
from inkforge_contracts.short_medium_execution import (
    ShortMediumCheckOutput,
    ShortMediumContentOutput,
    ShortMediumReplacementOutput,
)
from pydantic import BaseModel


def _bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def model_output_schema(model: type[BaseModel]) -> dict[str, Any]:
    """内联模型引用并去掉展示注解，保持 Core 已实现的严格 Schema 子集。"""

    source = model.model_json_schema(mode="validation")
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


def chapter_plan_schema() -> dict[str, Any]:
    return model_output_schema(ChapterPlanOutput)


def agent_updates_step_schema() -> dict[str, Any]:
    """候选与来源需求互斥，复用 Core 已支持的 anyOf/maxProperties，不改变旧候选 Schema。"""

    candidate = model_output_schema(AgentUpdatesOutput)
    expansion = model_output_schema(AgentUpdatesEvidenceRequestOutput)
    return candidate | {
        "required": [],
        "properties": candidate["properties"] | expansion["properties"],
        "anyOf": [
            {"required": candidate["required"], "maxProperties": 2},
            {"required": expansion["required"], "maxProperties": 1},
        ],
    }


def refresh(root: Path, *, check: bool) -> list[str]:
    changes: dict[Path, bytes] = {}
    prompt_path = root / "prompt-profile-registry.v1.json"
    prompts = json.loads(prompt_path.read_bytes())
    for prompt in prompts["prompts"]:
        prompt["sha256"] = hashlib.sha256(prompt["systemPrompt"].encode("utf-8")).hexdigest()
    changes[prompt_path] = _bytes(prompts)

    output_path = root / "output-schema-registry.v1.json"
    outputs = json.loads(output_path.read_bytes())
    agent_updates_schema = model_output_schema(AgentUpdatesOutput)
    if not any(output["key"] == "output.agent_updates.v2" for output in outputs["schemas"]):
        legacy_index = next(
            index
            for index, output in enumerate(outputs["schemas"])
            if output["key"] == "output.agent_updates.v1"
        )
        outputs["schemas"].insert(
            legacy_index + 1,
            {
                "key": "output.agent_updates.v2",
                "version": 2,
                "supported": True,
                "purpose": "generation",
                "sha256": canonical_execution_sha256(agent_updates_schema),
                "jsonSchema": agent_updates_schema,
            },
        )
    step_schema = agent_updates_step_schema()
    if not any(output["key"] == "output.agent_updates_step.v1" for output in outputs["schemas"]):
        outputs["schemas"].append(
            {
                "key": "output.agent_updates_step.v1",
                "version": 1,
                "supported": True,
                "purpose": "generation",
                "sha256": canonical_execution_sha256(step_schema),
                "jsonSchema": step_schema,
            }
        )
    original_review_schema = next(
        schema["jsonSchema"]
        for schema in outputs["schemas"]
        if schema["key"] == "output.chapter_review_report.v1"
    )
    for output in outputs["schemas"]:
        short_medium_models = {
            "output.short_medium_outline.v2": ShortMediumContentOutput,
            "output.short_medium_segment.v2": ShortMediumContentOutput,
            "output.short_medium_replacement.v2": ShortMediumReplacementOutput,
            "output.short_medium_check_report.v2": ShortMediumCheckOutput,
        }
        if output["key"] in short_medium_models:
            output["jsonSchema"] = model_output_schema(short_medium_models[output["key"]])
        if output["key"] == "output.agent_updates_step.v1":
            output["jsonSchema"] = step_schema
        elif output["key"] == "output.agent_updates.v2":
            output["supported"] = True
            output["jsonSchema"] = agent_updates_schema
        elif output["key"] == "output.beat_plan.v1":
            output["supported"] = True
            output["jsonSchema"] = chapter_plan_schema()
        elif output["key"] == "output.chapter_draft.v1":
            output["supported"] = True
            output["jsonSchema"] = model_output_schema(ChapterDraftOutput)
        elif output["key"] == "output.chapter_review_text.v1":
            output["supported"] = True
            output["jsonSchema"] = model_output_schema(ChapterReviewOutput)
        elif output["key"] == "output.outline_selection_replacement.v1":
            output["supported"] = True
            output["jsonSchema"] = model_output_schema(OutlineSelectionOutput)
        elif output["key"] == "output.proposed_command.v1":
            output["supported"] = True
            output["jsonSchema"] = model_output_schema(IntentResolutionOutput)
        elif output["key"] == "output.chapter_draft_review_report.v1":
            schema = json.loads(json.dumps(original_review_schema))
            patch = model_output_schema(CandidateTextPatch)
            patch.pop("$schema")
            schema["properties"]["findings"]["items"]["properties"]["candidatePatch"] = patch
            output["supported"] = True
            output["jsonSchema"] = schema
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
