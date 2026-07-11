import re
from pathlib import Path

ROOT = Path(__file__).parents[2]
COMPOSE = ROOT / "infra" / "compose.yaml"


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
    for service in ("web", "core-api", "agent-service", "redis", "postgres"):
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
    for service in ("nginx", "web", "core-api", "agent-service", "redis", "postgres"):
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


def test_redis_is_bounded_and_postgres_has_no_initialization_mount() -> None:
    source = COMPOSE.read_text(encoding="utf-8")
    postgres = _service_block(source, "postgres")
    redis_config = (ROOT / "infra" / "redis" / "redis.conf").read_text(encoding="utf-8")

    assert "64mb" in redis_config.lower()
    assert re.search(r"(?m)^appendonly\s+no$", redis_config)
    assert "/docker-entrypoint-initdb.d" not in postgres
    assert "postgres_data" in postgres
