from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[2]
UPLOAD = ROOT / "scripts" / "upload-docker-images.sh"
SOURCE_UPLOAD = ROOT / "scripts" / "upload-deploy-source.sh"
DEPLOY = ROOT / "scripts" / "deploy-production.sh"
RELEASE_DRIVER = ROOT / "scripts" / "durable-agent-v2-release.sh"
RELEASE_MANIFEST_HELPER = ROOT / "scripts" / "durable_agent_v2_release_manifest.py"
RELEASE_BOUNDARY_HELPER = ROOT / "scripts" / "durable_agent_release_boundary.py"
RELEASE_GUARD_HELPER = ROOT / "scripts" / "durable_agent_release_guard.py"
JOINT_DRAIN_HELPER = ROOT / "scripts" / "durable_agent_joint_drain.py"
ROLLBACK_DRILL = ROOT / "scripts" / "rollback_drill.sh"
BACKUP = ROOT / "scripts" / "backup.sh"
EXECUTION_RESTORE = ROOT / "scripts" / "restore-execution-journal.sh"
EXECUTION_CLEAR_QUARANTINE = ROOT / "scripts" / "clear-execution-journal-quarantine.sh"
FAKE_DOCKER = ROOT / "tests" / "architecture" / "fixtures" / "fake_docker.sh"
POSIX_SHELL = shutil.which("sh") or str(
    Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Git" / "bin" / "sh.exe"
)
TARGET_WEB_DIGEST = "sha256:" + "1" * 64
TARGET_CORE_DIGEST = "sha256:" + "2" * 64
TARGET_AGENT_DIGEST = "sha256:" + "3" * 64
ROLLBACK_WEB_DIGEST = "sha256:" + "4" * 64
ROLLBACK_CORE_DIGEST = "sha256:" + "5" * 64
ROLLBACK_AGENT_DIGEST = "sha256:" + "6" * 64
CONTROL_BUNDLE_SHA = "9" * 64
ROLLBACK_SOURCE_RECEIPT_SHA = "8" * 64


def test_upload_requires_pinned_known_hosts_before_network_calls() -> None:
    source = UPLOAD.read_text(encoding="utf-8")

    assert "StrictHostKeyChecking=no" not in source
    assert '"${SSH_KNOWN_HOSTS_FILE:?必须设置 known_hosts 文件路径}"' in source
    assert '[ -r "$SSH_KNOWN_HOSTS_FILE" ]' in source
    assert '[ -s "$SSH_KNOWN_HOSTS_FILE" ]' in source
    assert "StrictHostKeyChecking=yes" in source
    assert "UserKnownHostsFile=$SSH_KNOWN_HOSTS_FILE" in source
    assert "ssh-keyscan" not in source


def test_upload_preflights_and_processes_each_image_with_bounded_stages() -> None:
    source = UPLOAD.read_text(encoding="utf-8")

    for contract in (
        'CONNECT_TIMEOUT_SECONDS="${CONNECT_TIMEOUT_SECONDS:-15}"',
        'REMOTE_COMMAND_TIMEOUT_SECONDS="${REMOTE_COMMAND_TIMEOUT_SECONDS:-300}"',
        'IMAGE_ARCHIVE_TIMEOUT_SECONDS="${IMAGE_ARCHIVE_TIMEOUT_SECONDS:-600}"',
        'IMAGE_UPLOAD_TIMEOUT_SECONDS="${IMAGE_UPLOAD_TIMEOUT_SECONDS:-1200}"',
        "validate_timeout",
        "ConnectTimeout=$CONNECT_TIMEOUT_SECONDS",
        "ConnectionAttempts=2",
        "BatchMode=yes",
        "--kill-after=30s",
        "docker info",
        "DockerRootDir",
        "df -Pk",
        "服务器 SSH 响应正常",
        "服务器 Bash 可用，开始读取 Docker 信息",
        'mktemp -d "${RUNNER_TEMP:-/tmp}/inkforge-images.XXXXXX"',
        "trap cleanup_upload_archives EXIT",
        'for index in "${!images_to_upload[@]}"',
        'image="${images_to_upload[$index]}"',
        'docker save "$1" | gzip -1 > "$2"',
        'stat -c %s "$archive"',
        'stat -f %z "$archive"',
        'timeout --kill-after=30s "$IMAGE_UPLOAD_TIMEOUT_SECONDS"',
        "bash -o pipefail -c 'gunzip | docker load'",
        "服务器镜像查询失败",
        "服务器 Docker 容量不足",
        "image_size * 2 + REMOTE_DOCKER_SAFETY_BYTES",
        "镜像归档完成",
        "开始传输并导入镜像",
        "镜像传输并导入完成",
        "镜像传输或导入失败",
        "服务器镜像查询失败：${service}，退出码 ${current_status}",
    ):
        assert contract in source


def test_source_upload_validates_sha_and_has_bounded_ssh_retry() -> None:
    source = SOURCE_UPLOAD.read_text(encoding="utf-8")

    for contract in (
        'case "$DEPLOY_SHA" in',
        "部署提交必须是 40 位小写十六进制 SHA",
        'SOURCE_UPLOAD_TIMEOUT_SECONDS="${SOURCE_UPLOAD_TIMEOUT_SECONDS:-600}"',
        'SOURCE_UPLOAD_ATTEMPTS="${SOURCE_UPLOAD_ATTEMPTS:-3}"',
        'if [ "$upload_status" -ne 255 ]',
        "部署源码 bundle 上传失败，等待后重试",
        "部署源码 bundle 上传连续失败",
    ):
        assert contract in source


def test_deploy_scripts_contain_no_destructive_or_dynamic_trust_commands() -> None:
    source = "\n".join(
        path.read_text(encoding="utf-8") for path in (UPLOAD, SOURCE_UPLOAD, DEPLOY)
    ).lower()

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

    assert "退出码：${original_status}）" in DEPLOY.read_text(encoding="utf-8")
    assert "schema_profile_for_settings" in DEPLOY.read_text(encoding="utf-8")
    assert "profile=schema_profile_for_settings(settings)" in DEPLOY.read_text(encoding="utf-8")


def test_backup_files_default_to_private_permissions() -> None:
    source = BACKUP.read_text(encoding="utf-8")

    assert "umask 077" in source


def test_execution_journal_backup_is_consistent_and_verifiable() -> None:
    source = BACKUP.read_text(encoding="utf-8")

    for contract in (
        "redis-cli --rdb",
        "redis-check-rdb",
        "aof_enabled:1",
        "aof_last_write_status:ok",
        "execution-journal.rdb",
        "snapshotSha256",
        "restoreRequiresNamedReconciliation=true",
        "postgresRestoreRequiresExecutionQuarantine=true",
        "requiresNamedCoreProviderReconciliation=true",
        "executionJournalIncluded=%s",
        "restoreWithoutExecutionJournalKeepsProviderCallsFailClosed=true",
        "recovery-boundary.meta",
        "inkforge:executions:restore:quarantine",
    ):
        assert contract in source


def test_execution_journal_restore_is_quarantined_until_named_reconciliation() -> None:
    restore = EXECUTION_RESTORE.read_text(encoding="utf-8")
    clear = EXECUTION_CLEAR_QUARANTINE.read_text(encoding="utf-8")

    assert "inkforge_execution_redis_restore_" in restore
    assert "恢复目标卷不是空卷" in restore
    assert "redis-check-rdb" in restore
    assert "inkforge:executions:restore:quarantine" in restore
    assert "WAITAOF 1 0 5000" in restore
    assert '[ "$local_aof_ack" = "1" ]' in restore
    assert "clear-execution-journal-quarantine.sh" not in restore
    assert "RECONCILIATION_REPORT_SHA256" in clear
    assert "CLEAR_EXECUTION_JOURNAL_QUARANTINE" in clear
    assert "restore:last-reconciliation" in clear
    assert "WAITAOF 1 0 5000" in clear
    assert '[ "$pre_local_aof_ack" = "1" ]' in clear
    assert '[ "$local_aof_ack" = "1" ]' in clear


