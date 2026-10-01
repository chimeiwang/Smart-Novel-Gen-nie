#!/usr/bin/env python3
"""通过严格 SSH 在生产主机按已验证 digest 拉取镜像。"""

from __future__ import annotations

import argparse
import base64
import json
import os
import queue
import re
import shlex
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

from release_manifest import load_manifest

OVERALL_TIMEOUT_SECONDS = 3000
SSH_GRACE_SECONDS = 60
CONNECT_TIMEOUT_SECONDS = 15
_TOKEN = re.compile(r"[A-Za-z0-9_-]{20,255}\Z")
_ACTOR = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})(?:\[bot\])?\Z")


# 引导程序通过 SSH 命令行传递，但只包含仓库代码；令牌和清单从标准输入读取。
REMOTE_PROGRAM = r'''
from __future__ import annotations

import base64
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time

MODULE_SOURCE = base64.b64decode("__MANIFEST_SOURCE__").decode("utf-8")
module = {"__name__": "release_manifest", "__file__": "<embedded-release-manifest>"}
exec(compile(MODULE_SOURCE, "<embedded-release-manifest>", "exec"), module)
validate_manifest = module["validate_manifest"]
SERVICES = ("web", "core-api", "agent-service")
SAFETY_BYTES = 536870912
IMAGE_TIMEOUT_SECONDS = 900
OVERALL_TIMEOUT_SECONDS = 3000
_TOKEN = re.compile(r"[A-Za-z0-9_-]{20,255}\Z")
_ACTOR = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})(?:\[bot\])?\Z")


class PullFailure(Exception):
    pass


def log(message):
    print(message, flush=True)


def unique_pairs(pairs):
    values = {}
    for key, value in pairs:
        if key in values:
            raise PullFailure("输入包含重复 JSON 键")
        values[key] = value
    return values


def deadline_timeout(deadline, limit):
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise PullFailure("镜像拉取整体超时")
    return min(limit, remaining)


def command(argv, *, deadline, stage, service="发布", timeout=30,
            input_text=None, env=None, allow_missing=False):
    remaining = deadline - time.monotonic()
    effective_timeout = deadline_timeout(deadline, timeout)
    started = time.monotonic()
    try:
        result = subprocess.run(
            argv, input=input_text, capture_output=True, text=True, env=env,
            timeout=effective_timeout, check=False,
        )
    except subprocess.TimeoutExpired as exc:
        boundary = "整体时限" if remaining <= timeout else "单阶段时限"
        raise PullFailure(
            service + "：" + stage + "超过" + boundary + "，已运行 "
            + str(round(time.monotonic() - started, 1)) + " 秒"
        ) from exc
    if result.returncode and not allow_missing:
        # Docker 的错误文本可能包含 registry 签名 URL 或认证细节，不能转写到 CI。
        raise PullFailure(
            service + "：" + stage + "失败，exitCode=" + str(result.returncode)
            + "，耗时 " + str(round(time.monotonic() - started, 1)) + " 秒"
        )
    return result


def image_info(reference, deadline):
    result = command(
        ["docker", "image", "inspect", "--format", "{{json .Id}}|{{json .RepoDigests}}", reference],
        deadline=deadline, stage="镜像检查", allow_missing=True,
    )
    if result.returncode:
        command(
            ["docker", "info", "--format", "{{.DockerRootDir}}"],
            deadline=deadline, stage="Docker 状态检查",
        )
        return None
    try:
        image_id_raw, repo_digests_raw = result.stdout.strip().split("|", 1)
        image_id = json.loads(image_id_raw)
        repo_digests = json.loads(repo_digests_raw) or []
    except (ValueError, TypeError) as exc:
        raise PullFailure("Docker 镜像检查输出无效") from exc
    if not isinstance(image_id, str) or not isinstance(repo_digests, list):
        raise PullFailure("Docker 镜像检查字段无效")
    return image_id, repo_digests


def verified_image(service, item, deadline):
    reference = item["repository"] + "@" + item["digest"]
    info = image_info(reference, deadline)
    if info is None:
        return False
    image_id, repo_digests = info
    if image_id != item["imageId"] or reference not in repo_digests:
        raise PullFailure(service + " 的 image ID 或 RepoDigests 与清单不匹配")
    return True


def check_capacity(missing, deadline):
    result = command(
        ["docker", "info", "--format", "{{.DockerRootDir}}"],
        deadline=deadline, stage="容量预检",
    )
    docker_root = result.stdout.strip()
    if not docker_root or not os.path.isabs(docker_root):
        raise PullFailure("无法确认 Docker 数据目录")
    available = shutil.disk_usage(docker_root).free
    # 首次拉取时压缩层与解包内容可能并存，按两倍逻辑大小保守预留。
    required = 2 * sum(item["sizeBytes"] for item in missing) + SAFETY_BYTES
    if available < required:
        raise PullFailure("服务器 Docker 容量不足")
    log("Docker 容量预检通过：需要 " + str(required) + " 字节，可用 " + str(available) + " 字节")


def receive_payload():
    try:
        payload = json.load(sys.stdin, object_pairs_hook=unique_pairs)
    except (ValueError, TypeError, UnicodeError) as exc:
        raise PullFailure("远端输入无法解析") from exc
    if type(payload) is not dict or set(payload) != {
        "manifest", "sourceSha", "sourceRunId", "repository", "actor", "token"
    }:
        raise PullFailure("远端输入字段无效")
    actor, token = payload["actor"], payload["token"]
    if not isinstance(actor, str) or not _ACTOR.fullmatch(actor):
        raise PullFailure("GHCR 用户格式无效")
    if not isinstance(token, str) or not _TOKEN.fullmatch(token):
        raise PullFailure("GHCR 令牌格式无效")
    try:
        manifest = validate_manifest(
            payload["manifest"], payload["sourceSha"], payload["sourceRunId"], payload["repository"]
        )
    except (ValueError, TypeError) as exc:
        raise PullFailure("远端发布清单校验失败") from exc
    return manifest, actor, token


def main():
    deadline = time.monotonic() + OVERALL_TIMEOUT_SECONDS
    # 标准输入同样纳入总时限，避免 Runner 中断后远端永远卡在令牌接收。
    signal.setitimer(signal.ITIMER_REAL, OVERALL_TIMEOUT_SECONDS)
    try:
        run_release(deadline)
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)


def run_release(deadline):
    manifest, actor, token = receive_payload()
    images = manifest["images"]
    sha = manifest["sourceSha"]
    for service in SERVICES:
        tag = "inkforge-" + service + ":" + sha
        existing = image_info(tag, deadline)
        if existing is not None and existing[0] != images[service]["imageId"]:
            raise PullFailure(service + " 的现有本地标签指向不同镜像")

    missing = []
    for service in SERVICES:
        if verified_image(service, images[service], deadline):
            log(service + "：现有 digest 与 image ID 匹配，复用")
        else:
            missing.append(images[service])
    check_capacity(missing, deadline)

    config_dir = None
    try:
        if missing:
            config_dir = tempfile.mkdtemp(prefix="inkforge-ghcr-", dir="/tmp")
            os.chmod(config_dir, 0o700)
            docker_env = os.environ.copy()
            docker_env["DOCKER_CONFIG"] = config_dir
            command(
                ["docker", "login", "ghcr.io", "--username", actor, "--password-stdin"],
                deadline=deadline, stage="GHCR 临时登录", timeout=30,
                input_text=token + "\n", env=docker_env,
            )
            log("GHCR 临时登录成功")
            for service in SERVICES:
                item = images[service]
                if item not in missing:
                    continue
                reference = item["repository"] + "@" + item["digest"]
                started = time.monotonic()
                log(service + "：开始按 digest 拉取")
                command(
                    ["docker", "pull", reference], deadline=deadline,
                    stage="按 digest 拉取", service=service,
                    timeout=IMAGE_TIMEOUT_SECONDS, env=docker_env,
                )
                if not verified_image(service, item, deadline):
                    raise PullFailure(service + " 拉取后未发现指定 digest")
                log(
                    service + "：拉取和身份校验通过，耗时 "
                    + str(round(time.monotonic() - started, 1)) + " 秒"
                )

        for service in SERVICES:
            if not verified_image(service, images[service], deadline):
                raise PullFailure(service + " 在打标前失去已校验镜像")
        # 所有 digest 经二次校验后才创建本次 SHA 标签；旧版本标签始终不变。
        for service in SERVICES:
            item = images[service]
            tag = "inkforge-" + service + ":" + sha
            existing = image_info(tag, deadline)
            if existing is None:
                command(
                    ["docker", "image", "tag", item["imageId"], tag],
                    deadline=deadline, stage="本地 SHA 打标", service=service,
                )
            elif existing[0] != item["imageId"]:
                raise PullFailure(service + " 的本地标签在拉取期间被替换")
            log(service + "：本地 SHA 标签已核对")
    finally:
        if config_dir is not None:
            try:
                shutil.rmtree(config_dir)
            except OSError as exc:
                raise PullFailure("本次 GHCR 临时凭据清理失败") from exc
    log("三张发布镜像拉取、身份校验与打标完成")


def interrupted(signum, _frame):
    if signum == signal.SIGALRM:
        raise PullFailure("镜像拉取整体超时")
    raise PullFailure("镜像拉取被中断")


if __name__ == "__main__":
    for signum in (signal.SIGTERM, signal.SIGHUP, signal.SIGINT, signal.SIGALRM):
        signal.signal(signum, interrupted)
    try:
        main()
    except PullFailure as exc:
        print("生产镜像拉取失败：" + str(exc), file=sys.stderr, flush=True)
        raise SystemExit(1) from None
'''


