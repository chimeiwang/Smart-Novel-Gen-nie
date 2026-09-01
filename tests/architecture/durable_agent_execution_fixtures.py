from __future__ import annotations

import shutil
import subprocess
import time
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[2]
BASE_SCHEMA = (
    ROOT
    / "apps"
    / "core-api-java"
    / "src"
    / "test"
    / "resources"
    / "db"
    / "novelwriterdev-schema.sql"
)
POSTGRES_IMAGE = "pgvector/pgvector:0.8.0-pg14"


def _docker_command(
    docker: str,
    *arguments: str,
    input_text: str | None = None,
    timeout: int = 60,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 - 参数只来自本测试中的固定镜像、容器名和 SQL
        [docker, *arguments],
        input=input_text,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=timeout,
        check=False,
    )


def _psql(
    docker: str,
    container: str,
    sql: str,
    *,
    database: str = "novelwriterdev",
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    result = _docker_command(
        docker,
        "exec",
        "-i",
        container,
        "psql",
        "-X",
        "-v",
        "ON_ERROR_STOP=1",
        "-U",
        "postgres",
        "-d",
        database,
        input_text=sql,
        timeout=120,
    )
    if check and result.returncode != 0:
        pytest.fail(f"psql 执行失败：\n{result.stdout}\n{result.stderr}")
    return result


def _scalar(docker: str, container: str, query: str) -> str:
    result = _docker_command(
        docker,
        "exec",
        container,
        "psql",
        "-X",
        "-A",
        "-t",
        "-v",
        "ON_ERROR_STOP=1",
        "-U",
        "postgres",
        "-d",
        "novelwriterdev",
        "-c",
        query,
    )
    if result.returncode != 0:
        pytest.fail(f"查询失败：\n{result.stdout}\n{result.stderr}")
    return result.stdout.strip()


@pytest.fixture(scope="module")
def isolated_postgres() -> Iterator[tuple[str, str]]:
    docker = shutil.which("docker")
    if docker is None:
        pytest.skip("需要 Docker 才能运行 PostgreSQL 14 隔离迁移测试")

    docker_info = _docker_command(docker, "info", timeout=15)
    if docker_info.returncode != 0:
        pytest.skip("Docker daemon 不可用，跳过 PostgreSQL 14 隔离迁移测试")

    container = f"inkforge-durable-agent-{uuid.uuid4().hex[:12]}"
    started = _docker_command(
        docker,
        "run",
        "--rm",
        "-d",
        "--name",
        container,
        "-e",
        "POSTGRES_PASSWORD=postgres",
        "-e",
        "POSTGRES_DB=novelwriterdev",
        POSTGRES_IMAGE,
        timeout=120,
    )
    if started.returncode != 0:
        pytest.fail(f"隔离 PostgreSQL 启动失败：\n{started.stdout}\n{started.stderr}")

    try:
        deadline = time.monotonic() + 45
        consecutive_ready_checks = 0
        while time.monotonic() < deadline:
            ready = _docker_command(
                docker,
                "exec",
                container,
                "psql",
                "-X",
                "-U",
                "postgres",
                "-d",
                "novelwriterdev",
                "-c",
                "SELECT 1",
                timeout=5,
            )
            if ready.returncode == 0:
                consecutive_ready_checks += 1
                if consecutive_ready_checks >= 3:
                    break
            else:
                consecutive_ready_checks = 0
            time.sleep(0.25)
        else:
            pytest.fail("隔离 PostgreSQL 在 45 秒内未就绪")
        yield docker, container
    finally:
        _docker_command(docker, "rm", "-f", container, timeout=30)
