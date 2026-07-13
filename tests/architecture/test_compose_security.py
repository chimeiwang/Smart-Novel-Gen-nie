import re
from pathlib import Path

ROOT = Path(__file__).parents[2]
COMPOSE = ROOT / "infra" / "compose.yaml"
PRODUCTION_SERVICES = ("nginx", "web", "core-api", "agent-service", "redis")


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
    agent = _service_block(source, "agent-service")

    assert "DATABASE_URL" not in agent
    assert "data_net" not in agent
    assert "agent_net" in agent


def test_only_nginx_publishes_ports_and_internal_routes_are_blocked() -> None:
    source = COMPOSE.read_text(encoding="utf-8")
    for service in PRODUCTION_SERVICES[1:]:
        assert "ports:" not in _service_block(source, service)
    assert "ports:" in _service_block(source, "nginx")

    nginx = (ROOT / "infra" / "nginx" / "nginx.conf").read_text(encoding="utf-8")
    assert re.search(r"location\s+\^~\s+/internal/", nginx)
    assert re.search(r"location\s+\^~\s+/api/v1/", nginx)
    assert "proxy_buffering off;" in nginx


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


def test_redis_is_bounded() -> None:
    redis_config = (ROOT / "infra" / "redis" / "redis.conf").read_text(encoding="utf-8")

    assert "64mb" in redis_config.lower()
    assert re.search(r"(?m)^appendonly\s+no$", redis_config)


def test_production_compose_uses_existing_host_postgres() -> None:
    source = COMPOSE.read_text(encoding="utf-8")
    core = _service_block(source, "core-api")

    assert "host.docker.internal:host-gateway" in core
    assert "DATABASE_URL" in core
    assert not re.search(r"(?m)^  postgres:$", source)
    assert "POSTGRES_DATA_VOLUME" not in source
    assert "postgres_data:" not in source


def test_test_compose_owns_isolated_postgres() -> None:
    source = (ROOT / "infra" / "compose.test.yaml").read_text(encoding="utf-8")

    assert re.search(r"(?m)^  postgres:$", source)
    assert "TEST_POSTGRES_DATA_VOLUME" in source
    assert "pgvector/pgvector:pg16" in source
    assert "condition: service_healthy" in source


def test_production_env_example_targets_host_gateway() -> None:
    source = (ROOT / ".env.example").read_text(encoding="utf-8")

    assert "@host.docker.internal:5432/" in source
    for obsolete in (
        "POSTGRES_USER=",
        "POSTGRES_PASSWORD=",
        "POSTGRES_DB=",
        "POSTGRES_DATA_VOLUME=",
    ):
        assert obsolete not in source
