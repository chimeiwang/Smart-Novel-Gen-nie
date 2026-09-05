from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[2]
RUNNER = ROOT / "scripts" / "verify-running-core-schema.sh"
CORE_ID = "a" * 64
IMAGE_ID = "sha256:" + "b" * 64
PROBE_ID = "c" * 64
FINGERPRINT = "d" * 64
SECRET = "schema-probe-password-must-not-leak"  # noqa: S105 - 仅为凭据泄漏断言的虚构测试标记
POSIX_SHELL = shutil.which("sh") or str(
    Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Git" / "bin" / "sh.exe"
)

FAKE_DOCKER = r'''#!/usr/bin/env python3
import json
import os
import stat
import sys
import time
from pathlib import Path

arguments = sys.argv[1:]
state_dir = Path(os.environ["FAKE_SCHEMA_PROBE_STATE"])
with (state_dir / "calls.jsonl").open("a", encoding="utf-8") as stream:
    stream.write(json.dumps(arguments) + "\n")
core_id = "a" * 64
image_id = "sha256:" + "b" * 64
probe_id = "c" * 64
fingerprint = "d" * 64
scenario = os.environ.get("FAKE_SCHEMA_PROBE_SCENARIO", "success")

if arguments[:1] == ["inspect"]:
    if arguments[-1] != core_id:
        if not (state_dir / "created.json").exists():
            sys.exit(1)
        created = json.loads((state_dir / "created.json").read_text())
        if scenario in {
            "already_removed", "cleanup_inspect_failure", "cleanup_inspect_inconsistent",
            "timeout_cleanup_failure",
        }:
            sys.exit(1)
        if scenario == "cleanup_identity_mismatch":
            created["labels"] = {}
        print(json.dumps([{
            "Id": probe_id,
            "Name": "/" + created["name"],
            "Config": {"Labels": created["labels"]},
        }]))
        sys.exit(0)
    counter_file = state_dir / "inspections"
    count = int(counter_file.read_text()) + 1 if counter_file.exists() else 1
    counter_file.write_text(str(count))
    document = {
        "Id": core_id,
        "Image": image_id,
        "RestartCount": 0,
        "State": {
            "Running": True, "Paused": False, "Restarting": False,
            "StartedAt": "2026-09-06T01:00:00.000000000Z",
        },
        "Config": {"Env": [
            "DATABASE_URL=postgresql://owner:schema-probe-password-must-not-leak@host.docker.internal/novelwriter",
            "VIDEO_PREVIEW_ENABLED=false",
            "PHONE_AUTH_ENABLED=true",
            "PHONE_AUTH_SEND_ENABLED=true",
            "JWT_SECRET=jwt-must-not-leak",
            "MODEL_API_KEY=model-key-must-not-leak",
            "JAVA_TOOL_OPTIONS=-Xmx176m -Dsecret=service-jvm-must-not-leak",
        ]},
    }
    if scenario == "stopped":
        document["State"]["Running"] = False
    if scenario == "paused":
        document["State"]["Paused"] = True
    if scenario == "restarting":
        document["State"]["Restarting"] = True
    if scenario == "wrong_identity":
        document["Id"] = "e" * 64
    if scenario == "missing_database":
        document["Config"]["Env"] = [
            value for value in document["Config"]["Env"] if not value.startswith("DATABASE_URL=")
        ]
    if scenario == "multiline_database":
        document["Config"]["Env"][0] += "\nJWT_SECRET=injected"
    if scenario == "duplicate_database":
        document["Config"]["Env"].append(document["Config"]["Env"][0])
    if scenario == "missing_flags":
        document["Config"]["Env"] = [document["Config"]["Env"][0]]
    if count > 1:
        if scenario == "image_drift":
            document["Image"] = "sha256:" + "f" * 64
        if scenario == "started_at_drift":
            document["State"]["StartedAt"] = "2026-09-06T01:00:01.000000000Z"
        if scenario == "restart_drift":
            document["RestartCount"] = 1
        if scenario == "environment_drift":
            document["Config"]["Env"][1] = "VIDEO_PREVIEW_ENABLED=true"
        if scenario == "paused_drift":
            document["State"]["Paused"] = True
        if scenario == "restarting_drift":
            document["State"]["Restarting"] = True
    print(json.dumps([document]))
    sys.exit(0)

if arguments[:1] == ["run"]:
    def value(name):
        return arguments[arguments.index(name) + 1]
    env_path = Path(value("--env-file"))
    lines = env_path.read_text().splitlines()
    environment = dict(line.split("=", 1) for line in lines)
    assert set(environment) == {
        "DATABASE_URL", "VIDEO_PREVIEW_ENABLED", "PHONE_AUTH_ENABLED", "PHONE_AUTH_SEND_ENABLED"
    }
    assert "schema-probe-password-must-not-leak" in environment["DATABASE_URL"]
    assert stat.S_IMODE(env_path.stat().st_mode) == 0o600
    assert stat.S_IMODE(env_path.parent.stat().st_mode) == 0o700
    (state_dir / "environment-check.json").write_text(json.dumps({
        "keys": sorted(environment),
        "envPath": str(env_path),
        "flags": {name: value for name, value in environment.items() if name != "DATABASE_URL"},
    }))
    labels = {}
    for index, argument in enumerate(arguments[:-1]):
        if argument == "--label":
            key, content = arguments[index + 1].split("=", 1)
            labels[key] = content
    (state_dir / "created.json").write_text(json.dumps({"name": value("--name"), "labels": labels}))
    Path(value("--cidfile")).write_text(probe_id)
    if scenario in {"timeout", "timeout_cleanup_failure"}:
        time.sleep(10)
    if scenario == "failure":
        print("DATABASE_URL=schema-probe-password-must-not-leak", file=sys.stderr)
        print("jwt-must-not-leak")
        sys.exit(2)
    if scenario == "oom":
        sys.exit(137)
    if scenario == "invalid_output":
        print(fingerprint + "\nextra line")
    else:
        print(fingerprint)
    sys.exit(0)

if arguments[:2] == ["rm", "--force"]:
    assert arguments[-1] == probe_id
    if scenario == "cleanup_failure":
        sys.exit(1)
    sys.exit(0)

if arguments[:1] == ["ps"]:
    assert arguments[1:5] == ["--all", "--quiet", "--no-trunc", "--filter"]
    assert arguments[-1] == "id=" + probe_id
    if scenario in {"cleanup_inspect_failure", "timeout_cleanup_failure"}:
        print("Docker daemon 无法连接", file=sys.stderr)
        sys.exit(1)
    if scenario == "cleanup_inspect_inconsistent":
        print(probe_id)
    sys.exit(0)

print("不允许的 Docker 调用", file=sys.stderr)
sys.exit(99)
'''


