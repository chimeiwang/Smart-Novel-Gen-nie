import re
from pathlib import Path

import yaml

ROOT = Path(__file__).parents[2]
COMPOSE = ROOT / "infra" / "compose.yaml"
CORE_DOCKERFILE = ROOT / "infra" / "docker" / "core-api.Dockerfile"
PYTHON_ROLLBACK_COMPOSE = ROOT / "infra" / "compose.python-core-rollback.yaml"
DEPLOYMENT_FILES = (
    ROOT / ".github" / "workflows" / "build.yml",
    ROOT / "scripts" / "deploy-production.sh",
    ROOT / "scripts" / "upload-docker-images.sh",
    ROOT / "scripts" / "durable-agent-execution-migration.sh",
    ROOT / "scripts" / "durable-agent-v2-rollout-gate.sh",
    ROOT / "scripts" / "prepare-postgres-restore-quarantine.sh",
    ROOT / "scripts" / "verify-durable-agent-v2-image.sh",
)
PRODUCTION_SERVICES = (
    "nginx",
    "web",
    "core-api",
    "agent-service",
    "redis",
    "execution-redis",
)
_COMPOSE_DEFAULT_EXPRESSION = re.compile(
    r"^\$\{(?P<name>[A-Za-z_][A-Za-z0-9_]*):-(?P<default>.*)\}$"
)


def _compose_environment_mapping(service: str) -> dict[str, str]:
    document = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))
    assert isinstance(document, dict)
    services = document.get("services")
    assert isinstance(services, dict)
    service_config = services.get(service)
    assert isinstance(service_config, dict)
    environment = service_config.get("environment")
    assert isinstance(environment, dict)
    assert all(
        isinstance(key, str) and isinstance(value, str)
        for key, value in environment.items()
    )
    return environment


def _expand_compose_default(expression: object, overrides: dict[str, str]) -> str:
    assert isinstance(expression, str)
    match = _COMPOSE_DEFAULT_EXPRESSION.fullmatch(expression)
    assert match is not None, f"不是受控 Compose 默认表达式：{expression}"
    value = overrides.get(match.group("name"))
    return match.group("default") if value in (None, "") else value


def _service_block(source: str, service: str) -> str:
    match = re.search(
        rf"(?ms)^  {re.escape(service)}:\n(?P<body>.*?)"
        r"(?=^  [a-z][a-z0-9-]*:\n|^networks:|^volumes:|\Z)",
        source,
    )
    assert match is not None, f"缺少服务：{service}"
    return match.group("body")


def test_compose_keeps_database_out_of_agent_trust_boundary() -> None:
    source = COMPOSE.read_text(encoding="utf-8")
    core = _service_block(source, "core-api")
    agent = _service_block(source, "agent-service")

    assert "DATABASE_URL" not in agent
    assert "data_net" not in agent
    assert "agent_net" in agent
    assert "public_net" in agent
    assert "AGENT_SERVICE_URL: http://agent-service-internal:8001" in core
    assert "CORE_API_URL: http://core-api-internal:8000" in agent
    assert "core-api-internal" in core
    assert "agent-service-internal" in agent


def test_agent_log_volume_initializer_is_not_a_compose_runtime_service() -> None:
    source = COMPOSE.read_text(encoding="utf-8")
    agent = _service_block(source, "agent-service")

    assert "agent-logs-init:" not in source
    assert 'user: "10001:10001"' in agent
    assert "agent_logs:/data/agent-logs" in agent


def test_cancel_uses_postgres_outcome_instead_of_outbox_boundary() -> None:
    cancellation = (
        ROOT
        / "apps"
        / "core-api"
        / "src"
        / "inkforge_core"
        / "writing"
        / "cancellation.py"
    ).read_text(encoding="utf-8")
    sse = (
        ROOT
        / "apps"
        / "core-api"
        / "src"
        / "inkforge_core"
        / "writing"
        / "sse.py"
    ).read_text(encoding="utf-8")

    assert "WritingEventOutbox" not in cancellation
    assert "supersede_waiting_for_new_command" not in cancellation
    assert "outcome_provider" in sse
    assert "format_run_outcome" in sse


