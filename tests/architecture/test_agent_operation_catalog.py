from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, cast

import jsonschema_rs
from inkforge_contracts import (
    EXECUTION_HASH_ALGORITHM,
    canonical_execution_json_bytes,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
CONTRACT_ROOT = REPOSITORY_ROOT / "contracts" / "agent-execution"
CATALOG_PATH = CONTRACT_ROOT / "operation-catalog.v1.json"
SCHEMA_PATH = CONTRACT_ROOT / "operation-catalog.schema.json"
PROFILE_REGISTRY_PATH = CONTRACT_ROOT / "profile-registry.v1.json"
PROFILE_REGISTRY_SCHEMA_PATH = CONTRACT_ROOT / "profile-registry.schema.json"
DEPLOYMENT_PROFILE_REGISTRY_PATH = CONTRACT_ROOT / "deployment-profile-registry.v1.json"
DEPLOYMENT_PROFILE_REGISTRY_SCHEMA_PATH = (
    CONTRACT_ROOT / "deployment-profile-registry.schema.json"
)
PROMPT_PROFILE_REGISTRY_PATH = CONTRACT_ROOT / "prompt-profile-registry.v1.json"
PROMPT_PROFILE_REGISTRY_SCHEMA_PATH = CONTRACT_ROOT / "prompt-profile-registry.schema.json"
OUTPUT_SCHEMA_REGISTRY_PATH = CONTRACT_ROOT / "output-schema-registry.v1.json"
OUTPUT_SCHEMA_REGISTRY_SCHEMA_PATH = CONTRACT_ROOT / "output-schema-registry.schema.json"
STEP_BUDGET_REGISTRY_PATH = CONTRACT_ROOT / "step-budget-registry.v1.json"
STEP_BUDGET_REGISTRY_SCHEMA_PATH = CONTRACT_ROOT / "step-budget-registry.schema.json"
SYSTEM_PURPOSE_REGISTRY_PATH = CONTRACT_ROOT / "system-purpose-registry.v1.json"
SYSTEM_PURPOSE_REGISTRY_SCHEMA_PATH = CONTRACT_ROOT / "system-purpose-registry.schema.json"
HASH_VECTORS_PATH = CONTRACT_ROOT / "hash-vectors.v1.json"
MANIFEST_PATH = CONTRACT_ROOT / "manifest.json"

EXPECTED_OPERATION_KEYS = frozenset(
    {
        "long_serial.answer_question",
        "long_serial.create_lore",
        "long_serial.revise_lore",
        "long_serial.create_outline",
        "long_serial.revise_outline",
        "long_serial.plan_chapter",
        "long_serial.write_chapter",
        "long_serial.rewrite_scene",
        "long_serial.rewrite_chapter_selection",
        "long_serial.rewrite_outline_selection",
        "long_serial.review_chapter",
        "long_serial.manage_foreshadowing",
        "short_medium.generate_outline",
        "short_medium.generate_manuscript",
        "short_medium.replace_selection",
        "short_medium.full_check",
        "quality.consistency",
        "style.portrait",
        "rag.embedding",
        "video.chapter_cinematic_adaptation_v2",
        "video.chapter_shot_prompt_v2",
    }
)
DEVELOPMENT_ONLY_OPERATION_KEYS = frozenset(
    {
        "video.chapter_cinematic_adaptation_v2",
        "video.chapter_shot_prompt_v2",
    }
)
POSITIVE_BUDGET_LIMIT_FIELDS = frozenset(
    {
        "maxModelCalls",
        "maxInputTokens",
        "maxPromptCacheMissTokens",
        "maxWallClockSeconds",
    }
)
NON_NEGATIVE_BUDGET_LIMIT_FIELDS = frozenset(
    {
        "maxCompletionTokens",
        "maxReasoningTokens",
        "maxVisibleOutputTokens",
        "maxCostMicros",
        "maxProtocolCorrectionSteps",
        "maxProviderRetriesPerStep",
    }
)
STEP_POSITIVE_BUDGET_LIMIT_FIELDS = frozenset(
    {
        "maxInputTokens",
        "maxPromptCacheMissTokens",
        "maxWallClockSeconds",
    }
)
STEP_NON_NEGATIVE_BUDGET_LIMIT_FIELDS = frozenset(
    {
        "maxCompletionTokens",
        "maxReasoningTokens",
        "maxVisibleOutputTokens",
        "maxCostMicros",
        "maxProtocolCorrections",
        "maxProviderRetries",
    }
)
AGGREGATE_STEP_BUDGET_FIELDS = frozenset(
    {
        "maxModelCalls",
        "maxInputTokens",
        "maxPromptCacheMissTokens",
        "maxCompletionTokens",
        "maxReasoningTokens",
        "maxVisibleOutputTokens",
        "maxCostMicros",
        "maxWallClockSeconds",
    }
)
EXPECTED_SYSTEM_PURPOSES = frozenset(
    {
        "resolve_intent",
        "summarize_evidence",
        "protocol_correction",
    }
)
RETAINED_EXECUTION_PROFILE_KEYS = frozenset(
    {
        "style.portrait.v1",
        "quality.consistency.v1",
        "system.protocol_corrector.v1",
        "system.intent_resolver.v1",
        "system.intent_resolver.v2",
        "lore.generator.v1",
        "lore.reviser.v1",
        "plot.outline_generator.v1",
        "plot.outline_reviser.v1",
        "plot.foreshadowing.v1",
        "lore.generator.v2",
        "lore.reviser.v2",
        "plot.outline_generator.v2",
        "plot.outline_reviser.v2",
        "plot.foreshadowing.v2",
        "plot.short_medium_outline.v1",
        "writer.short_medium_manuscript.v1",
        "writer.short_medium_selection.v1",
        "quality.short_medium_full_check.v1",
    }
)
RETAINED_OUTPUT_SCHEMA_KEYS = frozenset(
    {
        "output.style_portrait.v1",
        "output.consistency_quality_report.v1", "output.protocol_correction.v1",
        "output.agent_updates.v1", "output.agent_updates.v2",
        "output.short_medium_outline.v1", "output.short_medium_segment_manifest.v1",
        "output.short_medium_replacement.v1", "output.short_medium_check_report.v1",
    }
)
AGENT_UPDATES_V2_ASSET_SHA256 = {
    "lore.generator": (
        "68ec2714b1f2f34f79ebabbe62aea2b6d867e6dbfa36c04611a8126422cddcbe",
        "c8cbb44cbd24fcd23e3038e73b98e6cc8be95966e214b6a5b3328764d41e2843",
        "9d633777c10e75609da406955b497cca0e9a0e937b3fa10adf842ef600f535b6",
    ),
    "lore.reviser": (
        "8cb29b3b1a375a62167cd4565f079fd4a44d616480d875bd4179c428d88e1b24",
        "4bfdcb9fb62bde46d11b0a0b84a69e7ed6ae12f1967b4905f292275d5d25064b",
        "75be6cdf5a19be5abc9b1618b416f700d9a4e23044bb9b19c448fcce11fd7bb0",
    ),
    "plot.outline_generator": (
        "c768d4265a8334be14ef359b787944a1854cf8f01ad1113f64dfd8c611c1523f",
        "bf40786822a3541555343c0a3e64fc1f17a06ec13ada1f9d23e49e89ed64be04",
        "89ae1fd13d7ca6237e4b072c24f3b22268a958c3a24611f77996cfaf743ee203",
    ),
    "plot.outline_reviser": (
        "ad0596bcfa9ba6508b8671aaed4631742b7cefc4042f44d62a607fdd24ad23bc",
        "50161c211c891bf12e674fced31459eb350b078767605331344c004bc9314bd9",
        "098344537db7236f2b6352ed488161445efdc58a81e5d45df2161f4dce949c1c",
    ),
    "plot.foreshadowing": (
        "b6c1c7660db55745ed452a42ee6d158a1dc45529c504caf54fd2def3ed7f9794",
        "cf3c0ae62d7fa7822f004cbb6c16890c3e50287adc075a564eaf31f8fdab5526",
        "9343fa42b202a75b78cd9825bb1e75f63ac344e74f20e51615ab414d52d742c6",
    ),
}
NO_THINKING_OPERATION_KEYS = frozenset(
    {
        "long_serial.answer_question",
        "long_serial.review_chapter",
        "short_medium.full_check",
        "quality.consistency",
        "style.portrait",
        "video.chapter_cinematic_adaptation_v2",
        "video.chapter_shot_prompt_v2",
    }
)
CHAPTER_DRAFT_OPERATION_KEYS = frozenset(
    {
        "long_serial.write_chapter",
        "long_serial.rewrite_scene",
        "long_serial.rewrite_chapter_selection",
    }
)


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict), f"JSON 根节点必须是对象：{path}"
    return cast(dict[str, Any], value)


