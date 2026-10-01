"""GHCR 生产拉取的隔离行为验证，不连接真实 Docker 或 SSH。"""

from __future__ import annotations

import importlib.util
import json
import os
import select
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
SPEC = importlib.util.spec_from_file_location(
    "pull_release_images", ROOT / "scripts" / "pull-release-images.py"
)
assert SPEC and SPEC.loader
pull = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(pull)

SHA = "a" * 40
REPOSITORY = "chimeiwang/Smart-Novel-Gen-nie"
TOKEN = "ghs_" + "S" * 40
SERVICES = ("web", "core-api", "agent-service")


def manifest(*, size: int = 1024) -> dict:
    return {
        "schemaVersion": 1,
        "repository": REPOSITORY,
        "sourceSha": SHA,
        "sourceRunId": 123,
        "images": {
            service: {
                "repository": f"ghcr.io/chimeiwang/smart-novel-gen-nie/{service}",
                "digest": "sha256:" + str(index + 1) * 64,
                "imageId": "sha256:" + str(index + 4) * 64,
                "sizeBytes": size,
            }
            for index, service in enumerate(SERVICES)
        },
    }


FAKE_DOCKER = r'''#!/usr/bin/env python3
import json,os,sys,time
from pathlib import Path
args=sys.argv[1:]
state_path=Path(os.environ["FAKE_DOCKER_STATE"])
calls_path=Path(os.environ["FAKE_DOCKER_CALLS"])
state=json.loads(state_path.read_text())
def record(value):
    with calls_path.open("a") as stream: stream.write(json.dumps(value)+"\n")
def save(): state_path.write_text(json.dumps(state))
if args[:2]==["info","--format"]:
    print(os.environ["FAKE_DOCKER_ROOT"])
elif args[:3]==["image","inspect","--format"]:
    ref=args[4]
    if ref not in state["images"]: sys.exit(1)
    item=state["images"][ref]
    print(json.dumps(item["id"])+"|"+json.dumps(item["digests"]))
elif args and args[0]=="login":
    token=sys.stdin.read().strip()
    config=Path(os.environ["DOCKER_CONFIG"])
    config.joinpath("config.json").write_text("temporary")
    record({"action":"login","argv":args,"token_length":len(token),
            "config":str(config),"mode":oct(config.stat().st_mode & 0o777)})
    if os.environ.get("FAKE_LOGIN_FAIL"): sys.exit(1)
elif args and args[0]=="pull":
    ref=args[1]
    record({"action":"pull","ref":ref})
    if os.environ.get("FAKE_PULL_SLEEP"): time.sleep(float(os.environ["FAKE_PULL_SLEEP"]))
    if os.environ.get("FAKE_PULL_FAIL"): sys.exit(1)
    item=state["expected"][ref]
    image_id=item["id"]
    if os.environ.get("FAKE_MISMATCH_REF")==ref: image_id="sha256:"+"f"*64
    state["images"][ref]={"id":image_id,"digests":[ref]}
    save()
elif args[:2]==["image","tag"]:
    source,target=args[2:]
    record({"action":"tag","source":source,"target":target})
    matching=next((v for v in state["images"].values() if v["id"]==source),None)
    if matching is None: sys.exit(1)
    state["images"][target]=matching
    save()
else:
    record({"action":"unknown","argv":args})
    sys.exit(2)
'''