def test_only_nginx_publishes_ports_and_internal_routes_are_blocked() -> None:
    source = COMPOSE.read_text(encoding="utf-8")
    for service in PRODUCTION_SERVICES[1:]:
        assert "ports:" not in _service_block(source, service)
    nginx_service = _service_block(source, "nginx")
    ports = re.search(
        r"(?ms)^    ports:\n(?P<body>.*?)(?=^    [a-z][a-z0-9_-]*:|\Z)",
        nginx_service,
    )
    assert ports is not None
    assert re.findall(r"(?m)^      -\s+(?P<binding>.+?)\s*$", ports.group("body")) == [
        '"127.0.0.1:${INKFORGE_PORT:-43120}:8080"'
    ]

    nginx = (ROOT / "infra" / "nginx" / "nginx.conf").read_text(encoding="utf-8")
    internal = re.search(
        r"location\s+\^~\s+/internal/\s*\{(?P<body>[^{}]*)\}",
        nginx,
    )
    assert internal is not None
    assert re.search(r"(?m)^\s*return\s+404;\s*$", internal.group("body"))
    assert "proxy_pass" not in internal.group("body")
    assert re.search(r"location\s+\^~\s+/api/v1/", nginx)
    assert "proxy_buffering off;" in nginx


def test_compose_nginx_preserves_only_trusted_https_forwarding() -> None:
    nginx = (ROOT / "infra" / "nginx" / "nginx.conf").read_text(encoding="utf-8")
    mapping = re.search(
        r"map\s+\$http_x_forwarded_proto\s+\$inkforge_forwarded_proto\s*\{"
        r"(?P<body>.*?)\}",
        nginx,
        re.DOTALL,
    )

    assert mapping is not None
    mapping_entries = [line.strip() for line in mapping.group("body").splitlines() if line.strip()]
    assert mapping_entries == ["default $scheme;", "~^https$ https;"]
    assert "HTTPS" not in mapping.group("body")
    assert "Https" not in mapping.group("body")
    # 普通 API、视频大文件 API 与 Web 三个代理入口必须使用同一可信映射。
    assert nginx.count(
        "proxy_set_header X-Forwarded-Proto $inkforge_forwarded_proto;"
    ) == 3
    assert "proxy_set_header X-Forwarded-Proto $scheme;" not in nginx


def test_compose_nginx_preserves_trusted_real_client_ip() -> None:
    nginx = (ROOT / "infra" / "nginx" / "nginx.conf").read_text(encoding="utf-8")
    mapping = re.search(
        r"map\s+\$http_x_real_ip\s+\$inkforge_real_ip\s*\{(?P<body>.*?)\}",
        nginx,
        re.DOTALL,
    )

    assert mapping is not None
    mapping_entries = [line.strip() for line in mapping.group("body").splitlines() if line.strip()]
    assert mapping_entries == ["default $http_x_real_ip;", '"" $remote_addr;']
    # 视频上传使用独立 location 后，代理入口数量由两个增加为三个。
    assert nginx.count("proxy_set_header X-Real-IP $inkforge_real_ip;") == 3
    assert "proxy_set_header X-Real-IP $remote_addr;" not in nginx


def test_every_container_has_health_resource_and_filesystem_limits() -> None:
    source = COMPOSE.read_text(encoding="utf-8")
    total_cpus = 0.0
    total_memory_mib = 0
    for service in PRODUCTION_SERVICES:
        block = _service_block(source, service)
        assert "healthcheck:" in block, f"{service} 缺少健康检查"
        assert "cpus:" in block, f"{service} 缺少处理器限制"
        assert "mem_limit:" in block, f"{service} 缺少内存限制"
        assert "read_only: true" in block, f"{service} 根文件系统不是只读"
        assert "security_opt:" in block and "no-new-privileges:true" in block
        user = re.search(r'(?m)^    user: "(?P<uid>\d+):(?P<gid>\d+)"$', block)
        assert user is not None and user.group("uid") != "0" and user.group("gid") != "0"
        cpu_limit = re.search(r'(?m)^    cpus: "(?P<value>[\d.]+)"$', block)
        memory_limit = re.search(r"(?m)^    mem_limit: (?P<value>\d+)m$", block)
        assert cpu_limit is not None and memory_limit is not None
        total_cpus += float(cpu_limit.group("value"))
        total_memory_mib += int(memory_limit.group("value"))

    assert total_cpus <= 2
    assert total_memory_mib <= 2048


