from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[2]
UPLOAD = ROOT / "scripts" / "upload-docker-images.sh"
SOURCE_UPLOAD = ROOT / "scripts" / "upload-deploy-source.sh"
DEPLOY = ROOT / "scripts" / "deploy-production.sh"
ROLLBACK_DRILL = ROOT / "scripts" / "rollback_drill.sh"
BACKUP = ROOT / "scripts" / "backup.sh"
FAKE_DOCKER = ROOT / "tests" / "architecture" / "fixtures" / "fake_docker.sh"
POSIX_SHELL = shutil.which("sh") or str(
    Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Git" / "bin" / "sh.exe"
)


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
        'ConnectTimeout=$CONNECT_TIMEOUT_SECONDS',
        "ConnectionAttempts=2",
        "BatchMode=yes",
        "--kill-after=30s",
        "docker info",
        "DockerRootDir",
        "df -Pk",
        "服务器 SSH 响应正常",
        "服务器 Bash 可用，开始读取 Docker 信息",
        'mktemp -d "${RUNNER_TEMP:-/tmp}/inkforge-images.XXXXXX"',
        'trap cleanup_upload_archives EXIT',
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
        '服务器镜像查询失败：${service}，退出码 ${current_status}',
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
    assert "profile=schema_profile_for_settings(settings)" in DEPLOY.read_text(
        encoding="utf-8"
    )


def test_backup_files_default_to_private_permissions() -> None:
    source = BACKUP.read_text(encoding="utf-8")

    assert "umask 077" in source


