"""退役预检必须排空、保全恢复点，并避免命令与诊断泄露凭据。"""

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "engine_retirement_preflight",
    Path(__file__).parents[2] / "scripts/engine_retirement_preflight.py",
)
assert SPEC is not None and SPEC.loader is not None
probe = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(probe)


def app(tmp_path):
    root = tmp_path / "app"
    (root / "scripts").mkdir(parents=True)
    (root / ".env").write_text(
        "DATABASE_URL=postgresql://writer:credential-test@host.docker.internal:5432/novelwriter\n"
        "DURABLE_AGENT_EXECUTION_ROUTE_MODE=off\nVIDEO_PREVIEW_ENABLED=false\n"
    )
    (root / "scripts/retirement_execution_snapshot.lua").write_text("return '{}'")
    return root


def facts(**changes):
    return {"activeV2Runs": 0, "nonterminalV2Steps": 0, "unsettledReservations": 3, **changes}


def journal(**changes):
    return {
        "quarantined": False,
        "active": [],
        "pending": [],
        "leased": [],
        "rejected": [],
        **changes,
    }


def test_credentials_are_only_in_clean_database_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("PGSERVICE", "unexpected-service")
    monkeypatch.setenv("PGDATABASE", "other-database")
    environment = probe.database_environment(app(tmp_path))
    assert environment["PGPASSWORD"] == "credential-test"
    assert environment["PGHOST"] == "127.0.0.1"
    assert environment["PGDATABASE"] == "novelwriter"
    assert "PGSERVICE" not in environment
    assert "default_transaction_read_only=on" in environment["PGOPTIONS"]


@pytest.mark.parametrize(
    "change",
    [
        "DURABLE_AGENT_EXECUTION_ROUTE_MODE=all",
        "VIDEO_PREVIEW_ENABLED=true",
        "DATABASE_URL=postgresql://writer:secret@host.docker.internal/other",
        "DATABASE_URL=postgresql://writer:secret@host.docker.internal/novelwriter?options=unsafe",
    ],
)
def test_unapproved_target_and_open_routes_fail_closed(tmp_path, change):
    root = app(tmp_path)
    name = change.split("=", 1)[0]
    lines = (root / ".env").read_text().splitlines()
    (root / ".env").write_text(
        "\n".join(change if line.startswith(name + "=") else line for line in lines)
    )
    with pytest.raises(ValueError):
        probe.database_environment(root)


@pytest.mark.parametrize(
    "value",
    [
        facts(activeV2Runs=1),
        facts(nonterminalV2Steps=1),
        facts(activeV2Runs=True),
        {"activeV2Runs": 0},
    ],
)
def test_inflight_and_invalid_counts_block_retirement(monkeypatch, value):
    monkeypatch.setattr(probe, "run", lambda *args, **kwargs: json.dumps(value))
    with pytest.raises(ValueError):
        probe.database_snapshot({})


def test_pending_billing_is_reported_without_fabricated_settlement(monkeypatch):
    seen = []

    def run(args, **kwargs):
        seen.append(args)
        return json.dumps(facts(unsettledReservations=9))

    monkeypatch.setattr(probe, "run", run)
    assert probe.database_snapshot({})["unsettledReservations"] == 9
    assert "BEGIN" not in seen[0][-1]
    assert "COMMIT" not in seen[0][-1]
    assert "UPDATE" not in seen[0][-1]


@pytest.mark.parametrize(
    "value",
    [
        journal(active=[{"id": "step-1"}]),
        journal(pending=[1]),
        journal(leased=[1]),
        journal(rejected=[1]),
        journal(quarantined=True),
        {"error": "missing_marker"},
    ],
)
def test_unfinished_or_invalid_journal_blocks_retirement(tmp_path, monkeypatch, value):
    monkeypatch.setattr(probe, "run", lambda *args, **kwargs: json.dumps(value))
    with pytest.raises(ValueError):
        probe.journal_snapshot(app(tmp_path), "old-journal")


