"""使用隔离容器和本机进程验证视频模拟链路，不读取开发或生产环境文件。"""

from __future__ import annotations

import argparse
import atexit
import json
import os
import secrets
import shlex
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parents[2]
DOCKER_FALLBACK = Path("/Applications/Docker.app/Contents/Resources/bin/docker")
CORE_JAR = ROOT / "apps/core-api-java/target/inkforge-core-api-0.1.0-SNAPSHOT.jar"
DURABLE_AGENT_MIGRATION = ROOT / "scripts/migrations/20260831_durable_agent_execution.sql"
sys.path.insert(0, str(ROOT))


def executable(name: str, fallback: Path | None = None) -> Path:
    found = shutil.which(name)
    if found:
        return Path(found).resolve()
    if fallback is not None and fallback.is_file():
        return fallback
    raise RuntimeError(f"本机缺少必需工具：{name}")


def java_home() -> Path:
    configured = os.environ.get("INKFORGE_VIDEO_E2E_JAVA_HOME", "").strip()
    for candidate in (
        Path(configured) if configured else None,
        Path("/opt/homebrew/opt/openjdk@21"),
        Path("/usr/local/opt/openjdk@21"),
    ):
        if candidate is not None and (candidate / "bin/java").is_file():
            return candidate.resolve()
    raise RuntimeError("本机缺少 JDK 21；可用 INKFORGE_VIDEO_E2E_JAVA_HOME 指定")


def run(
    args: list[str],
    *,
    input_text: str | None = None,
    timeout: float = 90,
    environment: dict[str, str] | None = None,
) -> str:
    result = subprocess.run(  # noqa: S603 - 仅固定本机工具与当前隔离容器
        args,
        cwd=ROOT,
        env=environment,
        input=input_text,
        text=True,
        capture_output=True,
        check=False,
        timeout=timeout,
    )
    if result.returncode:
        raise RuntimeError(f"本机操作失败：{args[0]}，退出码 {result.returncode}\n{result.stderr}")
    return result.stdout.strip()


