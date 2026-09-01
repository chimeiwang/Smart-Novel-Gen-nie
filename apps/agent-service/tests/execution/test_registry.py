from __future__ import annotations

import ast
import hashlib
import json
import shutil
from dataclasses import FrozenInstanceError
from pathlib import Path
from typing import Any, cast

import pytest
from inkforge_agents.app import create_app
from inkforge_agents.execution import (
    ExecutionOperationDisabledError,
    ExecutionOperationEnvironmentError,
    ExecutionRegistryError,
    load_execution_registry,
    resolve_execution_contract_dir,
)
from inkforge_agents.execution.registry import (
    ExecutionRegistryHashError,
    ExecutionRegistryReferenceError,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
CONTRACT_ROOT = REPOSITORY_ROOT / "contracts" / "agent-execution"
REGISTRY_SOURCE = (
    REPOSITORY_ROOT
    / "apps"
    / "agent-service"
    / "src"
    / "inkforge_agents"
    / "execution"
    / "registry.py"
)


@pytest.fixture
def contract_copy(tmp_path: Path) -> Path:
    target = tmp_path / "agent-execution"
    shutil.copytree(CONTRACT_ROOT, target)
    return target


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return cast(dict[str, Any], value)


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _refresh_manifest_hash(root: Path, entry_name: str) -> None:
    manifest_path = root / "manifest.json"
    manifest = _read_json(manifest_path)
    entry = manifest[entry_name]
    assert isinstance(entry, dict)
    contract_path = root / entry["path"]
    entry["sha256"] = hashlib.sha256(contract_path.read_bytes()).hexdigest()
    _write_json(manifest_path, manifest)


def test_loader_resolves_complete_enabled_long_serial_operations() -> None:
    registry = load_execution_registry(CONTRACT_ROOT, environment="production")
    assert registry.manifest_fingerprint == (
        "52e4eab24f009efd0354b401fa14117d9014edcd73f80ff08a1247c5867153d7"
    )

    resolved = registry.resolve("long_serial", "rewrite_chapter_selection")
    answer = registry.resolve("long_serial", "answer_question")

    assert resolved.operation.key == "long_serial.rewrite_chapter_selection"
    assert resolved.operation.run_budget.max_model_calls == 6
    assert resolved.operation.run_budget.max_provider_retries_per_step == 2
    assert resolved.generator_profile.key == "writer.chapter_selection.v1"
    assert resolved.generator_profile.deployment_profile_key == (
        "deployment.writer.chapter_selection.v1"
    )
    assert resolved.generator_profile.prompt_profile.key == (
        "prompt.writer.chapter_selection.v1"
    )
    assert hashlib.sha256(
        resolved.generator_profile.prompt_profile.system_prompt.encode("utf-8")
    ).hexdigest() == resolved.generator_profile.prompt_profile.sha256
    assert {profile.key for profile in resolved.reviewer_profiles} == {
        "reviewer.consistency.v1",
        "reviewer.editorial.v1",
    }
    assert len(
        {profile.prompt_profile.sha256 for profile in resolved.reviewer_profiles}
    ) == 2
    assert resolved.output_schema.key == "output.chapter_selection_replacement.v1"
    assert resolved.output_schema.json_schema["additionalProperties"] is False
    assert not hasattr(resolved.generator_profile, "api_key")
    assert not hasattr(resolved.generator_profile, "model")
    assert answer.operation.target_kinds == ("chapter",)
    assert answer.operation.scope_kinds == ("chapter",)
    assert answer.operation.mutating is False
    assert answer.operation.review_policy.mode == "none"
    assert answer.generator_profile.key == "editor.answer.v1"
    assert answer.generator_profile.reasoning_mode == "disabled"
    assert answer.generator_profile.prompt_profile.key == "prompt.editor.answer.v1"
    assert answer.generator_profile.deployment_profile_key == "deployment.editor.answer.v1"
    assert answer.generator_step_budget.key == (
        "step_budget.long_serial.answer_question.generator.v1"
    )
    assert answer.generator_step_budget.max_reasoning_tokens == 0
    assert answer.output_schema.key == "output.chat_answer.v1"
    assert answer.output_schema.json_schema_value()["required"] == ["answer"]
    assert answer.reviewer_profiles == ()
    assert answer.reviewer_step_budgets == {}
    assert answer.reviewer_output_schema is None

    with pytest.raises(FrozenInstanceError):
        resolved.operation.v2_enabled = False  # type: ignore[misc]
    with pytest.raises(TypeError):
        cast(Any, registry.operations)["forbidden"] = resolved.operation


def test_deployment_authorization_binds_transport_capability_and_environment() -> None:
    testing = load_execution_registry(CONTRACT_ROOT, environment="test")
    fake = testing.require_authorized_deployment(
        deployment_profile_key="deployment.writer.chapter_selection.v1",
        provider="fake",
        model="fake",
        transport_profile="transport.fake.v1",
        endpoint_profile="endpoint.local-fake.v1",
        structured_output_route="responses_json_schema_v1",
        capability_version="capability.fake.structured-output.v1",
        reasoning_mode="bounded",
        supports_request_idempotency=True,
    )
    assert fake.billable is False
    assert fake.pricing_version == "credit-pricing.v1"

    production = load_execution_registry(CONTRACT_ROOT, environment="production")
    with pytest.raises(ExecutionRegistryReferenceError, match="未被"):
        production.require_authorized_deployment(
            deployment_profile_key="deployment.writer.chapter_selection.v1",
            provider="fake",
            model="fake",
            transport_profile="transport.fake.v1",
            endpoint_profile="endpoint.local-fake.v1",
            structured_output_route="responses_json_schema_v1",
            capability_version="capability.fake.structured-output.v1",
            reasoning_mode="bounded",
            supports_request_idempotency=True,
        )
    deepseek = production.require_authorized_deployment(
        deployment_profile_key="deployment.writer.chapter_selection.v1",
        provider="openai_compatible",
        model="deepseek-v4-flash",
        transport_profile="transport.deepseek-v4.v1",
        endpoint_profile="endpoint.deepseek-official.v1",
        structured_output_route="chat_json_output_v1",
        capability_version="capability.deepseek-v4.chat-json.v1",
        reasoning_mode="bounded",
        supports_request_idempotency=False,
    )
    assert deepseek.billable is True

    with pytest.raises(ExecutionRegistryReferenceError, match="未被"):
        production.require_authorized_deployment(
            deployment_profile_key="deployment.writer.chapter_selection.v1",
            provider="openai_compatible",
            model="deepseek-v4-flash",
            transport_profile="transport.openai-compatible.v1",
            endpoint_profile="endpoint.deepseek-official.v1",
            structured_output_route="chat_json_output_v1",
            capability_version="capability.openai-compatible.structured-output.v1",
            reasoning_mode="bounded",
            supports_request_idempotency=False,
        )


def test_loader_rejects_disabled_and_environment_forbidden_operations() -> None:
    production = load_execution_registry(CONTRACT_ROOT, environment="production")
    with pytest.raises(ExecutionOperationDisabledError):
        production.resolve("long_serial", "review_chapter")
    with pytest.raises(ExecutionOperationEnvironmentError):
        production.resolve("video", "chapter_cinematic_adaptation_v2")

    development = load_execution_registry(CONTRACT_ROOT, environment="dev")
    with pytest.raises(ExecutionOperationDisabledError):
        development.resolve("video", "chapter_cinematic_adaptation_v2")


def test_enabled_no_review_operation_rejects_hidden_reviewer_execution_refs(
    contract_copy: Path,
) -> None:
    catalog_path = contract_copy / "operation-catalog.v1.json"
    catalog = _read_json(catalog_path)
    operation = catalog["operations"][0]
    assert operation["key"] == "long_serial.answer_question"
    operation["reviewPolicy"]["reviewerOutputSchema"] = (
        "output.chapter_review_report.v1"
    )
    _write_json(catalog_path, catalog)
    _refresh_manifest_hash(contract_copy, "catalog")

    with pytest.raises(ExecutionRegistryReferenceError, match="不能冻结 Reviewer"):
        load_execution_registry(contract_copy, environment="test")


def test_loader_uses_explicit_environment_contract_directory(
    contract_copy: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("INKFORGE_EXECUTION_CONTRACT_DIR", str(contract_copy))

    assert resolve_execution_contract_dir() == contract_copy.resolve()
    app = create_app(testing=True)
    assert app.state.execution_registry.resolve(
        "long_serial", "rewrite_chapter_selection"
    ).operation.v2_enabled


def test_loader_rejects_raw_hash_tampering(contract_copy: Path) -> None:
    profile_path = contract_copy / "profile-registry.v1.json"
    profile_path.write_bytes(profile_path.read_bytes() + b"\n")

    with pytest.raises(ExecutionRegistryHashError, match="哈希不一致"):
        load_execution_registry(contract_copy, environment="test")


def test_loader_rejects_missing_catalog_reference_after_valid_raw_hash(
    contract_copy: Path,
) -> None:
    catalog_path = contract_copy / "operation-catalog.v1.json"
    catalog = _read_json(catalog_path)
    operation = catalog["operations"][0]
    operation["generatorProfile"] = "missing.generator.v1"
    _write_json(catalog_path, catalog)
    _refresh_manifest_hash(contract_copy, "catalog")

    with pytest.raises(ExecutionRegistryReferenceError, match="缺失 Profile"):
        load_execution_registry(contract_copy, environment="test")


def test_loader_rejects_duplicate_registry_key_after_valid_raw_hash(
    contract_copy: Path,
) -> None:
    profile_path = contract_copy / "profile-registry.v1.json"
    registry = _read_json(profile_path)
    registry["profiles"].append(dict(registry["profiles"][0]))
    _write_json(profile_path, registry)
    _refresh_manifest_hash(contract_copy, "profileRegistry")

    with pytest.raises(ExecutionRegistryReferenceError, match="重复 key"):
        load_execution_registry(contract_copy, environment="test")


def test_loader_rejects_prompt_text_tampering_even_after_manifest_is_refreshed(
    contract_copy: Path,
) -> None:
    prompt_path = contract_copy / "prompt-profile-registry.v1.json"
    registry = _read_json(prompt_path)
    registry["prompts"][0]["systemPrompt"] += "被篡改"
    _write_json(prompt_path, registry)
    _refresh_manifest_hash(contract_copy, "promptProfileRegistry")

    with pytest.raises(ExecutionRegistryHashError, match="Prompt Profile UTF-8"):
        load_execution_registry(contract_copy, environment="test")


def test_loader_preserves_zero_output_run_budget_without_treating_it_as_step_budget() -> None:
    registry = load_execution_registry(CONTRACT_ROOT, environment="test")

    embedding = registry.operations["rag.embedding"]

    assert embedding.run_budget.max_model_calls == 1
    assert embedding.run_budget.max_completion_tokens == 0
    assert embedding.run_budget.max_reasoning_tokens == 0
    assert embedding.run_budget.max_visible_output_tokens == 0
    assert not hasattr(embedding, "step_budget")


def test_loader_rejects_catalog_that_replaces_run_budget_with_step_budget(
    contract_copy: Path,
) -> None:
    catalog_path = contract_copy / "operation-catalog.v1.json"
    catalog = _read_json(catalog_path)
    operation = catalog["operations"][0]
    operation["stepBudget"] = operation.pop("runBudgetProfile")
    _write_json(catalog_path, catalog)
    _refresh_manifest_hash(contract_copy, "catalog")

    with pytest.raises(ExecutionRegistryError, match="Operation Catalog"):
        load_execution_registry(contract_copy, environment="test")


def test_execution_registry_module_has_no_legacy_runtime_or_tool_imports() -> None:
    tree = ast.parse(REGISTRY_SOURCE.read_text(encoding="utf-8"))
    imported_modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imported_modules.add(node.module)

    assert not any(module.startswith("langgraph") for module in imported_modules)
    assert not any("inkforge_agents.runtime" in module for module in imported_modules)
    assert not any("inkforge_agents.tools" in module for module in imported_modules)