def test_quarantine_clear_rejects_waitaof_zero(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _write_executable(
        bin_dir / "docker",
        "#!/bin/sh\n"
        'case " $* " in\n'
        "  *' WAITAOF '*) printf '0\\n0\\n'; exit 0 ;;\n"
        "  *' EVAL '*) printf '1\\n'; exit 0 ;;\n"
        "  *) exit 0 ;;\n"
        "esac\n",
    )
    snapshot_sha = "a" * 64
    report_sha = "b" * 64
    epoch = "restore-test"
    env = {
        **os.environ,
        "PATH": f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}",
        "EXECUTION_REDIS_CONTAINER": "execution-redis-test",
        "RESTORE_EPOCH": epoch,
        "SNAPSHOT_SHA256": snapshot_sha,
        "RECONCILIATION_REPORT_SHA256": report_sha,
        "CLEAR_CONFIRM_TOKEN": (
            f"CLEAR_EXECUTION_JOURNAL_QUARANTINE:{epoch}:{snapshot_sha}:{report_sha}"
        ),
    }

    result = subprocess.run(  # noqa: S603 - 仅执行仓库固定脚本与测试夹具
        [POSIX_SHELL, str(EXECUTION_CLEAR_QUARANTINE)],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0
    assert "拒绝解除 quarantine" in result.stderr


def test_rollback_drill_normalizes_schema_fingerprints_across_contract_versions() -> None:
    source = ROLLBACK_DRILL.read_text(encoding="utf-8")

    assert 'getattr(db_session, "schema_profile_for_settings"' in source
    assert "inspect.signature(guard.verify_live_schema).parameters" in source
    assert 'actual["contractVersion"] = 1' in source
    assert 'table.pop("checkConstraints", None)' in source
    assert "guard.canonical_fingerprint(actual)" in source


def _write_executable(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)


def _posix_path(path: Path) -> str:
    resolved = path.resolve()
    if os.name != "nt":
        return resolved.as_posix()
    return f"/{resolved.drive[0].lower()}{resolved.as_posix()[2:]}"


def _execution_manifest_fingerprint(path: Path) -> str:
    document = json.loads(path.read_text(encoding="utf-8"))
    canonical = json.dumps(
        document,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _run_upload(
    tmp_path: Path,
    *,
    current_status: int = 20,
    has_image_status: int = 20,
    upload_status: int = 0,
) -> tuple[subprocess.CompletedProcess[str], str, Path]:
    bin_dir = tmp_path / "bin"
    runner_temp = tmp_path / "runner"
    bin_dir.mkdir()
    runner_temp.mkdir()
    known_hosts = tmp_path / "known_hosts"
    known_hosts.write_text("example ssh-ed25519 fixture\n", encoding="utf-8")
    log_path = tmp_path / "upload.log"

    _write_executable(
        bin_dir / "docker",
        "#!/bin/sh\n"
        'printf \'docker %s\\n\' "$*" >> "$UPLOAD_LOG"\n'
        'case "$*" in\n'
        "  'image inspect --format={{.Id}} '*) echo 'sha256:fixture' ;;\n"
        "  'image inspect --format={{.Size}} '*) echo '1048576' ;;\n"
        "  save*) printf 'fixture-archive' ;;\n"
        "  *) exit 1 ;;\n"
        "esac\n",
    )
    _write_executable(
        bin_dir / "ssh",
        "#!/bin/sh\n"
        "command_text=''\n"
        'for argument in "$@"; do command_text=$argument; done\n'
        'printf \'ssh %s\\n\' "$command_text" >> "$UPLOAD_LOG"\n'
        'case "$command_text" in\n'
        "  *'DockerRootDir'*) echo '服务器 Docker 响应正常'; exit 0 ;;\n"
        "  *'container_id='*) exit \"$FAKE_CURRENT_STATUS\" ;;\n"
        "  *'required_bytes'*) echo '服务器 Docker 容量满足要求'; exit 0 ;;\n"
        '  *\'docker image inspect "$image_id"\'*) exit "$FAKE_HAS_IMAGE_STATUS" ;;\n'
        "  *'gunzip | docker load'*) cat >/dev/null; exit \"$FAKE_UPLOAD_STATUS\" ;;\n"
        "  *) exit 0 ;;\n"
        "esac\n",
    )
    _write_executable(
        bin_dir / "timeout",
        "#!/bin/sh\n"
        'while [ "$#" -gt 0 ]; do\n'
        '  case "$1" in --foreground|--kill-after=*) shift ;; *) break ;; esac\n'
        "done\n"
        "shift\n"
        'exec "$@"\n',
    )
    env = {
        **os.environ,
        "SERVER_HOST": "example.invalid",
        "SERVER_USER": "deploy",
        "SSH_KEY_PATH": _posix_path(tmp_path / "key"),
        "SSH_KNOWN_HOSTS_FILE": _posix_path(known_hosts),
        "INKFORGE_IMAGE_TAG": "a" * 40,
        "DEPLOY_SHA": "a" * 40,
        "RUNNER_TEMP": _posix_path(runner_temp),
        "UPLOAD_LOG": _posix_path(log_path),
        "FAKE_CURRENT_STATUS": str(current_status),
        "FAKE_HAS_IMAGE_STATUS": str(has_image_status),
        "FAKE_UPLOAD_STATUS": str(upload_status),
    }
    result = subprocess.run(  # noqa: S603 - 仅执行仓库脚本和测试夹具
        [
            POSIX_SHELL,
            "-c",
            'PATH="$1:$PATH"; export PATH; exec /bin/bash "$2"',
            "upload-test",
            _posix_path(bin_dir),
            _posix_path(UPLOAD),
        ],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=20,
        check=False,
    )
    log = log_path.read_text(encoding="utf-8") if log_path.exists() else ""
    return result, log, runner_temp


def test_upload_stops_when_the_server_image_query_fails(tmp_path: Path) -> None:
    result, log, _ = _run_upload(tmp_path, current_status=255)

    assert result.returncode != 0
    assert "服务器镜像查询失败：web，退出码 255" in result.stderr
    assert "docker save" not in log


def test_upload_processes_images_separately_and_cleans_archives(tmp_path: Path) -> None:
    result, log, runner_temp = _run_upload(tmp_path)

    assert result.returncode == 0, result.stderr
    assert log.count("docker save ") == 3
    assert log.count("gunzip | docker load") == 3
    assert list(runner_temp.iterdir()) == []


def test_upload_timeout_names_the_image_and_stage(tmp_path: Path) -> None:
    result, _, runner_temp = _run_upload(tmp_path, upload_status=124)

    assert result.returncode != 0
    assert "镜像传输或导入超时：inkforge-web:" in result.stderr
    assert list(runner_temp.iterdir()) == []


def _run_source_upload(
    tmp_path: Path,
    *,
    transient_failures: int = 0,
    terminal_status: int = 0,
) -> tuple[subprocess.CompletedProcess[str], str, Path]:
    bin_dir = tmp_path / "source-bin"
    runner_temp = tmp_path / "source-runner"
    bin_dir.mkdir()
    runner_temp.mkdir()
    known_hosts = tmp_path / "source-known-hosts"
    known_hosts.write_text("example ssh-ed25519 fixture\n", encoding="utf-8")
    log_path = tmp_path / "source-upload.log"
    counter_path = tmp_path / "source-upload-count"
    deploy_sha = "b" * 40

    _write_executable(
        bin_dir / "git",
        "#!/bin/sh\n"
        'printf \'git %s\\n\' "$*" >> "$SOURCE_UPLOAD_LOG"\n'
        'case "$*" in\n'
        "  *'rev-parse HEAD') printf '%s\\n' \"$DEPLOY_SHA\" ;;\n"
        "  *'bundle create '*)\n"
        "    previous=''\n"
        "    for value in \"$@\"; do\n"
        "      [ \"$previous\" != create ] || { printf 'bundle-fixture' > \"$value\"; exit 0; }\n"
        "      previous=$value\n"
        "    done\n"
        "    exit 1 ;;\n"
        "  *'bundle verify '*) exit 0 ;;\n"
        "  *'bundle list-heads '*) printf '%s HEAD\\n' \"$DEPLOY_SHA\" ;;\n"
        "  *) exit 1 ;;\n"
        "esac\n",
    )
    _write_executable(
        bin_dir / "scp",
        "#!/bin/sh\n"
        'printf \'scp %s\\n\' "$*" >> "$SOURCE_UPLOAD_LOG"\n'
        "count=0\n"
        '[ ! -f "$SOURCE_UPLOAD_COUNTER" ] || count=$(sed -n \'1p\' "$SOURCE_UPLOAD_COUNTER")\n'
        "count=$((count + 1))\n"
        'printf \'%s\\n\' "$count" > "$SOURCE_UPLOAD_COUNTER"\n'
        'if [ "$count" -le "$SOURCE_TRANSIENT_FAILURES" ]; then exit 255; fi\n'
        'exit "$SOURCE_TERMINAL_STATUS"\n',
    )
    _write_executable(
        bin_dir / "ssh",
        "#!/bin/sh\n"
        "command_text=''\n"
        'for argument in "$@"; do command_text=$argument; done\n'
        'printf \'ssh %s\\n\' "$command_text" >> "$SOURCE_UPLOAD_LOG"\n'
        "exit 0\n",
    )
    _write_executable(
        bin_dir / "timeout",
        "#!/bin/sh\n"
        'while [ "$#" -gt 0 ]; do\n'
        '  case "$1" in --foreground|--kill-after=*) shift ;; *) break ;; esac\n'
        "done\n"
        "shift\n"
        'exec "$@"\n',
    )
    env = {
        **os.environ,
        "SERVER_HOST": "example.invalid",
        "SERVER_USER": "deploy",
        "SSH_KEY_PATH": _posix_path(tmp_path / "source-key"),
        "SSH_KNOWN_HOSTS_FILE": _posix_path(known_hosts),
        "DEPLOY_SHA": deploy_sha,
        "RUNNER_TEMP": _posix_path(runner_temp),
        "SOURCE_UPLOAD_LOG": _posix_path(log_path),
        "SOURCE_UPLOAD_COUNTER": _posix_path(counter_path),
        "SOURCE_TRANSIENT_FAILURES": str(transient_failures),
        "SOURCE_TERMINAL_STATUS": str(terminal_status),
    }
    result = subprocess.run(  # noqa: S603 - 仅执行仓库脚本和测试夹具
        [
            POSIX_SHELL,
            "-c",
            'PATH="$1:$PATH"; export PATH; exec /bin/bash "$2"',
            "source-upload-test",
            _posix_path(bin_dir),
            _posix_path(SOURCE_UPLOAD),
        ],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=20,
        check=False,
    )
    log = log_path.read_text(encoding="utf-8") if log_path.exists() else ""
    return result, log, runner_temp


def test_source_upload_creates_bundle_and_atomically_promotes_remote_file(
    tmp_path: Path,
) -> None:
    result, log, runner_temp = _run_source_upload(tmp_path)

    assert result.returncode == 0, result.stderr
    assert " bundle create " in log
    assert log.count("scp ") == 1
    assert "chmod 600 '/tmp/inkforge-deploy-" in log
    assert ".bundle.partial' '/tmp/inkforge-deploy-" in log
    assert list(runner_temp.iterdir()) == []


def test_source_upload_retries_only_transient_ssh_failure(tmp_path: Path) -> None:
    result, log, runner_temp = _run_source_upload(tmp_path, transient_failures=1)

    assert result.returncode == 0, result.stderr
    assert log.count("scp ") == 2
    assert "部署源码 bundle 上传失败，等待后重试第 2/3 次" in result.stderr
    assert list(runner_temp.iterdir()) == []


def test_source_upload_does_not_retry_deterministic_scp_failure(tmp_path: Path) -> None:
    result, log, runner_temp = _run_source_upload(tmp_path, terminal_status=7)

    assert result.returncode == 7
    assert log.count("scp ") == 1
    assert "部署源码 bundle 上传失败，退出码 7" in result.stderr
    assert list(runner_temp.iterdir()) == []


def _run_deploy(
    tmp_path: Path,
    *,
    previous_state: str,
    new_status: int = 0,
    rollback_status: int = 0,
    schema_verify_status: int = 0,
    agent_ready_sequence: str = "",
    agent_log_init_status: int = 0,
    upload_init_status: int = 0,
    migration_state: str = "migrated",
    migration_up_fail_attempt: int = 0,
    migration_down_status: int = 0,
    durable_migration_state: str = "unmigrated",
    durable_schema_ready: bool = False,
    durable_route_mode: str = "off",
    durable_user_allowlist: str = "user-canary",
    durable_novel_allowlist: str = "novel-canary",
    v1_fresh_starts: bool = False,
    core_v2_aware_status: int = 0,
    agent_v2_aware_status: int = 0,
    target_agent_manifest_fingerprint: str | None = None,
    rollback_agent_manifest_fingerprint: str | None = None,
    active_v2_run_count: int = 0,
    running_core_route_mode: str | None = None,
    new_core_runtime: str = "java",
    previous_core_runtime: str = "",
    deploy_sha: str | None = None,
    deploy_bundle: bool = True,
    protected_manifest: bool = True,
    protected_lock: bool = True,
    verified_drain: bool = True,
    boundary_consume_status: int = 0,
    boundary_applied_status: int = 0,
    real_release_driver: bool = False,
    release_fault_point: str = "",
) -> tuple[subprocess.CompletedProcess[str], str]:
    app_dir = tmp_path / "app"
    control_dir = tmp_path / "control"
    bin_dir = tmp_path / "bin"
    (app_dir / ".git").mkdir(parents=True)
    (app_dir / "infra" / "secrets").mkdir(parents=True)
    (app_dir / "scripts").mkdir(parents=True)
    (app_dir / "contracts" / "agent-execution").mkdir(parents=True)
    (control_dir / "scripts" / "migrations").mkdir(parents=True)
    (control_dir / "infra" / "nginx").mkdir(parents=True)
    (control_dir / "contracts" / "agent-execution").mkdir(parents=True)
    bin_dir.mkdir()
    deploy_sha = deploy_sha or hashlib.sha1(  # noqa: S324
        str(tmp_path).encode()
    ).hexdigest()
    deploy_route_mode = "off" if durable_route_mode == "allowlist" else durable_route_mode
    (app_dir / ".env").write_text(
        "DATABASE_URL=postgresql+asyncpg://user:pass@host.docker.internal:5432/novelwriter\n"
        f"DURABLE_AGENT_EXECUTION_SCHEMA_READY={'true' if durable_schema_ready else 'false'}\n"
        f"DURABLE_AGENT_EXECUTION_ROUTE_MODE={deploy_route_mode}\n"
        f"DURABLE_AGENT_EXECUTION_USER_ALLOWLIST={durable_user_allowlist}\n"
        f"DURABLE_AGENT_EXECUTION_NOVEL_ALLOWLIST={durable_novel_allowlist}\n"
        f"V1_FRESH_AGENT_STARTS_ENABLED={'true' if v1_fresh_starts else 'false'}\n",
        encoding="utf-8",
    )
    (app_dir / "infra" / "compose.yaml").write_text(
        "services:\n  core-api:\n    extra_hosts:\n      - host.docker.internal:host-gateway\n",
        encoding="utf-8",
    )
    shutil.copy2(
        ROOT / "infra" / "compose.python-core-rollback.yaml",
        app_dir / "infra" / "compose.python-core-rollback.yaml",
    )
    for key_file in (
        "core-to-agent-private.pem",
        "core-to-agent-jwks.json",
        "agent-to-core-private.pem",
        "agent-to-core-jwks.json",
    ):
        (app_dir / "infra" / "secrets" / key_file).write_text("fixture", encoding="utf-8")
    shutil.copy2(ROOT / "scripts" / "compose_smoke.sh", app_dir / "scripts")
    (app_dir / "scripts" / "compose_smoke.sh").chmod(0o755)
    shutil.copy2(ROOT / "scripts" / "agent_readiness_probe.py", app_dir / "scripts")
    source_manifest = ROOT / "contracts" / "agent-execution" / "manifest.json"
    fixture_manifest = app_dir / "contracts" / "agent-execution" / "manifest.json"
    shutil.copy2(source_manifest, fixture_manifest)
    shutil.copy2(
        source_manifest,
        control_dir / "contracts" / "agent-execution" / "manifest.json",
    )
    expected_manifest_fingerprint = _execution_manifest_fingerprint(fixture_manifest)
    target_agent_manifest_fingerprint = (
        target_agent_manifest_fingerprint or expected_manifest_fingerprint
    )
    rollback_agent_manifest_fingerprint = (
        rollback_agent_manifest_fingerprint or expected_manifest_fingerprint
    )
    scope_user = durable_user_allowlist or "user-canary"
    scope_novel = durable_novel_allowlist or "novel-canary"
    canary_scope_sha256 = hashlib.sha256(
        json.dumps(
            {"novelId": scope_novel, "userId": scope_user},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    manifest_dir = tmp_path / "release-manifest"
    manifest_sha256 = ""
    if protected_manifest:
        manifest_result = subprocess.run(  # noqa: S603 - 固定 helper 与测试输入
            [
                sys.executable,
                str(RELEASE_MANIFEST_HELPER),
                "create",
                "--repository-root",
                str(ROOT),
                "--output-dir",
                str(manifest_dir),
                "--workflow-trusted-commit",
                deploy_sha,
                "--target-release-commit",
                deploy_sha,
                "--rollback-source-release-commit",
                "f" * 40,
                "--cli-commit",
                deploy_sha,
                "--development-evidence-sha256",
                "7" * 64,
                "--control-bundle-sha256",
                CONTROL_BUNDLE_SHA,
                "--rollback-source-receipt-sha256",
                ROLLBACK_SOURCE_RECEIPT_SHA,
                "--producer-run-id",
                "123",
                "--producer-run-attempt",
                "1",
                "--producer-repository",
                "owner/repo",
                "--canary-scope-sha256",
                canary_scope_sha256,
                "--route-mode",
                "allowlist" if durable_route_mode == "allowlist" else "off",
                "--target-web-digest",
                TARGET_WEB_DIGEST,
                "--target-core-digest",
                TARGET_CORE_DIGEST,
                "--target-agent-digest",
                TARGET_AGENT_DIGEST,
                "--rollback-web-digest",
                ROLLBACK_WEB_DIGEST,
                "--rollback-core-digest",
                ROLLBACK_CORE_DIGEST,
                "--rollback-agent-digest",
                ROLLBACK_AGENT_DIGEST,
                "--target-manifest-fingerprint",
                target_agent_manifest_fingerprint,
                "--rollback-manifest-fingerprint",
                rollback_agent_manifest_fingerprint,
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        if manifest_result.returncode != 0:
            return manifest_result, ""
        manifest_sha256 = hashlib.sha256(
            (manifest_dir / "release-manifest.json").read_bytes()
        ).hexdigest()
    _write_executable(
        app_dir / "scripts" / "token-usage-production-migration.sh",
        "#!/bin/sh\n"
        "action=$1\n"
        'printf \'migration %s\\n\' "$action" >> "$FAKE_DOCKER_LOG"\n'
        "state_file=$FAKE_MIGRATION_STATE_FILE\n"
        'case "$action" in\n'
        "  status)\n"
        '    if [ -f "$state_file" ]; then sed -n \'1p\' "$state_file"; '
        "else printf '%s\\n' \"$FAKE_MIGRATION_STATE\"; fi ;;\n"
        "  backup) exit 0 ;;\n"
        "  up)\n"
        '    count=0; [ ! -f "$FAKE_MIGRATION_UP_COUNT" ] || '
        "count=$(sed -n '1p' \"$FAKE_MIGRATION_UP_COUNT\")\n"
        '    count=$((count + 1)); printf \'%s\\n\' "$count" > "$FAKE_MIGRATION_UP_COUNT"\n'
        '    [ "$count" -ne "$FAKE_MIGRATION_UP_FAIL_ATTEMPT" ] || exit 31\n'
        "    printf 'migrated\\n' > \"$state_file\" ;;\n"
        "  down)\n"
        '    [ "$FAKE_MIGRATION_DOWN_STATUS" -eq 0 ] || exit "$FAKE_MIGRATION_DOWN_STATUS"\n'
        "    printf 'unmigrated\\n' > \"$state_file\" ;;\n"
        "  *) exit 2 ;;\n"
        "esac\n",
    )
    _write_executable(
        app_dir / "scripts" / "durable-agent-execution-migration.sh",
        "#!/bin/sh\n"
        'printf \'durable-migration %s %s\\n\' "$1" "$2" >> "$FAKE_DOCKER_LOG"\n'
        "[ \"$2\" = 'novelwriter' ] || exit 2\n"
        'case "$1" in\n'
        "  status) printf '%s\\n' \"$FAKE_DURABLE_MIGRATION_STATE\" ;;\n"
        "  active-v2-count) printf '%s\\n' \"$FAKE_ACTIVE_V2_RUN_COUNT\" ;;\n"
        "  boundary-drain)\n"
        "    [ -n \"${FAKE_DRAIN_REPORT:-}\" ] || exit 1\n"
        "    python3 - \"$FAKE_DRAIN_REPORT\" <<'PY'\n"
        "import json\n"
        "import sys\n"
        "from datetime import UTC, datetime\n"
        "from pathlib import Path\n"
        "document = json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))\n"
        "document['capturedAt'] = datetime.now(UTC).isoformat().replace('+00:00', 'Z')\n"
        "print(json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(',', ':')))\n"
        "PY\n"
        "    ;;\n"
        "  *) exit 2 ;;\n"
        "esac\n",
    )
    _write_executable(
        app_dir / "scripts" / "verify-durable-agent-v2-image.sh",
        "#!/bin/sh\n"
        'printf \'v2-image %s %s %s\\n\' "$1" "$2" "${3:-<none>}" '
        '>> "$FAKE_DOCKER_LOG"\n'
        'case "$1" in\n'
        '  core) exit "${FAKE_CORE_V2_AWARE_STATUS:-0}" ;;\n'
        "  agent)\n"
        '    [ "${FAKE_AGENT_V2_AWARE_STATUS:-0}" -eq 0 ] '
        '      || exit "$FAKE_AGENT_V2_AWARE_STATUS"\n'
        '    case "$2" in\n'
        '      inkforge-agent-service:"$FAKE_NEW_TAG") '
        '        actual="$FAKE_TARGET_AGENT_MANIFEST_FINGERPRINT" ;;\n'
        '      *) actual="$FAKE_ROLLBACK_AGENT_MANIFEST_FINGERPRINT" ;;\n'
        "    esac\n"
        '    [ -z "${3:-}" ] || [ "$3" = "$actual" ] || exit 29\n'
        "    printf 'v2-aware-image-ok:agent:%s\\n' \"$actual\"\n"
        "    ;;\n"
        "  *) exit 2 ;;\n"
        "esac\n",
    )
    for name in (
        "token-usage-production-migration.sh",
        "durable-agent-execution-migration.sh",
        "verify-durable-agent-v2-image.sh",
    ):
        shutil.copy2(app_dir / "scripts" / name, control_dir / "scripts" / name)
    for name in (
        "20260823_token_usage_details.production.sql",
        "rollback_20260823_token_usage_details.sql",
    ):
        shutil.copy2(
            ROOT / "scripts" / "migrations" / name,
            control_dir / "scripts" / "migrations" / name,
        )
    shutil.copy2(ROOT / "scripts" / "compose_smoke.sh", control_dir / "scripts")
    shutil.copy2(ROOT / "scripts" / "agent_readiness_probe.py", control_dir / "scripts")
    shutil.copy2(ROOT / "infra" / "compose.yaml", control_dir / "infra" / "compose.yaml")
    shutil.copy2(
        ROOT / "infra" / "compose.python-core-rollback.yaml",
        control_dir / "infra" / "compose.python-core-rollback.yaml",
    )
    shutil.copy2(
        ROOT / "infra" / "compose.durable-agent-release-guard.yaml",
        control_dir / "infra" / "compose.durable-agent-release-guard.yaml",
    )
    shutil.copy2(
        ROOT / "infra" / "nginx" / "nginx.conf",
        control_dir / "infra" / "nginx" / "nginx.conf",
    )
    _write_executable(
        control_dir / "scripts" / "durable_agent_v2_control_bundle.py",
        "#!/usr/bin/env python3\n"
        "import os\n"
        "print('control-bundle-verified:' + os.environ['DURABLE_AGENT_CONTROL_BUNDLE_SHA256'])\n",
    )
    if real_release_driver:
        shutil.copy2(RELEASE_DRIVER, control_dir / "scripts" / RELEASE_DRIVER.name)
        shutil.copy2(
            RELEASE_BOUNDARY_HELPER,
            control_dir / "scripts" / RELEASE_BOUNDARY_HELPER.name,
        )
        shutil.copy2(
            RELEASE_GUARD_HELPER,
            control_dir / "scripts" / RELEASE_GUARD_HELPER.name,
        )
        shutil.copy2(
            JOINT_DRAIN_HELPER,
            control_dir / "scripts" / JOINT_DRAIN_HELPER.name,
        )
        (control_dir / "control-bundle.json").write_text(
            json.dumps(
                {
                    "workflowTrustedCommit": deploy_sha,
                    "targetReleaseCommit": deploy_sha,
                    "producerRunId": "123",
                    "producerRunAttempt": "1",
                }
            ),
            encoding="utf-8",
        )
    else:
        _write_executable(
            control_dir / "scripts" / "durable-agent-v2-release.sh",
            "#!/bin/sh\n"
            'printf \'release-driver %s %s\\n\' "$1" "${2:-}" '
            '>> "$FAKE_DOCKER_LOG"\n'
            'case "$1" in\n'
            "  verify-drain-binding)\n"
            '    [ -n "${VERIFIED_DRAIN_SHA256:-}" ] || exit 1\n'
            "    printf 'verified-drain-binding-ok:%s\\n' "
            '"$VERIFIED_DRAIN_SHA256" ;;\n'
            "  consume-live-boundary) exit \"${FAKE_BOUNDARY_CONSUME_STATUS:-0}\" ;;\n"
            "  mark-live-boundary-applied)\n"
            '    state="$APP_DIR/.durable-agent-v2-release-transactions/'
            '$DURABLE_AGENT_RELEASE_LOCK_ID/state"\n'
            '    state_value=$(sed -n \'1p\' "$state")\n'
            '    outcome=${DURABLE_AGENT_BOUNDARY_OUTCOME:-succeeded}\n'
            '    printf \'release-boundary-state %s %s\\n\' '
            '"$state_value" "$outcome" >> "$FAKE_DOCKER_LOG"\n'
            '    [ "$state_value" = active ] || exit 41\n'
            '    [ "${FAKE_BOUNDARY_APPLIED_STATUS:-0}" -eq 0 ] '
            '|| exit "$FAKE_BOUNDARY_APPLIED_STATUS"\n'
            '    printf \'release-boundary-applied %s\\n\' "$outcome" '
            '>> "$FAKE_DOCKER_LOG" ;;\n'
            "  mark-transaction-failed)\n"
            '    state="$APP_DIR/.durable-agent-v2-release-transactions/'
            '$DURABLE_AGENT_RELEASE_LOCK_ID/state"\n'
            '    state_value=$(sed -n \'1p\' "$state")\n'
            '    printf \'release-failed-state %s\\n\' "$state_value" '
            '>> "$FAKE_DOCKER_LOG"\n'
            '    case "$state_value" in\n'
            "      active)\n"
            '        printf \'failed\\n\' > "${state}.partial"\n'
            '        chmod 600 "${state}.partial"\n'
            '        mv -f "${state}.partial" "$state" ;;\n'
            "      failed) ;;\n"
            "      *) exit 41 ;;\n"
            "    esac ;;\n"
            "  *) exit 2 ;;\n"
            "esac\n",
        )
    shutil.copy2(FAKE_DOCKER, bin_dir / "docker")
    (bin_dir / "docker").chmod(0o755)
    _write_executable(
        bin_dir / "git",
        "#!/bin/sh\n"
        'while [ "${1:-}" = "-c" ]; do shift 2; done\n'
        'printf \'git %s\\n\' "$*" >> "$FAKE_DOCKER_LOG"\n'
        'if [ "${1:-}" = "rev-parse" ]; then printf \'%s\\n\' "$DEPLOY_SHA"; fi\n'
        "exit 0\n",
    )
    _write_executable(
        bin_dir / "stat",
        "#!/bin/sh\n"
        'case "$*" in\n'
        "  *%u*) echo 10001 ;;\n"
        "  *%g*) echo 10001 ;;\n"
        "  *%a*)\n"
        '    for path in "$@"; do :; done\n'
        '    if [ -d "$path" ]; then echo 700; else echo 600; fi ;;\n'
        "esac\n",
    )
    _write_executable(
        bin_dir / "curl",
        "#!/bin/sh\n"
        'case "$*" in '
        "*write-out*) printf 404;; "
        '*health/ready*) printf \'{"status":"ready","checks":{"agent":"ok"}}\';; '
        "esac\n",
    )
    log_path = tmp_path / "docker.log"
    agent_counter_path = tmp_path / "agent-ready-counter"
    migration_state_path = tmp_path / "migration-state"
    migration_up_count_path = tmp_path / "migration-up-count"
    snapshot_state_dir = tmp_path / "snapshot-state"
    snapshot_state_dir.mkdir()
    drain_report_path = tmp_path / "live-drain.json"
    drain_report_path.write_text(
        json.dumps(
            {
                "capturedAt": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
                "coreRuntime": {
                    "containerId": "c" * 64,
                    "imageId": ROLLBACK_CORE_DIGEST,
                    "routeMode": "off",
                    "schemaReady": False,
                    "v1FreshStartsEnabled": False,
                },
                "database": "novelwriter",
                "executionRedisIdentity": {
                    "containerId": "e" * 64,
                    "imageId": "sha256:" + "8" * 64,
                    "redisRunId": "9" * 40,
                },
                "format": "inkforge-durable-agent-v2-live-drain/1",
                "mode": "pre-contract",
                "postgresIdentity": {
                    "databaseOid": "1",
                    "serverAddress": "127.0.0.1",
                    "serverPort": "5432",
                    "serverVersionNum": "170000",
                },
                "redisIdentity": {
                    "containerId": "d" * 64,
                    "imageId": "sha256:" + "7" * 64,
                    "redisRunId": "8" * 40,
                },
                "runtimeTopologySha256": "a" * 64,
                "schemaState": "unmigrated",
                "sourceReportSha256": "b" * 64,
                "zeroDrain": True,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n",
        encoding="utf-8",
    )
    # 必须使用与生产脚本相同的固定目录，SHA 让并行测试互不覆盖。
    bundle_root = Path("/tmp")  # noqa: S108
    bundle_path = bundle_root / f"inkforge-deploy-{deploy_sha}.bundle"
    if deploy_bundle:
        bundle_path.write_text("bundle fixture", encoding="utf-8")
    lock_id = "d" * 64
    lock_root = app_dir / ".durable-agent-v2-release-transactions"
    lock_dir = lock_root / lock_id
    lock_file = app_dir / ".durable-agent-v2-release-transaction.lock"
    if protected_lock:
        lock_dir.mkdir(mode=0o700, parents=True)
        owner = lock_dir / "owner"
        owner.write_text(
            "\n".join(
                (
                    "format=2",
                    f"lockId={lock_id}",
                    "runId=123",
                    "runAttempt=1",
                    (
                        "operation=allowlist_release"
                        if durable_route_mode == "allowlist"
                        else "operation=route_off_release"
                    ),
                    f"workflowTrustedCommit={deploy_sha}",
                    f"targetReleaseCommit={deploy_sha}",
                    f"controlBundleSha256={CONTROL_BUNDLE_SHA}",
                    "",
                )
            ),
            encoding="ascii",
        )
        owner.chmod(0o600)
        os.link(owner, lock_file)
        state = lock_dir / "state"
        state.write_text("active\n", encoding="ascii")
        state.chmod(0o600)
        if real_release_driver:
            base_receipt = lock_dir / "base-receipt.sha256"
            base_receipt.write_text("0" * 64 + "\n", encoding="ascii")
            base_receipt.chmod(0o600)
    env = {
        **os.environ,
        "APP_DIR": _posix_path(app_dir),
        "DEPLOY_SHA": deploy_sha,
        "INKFORGE_IMAGE_TAG": "new-tag",
        "DURABLE_AGENT_RELEASE_MANIFEST_DIR": _posix_path(manifest_dir),
        "RELEASE_MANIFEST_DIR": _posix_path(manifest_dir),
        "DURABLE_AGENT_RELEASE_OPERATION": "release",
        "WORKFLOW_TRUSTED_COMMIT": deploy_sha,
        "TARGET_RELEASE_COMMIT": deploy_sha,
        "RELEASE_MANIFEST_SHA256": manifest_sha256,
        "RELEASE_ACTION": (
            "allowlist_release"
            if durable_route_mode == "allowlist"
            else "route_off_release"
        ),
        "DURABLE_AGENT_RELEASE_LOCK_ID": lock_id,
        "DURABLE_AGENT_CONTROL_BUNDLE_DIR": _posix_path(control_dir),
        "DURABLE_AGENT_CONTROL_BUNDLE_SHA256": CONTROL_BUNDLE_SHA,
        "DEPLOY_RUNTIME_ROUTE_MODE": "off",
        "GITHUB_ACTIONS": "true",
        "GITHUB_EVENT_NAME": "workflow_dispatch",
        "GITHUB_REF": "refs/heads/main",
        "GITHUB_SHA": deploy_sha,
        "GITHUB_RUN_ID": "123",
        "GITHUB_RUN_ATTEMPT": "1",
        "INKFORGE_RELEASE_APPROVED_ENVIRONMENT": "production",
        "FAKE_DOCKER_LOG": _posix_path(log_path),
        "FAKE_NEW_TAG": "new-tag",
        "FAKE_NEW_CORE_RUNTIME": new_core_runtime,
        "FAKE_PREVIOUS_CORE_RUNTIME": previous_core_runtime,
        "FAKE_PREVIOUS_STATE": previous_state,
        "FAKE_NEW_UP_STATUS": str(new_status),
        "FAKE_ROLLBACK_UP_STATUS": str(rollback_status),
        "FAKE_SCHEMA_VERIFY_STATUS": str(schema_verify_status),
        "FAKE_AGENT_READY_COUNTER": _posix_path(agent_counter_path),
        "FAKE_AGENT_READY_SEQUENCE": agent_ready_sequence,
        "FAKE_AGENT_LOG_INIT_STATUS": str(agent_log_init_status),
        "FAKE_UPLOAD_INIT_STATUS": str(upload_init_status),
        "FAKE_MIGRATION_STATE": migration_state,
        "FAKE_MIGRATION_STATE_FILE": _posix_path(migration_state_path),
        "FAKE_MIGRATION_UP_COUNT": _posix_path(migration_up_count_path),
        "FAKE_MIGRATION_UP_FAIL_ATTEMPT": str(migration_up_fail_attempt),
        "FAKE_MIGRATION_DOWN_STATUS": str(migration_down_status),
        "FAKE_DURABLE_MIGRATION_STATE": durable_migration_state,
        "FAKE_DRAIN_REPORT": _posix_path(drain_report_path),
        "FAKE_CORE_V2_AWARE_STATUS": str(core_v2_aware_status),
        "FAKE_AGENT_V2_AWARE_STATUS": str(agent_v2_aware_status),
        "FAKE_TARGET_AGENT_MANIFEST_FINGERPRINT": target_agent_manifest_fingerprint,
        "FAKE_ROLLBACK_AGENT_MANIFEST_FINGERPRINT": rollback_agent_manifest_fingerprint,
        "FAKE_ACTIVE_V2_RUN_COUNT": str(active_v2_run_count),
        "FAKE_RUNNING_CORE_ROUTE_MODE": (
            running_core_route_mode
            or ("off" if durable_route_mode == "allowlist" else durable_route_mode)
        ),
        "FAKE_RUNNING_CORE_SCHEMA_READY": (
            "true" if durable_schema_ready else "false"
        ),
        "FAKE_RUNNING_CORE_USER_ALLOWLIST": durable_user_allowlist,
        "FAKE_RUNNING_CORE_NOVEL_ALLOWLIST": durable_novel_allowlist,
        "FAKE_RUNNING_CORE_V1_FRESH_STARTS": (
            "true" if v1_fresh_starts else "false"
        ),
        "FAKE_TARGET_WEB_DIGEST": TARGET_WEB_DIGEST,
        "FAKE_TARGET_CORE_DIGEST": TARGET_CORE_DIGEST,
        "FAKE_TARGET_AGENT_DIGEST": TARGET_AGENT_DIGEST,
        "FAKE_ROLLBACK_WEB_DIGEST": ROLLBACK_WEB_DIGEST,
        "FAKE_ROLLBACK_CORE_DIGEST": ROLLBACK_CORE_DIGEST,
        "FAKE_ROLLBACK_AGENT_DIGEST": ROLLBACK_AGENT_DIGEST,
        "FAKE_BOUNDARY_CONSUME_STATUS": str(boundary_consume_status),
        "FAKE_BOUNDARY_APPLIED_STATUS": str(boundary_applied_status),
        "FAKE_SNAPSHOT_STATE_DIR": _posix_path(snapshot_state_dir),
        "SMOKE_AGENT_MAX_ATTEMPTS": "1",
        "SMOKE_AGENT_REQUIRED_SUCCESSES": "1",
        "SMOKE_AGENT_POLL_SECONDS": "0",
    }
    if release_fault_point:
        env["DURABLE_AGENT_RELEASE_FAULT_POINT"] = release_fault_point
        env["INKFORGE_LOCAL_RELEASE_TEST_MODE"] = "true"
    if real_release_driver:
        env["PATH"] = f"{Path(sys.executable).parent}:{env['PATH']}"
    if deploy_bundle:
        env["DEPLOY_BUNDLE_PATH"] = bundle_path.as_posix()
    if verified_drain and real_release_driver and protected_lock and protected_manifest:
        prepared = subprocess.run(  # noqa: S603 - 隔离 fake runtime 下执行真实发布 driver
            [
                POSIX_SHELL,
                str(control_dir / "scripts" / RELEASE_DRIVER.name),
                "prepare-release",
            ],
            cwd=ROOT,
            env={**env, "PATH": f"{bin_dir}:{env['PATH']}"},
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=60,
            check=False,
        )
        if prepared.returncode != 0:
            bundle_path.unlink(missing_ok=True)
            return prepared, log_path.read_text(encoding="utf-8")
        prefix = "prepare-release-ok:verifiedDrain:"
        if not prepared.stdout.startswith(prefix):
            bundle_path.unlink(missing_ok=True)
            return prepared, log_path.read_text(encoding="utf-8")
        env["VERIFIED_DRAIN_SHA256"] = prepared.stdout.strip().removeprefix(prefix)
    elif verified_drain:
        env["VERIFIED_DRAIN_SHA256"] = "a" * 64
    if not protected_manifest:
        env.pop("DURABLE_AGENT_RELEASE_MANIFEST_DIR", None)
        env.pop("RELEASE_MANIFEST_DIR", None)
    if not protected_lock:
        lock_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    result = subprocess.run(  # noqa: S603 - 仅执行仓库内固定脚本和测试夹具
        [
            POSIX_SHELL,
            "-c",
            'PATH="$1:$PATH"; export PATH; exec /bin/sh "$2"',
            "deploy-test",
            _posix_path(bin_dir),
            _posix_path(DEPLOY),
        ],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60 if real_release_driver else 20,
        check=False,
    )
    bundle_path.unlink(missing_ok=True)
    return result, log_path.read_text(encoding="utf-8") if log_path.exists() else ""


@pytest.mark.parametrize(
    ("overrides", "expected_error"),
    [
        ({"protected_manifest": False}, "release manifest 目录"),
        ({"deploy_bundle": False}, "部署源码 bundle"),
        ({"protected_lock": False}, "release-lock-file"),
    ],
)
def test_protected_deploy_missing_manifest_bundle_or_lock_fails_before_actions(
    tmp_path: Path,
    overrides: dict[str, bool],
    expected_error: str,
) -> None:
    result, log = _run_deploy(
        tmp_path,
        previous_state="valid",
        **overrides,
    )

    assert result.returncode != 0
    assert expected_error in result.stderr
    assert "docker compose" not in log
    assert "migration " not in log
    assert "git " not in log


def test_deploy_fetches_from_bundle_without_contacting_origin_and_cleans_file(
    tmp_path: Path,
) -> None:
    # SHA-1 只用于生成 Git 风格测试标识，不承担密码学安全职责。
    deploy_sha = hashlib.sha1(str(tmp_path).encode()).hexdigest()  # noqa: S324
    bundle_root = Path("/tmp")  # noqa: S108
    bundle_path = bundle_root / f"inkforge-deploy-{deploy_sha}.bundle"
    try:
        result, log = _run_deploy(
            tmp_path,
            previous_state="valid",
            deploy_sha=deploy_sha,
            deploy_bundle=True,
        )

        assert result.returncode == 0, result.stderr
        assert f"fetch {bundle_path} HEAD" in log
        assert "fetch --depth=1 origin" not in log
        assert bundle_path.exists() is False
    finally:
        bundle_path.unlink(missing_ok=True)


def _full_stack_up_lines(log: str) -> list[str]:
    return [line for line in log.splitlines() if line.endswith(" up --no-build -d --wait")]


def _protected_rollback_tag(tmp_path: Path) -> str:
    deploy_sha = hashlib.sha1(str(tmp_path).encode()).hexdigest()  # noqa: S324
    return f"rollback-release-{deploy_sha}"


def _nginx_refresh_lines(log: str) -> list[str]:
    return [
        line
        for line in log.splitlines()
        if line.endswith(" up --no-build -d --wait --no-deps --force-recreate nginx")
    ]


def _deployment_up_events(log: str) -> list[tuple[str, str]]:
    events: list[tuple[str, str]] = []
    for line in log.splitlines():
        tag = line.split("|", 1)[0]
        if line.endswith(" up --no-build -d --wait"):
            events.append((tag, "全栈"))
        elif line.endswith(" up --no-build -d --wait --no-deps --force-recreate nginx"):
            events.append((tag, "Nginx"))
    return events


@pytest.mark.parametrize(
    ("state", "expected_status", "expected_up_count"),
    [
        ("none", 1, 0),
        ("partial", 1, 0),
        ("mismatch", 0, 1),
        ("valid", 0, 1),
        ("missing_image", 1, 0),
        ("invalid_repository", 1, 0),
        ("snapshot_tag_failure", 1, 0),
        ("snapshot_verify_mismatch", 1, 0),
        ("snapshot_existing_conflict", 1, 0),
    ],
)
def test_previous_image_state_is_validated_before_switch(
    tmp_path: Path,
    state: str,
    expected_status: int,
    expected_up_count: int,
) -> None:
    result, log = _run_deploy(tmp_path, previous_state=state)

    assert (result.returncode == 0) is (expected_status == 0), result.stderr
    assert len(_full_stack_up_lines(log)) == expected_up_count


def test_current_running_bundle_is_snapshotted_by_exact_image_id_before_switch(
    tmp_path: Path,
) -> None:
    result, log = _run_deploy(tmp_path, previous_state="mismatch")

    assert result.returncode == 0, result.stderr
    lines = log.splitlines()
    deploy_sha = hashlib.sha1(str(tmp_path).encode()).hexdigest()  # noqa: S324
    snapshot_tag = f"rollback-release-{deploy_sha}"
    expected_tags = [
        f"docker image tag {ROLLBACK_WEB_DIGEST} inkforge-web:{snapshot_tag}",
        f"docker image tag {ROLLBACK_CORE_DIGEST} inkforge-core-api:{snapshot_tag}",
        f"docker image tag {ROLLBACK_AGENT_DIGEST} inkforge-agent-service:{snapshot_tag}",
    ]
    for expected in expected_tags:
        matching_index = next(index for index, line in enumerate(lines) if expected in line)
        first_switch_index = next(
            index for index, line in enumerate(lines) if line.endswith(" up --no-build -d --wait")
        )
        assert matching_index < first_switch_index

    assert f"已冻结当前生产三服务精确回滚快照：{snapshot_tag}（python）" in result.stdout


def test_existing_conflicting_rollback_snapshot_is_not_overwritten(
    tmp_path: Path,
) -> None:
    result, log = _run_deploy(
        tmp_path,
        previous_state="snapshot_existing_conflict",
    )

    assert result.returncode != 0
    assert "回滚镜像标签已存在但指向另一镜像" in result.stderr
    assert not any(
        "docker image tag" in line and ":rollback-" in line
        for line in log.splitlines()
    )
    assert _full_stack_up_lines(log) == []


def test_successful_deployment_refreshes_nginx_with_new_tag(tmp_path: Path) -> None:
    result, log = _run_deploy(tmp_path, previous_state="valid")

    assert result.returncode == 0, result.stderr
    refresh_lines = _nginx_refresh_lines(log)
    assert [line.split("|", 1)[0] for line in refresh_lines] == ["tag=new-tag"]
    assert _deployment_up_events(log) == [
        ("tag=new-tag", "全栈"),
        ("tag=new-tag", "Nginx"),
    ]
    assert "exec -T core-api /usr/local/bin/inkforge-schema-guard" in log
    assert "exec -T core-api python -c" not in log


def test_deployment_initializes_persistent_volumes_before_version_switch(
    tmp_path: Path,
) -> None:
    result, log = _run_deploy(tmp_path, previous_state="valid")

    assert result.returncode == 0, result.stderr
    lines = log.splitlines()
    uploads_create_index = next(
        index for index, line in enumerate(lines) if "docker volume create inkforge_uploads" in line
    )
    uploads_init_index = next(
        index
        for index, line in enumerate(lines)
        if "source=inkforge_uploads,target=/data/uploads" in line
    )
    logs_create_index = next(
        index
        for index, line in enumerate(lines)
        if "docker volume create inkforge_agent_logs" in line
    )
    logs_init_index = next(
        index
        for index, line in enumerate(lines)
        if "source=inkforge_agent_logs,target=/data/agent-logs" in line
    )
    execution_create_index = next(
        index
        for index, line in enumerate(lines)
        if "docker volume create inkforge_execution_redis_data" in line
    )
    execution_init_index = next(
        index
        for index, line in enumerate(lines)
        if "source=inkforge_execution_redis_data,target=/data" in line
    )
    up_index = next(
        index for index, line in enumerate(lines) if line.endswith(" up --no-build -d --wait")
    )
    assert uploads_create_index < uploads_init_index < logs_create_index
    assert logs_create_index < logs_init_index < execution_create_index
    assert execution_create_index < execution_init_index < up_index
    for init_index in (uploads_init_index, logs_init_index):
        assert (
            "docker run --rm --network none --read-only --cap-drop ALL --cap-add CHOWN"
            in lines[init_index]
        )
        assert "--user 0:0" in lines[init_index]
        assert "--entrypoint /usr/bin/chown" in lines[init_index]
    assert "inkforge-core-api:new-tag 10001:10001 /data/uploads" in lines[uploads_init_index]
    assert "inkforge-agent-service:new-tag 10001:10001 /data/agent-logs" in lines[logs_init_index]
    assert "--entrypoint /bin/chown" in lines[execution_init_index]
    assert "redis:7.4-alpine 999:999 /data" in lines[execution_init_index]
    assert " -R " not in lines[execution_init_index]


def test_deployment_requires_java_core_label_and_uses_java_schema_guard() -> None:
    source = DEPLOY.read_text(encoding="utf-8")

    assert "cn.inkforge.core.runtime" in source
    assert "新 Core 镜像不是 Java runtime" in source
    assert "/usr/local/bin/inkforge-schema-guard" in source
    assert "compose_python_rollback" in source
    assert "compose.python-core-rollback.yaml" in source


def test_non_java_new_core_is_rejected_before_version_switch(tmp_path: Path) -> None:
    result, log = _run_deploy(
        tmp_path,
        previous_state="valid",
        new_core_runtime="",
    )

    assert result.returncode != 0
    assert "新 Core 镜像不是 Java runtime" in result.stderr
    assert _full_stack_up_lines(log) == []


def test_live_boundary_rejection_preserves_status_before_git_or_compose(
    tmp_path: Path,
) -> None:
    result, log = _run_deploy(
        tmp_path,
        previous_state="valid",
        boundary_consume_status=17,
    )

    assert result.returncode == 17
    assert "release-driver consume-live-boundary compose-release" in log
    assert "git reset --hard" not in log
    assert _full_stack_up_lines(log) == []


def test_agent_log_volume_initialization_failure_stops_before_version_switch(
    tmp_path: Path,
) -> None:
    result, log = _run_deploy(
        tmp_path,
        previous_state="valid",
        agent_log_init_status=19,
    )

    assert result.returncode == 19
    assert _full_stack_up_lines(log) == []


def test_upload_volume_initialization_failure_stops_before_version_switch(
    tmp_path: Path,
) -> None:
    result, log = _run_deploy(
        tmp_path,
        previous_state="valid",
        upload_init_status=17,
    )

    assert result.returncode == 17
    assert _full_stack_up_lines(log) == []


def test_failed_new_version_restores_previous_version_and_keeps_failure(
    tmp_path: Path,
) -> None:
    result, log = _run_deploy(
        tmp_path,
        previous_state="valid",
        new_status=23,
        rollback_status=0,
    )

    assert result.returncode != 0
    up_lines = _full_stack_up_lines(log)
    assert [line.split("|", 1)[0] for line in up_lines] == [
        "tag=new-tag",
        f"tag={_protected_rollback_tag(tmp_path)}",
    ]
    assert "compose.python-core-rollback.yaml ps" in log
    assert "compose.python-core-rollback.yaml" in up_lines[1]
    assert " exec -T core-api python -c" in log
    boundary_marker = "release-boundary-state active compensated"
    assert boundary_marker in log
    assert log.index(" exec -T core-api python -c") < log.index(boundary_marker)
    assert "release-boundary-applied compensated" in log
    assert log.index("release-boundary-applied compensated") < log.index(
        "release-failed-state active"
    )
    lock_state = (
        tmp_path
        / "app"
        / ".durable-agent-v2-release-transactions"
        / ("d" * 64)
        / "state"
    )
    assert lock_state.read_text(encoding="ascii") == "failed\n"
    assert "新版本部署失败，旧版本已恢复" in result.stdout
    assert "生产编排已启动" not in result.stdout


@pytest.mark.parametrize("durable_route_mode", ("off", "allowlist"))
def test_real_release_driver_settles_compensation_before_failed_without_receipt(
    tmp_path: Path,
    durable_route_mode: str,
) -> None:
    result, log = _run_deploy(
        tmp_path,
        previous_state="valid",
        new_status=23,
        rollback_status=0,
        real_release_driver=True,
        durable_route_mode=durable_route_mode,
    )

    assert result.returncode == 23
    up_lines = _full_stack_up_lines(log)
    assert [line.split("|", 1)[0] for line in up_lines] == [
        "tag=new-tag",
        f"tag={_protected_rollback_tag(tmp_path)}",
    ]
    nginx_lines = _nginx_refresh_lines(log)
    assert [line.split("|", 1)[0] for line in nginx_lines] == [
        f"tag={_protected_rollback_tag(tmp_path)}"
    ]
    runtime_probe = " exec -T core-api python -c"
    assert runtime_probe in log
    assert log.index(nginx_lines[0]) < log.index(runtime_probe)
    assert "--no-deps --force-recreate core-api" not in log

    lock_dir = (
        tmp_path
        / "app"
        / ".durable-agent-v2-release-transactions"
        / ("d" * 64)
    )
    state = lock_dir / "state"
    assert state.read_text(encoding="ascii") == "failed\n"
    evidence_dir = lock_dir / "boundary-evidence"
    claimed = list(evidence_dir.glob("*-compose-release.claimed.json"))
    applied = list(evidence_dir.glob("*-compose-release.applied.json"))
    assert len(claimed) == len(applied) == 1
    assert json.loads(applied[0].read_text(encoding="utf-8")) == {
        "boundary": "compose-release",
        "evidenceSha256": hashlib.sha256(claimed[0].read_bytes()).hexdigest(),
        "format": "inkforge-durable-agent-v2-boundary-applied/1",
        "lockId": "d" * 64,
        "outcome": "compensated",
        "sequence": 1,
    }
    # 真实 driver 只允许 active lock 落 applied；最终 state 的替换必须发生在其后。
    assert applied[0].stat().st_mtime_ns <= state.stat().st_mtime_ns
    receipt_root = tmp_path / "app" / ".durable-agent-v2-release-receipts"
    assert not receipt_root.exists()
    assert "新版本部署失败，旧版本已恢复" in result.stdout
    assert "生产编排已启动" not in result.stdout


def test_failed_new_version_does_not_claim_proven_compensation_when_marker_fails(
    tmp_path: Path,
) -> None:
    result, log = _run_deploy(
        tmp_path,
        previous_state="valid",
        new_status=23,
        rollback_status=0,
        real_release_driver=True,
        release_fault_point="boundary-before-applied",
    )

    assert result.returncode == 23
    assert len(_full_stack_up_lines(log)) == 2
    lock_state = (
        tmp_path
        / "app"
        / ".durable-agent-v2-release-transactions"
        / ("d" * 64)
        / "state"
    )
    assert lock_state.read_text(encoding="ascii") == "failed\n"
    evidence_dir = lock_state.parent / "boundary-evidence"
    assert len(list(evidence_dir.glob("*-compose-release.claimed.json"))) == 1
    assert list(evidence_dir.glob("*-compose-release.applied.json")) == []
    assert not (tmp_path / "app" / ".durable-agent-v2-release-receipts").exists()
    assert "旧版本已恢复" not in result.stdout
    assert "自动回滚也失败（退出码：90）" in result.stderr


def test_failed_new_version_restores_previous_java_with_java_guard(
    tmp_path: Path,
) -> None:
    result, log = _run_deploy(
        tmp_path,
        previous_state="valid",
        previous_core_runtime="java",
        new_status=23,
    )

    assert result.returncode == 23
    up_lines = _full_stack_up_lines(log)
    assert [line.split("|", 1)[0] for line in up_lines] == [
        "tag=new-tag",
        f"tag={_protected_rollback_tag(tmp_path)}",
    ]
    assert "compose.python-core-rollback.yaml" not in up_lines[1]
    assert log.count("exec -T core-api /usr/local/bin/inkforge-schema-guard") == 1
    assert "exec -T core-api python -c" not in log
    assert "新版本部署失败，旧版本已恢复" in result.stdout


def test_unknown_previous_core_runtime_stops_before_version_switch(
    tmp_path: Path,
) -> None:
    result, log = _run_deploy(
        tmp_path,
        previous_state="valid",
        previous_core_runtime="node",
    )

    assert result.returncode != 0
    assert "上一 Core 镜像 runtime 标签无法识别" in result.stderr
    assert _full_stack_up_lines(log) == []


def test_protected_deploy_rejects_removed_first_deployment_compatibility(
    tmp_path: Path,
) -> None:
    result, log = _run_deploy(
        tmp_path,
        previous_state="none",
        new_status=23,
    )

    assert result.returncode != 0
    assert _full_stack_up_lines(log) == []
    assert "verifiedDrain 前置门禁找不到当前 Core" in result.stderr
    assert "旧版本已恢复" not in result.stdout
    assert "生产编排已启动" not in result.stdout


def test_failed_rollback_reports_both_failures_without_success(
    tmp_path: Path,
) -> None:
    result, log = _run_deploy(
        tmp_path,
        previous_state="valid",
        new_status=23,
        rollback_status=24,
    )

    assert result.returncode != 0
    assert len(_full_stack_up_lines(log)) == 2
    assert "新版本部署失败" in result.stderr
    assert "自动回滚也失败" in result.stderr
    assert "release-boundary-state" not in log
    lock_state = (
        tmp_path
        / "app"
        / ".durable-agent-v2-release-transactions"
        / ("d" * 64)
        / "state"
    )
    assert lock_state.read_text(encoding="ascii") == "failed\n"
    assert "生产编排已启动" not in result.stdout


def test_failed_rollback_schema_verification_is_not_masked_by_smoke(
    tmp_path: Path,
) -> None:
    result, log = _run_deploy(
        tmp_path,
        previous_state="valid",
        new_status=23,
        rollback_status=0,
        schema_verify_status=25,
    )

    assert result.returncode == 23
    assert len(_full_stack_up_lines(log)) == 2
    assert "自动回滚也失败（退出码：25）" in result.stderr
    assert "旧版本已恢复" not in result.stdout


def test_smoke_failure_refreshes_nginx_for_new_and_rollback_tags(
    tmp_path: Path,
) -> None:
    result, log = _run_deploy(
        tmp_path,
        previous_state="valid",
        agent_ready_sequence="not_ready,ready",
    )

    assert result.returncode != 0
    assert [line.split("|", 1)[0] for line in _full_stack_up_lines(log)] == [
        "tag=new-tag",
        f"tag={_protected_rollback_tag(tmp_path)}",
    ]
    assert [line.split("|", 1)[0] for line in _nginx_refresh_lines(log)] == [
        "tag=new-tag",
        f"tag={_protected_rollback_tag(tmp_path)}",
    ]
    assert _deployment_up_events(log) == [
        ("tag=new-tag", "全栈"),
        ("tag=new-tag", "Nginx"),
        (f"tag={_protected_rollback_tag(tmp_path)}", "全栈"),
        (f"tag={_protected_rollback_tag(tmp_path)}", "Nginx"),
    ]
    assert "新版本部署失败，旧版本已恢复" in result.stdout


def test_durable_release_refuses_to_mix_unmigrated_token_usage_ddl(
    tmp_path: Path,
) -> None:
    result, log = _run_deploy(tmp_path, previous_state="valid", migration_state="unmigrated")

    assert result.returncode != 0
    assert "禁止夹带 TokenUsage DDL" in result.stderr
    assert [line for line in log.splitlines() if line.startswith("migration ")] == [
        "migration status"
    ]
    assert _full_stack_up_lines(log) == []


def test_partial_schema_stops_before_backup_or_version_switch(tmp_path: Path) -> None:
    result, log = _run_deploy(tmp_path, previous_state="valid", migration_state="partial")

    assert result.returncode != 0
    assert [line for line in log.splitlines() if line.startswith("migration ")] == [
        "migration status"
    ]
    assert _full_stack_up_lines(log) == []


def test_second_forward_failure_runs_down_without_switching_images(tmp_path: Path) -> None:
    result, log = _run_deploy(
        tmp_path,
        previous_state="valid",
        migration_state="unmigrated",
        migration_up_fail_attempt=2,
    )

    assert result.returncode == 1
    assert "禁止夹带 TokenUsage DDL" in result.stderr
    assert [line for line in log.splitlines() if line.startswith("migration ")] == [
        "migration status"
    ]
    assert _full_stack_up_lines(log) == []


def test_first_forward_failure_runs_safe_down_without_switching_images(
    tmp_path: Path,
) -> None:
    result, log = _run_deploy(
        tmp_path,
        previous_state="valid",
        migration_state="unmigrated",
        migration_up_fail_attempt=1,
    )

    assert result.returncode == 1
    assert "禁止夹带 TokenUsage DDL" in result.stderr
    assert [line for line in log.splitlines() if line.startswith("migration ")] == [
        "migration status"
    ]
    assert _full_stack_up_lines(log) == []


def test_failed_new_version_downs_schema_before_restoring_previous_image(
    tmp_path: Path,
) -> None:
    result, log = _run_deploy(
        tmp_path,
        previous_state="valid",
        migration_state="unmigrated",
        new_status=23,
    )

    assert result.returncode == 1
    assert "禁止夹带 TokenUsage DDL" in result.stderr
    assert "migration down" not in log
    assert _full_stack_up_lines(log) == []


def test_failed_schema_down_does_not_restore_previous_image(tmp_path: Path) -> None:
    result, log = _run_deploy(
        tmp_path,
        previous_state="valid",
        migration_state="unmigrated",
        new_status=23,
        migration_down_status=32,
    )

    assert result.returncode == 1
    assert "禁止夹带 TokenUsage DDL" in result.stderr
    assert "migration down" not in log
    assert _full_stack_up_lines(log) == []


def test_durable_agent_partial_schema_stops_before_image_switch(tmp_path: Path) -> None:
    result, log = _run_deploy(
        tmp_path,
        previous_state="valid",
        durable_migration_state="partial",
    )

    assert result.returncode != 0
    assert "partial drift" in result.stderr
    assert _full_stack_up_lines(log) == []


@pytest.mark.parametrize(
    ("core_status", "agent_status"),
    [(19, 0), (0, 20)],
)
def test_non_v2_aware_new_image_stops_before_database_or_version_switch(
    tmp_path: Path, core_status: int, agent_status: int
) -> None:
    result, log = _run_deploy(
        tmp_path,
        previous_state="valid",
        core_v2_aware_status=core_status,
        agent_v2_aware_status=agent_status,
    )

    assert result.returncode in {19, 20}
    assert "durable-migration status" not in log
    assert _full_stack_up_lines(log) == []


def test_post_durable_schema_rejects_v1_only_python_rollback_target(
    tmp_path: Path,
) -> None:
    result, log = _run_deploy(
        tmp_path,
        previous_state="valid",
        durable_migration_state="migrated-empty-v2",
    )

    assert result.returncode != 0
    assert "V1-only Python Core" in result.stderr
    assert _full_stack_up_lines(log) == []


def test_post_durable_schema_exact_contract_is_checked_before_switch(
    tmp_path: Path,
) -> None:
    result, log = _run_deploy(
        tmp_path,
        previous_state="valid",
        previous_core_runtime="java",
        durable_migration_state="migrated-empty-v2",
        schema_verify_status=25,
    )

    assert result.returncode != 0
    assert "未精确命中冻结 contract" in result.stderr
    assert _full_stack_up_lines(log) == []


def test_existing_v2_data_requires_schema_ready_even_when_route_is_off(
    tmp_path: Path,
) -> None:
    result, log = _run_deploy(
        tmp_path,
        previous_state="valid",
        previous_core_runtime="java",
        durable_migration_state="migrated-with-v2",
        durable_schema_ready=False,
        durable_route_mode="off",
    )

    assert result.returncode != 0
    assert "必须保持 schemaReady=true" in result.stderr
    assert _full_stack_up_lines(log) == []


def test_deploy_cannot_skip_allowlist_and_enable_all_routes(tmp_path: Path) -> None:
    result, log = _run_deploy(
        tmp_path,
        previous_state="valid",
        previous_core_runtime="java",
        durable_migration_state="migrated-empty-v2",
        durable_schema_ready=True,
        durable_route_mode="all",
    )

    assert result.returncode != 0
    assert "当前运行 Core 未精确证明 V1/V2 新建入口关闭" in result.stderr
    assert _full_stack_up_lines(log) == []


def test_deploy_allows_only_complete_user_and_novel_intersection_allowlist(
    tmp_path: Path,
) -> None:
    rejected, rejected_log = _run_deploy(
        tmp_path / "rejected",
        previous_state="valid",
        previous_core_runtime="java",
        durable_migration_state="migrated-empty-v2",
        durable_schema_ready=True,
        durable_route_mode="allowlist",
        durable_user_allowlist="user-canary",
        durable_novel_allowlist="",
    )
    accepted, accepted_log = _run_deploy(
        tmp_path / "accepted",
        previous_state="valid",
        previous_core_runtime="java",
        durable_migration_state="migrated-empty-v2",
        durable_schema_ready=True,
        durable_route_mode="allowlist",
        durable_user_allowlist="user-canary",
        durable_novel_allowlist="novel-canary",
    )

    assert rejected.returncode != 0
    assert "精确单 userId 与单 novelId" in rejected.stderr
    assert _full_stack_up_lines(rejected_log) == []
    assert accepted.returncode == 0, accepted.stderr
    assert len(_full_stack_up_lines(accepted_log)) == 1
    assert f"v2-image agent {ROLLBACK_AGENT_DIGEST} <none>" in accepted_log


def test_allowlist_manifest_rejects_older_rollback_before_deploy(
    tmp_path: Path,
) -> None:
    result, log = _run_deploy(
        tmp_path,
        previous_state="valid",
        previous_core_runtime="java",
        durable_migration_state="migrated-empty-v2",
        durable_schema_ready=True,
        durable_route_mode="allowlist",
        durable_user_allowlist="user-canary",
        durable_novel_allowlist="novel-canary",
        rollback_agent_manifest_fingerprint="b" * 64,
    )

    assert result.returncode != 0
    assert "allowlist rollback execution manifest fingerprint 不兼容" in result.stderr
    assert log == ""
    assert _full_stack_up_lines(log) == []


def test_allowlist_requires_a_complete_compatible_rollback_snapshot(
    tmp_path: Path,
) -> None:
    result, log = _run_deploy(
        tmp_path,
        previous_state="none",
        durable_migration_state="migrated-empty-v2",
        durable_schema_ready=True,
        durable_route_mode="allowlist",
        durable_user_allowlist="user-canary",
        durable_novel_allowlist="novel-canary",
    )

    assert result.returncode != 0
    assert "verifiedDrain 前置门禁找不到当前 Core" in result.stderr
    assert _full_stack_up_lines(log) == []


def test_route_off_fingerprint_switch_requires_verified_drain_evidence(
    tmp_path: Path,
) -> None:
    result, log = _run_deploy(
        tmp_path,
        previous_state="valid",
        previous_core_runtime="java",
        durable_migration_state="migrated-with-v2",
        durable_schema_ready=True,
        durable_route_mode="off",
        rollback_agent_manifest_fingerprint="b" * 64,
        active_v2_run_count=0,
        verified_drain=False,
    )

    assert result.returncode != 0
    assert "verifiedDrain 不能由当前不可变 control bundle 复验" in result.stderr
    assert "durable-migration active-v2-count novelwriter" not in log
    assert _full_stack_up_lines(log) == []


def test_active_v2_count_cannot_replace_verified_drain_evidence(
    tmp_path: Path,
) -> None:
    result, log = _run_deploy(
        tmp_path,
        previous_state="valid",
        previous_core_runtime="java",
        durable_migration_state="migrated-with-v2",
        durable_schema_ready=True,
        durable_route_mode="off",
        rollback_agent_manifest_fingerprint="b" * 64,
        active_v2_run_count=1,
        verified_drain=False,
    )

    assert result.returncode != 0
    assert "verifiedDrain 不能由当前不可变 control bundle 复验" in result.stderr
    assert "durable-migration active-v2-count novelwriter" not in log
    assert _full_stack_up_lines(log) == []


def test_target_route_off_does_not_override_running_allowlist_during_manifest_switch(
    tmp_path: Path,
) -> None:
    result, log = _run_deploy(
        tmp_path,
        previous_state="valid",
        previous_core_runtime="java",
        durable_migration_state="migrated-with-v2",
        durable_schema_ready=True,
        durable_route_mode="off",
        rollback_agent_manifest_fingerprint="b" * 64,
        active_v2_run_count=0,
        running_core_route_mode="allowlist",
    )

    assert result.returncode != 0
    assert "当前运行 Core 未精确证明 V1/V2 新建入口关闭" in result.stderr
    assert "DURABLE_AGENT_EXECUTION_ROUTE_MODE" in log
    assert "durable-migration active-v2-count novelwriter" not in log
    assert _full_stack_up_lines(log) == []