def test_rollback_drill_normalizes_schema_fingerprints_across_contract_versions() -> None:
    source = ROLLBACK_DRILL.read_text(encoding="utf-8")

    assert 'getattr(db_session, "schema_profile_for_settings"' in source
    assert 'inspect.signature(guard.verify_live_schema).parameters' in source
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
        "printf 'docker %s\\n' \"$*\" >> \"$UPLOAD_LOG\"\n"
        "case \"$*\" in\n"
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
        "for argument in \"$@\"; do command_text=$argument; done\n"
        "printf 'ssh %s\\n' \"$command_text\" >> \"$UPLOAD_LOG\"\n"
        "case \"$command_text\" in\n"
        "  *'DockerRootDir'*) echo '服务器 Docker 响应正常'; exit 0 ;;\n"
        "  *'container_id='*) exit \"$FAKE_CURRENT_STATUS\" ;;\n"
        "  *'required_bytes'*) echo '服务器 Docker 容量满足要求'; exit 0 ;;\n"
        "  *'docker image inspect \"$image_id\"'*) exit \"$FAKE_HAS_IMAGE_STATUS\" ;;\n"
        "  *'gunzip | docker load'*) cat >/dev/null; exit \"$FAKE_UPLOAD_STATUS\" ;;\n"
        "  *) exit 0 ;;\n"
        "esac\n",
    )
    _write_executable(
        bin_dir / "timeout",
        "#!/bin/sh\n"
        "while [ \"$#\" -gt 0 ]; do\n"
        "  case \"$1\" in --foreground|--kill-after=*) shift ;; *) break ;; esac\n"
        "done\n"
        "shift\n"
        "exec \"$@\"\n",
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
        "printf 'git %s\\n' \"$*\" >> \"$SOURCE_UPLOAD_LOG\"\n"
        "case \"$*\" in\n"
        "  'rev-parse HEAD') printf '%s\\n' \"$DEPLOY_SHA\" ;;\n"
        "  bundle\\ create*) printf 'bundle-fixture' > \"$3\" ;;\n"
        "  bundle\\ verify*) exit 0 ;;\n"
        "  bundle\\ list-heads*) printf '%s HEAD\\n' \"$DEPLOY_SHA\" ;;\n"
        "  *) exit 1 ;;\n"
        "esac\n",
    )
    _write_executable(
        bin_dir / "scp",
        "#!/bin/sh\n"
        "printf 'scp %s\\n' \"$*\" >> \"$SOURCE_UPLOAD_LOG\"\n"
        "count=0\n"
        "[ ! -f \"$SOURCE_UPLOAD_COUNTER\" ] || count=$(sed -n '1p' \"$SOURCE_UPLOAD_COUNTER\")\n"
        "count=$((count + 1))\n"
        "printf '%s\\n' \"$count\" > \"$SOURCE_UPLOAD_COUNTER\"\n"
        "if [ \"$count\" -le \"$SOURCE_TRANSIENT_FAILURES\" ]; then exit 255; fi\n"
        "exit \"$SOURCE_TERMINAL_STATUS\"\n",
    )
    _write_executable(
        bin_dir / "ssh",
        "#!/bin/sh\n"
        "command_text=''\n"
        "for argument in \"$@\"; do command_text=$argument; done\n"
        "printf 'ssh %s\\n' \"$command_text\" >> \"$SOURCE_UPLOAD_LOG\"\n"
        "exit 0\n",
    )
    _write_executable(
        bin_dir / "timeout",
        "#!/bin/sh\n"
        "while [ \"$#\" -gt 0 ]; do\n"
        "  case \"$1\" in --foreground|--kill-after=*) shift ;; *) break ;; esac\n"
        "done\n"
        "shift\n"
        "exec \"$@\"\n",
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
    assert "git bundle create" in log
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
    new_core_runtime: str = "java",
    previous_core_runtime: str = "",
    deploy_sha: str = "new-tag",
    deploy_bundle: bool = False,
) -> tuple[subprocess.CompletedProcess[str], str]:
    app_dir = tmp_path / "app"
    bin_dir = tmp_path / "bin"
    (app_dir / ".git").mkdir(parents=True)
    (app_dir / "infra" / "secrets").mkdir(parents=True)
    (app_dir / "scripts").mkdir(parents=True)
    bin_dir.mkdir()
    (app_dir / ".env").write_text(
        "DATABASE_URL=postgresql+asyncpg://user:pass@host.docker.internal:5432/novelwriter\n",
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
    _write_executable(
        app_dir / "scripts" / "token-usage-production-migration.sh",
        "#!/bin/sh\n"
        "action=$1\n"
        "printf 'migration %s\\n' \"$action\" >> \"$FAKE_DOCKER_LOG\"\n"
        "state_file=$FAKE_MIGRATION_STATE_FILE\n"
        "case \"$action\" in\n"
        "  status)\n"
        "    if [ -f \"$state_file\" ]; then sed -n '1p' \"$state_file\"; "
        "else printf '%s\\n' \"$FAKE_MIGRATION_STATE\"; fi ;;\n"
        "  backup) exit 0 ;;\n"
        "  up)\n"
        "    count=0; [ ! -f \"$FAKE_MIGRATION_UP_COUNT\" ] || "
        "count=$(sed -n '1p' \"$FAKE_MIGRATION_UP_COUNT\")\n"
        "    count=$((count + 1)); printf '%s\\n' \"$count\" > \"$FAKE_MIGRATION_UP_COUNT\"\n"
        "    [ \"$count\" -ne \"$FAKE_MIGRATION_UP_FAIL_ATTEMPT\" ] || exit 31\n"
        "    printf 'migrated\\n' > \"$state_file\" ;;\n"
        "  down)\n"
        "    [ \"$FAKE_MIGRATION_DOWN_STATUS\" -eq 0 ] || exit \"$FAKE_MIGRATION_DOWN_STATUS\"\n"
        "    printf 'unmigrated\\n' > \"$state_file\" ;;\n"
        "  *) exit 2 ;;\n"
        "esac\n",
    )
    shutil.copy2(FAKE_DOCKER, bin_dir / "docker")
    (bin_dir / "docker").chmod(0o755)
    _write_executable(
        bin_dir / "git",
        "#!/bin/sh\n"
        "while [ \"${1:-}\" = \"-c\" ]; do shift 2; done\n"
        "printf 'git %s\\n' \"$*\" >> \"$FAKE_DOCKER_LOG\"\n"
        "if [ \"${1:-}\" = \"rev-parse\" ]; then printf '%s\\n' \"$DEPLOY_SHA\"; fi\n"
        "exit 0\n",
    )
    _write_executable(
        bin_dir / "stat",
        "#!/bin/sh\n"
        "case \"$*\" in *%u*) echo 10001;; *%g*) echo 10001;; *%a*) echo 600;; esac\n",
    )
    _write_executable(
        bin_dir / "curl",
        "#!/bin/sh\n"
        "case \"$*\" in "
        "*write-out*) printf 404;; "
        "*health/ready*) printf '{\"status\":\"ready\",\"checks\":{\"agent\":\"ok\"}}';; "
        "esac\n",
    )
    log_path = tmp_path / "docker.log"
    agent_counter_path = tmp_path / "agent-ready-counter"
    migration_state_path = tmp_path / "migration-state"
    migration_up_count_path = tmp_path / "migration-up-count"
    snapshot_state_dir = tmp_path / "snapshot-state"
    snapshot_state_dir.mkdir()
    # 必须使用与生产脚本相同的固定目录，SHA 让并行测试互不覆盖。
    bundle_root = Path("/tmp")  # noqa: S108
    bundle_path = bundle_root / f"inkforge-deploy-{deploy_sha}.bundle"
    if deploy_bundle:
        bundle_path.write_text("bundle fixture", encoding="utf-8")
    env = {
        **os.environ,
        "APP_DIR": _posix_path(app_dir),
        "DEPLOY_SHA": deploy_sha,
        "DEPLOY_BUNDLE_PATH": bundle_path.as_posix() if deploy_bundle else "",
        "INKFORGE_IMAGE_TAG": "new-tag",
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
        "FAKE_SNAPSHOT_STATE_DIR": _posix_path(snapshot_state_dir),
        "SMOKE_AGENT_MAX_ATTEMPTS": "1",
        "SMOKE_AGENT_REQUIRED_SUCCESSES": "1",
        "SMOKE_AGENT_POLL_SECONDS": "0",
    }
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
        timeout=20,
        check=False,
    )
    return result, log_path.read_text(encoding="utf-8") if log_path.exists() else ""


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
    return [
        line
        for line in log.splitlines()
        if line.endswith(" up --no-build -d --wait")
    ]