def test_snapshot_eval_has_exact_zero_keys_and_no_stdin_argument(tmp_path, monkeypatch):
    seen = []

    def run(args, **kwargs):
        seen.append(args)
        return json.dumps(journal())

    monkeypatch.setattr(probe, "run", run)
    probe.journal_snapshot(app(tmp_path), "old-journal")
    assert seen[0][-3:] == ["EVAL", "return '{}'", "0"]
    assert "-x" not in seen[0]


def test_first_retirement_requires_original_journal(tmp_path, monkeypatch):
    root = app(tmp_path)
    monkeypatch.setenv("APP_DIR", str(root))
    monkeypatch.setenv("DEPLOY_SHA", "a" * 40)
    monkeypatch.setattr(probe.sys, "argv", ["probe", "core", ""])
    monkeypatch.setattr(probe, "run", lambda *args, **kwargs: "")
    with pytest.raises(ValueError, match="日志容器缺失"):
        probe.main()


def test_backups_are_verified_private_and_commands_do_not_contain_credentials(
    tmp_path, monkeypatch, capsys
):
    root = app(tmp_path)
    backups = tmp_path / "backups"
    calls = []

    def run(args, **kwargs):
        calls.append(args)
        if args[0] == "psql":
            return json.dumps(facts())
        if args[0] == "pg_dump":
            Path(args[-1]).write_bytes(b"database-backup" * 200_000 + b"last-byte")
        if args[:2] == ["docker", "cp"]:
            Path(args[-1]).write_bytes(b"journal-backup")
        if "EVAL" in args:
            return json.dumps(journal())
        return ""

    monkeypatch.setattr(probe, "run", run)
    monkeypatch.setenv("APP_DIR", str(root))
    monkeypatch.setenv("DEPLOY_SHA", "a" * 40)
    monkeypatch.setenv("BACKUP_ROOT", str(backups))
    monkeypatch.setattr(probe.sys, "argv", ["probe", "core", "old-journal"])
    probe.main()
    target = next(backups.iterdir())
    assert (target.stat().st_mode & 0o777) == 0o700
    assert {path.name for path in target.iterdir()} == {
        "database.dump",
        "execution-journal.rdb",
        "facts.json",
        "SHA256SUMS",
    }
    assert all((path.stat().st_mode & 0o777) == 0o600 for path in target.iterdir())
    manifest = dict(
        line.split("  ", 1)[::-1] for line in (target / "SHA256SUMS").read_text().splitlines()
    )
    expected = hashlib.sha256(b"database-backup" * 200_000 + b"last-byte").hexdigest()
    assert manifest["database.dump"] == expected
    assert any(call[:2] == ["pg_restore", "--list"] for call in calls)
    assert any("redis-check-rdb" in call for call in calls)
    assert "credential-test" not in json.dumps(calls)
    output = capsys.readouterr().out
    assert "credential-test" not in output
    assert "历史待对账数=3" in output


def test_failed_commands_keep_provider_and_database_diagnostics_private(monkeypatch):
    import subprocess

    def failed(args, **kwargs):
        return subprocess.CompletedProcess(args, 1, "credential-test", "database=credential-test")

    monkeypatch.setattr(probe.subprocess, "run", failed)
    with pytest.raises(RuntimeError) as failure:
        probe.run(["psql", "--command", "SELECT 1"])
    assert "credential-test" not in str(failure.value)
    assert "psql" in str(failure.value)


def test_command_timeout_has_bounded_safe_failure(monkeypatch):
    import subprocess

    def timed_out(args, **kwargs):
        assert kwargs["timeout"] == 600
        raise subprocess.TimeoutExpired(args, 600, output="credential-test")

    monkeypatch.setattr(probe.subprocess, "run", timed_out)
    with pytest.raises(RuntimeError, match="超时") as failure:
        probe.run(["pg_dump", "--format=custom"])
    assert "credential-test" not in str(failure.value)