@pytest.fixture
def fake_docker(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    executable = bin_dir / "docker"
    executable.write_text(FAKE_DOCKER)
    executable.chmod(0o755)
    state_path = tmp_path / "state.json"
    calls_path = tmp_path / "calls.jsonl"
    doc = manifest()
    state_path.write_text(json.dumps({
        "images": {},
        "expected": {
            item["repository"] + "@" + item["digest"]: {"id": item["imageId"]}
            for item in doc["images"].values()
        },
    }))
    monkeypatch.setenv("FAKE_DOCKER_STATE", str(state_path))
    monkeypatch.setenv("FAKE_DOCKER_CALLS", str(calls_path))
    monkeypatch.setenv("FAKE_DOCKER_ROOT", str(tmp_path))
    monkeypatch.setenv("PATH", str(bin_dir) + os.pathsep + os.environ["PATH"])
    return doc, state_path, calls_path


def remote_result(
    doc: dict, *, program: str | None = None, actor: str = "release-bot"
) -> subprocess.CompletedProcess[str]:
    payload = {
        "manifest": doc,
        "sourceSha": SHA,
        "sourceRunId": 123,
        "repository": REPOSITORY,
        "actor": actor,
        "token": TOKEN,
    }
    # 仅运行当前仓库生成的测试程序，不经过 shell。
    return subprocess.run(  # noqa: S603
        [sys.executable, "-c", program or pull.remote_program()],
        input=json.dumps(payload), capture_output=True, text=True, timeout=10,
    )


def calls(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


def test_三图成功后才打标且临时凭据被清理(fake_docker):
    doc, state_path, calls_path = fake_docker
    result = remote_result(doc)
    assert result.returncode == 0, result.stderr
    events = calls(calls_path)
    assert [event["action"] for event in events] == [
        "login", "pull", "pull", "pull", "tag", "tag", "tag"
    ]
    assert events[0]["mode"] == "0o700"
    assert not Path(events[0]["config"]).exists()
    assert TOKEN not in str(events)
    assert TOKEN not in result.stdout + result.stderr
    images = json.loads(state_path.read_text())["images"]
    for service in SERVICES:
        assert images[f"inkforge-{service}:{SHA}"]["id"] == doc["images"][service]["imageId"]


def test_准确匹配的本地镜像全部复用(fake_docker):
    doc, state_path, calls_path = fake_docker
    state = json.loads(state_path.read_text())
    for item in doc["images"].values():
        ref = item["repository"] + "@" + item["digest"]
        state["images"][ref] = {"id": item["imageId"], "digests": [ref]}
    state_path.write_text(json.dumps(state))
    result = remote_result(doc)
    assert result.returncode == 0, result.stderr
    assert [event["action"] for event in calls(calls_path)] == ["tag", "tag", "tag"]


def test_机器人actor也可用于临时登录(fake_docker):
    doc, _state_path, calls_path = fake_docker
    result = remote_result(doc, actor="github-actions[bot]")
    assert result.returncode == 0, result.stderr
    assert calls(calls_path)[0]["action"] == "login"


def test_容量不足时不登录不拉取不打标(fake_docker):
    doc, _state_path, calls_path = fake_docker
    for item in doc["images"].values():
        item["sizeBytes"] = 10**15
    result = remote_result(doc)
    assert result.returncode != 0
    assert "容量不足" in result.stderr
    assert calls(calls_path) == []


@pytest.mark.parametrize("failure", ["pull", "mismatch", "timeout"])
def test_拉取失败超时或身份错配不打标并清理凭据(fake_docker, monkeypatch, failure):
    doc, _state_path, calls_path = fake_docker
    if failure == "pull":
        monkeypatch.setenv("FAKE_PULL_FAIL", "1")
    elif failure == "mismatch":
        item = doc["images"]["web"]
        monkeypatch.setenv("FAKE_MISMATCH_REF", item["repository"] + "@" + item["digest"])
    else:
        monkeypatch.setenv("FAKE_PULL_SLEEP", "0.5")
    program = pull.remote_program()
    if failure == "timeout":
        program = program.replace("IMAGE_TIMEOUT_SECONDS = 900", "IMAGE_TIMEOUT_SECONDS = 0.1")
    result = remote_result(doc, program=program)
    assert result.returncode != 0
    events = calls(calls_path)
    assert not any(event["action"] == "tag" for event in events)
    assert not Path(events[0]["config"]).exists()
    assert TOKEN not in result.stdout + result.stderr


def test_已有同名标签指向不同Id时拒绝拉取(fake_docker):
    doc, state_path, calls_path = fake_docker
    state = json.loads(state_path.read_text())
    state["images"][f"inkforge-web:{SHA}"] = {"id": "sha256:" + "f" * 64, "digests": []}
    state_path.write_text(json.dumps(state))
    result = remote_result(doc)
    assert result.returncode != 0
    assert calls(calls_path) == []


def test_SIGTERM中断后清理临时凭据(fake_docker, monkeypatch):
    doc, _state_path, calls_path = fake_docker
    monkeypatch.setenv("FAKE_PULL_SLEEP", "1")
    payload = {
        "manifest": doc, "sourceSha": SHA, "sourceRunId": 123,
        "repository": REPOSITORY, "actor": "release-bot", "token": TOKEN,
    }
    process = subprocess.Popen(  # noqa: S603
        [sys.executable, "-c", pull.remote_program()],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True,
    )
    assert process.stdin is not None
    process.stdin.write(json.dumps(payload))
    process.stdin.close()
    deadline = time.monotonic() + 3
    while (
        not any(item["action"] == "pull" for item in calls(calls_path))
        and time.monotonic() < deadline
    ):
        time.sleep(0.01)
    assert any(item["action"] == "pull" for item in calls(calls_path))
    process.send_signal(signal.SIGTERM)
    assert process.wait(timeout=5) != 0
    events = calls(calls_path)
    assert not Path(events[0]["config"]).exists()
    assert not any(item["action"] == "tag" for item in events)


def test_等待标准输入也受整体时限约束():
    program = pull.remote_program().replace(
        "OVERALL_TIMEOUT_SECONDS = 3000", "OVERALL_TIMEOUT_SECONDS = 0.2"
    )
    process = subprocess.Popen(  # noqa: S603
        [sys.executable, "-c", program],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True,
    )
    try:
        assert process.wait(timeout=3) != 0
        assert process.stderr is not None
        assert "整体超时" in process.stderr.read()
    finally:
        if process.stdin:
            process.stdin.close()
        if process.poll() is None:
            process.kill()
            process.wait(timeout=3)


def test_本地SSH命令与输出不含令牌(tmp_path: Path, monkeypatch, capsys):
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest()))
    key = tmp_path / "key"
    known_hosts = tmp_path / "known_hosts"
    key.write_text("test")
    known_hosts.write_text("test")
    for name, value in {
        "SERVER_HOST": "private.example",
        "SERVER_USER": "deploy",
        "SSH_KEY_PATH": str(key),
        "SSH_KNOWN_HOSTS_FILE": str(known_hosts),
        "GITHUB_TOKEN": TOKEN,
        "GITHUB_ACTOR": "github-actions[bot]",
    }.items():
        monkeypatch.setenv(name, value)
    observed = {}

    def fake_stream(argv, payload, child_env, token, host):
        observed.update(argv=argv, input=payload, env=child_env, token=token, host=host)
        print("ok [凭据] [服务器]")
        return 0

    monkeypatch.setattr(pull, "run_ssh_streaming", fake_stream)
    assert pull.main([
        "--manifest", str(manifest_path), "--source-sha", SHA,
        "--source-run-id", "123", "--repository", REPOSITORY,
    ]) == 0
    assert TOKEN not in str(observed["argv"])
    assert TOKEN in observed["input"]
    assert "GITHUB_TOKEN" not in observed["env"]
    assert "StrictHostKeyChecking=yes" in str(observed["argv"])
    assert TOKEN not in capsys.readouterr().out