def test_core_image_is_single_java21_runtime_without_python() -> None:
    source = CORE_DOCKERFILE.read_text(encoding="utf-8")

    assert "eclipse-temurin:21-jdk" in source
    assert "eclipse-temurin:21-jre" in source
    assert "./mvnw" in source
    assert "unzip" in source
    assert "-pl apps/core-api-java" in source
    assert "-am" in source
    assert "inkforge-core-api-0.1.0-SNAPSHOT.jar" in source
    assert 'LABEL cn.inkforge.core.runtime="java"' in source
    assert 'ENTRYPOINT ["java", "-jar", "/app/inkforge-core-api.jar"]' in source
    assert "ffmpeg" in source
    assert "fonts-noto-cjk" in source
    assert "curl" in source
    for forbidden in ("FROM python:", "ghcr.io/astral-sh/uv", "uv sync", "uvicorn"):
        assert forbidden not in source


def test_core_and_agent_images_prepare_non_root_persistent_mountpoints() -> None:
    core = CORE_DOCKERFILE.read_text(encoding="utf-8")
    agent = (ROOT / "infra" / "docker" / "agent-service.Dockerfile").read_text(
        encoding="utf-8"
    )

    assert "install -d -o 10001 -g 10001 /data/uploads" in core
    assert "install -d -o 10001 -g 10001 /data/agent-logs" in agent
    assert core.index("install -d -o 10001 -g 10001 /data/uploads") < core.index(
        "USER 10001:10001"
    )
    assert agent.index(
        "install -d -o 10001 -g 10001 /data/agent-logs"
    ) < agent.index("USER 10001:10001")


def test_java_core_compose_has_bounded_jvm_and_python_free_healthcheck() -> None:
    core = _service_block(COMPOSE.read_text(encoding="utf-8"), "core-api")

    assert "JAVA_TOOL_OPTIONS:" in core
    for option in (
        "-Xms64m",
        "-Xmx176m",
        "-XX:MaxMetaspaceSize=112m",
        "-XX:ReservedCodeCacheSize=32m",
        "-XX:MaxDirectMemorySize=24m",
        "-Xss512k",
        "-XX:+ExitOnOutOfMemoryError",
    ):
        assert option in core
    health = core.split("healthcheck:", maxsplit=1)[1]
    assert 'test: ["CMD", "curl"' in health
    assert "python" not in health
    assert "mem_limit: 448m" in core


def test_python_core_rollback_override_is_explicit_and_only_changes_healthcheck() -> None:
    document = yaml.safe_load(PYTHON_ROLLBACK_COMPOSE.read_text(encoding="utf-8"))

    assert set(document) == {"services"}
    assert set(document["services"]) == {"core-api"}
    core = document["services"]["core-api"]
    assert set(core) == {"healthcheck"}
    assert "python" in " ".join(core["healthcheck"]["test"])
    assert "inkforge_core" not in " ".join(core["healthcheck"]["test"])