def test_real_postgres14_psql_returns_single_snapshot_without_mutations(tmp_path):
    """真实 psql 14 的 -c 输出规则，不能由假 subprocess 的 JSON 响应代证。"""
    import os
    import shutil
    import subprocess
    import time
    import uuid

    docker_executable = shutil.which("docker")
    if docker_executable is None:
        pytest.skip("真实 PostgreSQL 回归需要 Docker")
    image = "pgvector/pgvector:0.8.0-pg14"
    available = subprocess.run(  # noqa: S603 - 本地固定镜像只读检查，不自动下载。
        [docker_executable, "image", "inspect", image], capture_output=True, timeout=15, check=False
    )
    if available.returncode:
        pytest.skip("本机没有隔离 PostgreSQL 14 测试镜像")
    container = "inkforge-retirement-pg14-" + uuid.uuid4().hex

    def docker(*arguments, stdin=None):
        result = subprocess.run(  # noqa: S603 - 固定 Docker 程序和随机隔离容器身份。
            [docker_executable, *arguments],
            input=stdin,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        assert result.returncode == 0, result.stderr
        return result.stdout.strip()

    try:
        docker(
            "run",
            "--detach",
            "--rm",
            "--network",
            "none",
            "--name",
            container,
            "--env",
            "POSTGRES_HOST_AUTH_METHOD=trust",
            "--env",
            "POSTGRES_DB=novelwriter",
            image,
        )
        for _ in range(60):
            ready = subprocess.run(  # noqa: S603 - 隔离 PostgreSQL 就绪检查。
                [
                    docker_executable,
                    "exec",
                    container,
                    "pg_isready",
                    "-h",
                    "127.0.0.1",
                    "-U",
                    "postgres",
                ],
                capture_output=True,
                timeout=5,
                check=False,
            )
            if ready.returncode == 0:
                break
            time.sleep(0.1)
        else:
            pytest.fail("隔离 PostgreSQL 未就绪")
        version = docker("exec", container, "psql", "--version")
        assert " 14." in version
        docker(
            "exec",
            "-i",
            container,
            "psql",
            "-U",
            "postgres",
            "-d",
            "novelwriter",
            "-v",
            "ON_ERROR_STOP=1",
            stdin="""
CREATE TABLE "WorkflowRun" (id text PRIMARY KEY, "engineVersion" int, status text);
CREATE TABLE "WorkflowStep" ("runId" text, status text);
CREATE TABLE "WorkflowBillingReservation" (status text);
INSERT INTO "WorkflowRun" VALUES ('done',2,'completed'),('ordinary',1,'running');
INSERT INTO "WorkflowStep" VALUES ('done','completed'),('ordinary','running');
INSERT INTO "WorkflowBillingReservation" VALUES ('pending'),('settled'),('released');
""",
        )
        binary = tmp_path / "bin"
        binary.mkdir()
        wrapper = binary / "psql"
        wrapper.write_text(
            "#!/bin/sh\nexec docker exec -i --env PGOPTIONS --env PGDATABASE "
            "--env PGUSER --env PGHOST=127.0.0.1 --env PGPORT=5432 " + container + ' psql "$@"\n'
        )
        wrapper.chmod(0o755)
        env = {
            **os.environ,
            "PATH": str(binary) + os.pathsep + os.environ["PATH"],
            "PGUSER": "postgres",
            "PGDATABASE": "novelwriter",
            "PGOPTIONS": "-c default_transaction_read_only=on -c statement_timeout=30000",
        }
        result = probe.database_snapshot(env)
        assert result == facts(unsettledReservations=1)
        assert probe.run(["psql", "-Atc", "SHOW default_transaction_read_only"], env=env) == "on"
        with pytest.raises(RuntimeError):
            probe.run(["psql", "-v", "ON_ERROR_STOP=1", "-c", 'DELETE FROM "WorkflowRun"'], env=env)
        assert probe.database_snapshot(env) == result
    finally:
        subprocess.run(  # noqa: S603 - 只删除本测试随机容器；没有卷或生产对象。
            [docker_executable, "rm", "--force", container],
            capture_output=True,
            timeout=30,
            check=False,
        )