def run_probe(
    tmp_path: Path,
    scenario: str = "success",
    arguments: tuple[str, ...] = (CORE_ID,),
) -> tuple[subprocess.CompletedProcess[str], list[list[str]], Path]:
    binary_dir = tmp_path / "bin"
    binary_dir.mkdir()
    fake_docker = binary_dir / "docker"
    fake_docker.write_text(
        FAKE_DOCKER.replace("#!/usr/bin/env python3", f"#!{sys.executable}", 1),
        encoding="utf-8",
    )
    fake_docker.chmod(0o700)
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    environment = {
        **os.environ,
        "PATH": str(binary_dir) + os.pathsep + os.environ["PATH"],
        "FAKE_SCHEMA_PROBE_STATE": str(state_dir),
        "FAKE_SCHEMA_PROBE_SCENARIO": scenario,
        "INKFORGE_SCHEMA_PROBE_TIMEOUT_SECONDS": (
            "1" if scenario in {"timeout", "timeout_cleanup_failure"} else "60"
        ),
    }
    result = subprocess.run(  # noqa: S603 - 测试只执行仓库固定脚本和离线 Docker 夹具
        [POSIX_SHELL, str(RUNNER), *arguments],
        capture_output=True,
        text=True,
        env=environment,
        timeout=15,
        check=False,
    )
    call_log = state_dir / "calls.jsonl"
    calls = (
        [json.loads(line) for line in call_log.read_text().splitlines()]
        if call_log.exists()
        else []
    )
    return result, calls, state_dir


def test_探针使用真实镜像独立资源且不在活动容器启动第二个JVM(tmp_path: Path) -> None:
    result, calls, state = run_probe(tmp_path)

    assert result.returncode == 0, result.stderr
    assert result.stdout == FINGERPRINT + "\n"
    assert result.stderr == ""
    run = next(call for call in calls if call[0] == "run")
    for name, value in (
        ("--network", "container:" + CORE_ID),
        ("--memory", "192m"),
        ("--memory-swap", "192m"),
        ("--cpus", "0.25"),
        ("--pids-limit", "64"),
        ("--user", "10001:10001"),
        ("--entrypoint", "/usr/local/bin/inkforge-schema-guard"),
    ):
        assert run[run.index(name) + 1] == value
    assert run[-1] == IMAGE_ID
    assert "--read-only" in run
    assert "--cap-drop" in run and run[run.index("--cap-drop") + 1] == "ALL"
    assert "no-new-privileges:true" in run
    assert not any(call[0] == "exec" for call in calls)
    assert all("--privileged" not in call and "--volume" not in call for call in calls)
    options = next(item for item in run if item.startswith("JAVA_TOOL_OPTIONS="))
    for expected in ("-Xms16m", "-Xmx64m", "-XX:MaxMetaspaceSize=48m", "-XX:+UseSerialGC"):
        assert expected in options
    assert "JDK_JAVA_OPTIONS=" in run and "_JAVA_OPTIONS=" in run
    assert (state / "inspections").read_text() == "2"
    assert ["rm", "--force", PROBE_ID] in calls
    env_path = Path(json.loads((state / "environment-check.json").read_text())["envPath"])
    assert not env_path.exists() and not env_path.parent.exists()
    for secret in (
        SECRET, "jwt-must-not-leak", "model-key-must-not-leak", "service-jvm-must-not-leak"
    ):
        assert secret not in result.stdout + result.stderr + json.dumps(calls)