def test_redis_is_bounded() -> None:
    redis_config_path = ROOT / "infra" / "redis" / "redis.conf"
    execution_config_path = ROOT / "infra" / "redis" / "execution-redis.conf"
    redis_config = redis_config_path.read_text(encoding="utf-8")
    execution_config = execution_config_path.read_text(encoding="utf-8")
    compose = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))
    redis = compose["services"]["redis"]
    execution_redis = compose["services"]["execution-redis"]
    agent = compose["services"]["agent-service"]

    assert "64mb" in redis_config.lower()
    assert re.search(r"(?m)^appendonly\s+no$", redis_config)
    assert re.search(r"(?m)^maxmemory-policy\s+noeviction$", redis_config)
    assert "allkeys-lru" not in redis_config
    assert any(item.startswith("/data:") for item in redis.get("tmpfs", []))
    assert all(not item.endswith(":/data") for item in redis.get("volumes", []))

    assert re.search(r"(?m)^maxmemory\s+32mb$", execution_config)
    assert re.search(r"(?m)^auto-aof-rewrite-min-size\s+8mb$", execution_config)
    assert re.search(r"(?m)^hash-max-listpack-value\s+4096$", execution_config)
    assert re.search(r"(?m)^hash-max-listpack-entries\s+64$", execution_config)
    for contract in (
        r"(?m)^appendonly\s+yes$",
        r"(?m)^appendfsync\s+always$",
        r"(?m)^aof-load-truncated\s+no$",
        r"(?m)^maxmemory-policy\s+noeviction$",
    ):
        assert re.search(contract, execution_config)
    assert "execution_redis_data:/data" in execution_redis["volumes"]
    assert all(
        not item.startswith("/data:") for item in execution_redis.get("tmpfs", [])
    )
    assert "execution_redis_data" in compose["volumes"]
    assert execution_redis["networks"] == ["execution_net"]
    assert "execution_net" in agent["networks"]
    assert "EXECUTION_REDIS_URL" in agent["environment"]
    assert execution_config_path.stat().st_mode & 0o777 == 0o644
    execution_memory_mib = int(execution_redis["mem_limit"].removesuffix("m"))
    # AOF rewrite 最坏按 live dataset 全量 CoW 预留，另留 64 MiB 给 Redis/AOF 缓冲。
    assert execution_memory_mib >= 2 * 32 + 64
    for service_name, service in compose["services"].items():
        if service_name not in {"agent-service", "execution-redis"}:
            assert "execution_net" not in (service.get("networks") or [])


def test_agent_queue_terminal_retention_is_configurable() -> None:
    source = COMPOSE.read_text(encoding="utf-8")
    agent = _service_block(source, "agent-service")

    assert (
        "QUEUE_TERMINAL_RETENTION_DAYS: ${QUEUE_TERMINAL_RETENTION_DAYS:-7}"
        in agent
    )
    assert (
        "EXECUTION_TERMINAL_RETENTION_HOURS: "
        "${EXECUTION_TERMINAL_RETENTION_HOURS:-24}" in agent
    )
    assert "EXECUTION_TERMINAL_RETENTION_HOURS=24" in (
        ROOT / ".env.example"
    ).read_text(encoding="utf-8")


def test_production_agent_static_compose_interpolation_contract_for_deepseek_defaults() -> None:
    """仅验证静态 Compose 插值契约，不等同真实 Docker 展开；Docker 验证另行进行。"""
    environment = _compose_environment_mapping("agent-service")

    profile_expression = environment["OPENAI_COMPATIBILITY_PROFILE"]
    base_url_expression = environment["OPENAI_BASE_URL"]
    assert profile_expression == "${OPENAI_COMPATIBILITY_PROFILE:-deepseek_v4}"
    assert base_url_expression == "${OPENAI_BASE_URL:-https://api.deepseek.com}"

    for variable, expression, default in (
        (
            "OPENAI_COMPATIBILITY_PROFILE",
            profile_expression,
            "deepseek_v4",
        ),
        ("OPENAI_BASE_URL", base_url_expression, "https://api.deepseek.com"),
    ):
        assert _expand_compose_default(expression, {}) == default
        assert _expand_compose_default(expression, {variable: ""}) == default
        override = "generic" if variable == "OPENAI_COMPATIBILITY_PROFILE" else "https://proxy.test"
        assert _expand_compose_default(expression, {variable: override}) == override


