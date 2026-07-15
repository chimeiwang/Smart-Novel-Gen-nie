from __future__ import annotations

import json
import subprocess
import sys
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[2]
PROBE = ROOT / "scripts" / "agent_readiness_probe.py"
DIAGNOSTIC_PREFIX = "INKFORGE_AGENT_READINESS_DIAGNOSTIC="


@contextmanager
def _local_response(status: int, body: bytes) -> Iterator[str]:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address
        yield f"http://{host}:{port}/internal/v1/health/ready"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _run_probe(status: int, body: bytes) -> subprocess.CompletedProcess[str]:
    with _local_response(status, body) as url:
        return subprocess.run(  # noqa: S603 - 仅执行当前解释器和仓库内固定探针
            [sys.executable, str(PROBE), url],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=10,
            check=False,
        )


def _diagnostic(stderr: str) -> dict[str, object]:
    assert stderr.startswith(DIAGNOSTIC_PREFIX)
    return json.loads(stderr.removeprefix(DIAGNOSTIC_PREFIX))


def test_agent_readiness_probe_accepts_ready_response() -> None:
    result = _run_probe(200, b'{"status":"ready"}')

    assert (result.returncode, result.stdout, result.stderr) == (0, "", "")


@pytest.mark.parametrize("status_code", [201, 202])
def test_agent_readiness_probe_rejects_non_200_ready_response(
    status_code: int,
) -> None:
    result = _run_probe(status_code, b'{"status":"ready"}')

    assert result.returncode == 1
    assert _diagnostic(result.stderr) == {"status": "ready"}


def test_agent_readiness_probe_filters_http_error_json() -> None:
    result = _run_probe(
        503,
        b'{"status":"not_ready","backgroundTasks":{"code":"BACKGROUND_TASK_BACKOFF"},"sensitiveToken":"secret"}',
    )

    assert result.returncode == 1
    assert _diagnostic(result.stderr) == {
        "status": "not_ready",
        "backgroundTasks": {"code": "BACKGROUND_TASK_BACKOFF"},
    }
    assert "sensitiveToken" not in result.stderr
    assert "secret" not in result.stderr


def test_agent_readiness_probe_reports_successful_not_ready_response() -> None:
    result = _run_probe(
        200,
        b'{"status":"not_ready","checks":{"queue":"starting"},"ignored":"secret"}',
    )

    assert result.returncode == 1
    assert _diagnostic(result.stderr) == {
        "status": "not_ready",
        "checks": {"queue": "starting"},
    }
    assert "ignored" not in result.stderr
    assert "secret" not in result.stderr


def test_agent_readiness_probe_reports_only_status_for_invalid_error_json() -> None:
    result = _run_probe(503, b"not-json-sensitive-body")

    assert result.returncode == 1
    assert result.stderr == "INKFORGE_AGENT_READINESS_HTTP_STATUS=503\n"
    assert "sensitive" not in result.stderr


@pytest.mark.parametrize("arguments", [[], ["http://127.0.0.1", "extra"]])
def test_agent_readiness_probe_requires_exactly_one_url(arguments: list[str]) -> None:
    result = subprocess.run(  # noqa: S603 - 仅执行当前解释器和仓库内固定探针
        [sys.executable, str(PROBE), *arguments],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=10,
        check=False,
    )

    assert result.returncode == 2
    assert "必须且只能提供一个就绪检查 URL" in result.stderr


def test_agent_readiness_probe_rejects_non_http_url() -> None:
    result = subprocess.run(  # noqa: S603 - 仅执行当前解释器和仓库内固定探针
        [sys.executable, str(PROBE), "file:///tmp/readiness.json"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=10,
        check=False,
    )

    assert result.returncode == 2
    assert "就绪检查 URL 必须使用 http 或 https" in result.stderr