def port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def private_json(path: Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    temporary.chmod(0o600)
    temporary.replace(path)


def env_file(path: Path, values: dict[str, str]) -> None:
    path.write_text(
        "".join(f"export {key}={shlex.quote(value)}\n" for key, value in values.items())
    )
    path.chmod(0o600)


def prepare(evidence_dir: Path | None = None) -> Path:
    from scripts.generate_service_keys import generate_service_keys

    docker = executable("docker", DOCKER_FALLBACK)
    jdk = java_home()
    directory = Path(tempfile.mkdtemp(prefix="inkforge-video-local-e2e-")).resolve()
    directory.chmod(0o700)
    generate_service_keys(directory / "keys")
    ports = {
        name: port()
        for name in ("postgres", "redis", "executionRedis", "core", "agent", "web")
    }
    prefix = "inkforge-video-local-" + secrets.token_hex(4)
    pg_password = secrets.token_urlsafe(24)
    pg_env = directory / "postgres.env"
    pg_env.write_text(
        f"POSTGRES_USER=inkforge_e2e\nPOSTGRES_PASSWORD={pg_password}\nPOSTGRES_DB=novelwriterdev\n"
    )
    pg_env.chmod(0o600)
    containers = {name: f"{prefix}-{name}" for name in ("postgres", "redis", "execution-redis")}
    pg_volume = prefix + "-postgres"
    execution_volume = prefix + "-execution"
    evidence = (
        evidence_dir.resolve()
        if evidence_dir is not None
        else ROOT
        / "output"
        / "video-local-e2e"
        / datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    )
    evidence.mkdir(parents=True, exist_ok=True)
    state = {
        "simulationOnly": True,
        "directory": str(directory),
        "evidenceDirectory": str(evidence),
        "docker": str(docker),
        "javaHome": str(jdk),
        "ports": ports,
        "containers": containers,
        "volumes": [pg_volume, execution_volume],
        "coreUrl": f"http://127.0.0.1:{ports['core']}",
        "agentUrl": f"http://127.0.0.1:{ports['agent']}",
        "webUrl": f"http://127.0.0.1:{ports['web']}",
        "processes": {},
        "createdAt": datetime.now(UTC).isoformat(),
    }
    private_json(directory / "state.json", state)
    cleanup_guard = {"active": True}

    def rollback_failed_prepare() -> None:
        if not cleanup_guard["active"]:
            return
        try:
            cleanup(directory)
        except Exception as cleanup_error:
            # 原始 prepare 异常仍是主错误；这里只记录清理失败类型，避免输出一次性凭据。
            print(
                f"prepare 失败后的隔离资源清理异常：{cleanup_error.__class__.__name__}",
                file=sys.stderr,
            )

    atexit.register(rollback_failed_prepare)
    for volume in (pg_volume, execution_volume):
        run([str(docker), "volume", "create", "--label", f"inkforge.video.local={prefix}", volume])
    run([
        str(docker), "run", "--detach", "--pull=never", "--name", containers["postgres"],
        "--label", f"inkforge.video.local={prefix}", "--memory=384m",
        "--publish", f"127.0.0.1:{ports['postgres']}:5432", "--env-file", str(pg_env),
        "--volume", f"{pg_volume}:/var/lib/postgresql/data", "pgvector/pgvector:0.8.0-pg14",
    ])
    for name, key in (("redis", "redis"), ("execution-redis", "executionRedis")):
        command = [
            str(docker), "run", "--detach", "--pull=never", "--name", containers[name],
            "--label", f"inkforge.video.local={prefix}", "--memory=96m",
            "--publish", f"127.0.0.1:{ports[key]}:6379",
        ]
        if name == "execution-redis":
            command.extend(["--volume", f"{execution_volume}:/data"])
        command.extend(["redis:7.4-alpine", "redis-server", "--save", ""])
        if name == "execution-redis":
            command.extend(["--appendonly", "yes", "--appendfsync", "everysec"])
        run(command)
    deadline = time.monotonic() + 45
    while True:
        try:
            run([str(docker), "exec", containers["postgres"], "pg_isready", "-U", "inkforge_e2e"])
            break
        except RuntimeError:
            if time.monotonic() >= deadline:
                raise
            time.sleep(0.25)
    run([
        str(docker), "exec", "-i", containers["postgres"], "psql", "-v", "ON_ERROR_STOP=1",
        "-U", "inkforge_e2e", "-d", "novelwriterdev",
    ], input_text=(
        ROOT / "apps/core-api-java/src/test/resources/db/novelwriterdev-schema.sql"
    ).read_text())
    # 测试 fixture 是 Durable Agent V2 迁移前基线。隔离库必须走与真实升级相同的具名
    # 迁移，避免用手工补列绕过 Core 的精确 schema gate。
    run(
        [
            str(docker),
            "exec",
            "-i",
            containers["postgres"],
            "psql",
            "-v",
            "ON_ERROR_STOP=1",
            "-U",
            "inkforge_e2e",
            "-d",
            "novelwriterdev",
        ],
        input_text=DURABLE_AGENT_MIGRATION.read_text(),
        timeout=180,
    )
    for container, script in (
        (containers["redis"], "durable_agent_v1_drain_index_initialize.lua"),
        (containers["execution-redis"], "durable_agent_v2_drain_index_initialize.lua"),
    ):
        run([str(docker), "exec", "-i", container, "redis-cli", "-x", "EVAL", (
            ROOT / "scripts" / script
        ).read_text(), "0"], input_text="")
    uploads = directory / "uploads"
    uploads.mkdir()
    (directory / "logs").mkdir()
    keys = directory / "keys"
    jwt_secret = secrets.token_urlsafe(48)
    common = {
        "ENVIRONMENT": "test",
        "REDIS_URL": f"redis://127.0.0.1:{ports['redis']}/0",
        "SEEDANCE_EXECUTION_MODE": "simulated",
        "SEEDANCE_ENABLED": "false",
        "SEEDANCE_CONFIGURED": "false",
        "SEEDANCE_API_KEY": "",
        "OPENAI_API_KEY": "",
        "MODEL_PROVIDER": "fake",
        "PATH": f"{jdk / 'bin'}:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin",
    }
    core = {
        **common,
        "JAVA_HOME": str(jdk),
        "PORT": str(ports["core"]),
        "SERVER_ADDRESS": "127.0.0.1",
        "DATABASE_URL": f"postgresql://inkforge_e2e:{pg_password}@127.0.0.1:{ports['postgres']}/novelwriterdev",
        "JWT_SECRET": jwt_secret,
        "ALLOW_INSECURE_HTTP_AUTH": "true",
        "USERNAME_REGISTRATION_ENABLED": "true",
        "PHONE_AUTH_ENABLED": "false",
        "PHONE_AUTH_SEND_ENABLED": "false",
        "AGENT_SERVICE_URL": str(state["agentUrl"]),
        "TRUSTED_AGENT_CIDRS": "127.0.0.1/32,::1/128",
        "TRUSTED_PROXY_CIDRS": "127.0.0.1/32,::1/128",
        "CORE_SERVICE_PRIVATE_KEY_PATH": str(keys / "core-to-agent-private.pem"),
        "CORE_SERVICE_KEY_ID": "core-api-v1",
        "AGENT_SERVICE_PUBLIC_KEY_PATH": str(keys / "agent-to-core-jwks.json"),
        "UPLOADS_ROOT": str(uploads),
        "VIDEO_PREVIEW_ENABLED": "true",
        # 隔离环境需要同时验证 V2 剧本/分镜任务和模拟逐镜任务的耐久派发；供应商仍由
        # SEEDANCE_EXECUTION_MODE=simulated 硬隔离，且没有任何 API Key。
        "VIDEO_DISPATCH_ENABLED": "true",
        "VIDEO_DISPATCH_NAMESPACE": "local-simulated-video",
        "DURABLE_AGENT_EXECUTION_SCHEMA_READY": "true",
        "DURABLE_AGENT_EXECUTION_ROUTE_MODE": "all",
        "V1_FRESH_AGENT_STARTS_ENABLED": "false",
        "AGENT_MAX_CONCURRENCY": "1",
    }
    agent = {
        **common,
        "EXECUTION_REDIS_URL": f"redis://127.0.0.1:{ports['executionRedis']}/0",
        "TRUSTED_CORE_CIDRS": "127.0.0.1/32,::1/128",
        "CORE_SERVICE_PUBLIC_KEY_PATH": str(keys / "core-to-agent-jwks.json"),
        "AGENT_SERVICE_PRIVATE_KEY_PATH": str(keys / "agent-to-core-private.pem"),
        "AGENT_SERVICE_KEY_ID": "agent-service-v1",
        "CORE_API_URL": str(state["coreUrl"]),
        "WORKFLOW_HUMAN_LOG_DIR": str(directory / "agent-logs"),
        "PYTHONPATH": ":".join((
            str(ROOT / "apps/agent-service/src"),
            str(ROOT / "packages/service-contracts/src"),
            str(ROOT / "packages/service-auth/src"),
        )),
    }
    env_file(directory / "core.env", core)
    env_file(directory / "agent.env", agent)
    env_file(directory / "web.env", {
        "CORE_API_INTERNAL_URL": str(state["coreUrl"]),
        "NEXT_PUBLIC_CORE_API_URL": "",
        # Next 页面路由会在进入工作台前本地验签，必须和隔离 Core 使用同一份一次性密钥。
        "JWT_SECRET": jwt_secret,
        "PATH": common["PATH"],
    })
    commands = {
        "agent": f"source {shlex.quote(str(directory / 'agent.env'))}\n"
        f"exec {shlex.quote(str(ROOT / '.venv/bin/python'))} -m uvicorn "
        "inkforge_agents.app:create_app "
        f"--factory --host 127.0.0.1 --port {ports['agent']} --workers 1 --no-access-log\n",
        "core": f"source {shlex.quote(str(directory / 'core.env'))}\n"
        f"exec {shlex.quote(str(jdk / 'bin/java'))} -Xms64m -Xmx640m -jar "
        f"{shlex.quote(str(CORE_JAR))}\n",
        "web": f"source {shlex.quote(str(directory / 'web.env'))}\n"
        f"cd {shlex.quote(str(ROOT / 'apps/web'))}\n"
        f"exec ../../node_modules/.bin/next dev --hostname 127.0.0.1 --port {ports['web']}\n",
    }
    for name, command in commands.items():
        target = directory / f"start-{name}.sh"
        target.write_text("#!/bin/zsh\nset -euo pipefail\n" + command)
        target.chmod(0o700)
    cleanup_guard["active"] = False
    atexit.unregister(rollback_failed_prepare)
    print(
        json.dumps(
            {
                "directory": str(directory),
                "evidenceDirectory": str(evidence),
                "simulationOnly": True,
                "urls": {
                    "core": state["coreUrl"],
                    "agent": state["agentUrl"],
                    "web": state["webUrl"],
                },
            },
            ensure_ascii=False,
        )
    )
    return directory


def load_state(directory: Path) -> dict[str, Any]:
    directory = directory.resolve()
    path = directory / "state.json"
    try:
        value = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exception:
        raise RuntimeError(f"无法读取隔离验收状态：{path}") from exception
    if not isinstance(value, dict) or value.get("simulationOnly") is not True:
        raise RuntimeError("拒绝操作不是本脚本创建的模拟验收目录")
    if Path(str(value.get("directory", ""))).resolve() != directory:
        raise RuntimeError("验收状态目录身份不一致")
    return value


def save_state(directory: Path, state: dict[str, Any]) -> None:
    private_json(directory.resolve() / "state.json", state)


def build() -> None:
    jdk = java_home()
    environment = {
        **os.environ,
        "JAVA_HOME": str(jdk),
        "PATH": ":".join(
            (
                str(jdk / "bin"),
                "/opt/homebrew/bin",
                "/usr/local/bin",
                "/usr/bin",
                "/bin",
                os.environ.get("PATH", ""),
            )
        ),
    }
    run(
        [
            str(ROOT / "mvnw"),
            "-pl",
            "apps/core-api-java",
            "-am",
            "package",
            "-DskipTests",
        ],
        timeout=1_800,
        environment=environment,
    )
    if not CORE_JAR.is_file():
        raise RuntimeError(f"Java Core 构建未生成预期产物：{CORE_JAR}")
    print(json.dumps({"built": True, "coreJar": str(CORE_JAR)}, ensure_ascii=False))


def start(directory: Path) -> None:
    state = load_state(directory)
    if not CORE_JAR.is_file():
        raise RuntimeError("缺少 Java Core JAR，请先执行 build")
    processes = state.get("processes")
    if not isinstance(processes, dict):
        processes = {}
    for name in ("agent", "core", "web"):
        existing = processes.get(name)
        if isinstance(existing, int):
            try:
                os.kill(existing, 0)
            except ProcessLookupError:
                pass
            else:
                raise RuntimeError(f"{name} 已由 PID {existing} 运行")
        log_path = directory / "logs" / f"{name}.log"
        with log_path.open("ab", buffering=0) as log:
            process = subprocess.Popen(  # noqa: S603 - 只启动 prepare 生成的固定脚本
                [str(directory / f"start-{name}.sh")],
                cwd=ROOT,
                env={
                    "HOME": str(directory),
                    "LANG": "en_US.UTF-8",
                    "PATH": "/usr/bin:/bin",
                    "TMPDIR": str(directory),
                },
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        processes[name] = process.pid
        state["processes"] = processes
        save_state(directory, state)
    print(json.dumps({"started": processes}, ensure_ascii=False))


def _wait_http(url: str, *, expected: set[int], timeout: float, label: str) -> None:
    deadline = time.monotonic() + timeout
    last = "尚未连接"
    with httpx.Client(timeout=2, trust_env=False, follow_redirects=False) as client:
        while time.monotonic() < deadline:
            try:
                response = client.get(url)
                last = f"HTTP {response.status_code}"
                if response.status_code in expected:
                    return
            except httpx.HTTPError as exception:
                last = exception.__class__.__name__
            time.sleep(0.25)
    raise RuntimeError(f"{label} 未在限定时间内就绪：{last}")


def wait(directory: Path) -> None:
    state = load_state(directory)
    _wait_http(
        str(state["agentUrl"]) + "/internal/v1/health/ready",
        expected={200},
        timeout=90,
        label="Agent",
    )
    _wait_http(
        str(state["coreUrl"]) + "/api/v1/health/ready",
        expected={200},
        timeout=150,
        label="Java Core",
    )
    _wait_http(
        str(state["webUrl"]) + "/login?mode=register",
        expected={200},
        timeout=150,
        label="Web",
    )
    state["readyAt"] = datetime.now(UTC).isoformat()
    save_state(directory, state)
    print(json.dumps({"ready": True, "readyAt": state["readyAt"]}, ensure_ascii=False))


def scenario(directory: Path, *, browser: bool = True) -> Path:
    from video_scenario import run_scenario

    state = load_state(directory)
    evidence = run_scenario(directory.resolve(), state, browser=browser)
    state["scenarioEvidence"] = str(evidence)
    save_state(directory, state)
    print(json.dumps({"scenario": "passed", "evidence": str(evidence)}, ensure_ascii=False))
    return evidence


def _stop_process(pid: int) -> None:
    try:
        os.killpg(pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        try:
            reaped, _ = os.waitpid(pid, os.WNOHANG)
        except ChildProcessError:
            reaped = 0
        if reaped == pid:
            return
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return
        time.sleep(0.1)
    try:
        os.killpg(pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    try:
        os.waitpid(pid, 0)
    except (ChildProcessError, ProcessLookupError):
        pass


def cleanup(directory: Path, *, remove_directory: bool = True) -> dict[str, object]:
    directory = directory.resolve()
    state = load_state(directory)
    cleanup_errors: list[str] = []
    processes = state.get("processes") or {}
    if isinstance(processes, dict):
        for pid in reversed(list(processes.values())):
            if isinstance(pid, int) and pid > 1:
                try:
                    _stop_process(pid)
                except OSError as exception:
                    # 单个进程异常不能阻断后续容器和卷清理；保留状态目录供再次 cleanup。
                    cleanup_errors.append(f"process:{pid}:{exception.__class__.__name__}")
    docker = Path(str(state["docker"]))
    residual_containers: list[str] = []
    residual_volumes: list[str] = []
    containers = state.get("containers") or {}
    if isinstance(containers, dict):
        for container in containers.values():
            if not isinstance(container, str):
                continue
            try:
                subprocess.run(  # noqa: S603 - 只删除当前状态中随机命名的隔离容器
                    [str(docker), "rm", "--force", container],
                    cwd=ROOT,
                    text=True,
                    capture_output=True,
                    check=False,
                    timeout=60,
                )
            except subprocess.TimeoutExpired:
                cleanup_errors.append(f"container:{container}:TimeoutExpired")
            inspected = subprocess.run(  # noqa: S603 - 只读检查当前隔离容器
                [str(docker), "container", "inspect", container],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
                timeout=30,
            )
            if inspected.returncode == 0:
                residual_containers.append(container)
    for volume in state.get("volumes") or []:
        if not isinstance(volume, str):
            continue
        try:
            subprocess.run(  # noqa: S603 - 只删除当前状态中随机命名的隔离卷
                [str(docker), "volume", "rm", volume],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
                timeout=60,
            )
        except subprocess.TimeoutExpired:
            cleanup_errors.append(f"volume:{volume}:TimeoutExpired")
        inspected = subprocess.run(  # noqa: S603 - 只读检查当前隔离卷
            [str(docker), "volume", "inspect", volume],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
            timeout=30,
        )
        if inspected.returncode == 0:
            residual_volumes.append(volume)
    result: dict[str, object] = {
        "residualContainers": residual_containers,
        "residualVolumes": residual_volumes,
        "cleanupErrors": cleanup_errors,
        "evidenceDirectory": state.get("evidenceDirectory"),
    }
    if remove_directory and not (
        cleanup_errors or residual_containers or residual_volumes
    ):
        shutil.rmtree(directory, ignore_errors=True)
        result["temporaryDirectoryRemoved"] = not directory.exists()
    if cleanup_errors or residual_containers or residual_volumes:
        raise RuntimeError(f"隔离资源清理不完整：{result}")
    print(json.dumps(result, ensure_ascii=False))
    return result


def run_all(*, evidence_dir: Path | None, browser: bool, keep: bool) -> None:
    build()
    directory = prepare(evidence_dir)
    failure: BaseException | None = None
    try:
        start(directory)
        wait(directory)
        scenario(directory, browser=browser)
    except BaseException as exception:
        failure = exception
        raise
    finally:
        try:
            cleanup(directory, remove_directory=not keep)
        except BaseException as cleanup_exception:
            if failure is None:
                raise
            print(
                f"场景失败后的隔离资源清理异常：{cleanup_exception}",
                file=sys.stderr,
            )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action",
        choices=["build", "prepare", "start", "wait", "scenario", "cleanup", "all"],
    )
    parser.add_argument("directory", nargs="?", type=Path)
    parser.add_argument("--evidence-dir", type=Path)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--keep", action="store_true", help="all 完成后保留临时目录")
    args = parser.parse_args()
    if args.action in {"start", "wait", "scenario", "cleanup"} and args.directory is None:
        parser.error(f"{args.action} 需要 prepare 返回的目录")
    if args.action == "build":
        build()
    elif args.action == "prepare":
        prepare(args.evidence_dir)
    elif args.action == "start":
        start(args.directory)
    elif args.action == "wait":
        wait(args.directory)
    elif args.action == "scenario":
        scenario(args.directory, browser=not args.no_browser)
    elif args.action == "cleanup":
        cleanup(args.directory, remove_directory=not args.keep)
    else:
        run_all(evidence_dir=args.evidence_dir, browser=not args.no_browser, keep=args.keep)


if __name__ == "__main__":
    main()