def test_阶段日志在SSH结束前实时脱敏转发(tmp_path: Path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake_ssh = bin_dir / "ssh"
    fake_ssh.write_text(
        "#!/usr/bin/env python3\n"
        "import json,os,sys,time\n"
        "data=json.load(sys.stdin)\n"
        "print('stage token='+data['token']+' host=private.example',flush=True)\n"
        "time.sleep(0.8)\n"
        "print('env_has_token='+str('GITHUB_TOKEN' in os.environ),flush=True)\n"
    )
    fake_ssh.chmod(0o755)
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest()))
    key = tmp_path / "key"
    known_hosts = tmp_path / "known_hosts"
    key.write_text("test")
    known_hosts.write_text("test")
    env = os.environ.copy()
    env.update({
        "PATH": str(bin_dir) + os.pathsep + env["PATH"],
        "SERVER_HOST": "private.example", "SERVER_USER": "deploy",
        "SSH_KEY_PATH": str(key), "SSH_KNOWN_HOSTS_FILE": str(known_hosts),
        "GITHUB_TOKEN": TOKEN, "GITHUB_ACTOR": "github-actions[bot]",
    })
    process = subprocess.Popen(  # noqa: S603
        [sys.executable, str(ROOT / "scripts" / "pull-release-images.py"),
         "--manifest", str(manifest_path), "--source-sha", SHA,
         "--source-run-id", "123", "--repository", REPOSITORY],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env,
    )
    try:
        assert process.stdout is not None
        ready, _, _ = select.select([process.stdout], [], [], 3)
        assert ready
        first_line = process.stdout.readline()
        assert "stage token=[凭据] host=[服务器]" in first_line
        assert TOKEN not in first_line
        assert process.poll() is None
        rest, error = process.communicate(timeout=5)
        assert process.returncode == 0, error
        assert "env_has_token=False" in rest
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=3)


def test_整体超时保留阶段日志并终止SSH(tmp_path: Path, monkeypatch, capsys):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake_ssh = bin_dir / "ssh"
    pid_path = tmp_path / "ssh.pid"
    fake_ssh.write_text(
        "#!/usr/bin/env python3\n"
        "import os,sys,time\n"
        "open(os.environ['FAKE_SSH_PID_PATH'],'w').write(str(os.getpid()))\n"
        "print('阶段开始',flush=True)\n"
        "time.sleep(10)\n"
    )
    fake_ssh.chmod(0o755)
    monkeypatch.setenv("PATH", str(bin_dir) + os.pathsep + os.environ["PATH"])
    monkeypatch.setenv("FAKE_SSH_PID_PATH", str(pid_path))
    monkeypatch.setattr(pull, "OVERALL_TIMEOUT_SECONDS", 1.0)
    monkeypatch.setattr(pull, "SSH_GRACE_SECONDS", 0)
    with pytest.raises(subprocess.TimeoutExpired):
        pull.run_ssh_streaming(["ssh"], "{}", os.environ.copy(), TOKEN, "private.example")
    assert "阶段开始" in capsys.readouterr().out
    pid = int(pid_path.read_text())
    with pytest.raises(ProcessLookupError):
        os.kill(pid, 0)
