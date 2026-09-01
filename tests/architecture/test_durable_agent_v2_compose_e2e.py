from pathlib import Path

import yaml

ROOT = Path(__file__).parents[2]
OVERLAY = ROOT / "infra" / "compose.durable-agent-v2-e2e.yaml"
PRODUCTION_COMPOSE = ROOT / "infra" / "compose.yaml"
CONTROL = ROOT / "tests" / "durable_agent_v2_e2e" / "control_app.py"
AGENT_FACTORY = ROOT / "tests" / "durable_agent_v2_e2e" / "agent_app.py"
PROVIDER = ROOT / "tests" / "durable_agent_v2_e2e" / "controlled_provider.py"
RUNNER = ROOT / "tests" / "durable_agent_v2_e2e" / "run_e2e.py"


def _document() -> dict[str, object]:
    value = yaml.safe_load(OVERLAY.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_e2e_compose_is_standalone_local_pg14_and_uses_two_redis_instances() -> None:
    document = _document()
    services = document["services"]
    assert set(services) == {
        "postgres",
        "redis",
        "redis-drain-init",
        "execution-redis",
        "execution-redis-drain-init",
        "e2e-control",
        "agent-service",
        "core-api",
    }
    postgres = services["postgres"]
    assert postgres["image"] == "pgvector/pgvector:0.8.0-pg14"
    assert postgres["environment"]["POSTGRES_DB"] == "novelwriterdev"
    assert any("novelwriterdev-schema.sql" in value for value in postgres["volumes"])
    assert any("20260831_durable_agent_execution.sql" in value for value in postgres["volumes"])

    agent = services["agent-service"]
    assert agent["environment"]["REDIS_URL"] == "redis://redis:6379/0"
    assert agent["environment"]["EXECUTION_REDIS_URL"] == (
        "redis://execution-redis:6379/0"
    )
    assert services["execution-redis"]["networks"] == ["execution_net"]
    assert "execution_redis_e2e_data:/data" in services["execution-redis"]["volumes"]
    assert "execution_net" not in services["redis"]["networks"]

    ordinary_init = services["redis-drain-init"]
    execution_init = services["execution-redis-drain-init"]
    assert ordinary_init["restart"] == "no"
    assert execution_init["restart"] == "no"
    assert ordinary_init["depends_on"]["redis"]["condition"] == "service_healthy"
    assert execution_init["depends_on"]["execution-redis"]["condition"] == (
        "service_healthy"
    )
    ordinary_command = " ".join(ordinary_init["command"])
    execution_command = " ".join(execution_init["command"])
    assert "DBSIZE" in ordinary_command
    assert "durable_agent_v1_drain_index_initialize.lua" in ordinary_command
    assert "inkforge:runs:drain:index-version" in ordinary_command
    assert "DBSIZE" in execution_command
    assert "durable_agent_v2_drain_index_initialize.lua" in execution_command
    assert "inkforge:executions:drain:index-version" in execution_command
    assert services["agent-service"]["depends_on"]["redis-drain-init"][
        "condition"
    ] == "service_completed_successfully"
    assert services["agent-service"]["depends_on"]["execution-redis-drain-init"][
        "condition"
    ] == "service_completed_successfully"


def test_e2e_only_core_and_control_publish_loopback_ports() -> None:
    services = _document()["services"]
    for name, service in services.items():
        ports = service.get("ports", [])
        if name in {"core-api", "e2e-control"}:
            assert len(ports) == 1
            assert ports[0].startswith("127.0.0.1:")
        else:
            assert ports == []


def test_e2e_fresh_v2_uses_exact_allowlist_and_read_only_release_guard() -> None:
    core = _document()["services"]["core-api"]
    environment = core["environment"]
    assert environment["DURABLE_AGENT_EXECUTION_ROUTE_MODE"] == (
        "${E2E_DURABLE_ROUTE_MODE:-off}"
    )
    assert environment["DURABLE_AGENT_EXECUTION_USER_ALLOWLIST"] == (
        "${E2E_DURABLE_USER_ID:-bootstrap-disabled-user}"
    )
    assert environment["DURABLE_AGENT_EXECUTION_NOVEL_ALLOWLIST"] == (
        "${E2E_DURABLE_NOVEL_ID:-bootstrap-disabled-novel}"
    )
    assert environment["DURABLE_AGENT_RELEASE_GUARD_PATH"] == (
        "/run/inkforge-release-guard/guard.json"
    )
    guard_mounts = [
        value for value in core["volumes"] if "release-guard" in value
    ]
    assert guard_mounts == [
        "${E2E_RELEASE_GUARD_DIR:?必须配置临时 release guard 目录}:"
        "/run/inkforge-release-guard:ro"
    ]
    source = RUNNER.read_text(encoding="utf-8")
    assert '"state": state' in source
    assert '"executionManifestFingerprint"' in source
    assert '"E2E_DURABLE_ROUTE_MODE": "allowlist"' in source
    assert source.index("acceptance.bootstrap()") < source.index(
        "stack.activate_durable_scope("
    )


def test_e2e_agent_uses_test_only_injected_provider_without_real_credentials() -> None:
    services = _document()["services"]
    agent = services["agent-service"]
    environment = agent["environment"]
    assert environment["ENVIRONMENT"] == "test"
    assert environment["MODEL_PROVIDER"] == "fake"
    assert environment["OPENAI_API_KEY"] == ""
    assert environment["E2E_EXECUTION_CONTROL_URL"] == "http://e2e-control:8090"
    assert "E2E_EXECUTION_CONTROL_TOKEN" in environment
    assert "agent_app:create_app" in agent["command"]
    assert environment["CORE_API_URL"] == "http://e2e-control:8090"
    source = "\n".join(
        path.read_text(encoding="utf-8") for path in (AGENT_FACTORY, PROVIDER)
    )
    assert "ControlledFakeModelProvider" in source
    assert "FakeModelProvider" in source
    for forbidden in (
        "api.deepseek.com",
        "inkforge.cn",
        "novelwriterdev@",
        "novelwriter@",
        "sleep(",
    ):
        assert forbidden not in source


def test_callback_proxy_records_complete_identity_and_can_drop_only_after_forward() -> None:
    source = CONTROL.read_text(encoding="utf-8")
    for field in (
        'identity["runId"]',
        'identity["stepId"]',
        'identity["jobId"]',
        'identity["fencingToken"]',
        'identity["requestHash"]',
        'identity["resultHash"]',
    ):
        assert field in source
    assert "drop_after_forward_once" in source
    assert source.index("await core_http.put") < source.index(
        'action="dropped_after_forward"'
    )
    assert "held_before_forward" in source
    assert "aborted_before_forward" in source


def test_execution_submit_proxy_records_only_safe_422_shape() -> None:
    services = _document()["services"]
    assert services["core-api"]["environment"]["AGENT_SERVICE_URL"] == (
        "http://e2e-control:8090"
    )
    assert services["e2e-control"]["environment"]["E2E_AGENT_UPSTREAM"] == (
        "http://agent-service:8001"
    )
    source = CONTROL.read_text(encoding="utf-8")
    assert 'validation_errors.append({"loc": location, "type": error_type})' in source
    assert "body_sha256 TEXT NOT NULL" in source
    assert "request_body" not in source
    assert "validation_input" not in source
    assert "validation_message" not in source
    assert services["e2e-control"]["environment"]["ENVIRONMENT"] == "test"
    assert 'environment != "test"' in source
    assert '/internal/v1/health/{health_kind}' in source
    assert 'Literal["live", "ready"]' in source
    assert '@app.post("/internal/v1/runs")' in source
    assert "response_headers(upstream_response)" in source


def test_production_compose_and_agent_openapi_have_no_e2e_control_plane() -> None:
    production = PRODUCTION_COMPOSE.read_text(encoding="utf-8")
    assert "E2E_EXECUTION_CONTROL" not in production
    assert "e2e-control" not in production
    assert "control_app" not in production
    for openapi in (
        ROOT / "contracts" / "agent-service" / "openapi-java-baseline.json",
        ROOT / "contracts" / "agent-service" / "openapi-python-baseline.json",
    ):
        source = openapi.read_text(encoding="utf-8")
        assert "/control/" not in source
        assert "E2E execution" not in source


def test_e2e_services_keep_non_root_read_only_and_resource_limits() -> None:
    services = _document()["services"]
    total_cpus = 0.0
    total_memory_mib = 0
    for _name, service in services.items():
        assert service["read_only"] is True
        assert service["user"].split(":")[0] != "0"
        assert "no-new-privileges:true" in service["security_opt"]
        if _name.endswith("-drain-init"):
            assert service["restart"] == "no"
            assert "healthcheck" not in service
        else:
            assert "healthcheck" in service
        total_cpus += float(service["cpus"])
        total_memory_mib += int(service["mem_limit"].removesuffix("m"))
    # 该值只约束容器，不宣称已经证明含宿主开销的 2 核 2 GB 整机稳定性。
    assert total_cpus <= 2
    assert total_memory_mib <= 2048


def test_agent_only_rebuild_has_source_hash_preflight_before_stack_start() -> None:
    source = RUNNER.read_text(encoding="utf-8")
    assert 'self.run(["build", "agent-service"]' in source
    assert '"--network",\n                "none"' in source
    assert '"execution/journal.py"' in source
    assert '"queue/repository.py"' in source
    assert source.index('report["images"] = stack.image_facts()') < source.index(
        "stack.start(build="
    )


def test_e2e_http_clients_never_inherit_host_proxy_environment() -> None:
    sources = "\n".join(
        path.read_text(encoding="utf-8") for path in (RUNNER, CONTROL, PROVIDER)
    )
    assert sources.count("trust_env=False") >= 5


def test_happy_path_keeps_fake_billing_audit_and_scrubs_failure_evidence() -> None:
    source = RUNNER.read_text(encoding="utf-8")
    for field in (
        '"reservationCount"',
        '"reservedMicros"',
        '"chargedMicros"',
        '"settledAtPresent"',
        '"usageMatchesStep"',
        '"tokenUsageCount"',
        '"requestBindingMatches"',
        '"tokenFieldsMatchUsage"',
        '"creditLedgerCount"',
        '"balanceDeltaMicros"',
        '"balanceUnchanged"',
    ):
        assert field in source
    assert 'reservation.get("status") == "settled"' in source
    assert 'reservation.get("reservedMicros") == 0' in source
    assert 'reservation.get("chargedMicros") == 0' in source
    assert 'billing.get("tokenUsageCount") == 1' in source
    assert 'billing.get("creditLedgerCount") == 0' in source
    assert 'self.safe_diagnostics["billing"] = billing' in source
    assert source.index('self.safe_diagnostics["billing"] = billing') < source.index(
        "return value\n\n    def assert_scenario_facts"
    )
    assert '"reservationCount",\n            "tokenUsageCount"' not in source