def _nginx_refresh_lines(log: str) -> list[str]:
    return [
        line
        for line in log.splitlines()
        if line.endswith(
            " up --no-build -d --wait --no-deps --force-recreate nginx"
        )
    ]


def _deployment_up_events(log: str) -> list[tuple[str, str]]:
    events: list[tuple[str, str]] = []
    for line in log.splitlines():
        tag = line.split("|", 1)[0]
        if line.endswith(" up --no-build -d --wait"):
            events.append((tag, "全栈"))
        elif line.endswith(
            " up --no-build -d --wait --no-deps --force-recreate nginx"
        ):
            events.append((tag, "Nginx"))
    return events


@pytest.mark.parametrize(
    ("state", "expected_status", "expected_up_count"),
    [
        ("none", 0, 1),
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
    expected_tags = [
        "docker image tag sha256:previous-web-id inkforge-web:rollback-new-tag",
        "docker image tag sha256:previous-core-api-id inkforge-core-api:rollback-new-tag",
        "docker image tag sha256:previous-agent-service-id inkforge-agent-service:rollback-new-tag",
    ]
    for expected in expected_tags:
        matching_index = next(
            index for index, line in enumerate(lines) if expected in line
        )
        first_switch_index = next(
            index
            for index, line in enumerate(lines)
            if line.endswith(" up --no-build -d --wait")
        )
        assert matching_index < first_switch_index

    assert "已冻结当前生产三服务精确回滚快照：rollback-new-tag（python）" in result.stdout


def test_existing_conflicting_rollback_snapshot_is_not_overwritten(
    tmp_path: Path,
) -> None:
    result, log = _run_deploy(
        tmp_path,
        previous_state="snapshot_existing_conflict",
    )

    assert result.returncode != 0
    assert "回滚镜像标签已存在但指向另一镜像" in result.stderr
    assert "docker image tag" not in log
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
        index
        for index, line in enumerate(lines)
        if "docker volume create inkforge_uploads" in line
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
    up_index = next(
        index
        for index, line in enumerate(lines)
        if line.endswith(" up --no-build -d --wait")
    )
    assert uploads_create_index < uploads_init_index < logs_create_index
    assert logs_create_index < logs_init_index < up_index
    for init_index in (uploads_init_index, logs_init_index):
        assert (
            "docker run --rm --network none --read-only --cap-drop ALL --cap-add CHOWN"
            in lines[init_index]
        )
        assert "--user 0:0" in lines[init_index]
        assert "--entrypoint /usr/bin/chown" in lines[init_index]
    assert "inkforge-core-api:new-tag 10001:10001 /data/uploads" in lines[
        uploads_init_index
    ]
    assert "inkforge-agent-service:new-tag 10001:10001 /data/agent-logs" in lines[
        logs_init_index
    ]


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
        "tag=rollback-new-tag",
    ]
    assert (
        " compose --env-file .env -f infra/compose.yaml "
        "-f infra/compose.python-core-rollback.yaml ps"
    ) in log
    assert "-f infra/compose.python-core-rollback.yaml" in up_lines[1]
    assert " exec -T core-api python -c" in log
    assert "新版本部署失败，旧版本已恢复" in result.stdout
    assert "生产编排已启动" not in result.stdout


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
        "tag=rollback-new-tag",
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


def test_failed_first_deployment_does_not_fabricate_rollback(tmp_path: Path) -> None:
    result, log = _run_deploy(
        tmp_path,
        previous_state="none",
        new_status=23,
    )

    assert result.returncode == 23
    assert len(_full_stack_up_lines(log)) == 1
    assert "本次为首次部署，没有可自动恢复的上一版本" in result.stderr
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
        "tag=rollback-new-tag",
    ]
    assert [line.split("|", 1)[0] for line in _nginx_refresh_lines(log)] == [
        "tag=new-tag",
        "tag=rollback-new-tag",
    ]
    assert _deployment_up_events(log) == [
        ("tag=new-tag", "全栈"),
        ("tag=new-tag", "Nginx"),
        ("tag=rollback-new-tag", "全栈"),
        ("tag=rollback-new-tag", "Nginx"),
    ]
    assert "新版本部署失败，旧版本已恢复" in result.stdout