def test_execution_derived_manifest_and_planning_schema_have_no_drift() -> None:
    result = subprocess.run(  # noqa: S603 -- 固定解释器只检查仓内派生资产，不联网不修改文件
        [
            sys.executable,
            str(REPOSITORY_ROOT / "scripts/refresh_agent_execution_manifest.py"),
            "--check",
        ],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def _operations() -> list[dict[str, Any]]:
    value = _read_json(CATALOG_PATH)["operations"]
    assert isinstance(value, list)
    assert all(isinstance(item, dict) for item in value)
    return cast(list[dict[str, Any]], value)


def _system_purposes() -> dict[str, dict[str, Any]]:
    value = _read_json(SYSTEM_PURPOSE_REGISTRY_PATH)["purposes"]
    assert isinstance(value, list)
    assert all(isinstance(item, dict) for item in value)
    items = cast(list[dict[str, Any]], value)
    purposes = [item["purpose"] for item in items]
    assert len(purposes) == len(set(purposes)), "System Purpose Registry 存在重复 purpose"
    return {cast(str, item["purpose"]): item for item in items}


def _keyed_items(path: Path, field: str) -> dict[str, dict[str, Any]]:
    value = _read_json(path)[field]
    assert isinstance(value, list)
    assert all(isinstance(item, dict) for item in value)
    items = cast(list[dict[str, Any]], value)
    keys = [item["key"] for item in items]
    assert len(keys) == len(set(keys)), f"{path.name} 存在重复 key"
    return {cast(str, item["key"]): item for item in items}


def _canonical_sha256(value: object) -> str:
    canonical = canonical_execution_json_bytes(value)
    return hashlib.sha256(canonical).hexdigest()


def _assert_key_version(item: dict[str, Any]) -> None:
    key = item["key"]
    version = item["version"]
    assert isinstance(key, str)
    assert isinstance(version, int) and not isinstance(version, bool) and version > 0
    assert key.endswith(f".v{version}"), f"{key} 的 key 与 version 不一致"


def test_operation_catalog_conforms_to_its_schema() -> None:
    schema = _read_json(SCHEMA_PATH)
    catalog = _read_json(CATALOG_PATH)

    validator = jsonschema_rs.validator_for(schema)
    validator.validate(catalog)


def test_all_execution_registries_conform_to_their_schemas() -> None:
    for registry_path, registry_schema_path in (
        (PROFILE_REGISTRY_PATH, PROFILE_REGISTRY_SCHEMA_PATH),
        (DEPLOYMENT_PROFILE_REGISTRY_PATH, DEPLOYMENT_PROFILE_REGISTRY_SCHEMA_PATH),
        (PROMPT_PROFILE_REGISTRY_PATH, PROMPT_PROFILE_REGISTRY_SCHEMA_PATH),
        (OUTPUT_SCHEMA_REGISTRY_PATH, OUTPUT_SCHEMA_REGISTRY_SCHEMA_PATH),
        (STEP_BUDGET_REGISTRY_PATH, STEP_BUDGET_REGISTRY_SCHEMA_PATH),
        (SYSTEM_PURPOSE_REGISTRY_PATH, SYSTEM_PURPOSE_REGISTRY_SCHEMA_PATH),
    ):
        validator = jsonschema_rs.validator_for(_read_json(registry_schema_path))
        validator.validate(_read_json(registry_path))


def test_operation_catalog_has_complete_unique_keys() -> None:
    operations = _operations()
    keys = [operation["key"] for operation in operations]

    assert len(keys) == len(set(keys)), "Operation Catalog 存在重复 key"
    assert frozenset(keys) == EXPECTED_OPERATION_KEYS
    for operation in operations:
        assert operation["key"] == (f"{operation['workflow']}.{operation['operation']}"), (
            "Operation key 必须由 workflow 与 operation 确定性组成"
        )
        assert operation["labels"]["zh-CN"].strip(), "Operation 必须提供中文标签"

    enabled_keys = {operation["key"] for operation in operations if operation["v2Enabled"]}
    assert enabled_keys == {
        "long_serial.answer_question",
        "long_serial.create_lore",
        "long_serial.revise_lore",
        "long_serial.create_outline",
        "long_serial.revise_outline",
        "long_serial.manage_foreshadowing",
        "long_serial.plan_chapter",
        "long_serial.write_chapter",
        "long_serial.rewrite_scene",
        "long_serial.rewrite_chapter_selection",
        "long_serial.rewrite_outline_selection",
        "long_serial.review_chapter",
        "short_medium.generate_outline",
        "short_medium.generate_manuscript",
        "short_medium.replace_selection",
        "short_medium.full_check",
        "quality.consistency",
        "style.portrait",
    }
    answer = next(
        operation
        for operation in operations
        if operation["key"] == "long_serial.answer_question"
    )
    assert answer["targetKinds"] == ["chapter"]
    assert answer["scopeKinds"] == ["chapter"]
    assert answer["reviewPolicy"]["mode"] == "none"
    assert answer["reviewPolicy"]["reviewerProfiles"] == []
    assert answer["reviewPolicy"].get("reviewerStepBudgetProfiles") is None
    assert answer["reviewPolicy"].get("reviewerOutputSchema") is None

    development_only_keys = {
        operation["key"] for operation in operations if operation["developmentOnly"]
    }
    assert development_only_keys == DEVELOPMENT_ONLY_OPERATION_KEYS


def test_catalog_and_system_registry_references_are_complete() -> None:
    profiles = _keyed_items(PROFILE_REGISTRY_PATH, "profiles")
    deployments = _keyed_items(DEPLOYMENT_PROFILE_REGISTRY_PATH, "profiles")
    prompts = _keyed_items(PROMPT_PROFILE_REGISTRY_PATH, "prompts")
    output_schemas = _keyed_items(OUTPUT_SCHEMA_REGISTRY_PATH, "schemas")
    step_budgets = _keyed_items(STEP_BUDGET_REGISTRY_PATH, "budgets")
    system_purposes = _system_purposes()
    operations = _operations()

    referenced_profiles = {cast(str, operation["generatorProfile"]) for operation in operations}
    referenced_profiles.update(
        cast(str, reviewer)
        for operation in operations
        for reviewer in operation["reviewPolicy"]["reviewerProfiles"]
    )
    referenced_output_schemas = {cast(str, operation["outputSchema"]) for operation in operations}
    referenced_output_schemas.update(
        cast(str, operation["reviewPolicy"]["reviewerOutputSchema"])
        for operation in operations
        if "reviewerOutputSchema" in operation["reviewPolicy"]
    )
    referenced_profiles.update(
        cast(str, system_purpose["modelProfile"])
        for system_purpose in system_purposes.values()
    )
    referenced_profiles.update(RETAINED_EXECUTION_PROFILE_KEYS)
    referenced_output_schemas.update(
        cast(str, system_purpose["outputSchema"])
        for system_purpose in system_purposes.values()
    )
    referenced_output_schemas.update(RETAINED_OUTPUT_SCHEMA_KEYS)
    referenced_step_budgets = {
        cast(str, system_purpose["stepBudgetProfile"])
        for system_purpose in system_purposes.values()
    }
    for operation in operations:
        generator_step_budget = operation.get("generatorStepBudgetProfile")
        if generator_step_budget is not None:
            referenced_step_budgets.add(cast(str, generator_step_budget))
        reviewer_budget_profiles = operation["reviewPolicy"].get(
            "reviewerStepBudgetProfiles", {}
        )
        referenced_step_budgets.update(
            cast(dict[str, str], reviewer_budget_profiles).values()
        )

    assert set(profiles) == referenced_profiles
    assert set(output_schemas) == referenced_output_schemas
    assert set(step_budgets) == referenced_step_budgets | {
        "step_budget.system.protocol_correction.v1"
    }
    for profile in profiles.values():
        _assert_key_version(profile)
        assert set(profile) == {
            "key",
            "version",
            "supported",
            "reasoningMode",
            "purpose",
            "promptProfile",
            "deploymentProfileKey",
        }
        prompt = prompts[profile["promptProfile"]]
        deployment = deployments[profile["deploymentProfileKey"]]
        assert prompt["purpose"] == profile["purpose"]
        assert deployment["purpose"] == profile["purpose"]
        if profile["supported"]:
            assert prompt["supported"] is True
            assert deployment["supported"] is True
        forbidden_names = {"apiKey", "baseUrl", "model", "provider", "secret", "token"}
        assert not (set(profile) & forbidden_names), "Profile Registry 禁止保存模型密钥或部署详情"

    for output_schema in output_schemas.values():
        _assert_key_version(output_schema)

    assert set(prompts) == {profile["promptProfile"] for profile in profiles.values()}
    assert set(deployments) == {
        profile["deploymentProfileKey"] for profile in profiles.values()
    }
    for prompt in prompts.values():
        _assert_key_version(prompt)
        assert prompt["sha256"] == hashlib.sha256(
            prompt["systemPrompt"].encode("utf-8")
        ).hexdigest()
        assert not ({"apiKey", "baseUrl", "model", "provider", "secret", "token"} & set(prompt))

    for step_budget in step_budgets.values():
        _assert_key_version(step_budget)

    forbidden_deployment_names = {"apiKey", "baseUrl", "secret", "token"}
    for deployment in deployments.values():
        _assert_key_version(deployment)
        assert not (set(deployment) & forbidden_deployment_names)
        allowed_models = deployment["allowedModels"]
        assert bool(allowed_models) is deployment["supported"]
        identities = set()
        for allowed in allowed_models:
            assert set(allowed) == {
                "provider",
                "model",
                "transportProfile",
                "endpointProfile",
                "structuredOutputRoute",
                "capabilityVersion",
                "reasoningMode",
                "supportsRequestIdempotency",
                "allowedEnvironments",
                "pricingVersion",
                "billable",
            }
            assert allowed["pricingVersion"].endswith(".v1")
            identity = (
                allowed["provider"],
                allowed["model"],
                allowed["transportProfile"],
                allowed["endpointProfile"],
                allowed["structuredOutputRoute"],
                allowed["capabilityVersion"],
                allowed["reasoningMode"],
                allowed["supportsRequestIdempotency"],
            )
            assert identity not in identities
            identities.add(identity)
            if allowed["provider"] == "fake":
                assert "production" not in allowed["allowedEnvironments"]
            if "production" in allowed["allowedEnvironments"]:
                assert allowed["endpointProfile"] == (
                    "endpoint.deepseek-strict-official.v1"
                    if deployment["key"] == "deployment.quality.consistency.v2"
                    else "endpoint.deepseek-official.v1"
                )
            if allowed["transportProfile"] == "transport.deepseek-v4.v1":
                assert allowed["structuredOutputRoute"] == (
                    "quality_strict_tool_v1"
                    if deployment["key"] == "deployment.quality.consistency.v2"
                    else "plain_text_v1"
                    if deployment["key"] == "deployment.style.portrait.v2"
                    else "chat_json_output_v1"
                )


def test_every_registered_output_schema_is_strict_hash_bound_and_honest() -> None:
    registry = _read_json(OUTPUT_SCHEMA_REGISTRY_PATH)
    assert registry["hashAlgorithm"] == EXECUTION_HASH_ALGORITHM
    for item in _keyed_items(OUTPUT_SCHEMA_REGISTRY_PATH, "schemas").values():
        schema = item["jsonSchema"]
        assert isinstance(schema, dict)
        assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
        assert schema["type"] == "object"
        assert schema["additionalProperties"] is False
        assert isinstance(schema["required"], list)
        assert isinstance(schema["properties"], dict)
        assert set(schema["required"]) <= set(schema["properties"])
        assert item["sha256"] == _canonical_sha256(schema)
        jsonschema_rs.validator_for(schema)

        if not item["supported"]:
            assert schema["required"] == []
            assert schema["properties"] == {}, (
                f"{item['key']} 尚未支持，不能用占位业务字段伪装可执行"
            )


def test_agent_updates_v2_schema_is_generated_without_changing_v1_placeholder() -> None:
    outputs = _keyed_items(OUTPUT_SCHEMA_REGISTRY_PATH, "schemas")
    legacy = outputs["output.agent_updates.v1"]
    assert legacy == {
        "key": "output.agent_updates.v1",
        "version": 1,
        "supported": False,
        "purpose": "generation",
        "sha256": "7cce9970b1299f7789482edd63b456ed5edd6cb79dd6d9be98e076866db957e5",
        "jsonSchema": {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "additionalProperties": False,
            "required": [],
            "properties": {},
        },
    }

    current = outputs["output.agent_updates.v2"]
    assert current["version"] == 2
    assert current["supported"] is True
    assert current["purpose"] == "generation"
    schema = current["jsonSchema"]
    assert schema["required"] == ["summary", "updates"]
    assert set(schema["properties"]) == {"summary", "updates"}
    assert "updatesSha256" not in schema["properties"]
    assert schema["properties"]["updates"]["additionalProperties"] is False
    character_actions = schema["properties"]["updates"]["properties"]["characters"][
        "items"
    ]["anyOf"]
    assert [branch["properties"]["action"]["const"] for branch in character_actions] == [
        "create",
        "update",
        "delete",
    ]
    assert all(branch["additionalProperties"] is False for branch in character_actions)

    def assert_no_generator_annotations(node: object) -> None:
        if not isinstance(node, dict):
            return
        assert not ({"$defs", "$ref", "title", "description", "default"} & set(node))
        for name, child in node.get("properties", {}).items():
            assert isinstance(name, str)
            assert_no_generator_annotations(child)
        assert_no_generator_annotations(node.get("items"))
        for keyword in ("anyOf", "allOf", "oneOf"):
            for child in node.get(keyword, []):
                assert_no_generator_annotations(child)
        for keyword in ("if", "then", "else"):
            assert_no_generator_annotations(node.get(keyword))

    assert_no_generator_annotations(schema)


def test_agent_updates_step_schema_is_closed_and_requests_only_bounded_sources() -> None:
    step = _keyed_items(OUTPUT_SCHEMA_REGISTRY_PATH, "schemas")[
        "output.agent_updates_step.v1"
    ]
    assert step["version"] == 1
    assert step["supported"] is True
    assert step["purpose"] == "generation"

    schema = step["jsonSchema"]
    assert schema["required"] == []
    assert set(schema["properties"]) == {"summary", "updates", "evidenceRequest"}
    assert schema["anyOf"] == [
        {"required": ["summary", "updates"], "maxProperties": 2},
        {"required": ["evidenceRequest"], "maxProperties": 1},
    ]
    request = schema["properties"]["evidenceRequest"]
    assert request["minItems"] == 1
    assert request["maxItems"] == 100
    need = request["items"]
    assert need["additionalProperties"] is False
    assert need["required"] == ["resourceType", "resourceId", "purposeCode"]
    assert set(need["properties"]["resourceType"]["enum"]) == {
        "character",
        "location",
        "item",
        "faction",
        "glossary",
        "character_experience",
        "outline_node",
        "foreshadowing",
        "reference",
        "outline_content",
        "world_setting",
        "story_background",
        "chapter_reference",
        "outline_tree",
    }
    assert need["properties"]["purposeCode"]["enum"] == [
        "target",
        "delete_impact",
        "replace_tree",
    ]
    assert need["allOf"] == [
        {
            "if": {"properties": {"resourceType": {"const": "outline_tree"}}},
            "then": {"properties": {"purposeCode": {"const": "replace_tree"}}},
            "else": {
                "properties": {
                    "purposeCode": {"enum": ["target", "delete_impact"]}
                }
            },
        },
        {
            "if": {"properties": {"purposeCode": {"const": "delete_impact"}}},
            "then": {
                "properties": {
                    "resourceType": {
                        "enum": ["character", "location", "faction", "outline_node"]
                    }
                }
            },
        },
    ]


def test_short_medium_v2_assets_are_enabled_and_keep_placeholders() -> None:
    purposes = _system_purposes()
    short_operations = {key for key in EXPECTED_OPERATION_KEYS if key.startswith("short_medium.")}
    assert short_operations <= set(purposes["summarize_evidence"]["parentOperations"])
    assert not short_operations & set(purposes["protocol_correction"]["parentOperations"])
    assert purposes["protocol_correction"]["supported"] is True
    assert purposes["protocol_correction"]["parentOperations"] == ["quality.consistency"]
    operations = {operation["key"]: operation for operation in _operations()}
    profiles = _keyed_items(PROFILE_REGISTRY_PATH, "profiles")
    outputs = _keyed_items(OUTPUT_SCHEMA_REGISTRY_PATH, "schemas")
    cases = (
        ("generate_outline", "plot.short_medium_outline", "outline", "content"),
        ("generate_manuscript", "writer.short_medium_manuscript", "segment", "content"),
        ("replace_selection", "writer.short_medium_selection", "replacement", "replacement"),
        ("full_check", "quality.short_medium_full_check", "check_report", "text"),
    )
    for name, profile, schema, field in cases:
        operation = operations["short_medium." + name]
        assert operation["v2Enabled"] is True
        assert operation["generatorProfile"] == profile + ".v2"
        assert operation["generatorStepBudgetProfile"] == (
            f"step_budget.short_medium.{name}.generator.v2"
        )
        assert operation["reviewPolicy"]["mode"] == "none"
        assert operation["reviewPolicy"]["reviewerProfiles"] == []
        assert operation["runBudgetProfile"]["maxProtocolCorrectionSteps"] == 0
        old_purpose = "evaluation" if name == "full_check" else "generation"
        assert profiles[profile + ".v1"] == {
            "key": profile + ".v1", "version": 1, "supported": False,
            "reasoningMode": "disabled" if name == "full_check" else "bounded",
            "purpose": old_purpose,
            "promptProfile": f"prompt.unavailable.{old_purpose}.v1",
            "deploymentProfileKey": f"deployment.unavailable.{old_purpose}.v1",
        }
        assert profiles[profile + ".v2"]["purpose"] == "generation"
        old_schema = "segment_manifest" if name == "generate_manuscript" else schema
        retained = outputs[f"output.short_medium_{old_schema}.v1"]
        assert retained["supported"] is False
        assert retained["sha256"] == (
            "7cce9970b1299f7789482edd63b456ed5edd6cb79dd6d9be98e076866db957e5"
        )
        output = outputs[operation["outputSchema"]]
        assert output["purpose"] == "generation"
        assert output["supported"] is True
        assert output["jsonSchema"]["required"] == [field]
        assert output["jsonSchema"]["properties"] == {field: {"minLength": 1, "type": "string"}}
        assert output["jsonSchema"]["additionalProperties"] is False


def test_structured_updates_business_enabled_assets_keep_complete_and_retained_contracts() -> None:
    operations = {operation["operation"]: operation for operation in _operations()}
    profiles = _keyed_items(PROFILE_REGISTRY_PATH, "profiles")
    prompts = _keyed_items(PROMPT_PROFILE_REGISTRY_PATH, "prompts")
    deployments = _keyed_items(DEPLOYMENT_PROFILE_REGISTRY_PATH, "profiles")
    outputs = _keyed_items(OUTPUT_SCHEMA_REGISTRY_PATH, "schemas")
    budgets = _keyed_items(STEP_BUDGET_REGISTRY_PATH, "budgets")
    cases = (
        ("create_lore", "lore.generator", "consistency"),
        ("revise_lore", "lore.reviser", "consistency"),
        ("create_outline", "plot.outline_generator", "editorial"),
        ("revise_outline", "plot.outline_reviser", "editorial"),
        ("manage_foreshadowing", "plot.foreshadowing", "consistency"),
    )
    for operation_name, generator_name, reviewer_name in cases:
        operation = operations[operation_name]
        assert operation["v2Enabled"] is True
        assert operation["generatorProfile"] == generator_name + ".v3"
        assert operation["outputSchema"] == "output.agent_updates_step.v1"
        assert operation["applyHandler"] == "apply.agent_updates.v1"
        generator = profiles[operation["generatorProfile"]]
        assert generator["supported"] is True
        assert generator["reasoningMode"] == "bounded"
        assert generator["version"] == 3
        assert profiles[generator_name + ".v1"] == {
            "key": generator_name + ".v1",
            "version": 1,
            "supported": False,
            "reasoningMode": "bounded",
            "purpose": "generation",
            "promptProfile": "prompt.unavailable.generation.v1",
            "deploymentProfileKey": "deployment.unavailable.generation.v1",
        }
        v2_profile = profiles[generator_name + ".v2"]
        v2_prompt = prompts["prompt." + generator_name + ".v2"]
        v2_deployment = deployments["deployment." + generator_name + ".v2"]
        assert (
            _canonical_sha256(v2_profile),
            _canonical_sha256(v2_prompt),
            _canonical_sha256(v2_deployment),
        ) == AGENT_UPDATES_V2_ASSET_SHA256[generator_name]
        assert generator == v2_profile | {
            "key": generator_name + ".v3",
            "version": 3,
            "promptProfile": "prompt." + generator_name + ".v3",
            "deploymentProfileKey": "deployment." + generator_name + ".v3",
        }
        prompt = prompts[generator["promptProfile"]]
        assert prompt["version"] == 3
        assert prompt["supported"] is True
        assert prompt["purpose"] == "generation"
        assert "两种互斥对象之一" in prompt["systemPrompt"]
        assert "不得同时返回 summary、updates 或半份候选" in prompt["systemPrompt"]
        assert "agent_updates_index 冻结名录中已有的真实 ID" in prompt["systemPrompt"]
        assert "三种单例的 resourceId 只能是当前 evidenceBundle 绑定的 novelId" in prompt[
            "systemPrompt"
        ]
        assert "resourceType=outline_tree、resourceId=该 novelId、purposeCode=replace_tree" in (
            prompt["systemPrompt"]
        )
        assert "purposeCode 仅可为 target、delete_impact、replace_tree" in prompt[
            "systemPrompt"
        ]
        assert "不得请求 SQL、路径、正文范围、全 workspace" in prompt["systemPrompt"]
        deployment = deployments[generator["deploymentProfileKey"]]
        assert deployment == v2_deployment | {
            "key": "deployment." + generator_name + ".v3",
            "version": 3,
        }
        review = operation["reviewPolicy"]
        reviewer_key = f"reviewer.agent_updates_{reviewer_name}.v1"
        assert review["reviewerProfiles"] == [reviewer_key]
        assert review["rubricVersion"] == "rubric.agent_updates.review.v1"
        assert review["onUnavailable"] == "awaiting_user"
        assert review["maxAutomaticRevisions"] == 1
        assert profiles[reviewer_key]["reasoningMode"] == "disabled"
        assert "candidateRange 必须为 null" in prompts[
            profiles[reviewer_key]["promptProfile"]
        ]["systemPrompt"]
        finding = outputs[review["reviewerOutputSchema"]]["jsonSchema"]["properties"][
            "findings"
        ]["items"]
        assert "candidatePatch" not in finding["properties"]
        generator_budget = budgets[operation["generatorStepBudgetProfile"]]["budget"]
        reviewer_budget = budgets[review["reviewerStepBudgetProfiles"][reviewer_key]][
            "budget"
        ]
        assert generator_budget["maxModelCalls"] == reviewer_budget["maxModelCalls"] == 1
        assert reviewer_budget["maxReasoningTokens"] == 0
        for budget in (generator_budget, reviewer_budget):
            assert budget["maxInputTokens"] == budget["maxPromptCacheMissTokens"]
        for field in AGGREGATE_STEP_BUDGET_FIELDS:
            assert 2 * (generator_budget[field] + reviewer_budget[field]) <= operation[
                "runBudgetProfile"
            ][field]


def test_system_purposes_are_language_neutral_closed_and_honest() -> None:
    operations = {operation["key"]: operation for operation in _operations()}
    profiles = _keyed_items(PROFILE_REGISTRY_PATH, "profiles")
    output_schemas = _keyed_items(OUTPUT_SCHEMA_REGISTRY_PATH, "schemas")
    step_budgets = _keyed_items(STEP_BUDGET_REGISTRY_PATH, "budgets")
    system_purposes = _system_purposes()

    assert frozenset(system_purposes) == EXPECTED_SYSTEM_PURPOSES
    forbidden_names = {"apiKey", "baseUrl", "model", "prompt", "provider", "secret", "token"}
    for purpose, definition in system_purposes.items():
        assert not (set(definition) & forbidden_names), (
            f"{purpose} 禁止保存 prompt、供应商、模型或密钥"
        )

        profile = profiles[definition["modelProfile"]]
        output_schema = output_schemas[definition["outputSchema"]]
        step_budget = step_budgets[definition["stepBudgetProfile"]]
        dependencies_supported = (
            profile["supported"]
            and output_schema["supported"]
            and step_budget["supported"]
        )
        assert definition["supported"] is dependencies_supported

        workflows = set(definition["workflows"])
        parent_operations = definition["parentOperations"]
        if purpose == "resolve_intent":
            assert parent_operations == [], "意图未解析时不得伪造父 Operation"
        else:
            assert parent_operations, f"{purpose} 必须声明适用的父 Operation"
        for operation_key in parent_operations:
            assert operation_key in operations
            assert operations[operation_key]["workflow"] in workflows


def test_step_budget_registry_matches_execution_step_budget_boundaries() -> None:
    for profile in _keyed_items(STEP_BUDGET_REGISTRY_PATH, "budgets").values():
        budget = profile["budget"]
        assert set(budget) == (
            STEP_POSITIVE_BUDGET_LIMIT_FIELDS
            | STEP_NON_NEGATIVE_BUDGET_LIMIT_FIELDS
            | {"maxModelCalls"}
        )
        assert budget["maxModelCalls"] == 1
        for field in STEP_POSITIVE_BUDGET_LIMIT_FIELDS:
            value = budget[field]
            assert isinstance(value, int) and not isinstance(value, bool) and value > 0
        for field in STEP_NON_NEGATIVE_BUDGET_LIMIT_FIELDS:
            value = budget[field]
            assert isinstance(value, int) and not isinstance(value, bool) and value >= 0

        assert budget["maxPromptCacheMissTokens"] <= budget["maxInputTokens"]
        assert (
            budget["maxReasoningTokens"] + budget["maxVisibleOutputTokens"]
            <= budget["maxCompletionTokens"]
        )
        assert budget["maxProviderRetries"] <= 2
        assert budget["maxProtocolCorrections"] <= 1


def test_execution_hash_vectors_are_shared_and_stable() -> None:
    fixture = _read_json(HASH_VECTORS_PATH)
    assert fixture["algorithm"] == EXECUTION_HASH_ALGORITHM
    vectors = fixture["vectors"]
    assert isinstance(vectors, list) and vectors
    for vector in vectors:
        assert isinstance(vector, dict)
        canonical = canonical_execution_json_bytes(vector["value"])
        assert canonical.decode("utf-8") == vector["canonicalUtf8"]
        assert hashlib.sha256(canonical).hexdigest() == vector["sha256"]


def test_enabled_operation_has_complete_executable_profiles_and_output_schema() -> None:
    profiles = _keyed_items(PROFILE_REGISTRY_PATH, "profiles")
    deployments = _keyed_items(DEPLOYMENT_PROFILE_REGISTRY_PATH, "profiles")
    prompts = _keyed_items(PROMPT_PROFILE_REGISTRY_PATH, "prompts")
    output_schemas = _keyed_items(OUTPUT_SCHEMA_REGISTRY_PATH, "schemas")
    enabled = [operation for operation in _operations() if operation["v2Enabled"]]

    assert [operation["key"] for operation in enabled] == [
        "long_serial.answer_question",
        "long_serial.create_lore",
        "long_serial.revise_lore",
        "long_serial.create_outline",
        "long_serial.revise_outline",
        "long_serial.plan_chapter",
        "long_serial.write_chapter",
        "long_serial.rewrite_scene",
        "long_serial.rewrite_chapter_selection",
        "long_serial.rewrite_outline_selection",
        "long_serial.review_chapter",
        "long_serial.manage_foreshadowing",
        "short_medium.generate_outline",
        "short_medium.generate_manuscript",
        "short_medium.replace_selection",
        "short_medium.full_check",
        "quality.consistency",
        "style.portrait",
    ]
    for operation in enabled:
        assert operation["developmentOnly"] is False
        generator = profiles[operation["generatorProfile"]]
        assert generator["supported"] is True
        assert generator["purpose"] == "generation"
        expected_reasoning = (
            "disabled"
            if operation["key"]
            in {
                "long_serial.answer_question",
                "long_serial.review_chapter",
                "short_medium.full_check",
                "quality.consistency",
                "style.portrait",
            }
            else "bounded"
        )
        assert generator["reasoningMode"] == expected_reasoning
        assert generator["deploymentProfileKey"]
        generator_deployment = deployments[generator["deploymentProfileKey"]]
        assert generator_deployment["supported"] is True
        assert {item["reasoningMode"] for item in generator_deployment["allowedModels"]} == {
            generator["reasoningMode"]
        }

        reviewers = [profiles[key] for key in operation["reviewPolicy"]["reviewerProfiles"]]
        if operation["reviewPolicy"]["mode"] == "none":
            assert reviewers == []
        else:
            assert reviewers
        assert all(profile["supported"] is True for profile in reviewers)
        assert all(profile["purpose"] == "review" for profile in reviewers)
        assert all(profile["reasoningMode"] == "disabled" for profile in reviewers)
        assert all(profile["deploymentProfileKey"] for profile in reviewers)
        assert all(
            deployments[profile["deploymentProfileKey"]]["supported"] is True
            for profile in reviewers
        )

        if reviewers:
            reviewer_output_schema = output_schemas[
                operation["reviewPolicy"]["reviewerOutputSchema"]
            ]
            assert reviewer_output_schema["supported"] is True
            assert reviewer_output_schema["purpose"] == "evaluation"
            assert reviewer_output_schema["jsonSchema"]["properties"]
            finding_schema = reviewer_output_schema["jsonSchema"]["properties"][
                "findings"
            ]["items"]
            assert set(finding_schema["required"]) == {
                "dimension",
                "severity",
                "claim",
                "candidateRange",
                "evidence",
                "suggestion",
                "confidence",
            }
            evidence_reference_schema = finding_schema["properties"]["evidence"]["items"]
            assert set(evidence_reference_schema["required"]) == {
                "evidenceItemId",
                "contentSha256",
                "range",
            }
            assert operation["reviewPolicy"]["rubricVersion"].endswith(".v1")
            assert operation["reviewPolicy"]["evidencePolicy"].endswith(".v1")
            assert operation["reviewPolicy"]["lane"] == "interactive"

        output_schema = output_schemas[operation["outputSchema"]]
        assert output_schema["supported"] is True
        assert output_schema["purpose"] == "generation"
        assert output_schema["jsonSchema"]["properties"]
        if operation["key"] == "long_serial.plan_chapter":
            assert output_schema["jsonSchema"]["required"] == [
                "title", "summary", "chapterGoal", "sceneBeats"
            ]
            scene = output_schema["jsonSchema"]["properties"]["sceneBeats"]["items"]
            assert scene["additionalProperties"] is False
            assert scene["required"] == ["goal"]
            assert "order" not in scene["properties"]
            assert "beatCount" not in output_schema["jsonSchema"]["properties"]
        elif operation["key"] in {
            "long_serial.write_chapter",
            "long_serial.rewrite_scene",
        }:
            assert output_schema["jsonSchema"]["required"] == ["summary", "content"]
            assert set(output_schema["jsonSchema"]["properties"]) == {"summary", "content"}
            assert output_schema["jsonSchema"]["properties"]["summary"]["maxLength"] == 1000
            assert "maxLength" not in output_schema["jsonSchema"]["properties"]["content"]
            assert "candidatePatch" not in finding_schema["required"]
            assert finding_schema["properties"]["candidatePatch"]["additionalProperties"] is False
        elif operation["key"] in {
            "long_serial.create_lore", "long_serial.revise_lore", "long_serial.create_outline",
            "long_serial.revise_outline", "long_serial.manage_foreshadowing",
        }:
            schema = output_schema["jsonSchema"]
            assert schema["required"] == []
            assert set(schema["properties"]) == {"summary", "updates", "evidenceRequest"}
            assert schema["anyOf"] == [
                {"required": ["summary", "updates"], "maxProperties": 2},
                {"required": ["evidenceRequest"], "maxProperties": 1},
            ]
            assert schema["additionalProperties"] is False
            assert schema["properties"]["updates"]["additionalProperties"] is False
            assert schema["properties"]["evidenceRequest"]["minItems"] == 1
            assert schema["properties"]["evidenceRequest"]["maxItems"] == 100
        elif operation["key"] == "quality.consistency":
            schema = output_schema["jsonSchema"]
            assert schema["required"] == ["scores", "qualityGate", "issues", "report"]
            assert set(schema["properties"]) == {
                "scores", "qualityGate", "issues", "report", "rewriteBrief",
            }
            assert schema["properties"]["qualityGate"]["enum"] == ["pass", "revise"]
            assert schema["properties"]["issues"]["maxItems"] == 100
            assert schema["properties"]["report"] == {"minLength": 1, "type": "string"}
        elif operation["key"] == "style.portrait":
            schema = output_schema["jsonSchema"]
            assert schema["required"] == ["content"]
            assert schema["properties"] == {"content": {"minLength": 1, "type": "string"}}
            assert schema["additionalProperties"] is False
            assert generator["key"] == "style.portrait.v2"
            assert {
                item["structuredOutputRoute"] for item in generator_deployment["allowedModels"]
            } == {"plain_text_v1"}
            assert operation["runBudgetProfile"]["maxModelCalls"] == 5
            assert operation["runBudgetProfile"]["maxPromptCacheMissTokens"] == 300000
            assert operation["runBudgetProfile"]["maxProtocolCorrectionSteps"] == 0
        elif operation["workflow"] == "short_medium":
            expected_field = {
                "generate_outline": "content",
                "generate_manuscript": "content",
                "replace_selection": "replacement",
                "full_check": "text",
            }[operation["operation"]]
            assert output_schema["jsonSchema"]["required"] == [expected_field]
            assert output_schema["jsonSchema"]["properties"] == {
                expected_field: {"type": "string", "minLength": 1},
            }
            assert output_schema["jsonSchema"]["additionalProperties"] is False
        else:
            expected_output_field = (
                "answer"
                if operation["key"] == "long_serial.answer_question"
                else (
                    "report"
                    if operation["key"] == "long_serial.review_chapter"
                    else "replacement"
                )
            )
            assert output_schema["jsonSchema"]["required"] == [expected_output_field]
            assert set(output_schema["jsonSchema"]["properties"]) == {expected_output_field}
            expected_pattern = (
                "[^\\u0009-\\u000d\\u0020\\u0085\\u00a0\\u1680"
                "\\u2000-\\u200a\\u2028\\u2029\\u202f\\u205f\\u3000\\ufeff]"
                if operation["key"]
                in {
                    "long_serial.rewrite_outline_selection",
                    "long_serial.review_chapter",
                }
                else r"\S"
            )
            assert output_schema["jsonSchema"]["properties"][expected_output_field] == {
                "type": "string",
                "minLength": 1,
                "pattern": expected_pattern,
            }

        prompt_hashes = {
            profiles[operation["generatorProfile"]]["promptProfile"]: prompts[
                profiles[operation["generatorProfile"]]["promptProfile"]
            ]["sha256"],
            **{
                profiles[profile_key]["promptProfile"]: prompts[
                    profiles[profile_key]["promptProfile"]
                ]["sha256"]
                for profile_key in operation["reviewPolicy"]["reviewerProfiles"]
            },
        }
        expected_prompt_count = 1 + len(reviewers)
        assert len(prompt_hashes) == expected_prompt_count
        assert len(set(prompt_hashes.values())) == expected_prompt_count


def test_operation_catalog_budgets_are_explicit_and_bounded() -> None:
    for operation in _operations():
        budget = operation["runBudgetProfile"]
        assert isinstance(budget, dict)
        assert set(budget) == (
            POSITIVE_BUDGET_LIMIT_FIELDS | NON_NEGATIVE_BUDGET_LIMIT_FIELDS | {"profile"}
        )
        for field in POSITIVE_BUDGET_LIMIT_FIELDS:
            value = budget[field]
            assert isinstance(value, int) and not isinstance(value, bool) and value > 0, (
                f"{operation['key']} 的 {field} 必须是正整数"
            )
        for field in NON_NEGATIVE_BUDGET_LIMIT_FIELDS:
            value = budget[field]
            assert isinstance(value, int) and not isinstance(value, bool) and value >= 0, (
                f"{operation['key']} 的 {field} 必须是非负整数"
            )

        assert budget["maxPromptCacheMissTokens"] <= budget["maxInputTokens"]
        assert budget["maxReasoningTokens"] <= budget["maxCompletionTokens"]
        assert budget["maxVisibleOutputTokens"] <= budget["maxCompletionTokens"]
        assert (
            budget["maxReasoningTokens"] + budget["maxVisibleOutputTokens"]
            <= budget["maxCompletionTokens"]
        )


def test_enabled_operation_step_budgets_are_explicit_supported_and_fit_run() -> None:
    profiles = _keyed_items(PROFILE_REGISTRY_PATH, "profiles")
    step_budgets = _keyed_items(STEP_BUDGET_REGISTRY_PATH, "budgets")
    enabled = [operation for operation in _operations() if operation["v2Enabled"]]

    for operation in enabled:
        review_policy = operation["reviewPolicy"]
        reviewer_budget_profiles = review_policy.get("reviewerStepBudgetProfiles", {})
        assert set(reviewer_budget_profiles) == set(review_policy["reviewerProfiles"])

        generator_budget_key = operation["generatorStepBudgetProfile"]
        generator_budget = step_budgets[generator_budget_key]
        assert generator_budget["supported"] is True
        if profiles[operation["generatorProfile"]]["reasoningMode"] == "disabled":
            assert generator_budget["budget"]["maxReasoningTokens"] == 0

        reviewer_budgets = []
        for reviewer_profile_key in review_policy["reviewerProfiles"]:
            reviewer_budget = step_budgets[
                reviewer_budget_profiles[reviewer_profile_key]
            ]
            assert reviewer_budget["supported"] is True
            if profiles[reviewer_profile_key]["reasoningMode"] == "disabled":
                assert reviewer_budget["budget"]["maxReasoningTokens"] == 0
            reviewer_budgets.append(reviewer_budget)

        review_rounds = 1 + review_policy["maxAutomaticRevisions"]
        planned_budgets = [generator_budget["budget"]] * review_rounds
        planned_budgets.extend(
            reviewer_budget["budget"]
            for _ in range(review_rounds)
            for reviewer_budget in reviewer_budgets
        )
        run_budget = operation["runBudgetProfile"]
        for field in AGGREGATE_STEP_BUDGET_FIELDS:
            assert sum(budget[field] for budget in planned_budgets) <= run_budget[field], (
                f"{operation['key']} 的首切 Step 保留量超过 Run {field}"
            )
        assert all(
            budget["maxProviderRetries"] <= run_budget["maxProviderRetriesPerStep"]
            for budget in planned_budgets
        )


def test_system_step_budgets_fit_every_applicable_run_budget() -> None:
    operations = {operation["key"]: operation for operation in _operations()}
    profiles = _keyed_items(PROFILE_REGISTRY_PATH, "profiles")
    step_budgets = _keyed_items(STEP_BUDGET_REGISTRY_PATH, "budgets")

    for purpose, definition in _system_purposes().items():
        step_budget = step_budgets[definition["stepBudgetProfile"]]["budget"]
        profile = profiles[definition["modelProfile"]]
        if profile["reasoningMode"] == "disabled":
            assert step_budget["maxReasoningTokens"] == 0

        parent_keys = definition["parentOperations"]
        if purpose == "resolve_intent":
            workflows = set(definition["workflows"])
            parent_keys = [
                key
                for key, operation in operations.items()
                if operation["workflow"] in workflows
            ]

        for operation_key in parent_keys:
            run_budget = operations[operation_key]["runBudgetProfile"]
            for field in AGGREGATE_STEP_BUDGET_FIELDS:
                assert step_budget[field] <= run_budget[field], (
                    f"{purpose} 的 Step {field} 超过 {operation_key} Run 上限"
                )
            assert (
                step_budget["maxProviderRetries"]
                <= run_budget["maxProviderRetriesPerStep"]
            )
            if purpose == "protocol_correction":
                assert run_budget["maxProtocolCorrectionSteps"] == 1


def test_operation_catalog_locks_critical_budget_policies() -> None:
    operations = {operation["key"]: operation for operation in _operations()}

    for key in NO_THINKING_OPERATION_KEYS:
        assert operations[key]["runBudgetProfile"]["maxReasoningTokens"] == 0

    for key in CHAPTER_DRAFT_OPERATION_KEYS:
        budget = operations[key]["runBudgetProfile"]
        if key in {"long_serial.write_chapter", "long_serial.rewrite_scene"}:
            assert budget["maxPromptCacheMissTokens"] == budget["maxInputTokens"] == 180000
        else:
            assert budget["maxPromptCacheMissTokens"] <= 60000
        assert budget["maxReasoningTokens"] <= 16000
        assert budget["maxVisibleOutputTokens"] <= 24000

    chapter_plan_budget = operations["long_serial.plan_chapter"]["runBudgetProfile"]
    assert chapter_plan_budget["maxPromptCacheMissTokens"] == 120000
    assert chapter_plan_budget["maxPromptCacheMissTokens"] == chapter_plan_budget["maxInputTokens"]
    assert chapter_plan_budget["maxReasoningTokens"] <= 12000
    assert chapter_plan_budget["maxVisibleOutputTokens"] <= 8000

    rag_budget = operations["rag.embedding"]["runBudgetProfile"]
    assert rag_budget["maxCompletionTokens"] == 0
    assert rag_budget["maxReasoningTokens"] == 0
    assert rag_budget["maxVisibleOutputTokens"] == 0
    assert rag_budget["maxProtocolCorrectionSteps"] == 0

    video_budget = operations["video.chapter_cinematic_adaptation_v2"]["runBudgetProfile"]
    assert video_budget["maxModelCalls"] == 5
    assert operations["style.portrait"]["scopeKinds"] == ["user"]


def test_operation_catalog_manifest_hashes_are_stable() -> None:
    manifest = _read_json(MANIFEST_PATH)

    assert manifest["manifestVersion"] == "1"
    assert manifest["catalogVersion"] == _read_json(CATALOG_PATH)["catalogVersion"]
    assert set(manifest) == {
        "manifestVersion",
        "catalogVersion",
        "catalog",
        "schema",
        "profileRegistry",
        "profileRegistrySchema",
        "deploymentProfileRegistry",
        "deploymentProfileRegistrySchema",
        "promptProfileRegistry",
        "promptProfileRegistrySchema",
        "outputSchemaRegistry",
        "outputSchemaRegistrySchema",
        "stepBudgetRegistry",
        "stepBudgetRegistrySchema",
        "systemPurposeRegistry",
        "systemPurposeRegistrySchema",
        "hashVectors",
    }
    for entry_name in (
        "catalog",
        "schema",
        "profileRegistry",
        "profileRegistrySchema",
        "deploymentProfileRegistry",
        "deploymentProfileRegistrySchema",
        "promptProfileRegistry",
        "promptProfileRegistrySchema",
        "outputSchemaRegistry",
        "outputSchemaRegistrySchema",
        "stepBudgetRegistry",
        "stepBudgetRegistrySchema",
        "systemPurposeRegistry",
        "systemPurposeRegistrySchema",
        "hashVectors",
    ):
        entry = manifest[entry_name]
        assert isinstance(entry, dict)
        path = CONTRACT_ROOT / entry["path"]
        actual_sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
        assert actual_sha256 == entry["sha256"], f"{entry_name} SHA-256 已漂移"
