from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[2]


@pytest.mark.parametrize("base_file", [None, "infra/.rollback-frozen.yaml"])
def test_smoke_checks_current_services_with_selected_compose_and_real_volume_probes(
    tmp_path: Path, base_file: str | None
) -> None:
    binaries = tmp_path / "bin"
    binaries.mkdir()
    log = tmp_path / "docker.log"
    uploads = tmp_path / "uploads"
    human_logs = tmp_path / "human-logs"
    uploads.mkdir()
    human_logs.mkdir()
    docker = binaries / "docker"
    docker.write_text(
        """#!/bin/sh
set -eu
printf '%s\\n' "$*" >> "$SMOKE_DOCKER_LOG"
case "$*" in
  *execution-redis*) echo '退役服务不能作为冒烟依赖' >&2; exit 9 ;;
  *'port nginx 8080'*) echo '127.0.0.1:18080' ;;
  *'exec -T agent-service python - '*) cat >/dev/null ;;
  *'exec -T core-api sh -c '*|*'exec -T agent-service sh -c '*)
    for arg do probe="$arg"; done
    sh -c "$probe"
    ;;
esac
"""
    )
    curl = binaries / "curl"
    curl.write_text(
        """#!/bin/sh
set -eu
case "$*" in
  *'/api/v1/health/ready'*) printf '%s' '{"status":"ready","agent":"ok"}' ;;
  *'/internal/v1/health/live'*) printf '%s' 404 ;;
esac
"""
    )
    docker.chmod(0o755)
    curl.chmod(0o755)
    env = {
        **os.environ,
        "PATH": str(binaries) + os.pathsep + os.environ["PATH"],
        "SMOKE_DOCKER_LOG": str(log),
        "UPLOADS_ROOT": str(uploads),
        "WORKFLOW_HUMAN_LOG_DIR": str(human_logs),
        "SMOKE_AGENT_POLL_SECONDS": "0",
        "SMOKE_AGENT_REQUIRED_SUCCESSES": "2",
        "SMOKE_AGENT_MAX_ATTEMPTS": "2",
    }
    env.pop("COMPOSE_BASE_FILE", None)
    env.pop("COMPOSE_OVERRIDE_FILE", None)
    env.pop("COMPOSE_ADDITIONAL_OVERRIDE_FILE", None)
    if base_file:
        env["COMPOSE_BASE_FILE"] = base_file
    # 仅执行固定仓库脚本和固定参数，环境与替身均由本测试创建。
    result = subprocess.run(  # noqa: S603
        [shutil.which("sh") or "sh", "scripts/compose_smoke.sh"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 0, result.stderr
    commands = [line for line in log.read_text().splitlines() if line.startswith("compose ")]
    selected = base_file or "infra/compose.yaml"
    assert all(f"-f {selected} " in command for command in commands)
    assert not any("execution-redis" in command for command in commands)
    assert sum("exec -T agent-service python" in command for command in commands) == 2
    assert any("exec -T core-api sh -c" in command for command in commands)
    assert any("exec -T agent-service sh -c" in command for command in commands)
    assert list(uploads.iterdir()) == []
    assert list(human_logs.iterdir()) == []
