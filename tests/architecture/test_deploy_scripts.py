from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[2]
UPLOAD = ROOT / "scripts" / "upload-docker-images.sh"
DEPLOY = ROOT / "scripts" / "deploy-production.sh"
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
        'timeout --kill-after=30s "$IMAGE_UPLOAD_TIMEOUT_SECONDS"',
        "bash -o pipefail -c 'gunzip | docker load'",
        "服务器镜像查询失败",
        "服务器 Docker 容量不足",
        "image_size * 2 + REMOTE_DOCKER_SAFETY_BYTES",
        "镜像归档完成",
        "开始传输并导入镜像",
        "镜像传输并导入完成",
        "镜像传输或导入失败",
    ):
        assert contract in source


def test_deploy_scripts_contain_no_destructive_or_dynamic_trust_commands() -> None:
    source = "\n".join(
        path.read_text(encoding="utf-8") for path in (UPLOAD, DEPLOY)
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


def _run_deploy(
    tmp_path: Path,
    *,
    previous_state: str,
    new_status: int = 0,
    rollback_status: int = 0,
    schema_verify_status: int = 0,
    agent_ready_sequence: str = "",
) -> tuple[subprocess.CompletedProcess[str], str]:
    app_dir = tmp_path / "app"
    bin_dir = tmp_path / "bin"
    (app_dir / ".git").mkdir(parents=True)
    (app_dir / "infra" / "secrets").mkdir(parents=True)
    (app_dir / "scripts").mkdir(parents=True)
    bin_dir.mkdir()
    (app_dir / ".env").write_text(
        "DATABASE_URL=postgresql+asyncpg://user:pass@host.docker.internal:5432/inkforge\n",
        encoding="utf-8",
    )
    (app_dir / "infra" / "compose.yaml").write_text(
        "services:\n  core-api:\n    extra_hosts:\n      - host.docker.internal:host-gateway\n",
        encoding="utf-8",
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
    shutil.copy2(FAKE_DOCKER, bin_dir / "docker")
    (bin_dir / "docker").chmod(0o755)
    _write_executable(
        bin_dir / "git",
        "#!/bin/sh\n"
        "while [ \"${1:-}\" = \"-c\" ]; do shift 2; done\n"
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
        "*health/ready*) printf '{\"status\":\"ready\"}';; "
        "esac\n",
    )
    log_path = tmp_path / "docker.log"
    agent_counter_path = tmp_path / "agent-ready-counter"
    env = {
        **os.environ,
        "APP_DIR": _posix_path(app_dir),
        "DEPLOY_SHA": "new-tag",
        "INKFORGE_IMAGE_TAG": "new-tag",
        "FAKE_DOCKER_LOG": _posix_path(log_path),
        "FAKE_NEW_TAG": "new-tag",
        "FAKE_PREVIOUS_STATE": previous_state,
        "FAKE_NEW_UP_STATUS": str(new_status),
        "FAKE_ROLLBACK_UP_STATUS": str(rollback_status),
        "FAKE_SCHEMA_VERIFY_STATUS": str(schema_verify_status),
        "FAKE_AGENT_READY_COUNTER": _posix_path(agent_counter_path),
        "FAKE_AGENT_READY_SEQUENCE": agent_ready_sequence,
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
        ("mismatch", 1, 0),
        ("valid", 0, 1),
        ("missing_image", 1, 0),
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


def test_successful_deployment_refreshes_nginx_with_new_tag(tmp_path: Path) -> None:
    result, log = _run_deploy(tmp_path, previous_state="valid")

    assert result.returncode == 0, result.stderr
    refresh_lines = _nginx_refresh_lines(log)
    assert [line.split("|", 1)[0] for line in refresh_lines] == ["tag=new-tag"]
    assert _deployment_up_events(log) == [
        ("tag=new-tag", "全栈"),
        ("tag=new-tag", "Nginx"),
    ]


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
        "tag=previous-tag",
    ]
    assert " compose --env-file .env -f infra/compose.yaml ps" in log
    assert " exec -T core-api python -c" in log
    assert "新版本部署失败，旧版本已恢复" in result.stdout
    assert "生产编排已启动" not in result.stdout


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
        "tag=previous-tag",
    ]
    assert [line.split("|", 1)[0] for line in _nginx_refresh_lines(log)] == [
        "tag=new-tag",
        "tag=previous-tag",
    ]
    assert _deployment_up_events(log) == [
        ("tag=new-tag", "全栈"),
        ("tag=new-tag", "Nginx"),
        ("tag=previous-tag", "全栈"),
        ("tag=previous-tag", "Nginx"),
    ]
    assert "新版本部署失败，旧版本已恢复" in result.stdout