def test_model_examples_document_explicit_profile_boundary_without_secrets() -> None:
    for path in (ROOT / ".env.example", ROOT / ".env.local.example"):
        source = path.read_text(encoding="utf-8")
        assert "OPENAI_COMPATIBILITY_PROFILE=generic|deepseek_v4" in source
        assert re.search(r"(?m)^OPENAI_API_KEY=\s*$", source)
        assert "API key" in source
        assert "根据 URL" in source
        if path.name == ".env.local.example":
            assert "MODEL_PROVIDER=fake" in source
            assert "OPENAI_COMPATIBILITY_PROFILE=generic" in source
        else:
            assert "MODEL_PROVIDER=openai_compatible" in source
            assert "OPENAI_COMPATIBILITY_PROFILE=deepseek_v4" in source


def test_agent_parallel_limit_is_explicit_and_keeps_one_process() -> None:
    compose = COMPOSE.read_text(encoding="utf-8")
    core = _service_block(compose, "core-api")
    agent = _service_block(compose, "agent-service")
    production_env = (ROOT / ".env.example").read_text(encoding="utf-8")
    local_env = (ROOT / ".env.local.example").read_text(encoding="utf-8")
    dockerfile = (ROOT / "infra" / "docker" / "agent-service.Dockerfile").read_text(
        encoding="utf-8"
    )

    assert "AGENT_MAX_CONCURRENCY: ${AGENT_MAX_CONCURRENCY:-3}" in agent
    assert "AGENT_MAX_CONCURRENCY: ${AGENT_MAX_CONCURRENCY:-3}" in core
    assert "AGENT_MAX_CONCURRENCY=3" in production_env
    assert "AGENT_MAX_CONCURRENCY=3" in local_env
    assert '"--workers", "1"' in dockerfile


def test_durable_agent_schema_and_route_gates_default_closed() -> None:
    compose = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))
    core = compose["services"]["core-api"]
    production_env = (ROOT / ".env.example").read_text(encoding="utf-8")
    local_env = (ROOT / ".env.local.example").read_text(encoding="utf-8")

    assert core["environment"]["DURABLE_AGENT_EXECUTION_SCHEMA_READY"] == (
        "${DURABLE_AGENT_EXECUTION_SCHEMA_READY:-false}"
    )
    assert core["environment"]["DURABLE_AGENT_EXECUTION_ROUTE_MODE"] == (
        "${DURABLE_AGENT_EXECUTION_ROUTE_MODE:-off}"
    )
    for source in (production_env, local_env):
        assert "DURABLE_AGENT_EXECUTION_SCHEMA_READY=false" in source
        assert "DURABLE_AGENT_EXECUTION_ROUTE_MODE=off" in source
    assert "DURABLE_AGENT_EXECUTION_SCHEMA_READY" not in (
        compose["services"]["agent-service"]["environment"]
    )


def test_python_redis_pools_allow_bounded_agent_parallelism() -> None:
    for path in (
        ROOT / "apps" / "agent-service" / "src" / "inkforge_agents" / "app.py",
        ROOT / "apps" / "core-api" / "src" / "inkforge_core" / "app.py",
    ):
        source = path.read_text(encoding="utf-8")
        assert re.search(r"max_connections\s*=\s*8", source)


def test_web_and_core_require_the_same_production_jwt_secret() -> None:
    source = COMPOSE.read_text(encoding="utf-8")
    expected = "JWT_SECRET: ${JWT_SECRET:?必须配置会话签名密钥}"

    assert expected in _service_block(source, "web")
    assert expected in _service_block(source, "core-api")


def test_aliyun_phone_credentials_only_enter_core_and_feature_defaults_closed() -> None:
    source = COMPOSE.read_text(encoding="utf-8")
    web = _service_block(source, "web")
    core = _service_block(source, "core-api")
    agent = _service_block(source, "agent-service")
    env_example = (ROOT / ".env.example").read_text(encoding="utf-8")

    for secret in (
        "ALIYUN_ACCESS_KEY_ID",
        "ALIYUN_ACCESS_KEY_SECRET",
        "PHONE_AUTH_HMAC_SECRET",
    ):
        assert secret in core
        assert secret not in web
        assert secret not in agent
    for public_value in ("ALIYUN_CAPTCHA_PREFIX", "ALIYUN_CAPTCHA_SCENE_ID"):
        assert public_value in web
        assert public_value in core
        assert public_value not in agent
    for flag in ("PHONE_AUTH_ENABLED", "PHONE_AUTH_SEND_ENABLED"):
        assert f"{flag}: ${{{flag}:-false}}" in web
        assert f"{flag}: ${{{flag}:-false}}" in core
        assert f"{flag}=false" in env_example
    assert "USERNAME_REGISTRATION_ENABLED: ${USERNAME_REGISTRATION_ENABLED:-true}" in core
    assert "USERNAME_REGISTRATION_ENABLED=true" in env_example