def test_兼容指纹参数透传给原检查器(tmp_path: Path) -> None:
    result, calls, _ = run_probe(tmp_path, arguments=(CORE_ID, "--compatibility-fingerprint-v1"))

    assert result.returncode == 0, result.stderr
    run = next(call for call in calls if call[0] == "run")
    assert run[-2:] == [IMAGE_ID, "--compatibility-fingerprint-v1"]


@pytest.mark.parametrize(
    "scenario",
    [
        "stopped", "paused", "restarting", "wrong_identity", "missing_database",
        "multiline_database", "duplicate_database",
    ],
)
def test_无效来源拒绝启动任何探针(tmp_path: Path, scenario: str) -> None:
    result, calls, _ = run_probe(tmp_path, scenario)

    assert result.returncode != 0
    assert result.stdout == ""
    assert not any(call[0] == "run" for call in calls)
    assert SECRET not in result.stderr


def test_历史镜像缺省能力开关维持false投影(tmp_path: Path) -> None:
    result, _, state = run_probe(tmp_path, "missing_flags")

    assert result.returncode == 0, result.stderr
    flags = json.loads((state / "environment-check.json").read_text())["flags"]
    assert set(flags.values()) == {"false"}


@pytest.mark.parametrize(
    "scenario",
    [
        "image_drift", "started_at_drift", "restart_drift", "environment_drift",
        "paused_drift", "restarting_drift",
    ],
)
def test_目标实例变化即拒绝输出指纹且清理探针(tmp_path: Path, scenario: str) -> None:
    result, calls, _ = run_probe(tmp_path, scenario)

    assert result.returncode != 0
    assert result.stdout == ""
    assert ["rm", "--force", PROBE_ID] in calls


@pytest.mark.parametrize(
    "scenario,expected_status", [("failure", 2), ("oom", 137), ("timeout", 124)]
)
def test_失败超时透传并清理且不泄漏模型和数据库凭据(
    tmp_path: Path, scenario: str, expected_status: int
) -> None:
    result, calls, state = run_probe(tmp_path, scenario)

    assert result.returncode == expected_status, result.stderr
    assert result.stdout == ""
    assert SECRET not in result.stderr and "jwt-must-not-leak" not in result.stderr
    assert ["rm", "--force", PROBE_ID] in calls
    assert (state / "inspections").read_text() == "2"
    env_path = Path(json.loads((state / "environment-check.json").read_text())["envPath"])
    assert not env_path.parent.exists()


def test_非单行指纹不能冒充通过(tmp_path: Path) -> None:
    result, calls, _ = run_probe(tmp_path, "invalid_output")

    assert result.returncode != 0
    assert result.stdout == ""
    assert ["rm", "--force", PROBE_ID] in calls


@pytest.mark.parametrize(
    "scenario",
    [
        "cleanup_failure", "cleanup_identity_mismatch", "cleanup_inspect_failure",
        "cleanup_inspect_inconsistent",
    ],
)
def test_清理无法确认时不能报成功且不删除未知目标(tmp_path: Path, scenario: str) -> None:
    result, calls, state = run_probe(tmp_path, scenario)

    assert result.returncode != 0
    assert result.stdout == ""
    if scenario == "cleanup_identity_mismatch":
        assert not any(call[0] == "rm" for call in calls)
    env_path = Path(json.loads((state / "environment-check.json").read_text())["envPath"])
    assert not env_path.parent.exists()


def test_Docker已经自动回收的本次探针无需删除其他目标(tmp_path: Path) -> None:
    result, calls, _ = run_probe(tmp_path, "already_removed")

    assert result.returncode == 0, result.stderr
    assert result.stdout == FINGERPRINT + "\n"
    assert not any(call[0] == "rm" for call in calls)


def test_原探针超时遇清理通信失败保留原退出码并明确报告(tmp_path: Path) -> None:
    result, calls, state = run_probe(tmp_path, "timeout_cleanup_failure")

    assert result.returncode == 124, result.stderr
    assert result.stdout == ""
    assert "清理未能确认完成" in result.stderr
    assert "超时" in result.stderr
    assert not any(call[0] == "rm" for call in calls)
    env_path = Path(json.loads((state / "environment-check.json").read_text())["envPath"])
    assert not env_path.parent.exists()


@pytest.mark.parametrize("arguments", [("core-api",), ("a" * 12,), (CORE_ID, "--unsafe"), ()])
def test_入口只接受完整容器ID和唯一兼容参数(tmp_path: Path, arguments: tuple[str, ...]) -> None:
    result, calls, _ = run_probe(tmp_path, arguments=arguments)

    assert result.returncode == 2
    assert result.stdout == ""
    assert calls == []
