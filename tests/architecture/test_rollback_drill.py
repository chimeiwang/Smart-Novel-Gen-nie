from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from urllib.parse import urlsplit

import pytest

ROOT = Path(__file__).parents[2]
ROLLBACK = ROOT / "scripts" / "rollback_drill.sh"
SMOKE_SH = ROOT / "scripts" / "compose_smoke.sh"
SMOKE_PS1 = ROOT / "scripts" / "compose_smoke.ps1"
AGENT_PROBE = ROOT / "scripts" / "agent_readiness_probe.py"
FAKE_DOCKER = ROOT / "tests" / "architecture" / "fixtures" / "fake_docker.sh"
POSIX_SHELL = shutil.which("sh") or str(
    Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Git" / "bin" / "sh.exe"
)


def _write_executable(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)


def _posix_path(path: Path) -> str:
    resolved = path.resolve()
    if os.name != "nt":
        return resolved.as_posix()
    return f"/{resolved.drive[0].lower()}{resolved.as_posix()[2:]}"


def _run_compose_smoke(
    tmp_path: Path,
    *,
    ready_after: int,
    required_successes: int,
    max_attempts: int,
    ready_sequence: str = "",
    nginx_binding: str = "0.0.0.0:43120",
) -> tuple[subprocess.CompletedProcess[str], int, list[str]]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    shutil.copy2(FAKE_DOCKER, bin_dir / "docker")
    (bin_dir / "docker").chmod(0o755)
    _write_executable(
        bin_dir / "curl",
        "#!/bin/sh\n"
        "url=''\n"
        "for argument in \"$@\"; do\n"
        "  case \"$argument\" in http://*|https://*) url=\"$argument\";; esac\n"
        "done\n"
        "printf '%s\\n' \"$url\" >> \"$FAKE_CURL_LOG\"\n"
        "case \"$url\" in\n"
        "  */login) exit 0;;\n"
        "  */api/v1/health/ready) printf '%s\\n' '{\"status\":\"ready\"}';;\n"
        "  */internal/v1/health/live) printf 404;;\n"
        "  *) exit 1;;\n"
        "esac\n",
    )
    docker_log = tmp_path / "docker.log"
    curl_log = tmp_path / "curl.log"
    agent_counter = tmp_path / "agent-ready-count"
    env = {
        **os.environ,
        "FAKE_DOCKER_LOG": _posix_path(docker_log),
        "FAKE_CURL_LOG": _posix_path(curl_log),
        "FAKE_NGINX_BINDING": nginx_binding,
        "FAKE_AGENT_READY_COUNTER": _posix_path(agent_counter),
        "FAKE_AGENT_READY_AFTER": str(ready_after),
        "FAKE_AGENT_READY_SEQUENCE": ready_sequence,
        "SMOKE_AGENT_REQUIRED_SUCCESSES": str(required_successes),
        "SMOKE_AGENT_MAX_ATTEMPTS": str(max_attempts),
        "SMOKE_AGENT_POLL_SECONDS": "0",
    }
    result = subprocess.run(  # noqa: S603 - 测试仅执行仓库内固定脚本和测试夹具
        [
            POSIX_SHELL,
            "-c",
            'PATH="$1:$PATH"; export PATH; exec /bin/sh "$2"',
            "smoke-test",
            _posix_path(bin_dir),
            _posix_path(SMOKE_SH),
        ],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=20,
        check=False,
    )
    call_count = (
        int(agent_counter.read_text(encoding="utf-8"))
        if agent_counter.exists()
        else 0
    )
    urls = curl_log.read_text(encoding="utf-8").splitlines() if curl_log.exists() else []
    return result, call_count, urls


def test_production_smoke_does_not_enable_test_compose_by_default() -> None:
    shell_source = SMOKE_SH.read_text(encoding="utf-8")
    powershell_source = SMOKE_PS1.read_text(encoding="utf-8")

    assert "COMPOSE_OVERRIDE_FILE" in shell_source
    assert "COMPOSE_OVERRIDE_FILE" in powershell_source
    unsafe_default = 'compose="docker compose -f infra/compose.yaml -f infra/compose.test.yaml"'
    assert unsafe_default not in shell_source