def test_test_compose_does_not_fork_core_and_web_session_secrets() -> None:
    source = (ROOT / "infra" / "compose.test.yaml").read_text(encoding="utf-8")
    core = _service_block(source, "core-api")

    assert "TEST_JWT_SECRET" not in source
    assert "JWT_SECRET" not in core


def test_production_compose_uses_existing_host_postgres() -> None:
    source = COMPOSE.read_text(encoding="utf-8")
    core = _service_block(source, "core-api")

    assert "host.docker.internal:host-gateway" in core
    assert "DATABASE_URL" in core
    assert not re.search(r"(?m)^  postgres:$", source)
    assert "POSTGRES_DATA_VOLUME" not in source
    assert "postgres_data:" not in source


def test_test_compose_owns_isolated_postgres() -> None:
    compose_path = ROOT / "infra" / "compose.test.yaml"
    source = compose_path.read_text(encoding="utf-8")
    document = yaml.safe_load(source)
    assert isinstance(document, dict)
    services = document["services"]
    networks = document["networks"]

    assert re.search(r"(?m)^  postgres:$", source)
    assert "TEST_POSTGRES_DATA_VOLUME" in source
    assert "pgvector/pgvector:0.8.0-pg16" in source
    assert '"127.0.0.1:${TEST_POSTGRES_PORT:-0}:5432"' in source
    assert "condition: service_healthy" in source
    assert services["postgres"]["networks"] == ["data_net", "test_host_net"]
    assert networks["test_host_net"] is None
    assert all(
        "test_host_net" not in (service.get("networks") or [])
        for name, service in services.items()
        if name != "postgres"
    )


def test_production_env_example_targets_host_gateway() -> None:
    source = (ROOT / ".env.example").read_text(encoding="utf-8")

    assert "INKFORGE_PORT=43120" in source
    assert "宿主机 Nginx" in source
    assert "回环" in source
    assert "@host.docker.internal:5432/novelwriter" in source
    for obsolete in (
        "POSTGRES_USER=",
        "POSTGRES_PASSWORD=",
        "POSTGRES_DB=",
        "POSTGRES_DATA_VOLUME=",
    ):
        assert obsolete not in source


def test_ip_http_auth_mode_is_explicit_and_disabled_by_default() -> None:
    compose = COMPOSE.read_text(encoding="utf-8")
    env_example = (ROOT / ".env.example").read_text(encoding="utf-8")
    compose_variable = "ALLOW_INSECURE_HTTP_AUTH: ${ALLOW_INSECURE_HTTP_AUTH:-false}"

    assert compose_variable in _service_block(compose, "core-api")
    assert compose.count(compose_variable) == 1
    assert "ALLOW_INSECURE_HTTP_AUTH=false" in env_example
    assert "ALLOW_INSECURE_HTTP_AUTH=true" not in env_example
    assert "生产 HTTPS" in env_example
    assert "不得开启明文 HTTP 认证" in env_example


def test_production_deployment_forbids_dynamic_trust_and_destructive_commands() -> None:
    source = "\n".join(path.read_text(encoding="utf-8") for path in DEPLOYMENT_FILES).lower()

    for forbidden in (
        "stricthostkeychecking=no",
        "ssh-keyscan",
        "down -v",
        "docker compose build",
        "alembic upgrade",
        "prisma migrate",
        "docker volume rm",
    ):
        assert forbidden not in source