def test_unmigrated_schema_is_backed_up_and_migrated_twice_before_switch(
    tmp_path: Path,
) -> None:
    result, log = _run_deploy(tmp_path, previous_state="valid", migration_state="unmigrated")

    assert result.returncode == 0, result.stderr
    lines = log.splitlines()
    assert [line for line in lines if line.startswith("migration ")] == [
        "migration status",
        "migration backup",
        "migration up",
        "migration status",
        "migration up",
        "migration status",
    ]
    assert lines.index("migration up", lines.index("migration up") + 1) < next(
        index for index, line in enumerate(lines) if line.endswith(" up --no-build -d --wait")
    )


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

    assert result.returncode == 31
    assert [line for line in log.splitlines() if line.startswith("migration ")] == [
        "migration status",
        "migration backup",
        "migration up",
        "migration status",
        "migration up",
        "migration down",
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

    assert result.returncode == 31
    assert [line for line in log.splitlines() if line.startswith("migration ")] == [
        "migration status",
        "migration backup",
        "migration up",
        "migration down",
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

    assert result.returncode == 23
    lines = log.splitlines()
    down_index = lines.index("migration down")
    previous_up_index = next(
        index
        for index, line in enumerate(lines)
        if line.startswith("tag=rollback-new-tag|")
        and line.endswith(" up --no-build -d --wait")
    )
    assert down_index < previous_up_index


def test_failed_schema_down_does_not_restore_previous_image(tmp_path: Path) -> None:
    result, log = _run_deploy(
        tmp_path,
        previous_state="valid",
        migration_state="unmigrated",
        new_status=23,
        migration_down_status=32,
    )

    assert result.returncode == 23
    assert "migration down" in log
    assert not any(
        line.startswith("tag=rollback-new-tag|")
        for line in _full_stack_up_lines(log)
    )
    assert "数据库结构回退失败" in result.stderr