def test_compose_smoke_executes_standalone_agent_readiness_probe() -> None:
    smoke_source = SMOKE_SH.read_text(encoding="utf-8")
    probe_source = AGENT_PROBE.read_text(encoding="utf-8")

    assert "python - http://127.0.0.1:8001/internal/v1/health/ready" in smoke_source
    assert "< scripts/agent_readiness_probe.py" in smoke_source
    assert "DIAGNOSTIC_FIELDS" in probe_source
    assert "with error:" in probe_source


def test_rollback_requires_distinct_current_and_previous_python_tags() -> None:
    source = ROLLBACK.read_text(encoding="utf-8")

    assert "CURRENT_IMAGE_TAG" in source
    assert "ROLLBACK_IMAGE_TAG" in source
    assert '"$CURRENT_IMAGE_TAG" != "$ROLLBACK_IMAGE_TAG"' in source
    for image in ("inkforge-web", "inkforge-core-api", "inkforge-agent-service"):
        assert f"{image}:$ROLLBACK_IMAGE_TAG" in source
        assert f"{image}:$CURRENT_IMAGE_TAG" in source


def test_rollback_restores_current_stack_when_verification_fails() -> None:
    source = ROLLBACK.read_text(encoding="utf-8")

    assert "restore_current" in source
    assert "trap" in source
    assert "scripts/compose_smoke.sh" in source
    assert "inkforge_core.db.schema_guard" in source
    assert "--no-build" in source
    assert "down -v" not in source
    assert "restore_verify.sh" not in source


@pytest.mark.parametrize("nginx_binding", ["0.0.0.0:43120", "[::]:43120"])
def test_compose_smoke_waits_for_stable_agent_and_uses_published_nginx_port(
    tmp_path: Path,
    nginx_binding: str,
) -> None:
    result, call_count, urls = _run_compose_smoke(
        tmp_path,
        ready_after=3,
        required_successes=3,
        max_attempts=6,
        nginx_binding=nginx_binding,
    )

    actual_endpoints = {
        (parsed.hostname, parsed.port) for parsed in map(urlsplit, urls)
    }
    assert (result.returncode, call_count, actual_endpoints) == (
        0,
        5,
        {("127.0.0.1", 43120)},
    ), result.stderr


def test_compose_smoke_fails_after_agent_readiness_attempt_limit(
    tmp_path: Path,
) -> None:
    result, call_count, _ = _run_compose_smoke(
        tmp_path,
        ready_after=5,
        required_successes=3,
        max_attempts=4,
    )

    assert result.returncode != 0
    assert call_count == 4
    assert "BACKGROUND_TASK_BACKOFF" in result.stderr
    assert "fixture-sensitive-token" not in result.stderr
    assert "最多尝试 4 次，要求连续成功 3 次" in result.stderr


def test_compose_smoke_rejects_required_successes_above_attempt_limit(
    tmp_path: Path,
) -> None:
    result, call_count, urls = _run_compose_smoke(
        tmp_path,
        ready_after=1,
        required_successes=4,
        max_attempts=3,
    )

    assert result.returncode != 0
    assert call_count == 0
    assert urls == []
    assert "SMOKE_AGENT_REQUIRED_SUCCESSES" in result.stderr
    assert "SMOKE_AGENT_MAX_ATTEMPTS" in result.stderr


def test_compose_smoke_resets_consecutive_successes_after_agent_failure(
    tmp_path: Path,
) -> None:
    result, call_count, _ = _run_compose_smoke(
        tmp_path,
        ready_after=1,
        ready_sequence="not_ready,ready,not_ready,ready,ready,ready",
        required_successes=3,
        max_attempts=6,
    )

    assert (result.returncode, call_count) == (0, 6), result.stderr
