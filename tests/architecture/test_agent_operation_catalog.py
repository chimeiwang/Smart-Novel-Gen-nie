from __future__ import annotations

import hashlib
import json
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
        "long_serial.rewrite_chapter_selection",
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
    referenced_output_schemas.update(
        cast(str, system_purpose["outputSchema"])
        for system_purpose in system_purposes.values()
    )
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
    assert set(step_budgets) == referenced_step_budgets
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
                assert allowed["endpointProfile"] == "endpoint.deepseek-official.v1"
            if allowed["transportProfile"] == "transport.deepseek-v4.v1":
                assert allowed["structuredOutputRoute"] == "chat_json_output_v1"


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
        assert set(schema["required"]) == set(schema["properties"])
        assert item["sha256"] == _canonical_sha256(schema)
        jsonschema_rs.validator_for(schema)

        if not item["supported"]:
            assert schema["required"] == []
            assert schema["properties"] == {}, (
                f"{item['key']} 尚未支持，不能用占位业务字段伪装可执行"
            )


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
        "long_serial.rewrite_chapter_selection",
    ]
    for operation in enabled:
        assert operation["developmentOnly"] is False
        generator = profiles[operation["generatorProfile"]]
        assert generator["supported"] is True
        assert generator["purpose"] == "generation"
        expected_reasoning = (
            "disabled"
            if operation["key"] == "long_serial.answer_question"
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
        if operation["key"] == "long_serial.answer_question":
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
        expected_output_field = (
            "answer"
            if operation["key"] == "long_serial.answer_question"
            else "replacement"
        )
        assert output_schema["jsonSchema"]["required"] == [expected_output_field]
        assert set(output_schema["jsonSchema"]["properties"]) == {expected_output_field}
        assert output_schema["jsonSchema"]["properties"][expected_output_field] == {
            "type": "string",
            "minLength": 1,
            "pattern": r"\S",
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
        expected_prompt_count = 1 if not reviewers else 3
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
        assert budget["maxPromptCacheMissTokens"] <= 60000
        assert budget["maxReasoningTokens"] <= 16000
        assert budget["maxVisibleOutputTokens"] <= 24000

    chapter_plan_budget = operations["long_serial.plan_chapter"]["runBudgetProfile"]
    assert chapter_plan_budget["maxPromptCacheMissTokens"] <= 40000
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