def remote_program() -> str:
    source = (Path(__file__).with_name("release_manifest.py")).read_bytes()
    return REMOTE_PROGRAM.replace("__MANIFEST_SOURCE__", base64.b64encode(source).decode("ascii"))


def checked_environment() -> tuple[str, str, str, str, str, str]:
    names = (
        "SERVER_HOST", "SERVER_USER", "SSH_KEY_PATH", "SSH_KNOWN_HOSTS_FILE",
        "GITHUB_TOKEN", "GITHUB_ACTOR",
    )
    values = tuple(os.environ.get(name, "") for name in names)
    if any(not value for value in values):
        raise ValueError("生产镜像拉取缺少 SSH 或 GHCR 环境配置")
    host, user, key_path, known_hosts_path, token, actor = values
    if not _TOKEN.fullmatch(token) or not _ACTOR.fullmatch(actor):
        raise ValueError("GHCR 凭据格式无效")
    for path in (key_path, known_hosts_path):
        file = Path(path)
        if not file.is_file() or not os.access(file, os.R_OK) or file.stat().st_size == 0:
            raise ValueError("SSH 凭据或已核验主机文件不可读")
    return host, user, key_path, known_hosts_path, token, actor


def _stop_ssh(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    # 独立进程组保证本地总时限到达时，SSH 及其子进程一并退出。
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait(timeout=5)


def run_ssh_streaming(
    ssh_command: list[str], payload: str, child_env: dict[str, str], token: str, host: str
) -> int:
    deadline = time.monotonic() + OVERALL_TIMEOUT_SECONDS + SSH_GRACE_SECONDS
    # stderr 合并进 stdout，单个读取线程不会因另一条管道填满而死锁。
    process = subprocess.Popen(  # noqa: S603
        ssh_command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, text=True, bufsize=1, env=child_env,
        start_new_session=True,
    )
    if process.stdout is None or process.stdin is None:
        _stop_ssh(process)
        raise ValueError("SSH 标准流不可用")
    stdout_pipe = process.stdout
    stdin_pipe = process.stdin
    lines: queue.Queue[str | None] = queue.Queue()

    def read_lines() -> None:
        try:
            for line in stdout_pipe:
                lines.put(line)
        finally:
            lines.put(None)

    reader = threading.Thread(target=read_lines, name="inkforge-ssh-log-reader", daemon=True)
    reader.start()
    try:
        try:
            stdin_pipe.write(payload)
        except BrokenPipeError:
            pass
        finally:
            try:
                stdin_pipe.close()
            except BrokenPipeError:
                pass
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise subprocess.TimeoutExpired(
                    ssh_command, OVERALL_TIMEOUT_SECONDS + SSH_GRACE_SECONDS
                )
            try:
                line = lines.get(timeout=min(0.5, remaining))
            except queue.Empty:
                continue
            if line is None:
                break
            print(line.replace(token, "[凭据]").replace(host, "[服务器]"), end="", flush=True)
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise subprocess.TimeoutExpired(
                ssh_command, OVERALL_TIMEOUT_SECONDS + SSH_GRACE_SECONDS
            )
        return process.wait(timeout=remaining)
    finally:
        _stop_ssh(process)
        reader.join(timeout=1)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="从 GHCR 按清单拉取生产镜像")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--source-run-id", required=True, type=int)
    parser.add_argument("--repository", required=True)
    args = parser.parse_args(argv)

    try:
        manifest = load_manifest(
            args.manifest, args.source_sha, args.source_run_id, args.repository
        )
        host, user, key_path, known_hosts_path, token, actor = checked_environment()
        encoded_program = base64.b64encode(remote_program().encode("utf-8")).decode("ascii")
        remote_command = "python3 -c " + shlex.quote(
            'import base64;exec(compile(base64.b64decode("' + encoded_program
            + '"),"<inkforge-ghcr-bootstrap>","exec"))'
        )
        ssh_command = [
            "ssh", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes",
            "-o", "UserKnownHostsFile=" + known_hosts_path,
            "-o", "ConnectTimeout=" + str(CONNECT_TIMEOUT_SECONDS),
            "-o", "ServerAliveInterval=30", "-o", "ServerAliveCountMax=20",
            "-i", key_path, user + "@" + host, remote_command,
        ]
        payload = json.dumps({
            "manifest": manifest, "sourceSha": args.source_sha,
            "sourceRunId": args.source_run_id, "repository": args.repository,
            "actor": actor, "token": token,
        }, ensure_ascii=False)
        child_env = os.environ.copy()
        child_env.pop("GITHUB_TOKEN", None)
        # 固定 ssh 可执行文件、参数数组和严格主机检查；不经过本地 shell。
        if run_ssh_streaming(ssh_command, payload, child_env, token, host):
            raise ValueError("生产镜像拉取未完成")
        return 0
    except subprocess.TimeoutExpired:
        print("生产镜像拉取失败：SSH 整体超时", file=sys.stderr)
        return 1
    except (ValueError, OSError) as exc:
        # 不转写异常原文，避免带出 SSH 地址、凭据或 registry 临时 URL。
        print("生产镜像拉取失败：" + type(exc).__name__, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
