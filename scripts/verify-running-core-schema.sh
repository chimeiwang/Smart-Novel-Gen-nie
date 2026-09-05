#!/bin/sh
set -eu

# 仅在独立受限容器中启动结构守卫；绝不在活动 Core 内叠加 JVM。
command -v python3 >/dev/null 2>&1 || { echo "结构探针缺少 python3" >&2; exit 2; }
command -v docker >/dev/null 2>&1 || { echo "结构探针缺少 docker" >&2; exit 2; }

exec python3 - "$@" <<'PY'
import json
import os
import re
import signal
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path


class ProbeFailure(Exception):
    def __init__(self, message, status=1):
        super().__init__(message)
        self.status = status


def docker(arguments, timeout=10):
    try:
        return subprocess.run(
            ["docker", *arguments],
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as error:
        raise ProbeFailure("结构探针 Docker 操作超时", 124) from error
    except OSError as error:
        raise ProbeFailure("结构探针无法调用 Docker", 2) from error


def inspect(container_id, allow_missing=False):
    result = docker(["inspect", "--type", "container", container_id])
    if result.returncode != 0:
        if allow_missing:
            # inspect 失败不等于容器已回收；必须由成功的精确枚举确认不存在。
            if re.fullmatch(r"[0-9a-f]{64}", container_id):
                target_filter = "id=" + container_id
            elif re.fullmatch(r"inkforge-schema-probe-[0-9a-f]{32}", container_id):
                target_filter = "name=^/" + container_id + "$"
            else:
                raise ProbeFailure("探针清理身份格式无效")
            remaining = docker(["ps", "--all", "--quiet", "--no-trunc", "--filter", target_filter])
            if remaining.returncode == 0 and not remaining.stdout.strip():
                return None
            raise ProbeFailure("无法确认本次临时结构探针是否已清理")
        raise ProbeFailure("无法读取目标 Core 容器；未运行结构检查")
    try:
        documents = json.loads(result.stdout)
        if not isinstance(documents, list) or len(documents) != 1:
            raise ValueError()
        document = documents[0]
        if not isinstance(document, dict):
            raise ValueError()
        return document
    except (ValueError, TypeError) as error:
        raise ProbeFailure("Docker 容器身份输出无效") from error


def target_snapshot(container_id):
    document = inspect(container_id)
    state = document.get("State", {})
    image = document.get("Image", "")
    restart_count = document.get("RestartCount")
    started_at = state.get("StartedAt")
    paused = state.get("Paused", False)
    restarting = state.get("Restarting", False)
    if (
        document.get("Id") != container_id
        or state.get("Running") is not True
        or paused is not False
        or restarting is not False
        or not isinstance(image, str)
        or re.fullmatch(r"sha256:[0-9a-f]{64}", image) is None
        or type(restart_count) is not int
        or restart_count < 0
        or not isinstance(started_at, str)
        or not started_at
    ):
        raise ProbeFailure("目标 Core 必须是身份完整且正在运行的容器")
    entries = document.get("Config", {}).get("Env", [])
    if not isinstance(entries, list) or not all(isinstance(entry, str) for entry in entries):
        raise ProbeFailure("目标 Core 环境配置格式无效")
    names = (
        "DATABASE_URL",
        "VIDEO_PREVIEW_ENABLED",
        "PHONE_AUTH_ENABLED",
        "PHONE_AUTH_SEND_ENABLED",
    )
    environment = {}
    for entry in entries:
        name, separator, value = entry.partition("=")
        if name not in names:
            continue
        if not separator or name in environment or any(character in value for character in "\r\n\0"):
            raise ProbeFailure("目标 Core 的结构检查配置无效")
        environment[name] = value
    if not environment.get("DATABASE_URL"):
        raise ProbeFailure("目标 Core 缺少数据库配置")
    for name in names[1:]:
        environment.setdefault(name, "false")
    return (container_id, image, started_at, restart_count, environment, paused, restarting)


def cleanup_probe(name, token, cid_file, target_id):
    # cidfile 仅存在本次 0700 临时目录；兜底名称也由本次随机令牌唯一生成。
    probe_id = cid_file.read_text(encoding="utf-8").strip() if cid_file.exists() else name
    document = inspect(probe_id, allow_missing=True)
    if document is None:
        return
    identifier = document.get("Id", "")
    if (
        not isinstance(identifier, str)
        or re.fullmatch(r"[0-9a-f]{64}", identifier) is None
        or identifier == target_id
        or document.get("Name") != "/" + name
        or document.get("Config", {}).get("Labels", {}).get("cn.inkforge.schema-probe") != token
    ):
        raise ProbeFailure("探针清理身份不匹配；未删除任何容器")
    result = docker(["rm", "--force", identifier])
    if result.returncode != 0:
        raise ProbeFailure("本次临时结构探针无法清理")


def execute(container_id, guard_arguments, timeout):
    before = target_snapshot(container_id)
    token = uuid.uuid4().hex
    name = "inkforge-schema-probe-" + token
    output = ""
    with tempfile.TemporaryDirectory(prefix="inkforge-schema-probe-") as directory:
        directory_path = Path(directory)
        os.chmod(directory_path, 0o700)
        env_file = directory_path / "probe.env"
        cid_file = directory_path / "probe.cid"
        descriptor = os.open(env_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            for key, value in before[4].items():
                stream.write(key + "=" + value + "\n")
        options = (
            "-Xms16m -Xmx64m -XX:MaxMetaspaceSize=48m "
            "-XX:ReservedCodeCacheSize=16m -XX:MaxDirectMemorySize=8m "
            "-Xss512k -XX:+UseSerialGC -XX:+ExitOnOutOfMemoryError -Djava.io.tmpdir=/tmp"
        )
        arguments = [
            "run", "--rm", "--name", name, "--cidfile", str(cid_file),
            "--label", "cn.inkforge.schema-probe=" + token,
            "--network", "container:" + container_id,
            "--memory", "192m", "--memory-swap", "192m", "--cpus", "0.25", "--pids-limit", "64",
            "--user", "10001:10001", "--read-only", "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges:true", "--tmpfs", "/tmp:size=16m,mode=1777",
            "--env-file", str(env_file),
            # 固定 JVM 参数也适用于旧镜像中的原 wrapper，不需要先更新业务镜像。
            "--env", "JAVA_TOOL_OPTIONS=" + options,
            "--env", "JDK_JAVA_OPTIONS=", "--env", "_JAVA_OPTIONS=",
            "--entrypoint", "/usr/local/bin/inkforge-schema-guard",
            before[1], *guard_arguments,
        ]
        failure = None
        try:
            try:
                result = docker(arguments, timeout)
            except ProbeFailure as error:
                failure = error
                result = None
            if target_snapshot(container_id) != before:
                raise ProbeFailure("结构检查期间目标 Core 已变化或重启，结果无效")
            if failure is not None:
                raise failure
            if result.returncode != 0:
                status = result.returncode if result.returncode > 0 else 128 - result.returncode
                raise ProbeFailure("隔离结构探针失败（退出码 " + str(status) + "）", status)
            try:
                output = result.stdout.decode("utf-8")
            except UnicodeError as error:
                raise ProbeFailure("结构探针未返回有效指纹") from error
            if re.fullmatch(r"[0-9a-f]{64}\r?\n?", output) is None:
                raise ProbeFailure("结构探针未返回唯一的完整指纹")
        finally:
            had_failure = sys.exc_info()[0] is not None
            try:
                cleanup_probe(name, token, cid_file, container_id)
            except ProbeFailure:
                # 若原检查已失败，保留它的退出码，同时明确告知清理问题。
                if had_failure:
                    print("本次结构探针清理未能确认完成", file=sys.stderr)
                else:
                    raise
    return output.rstrip("\r\n")


def interrupted(signum, _frame):
    raise ProbeFailure("结构探针已中断", 128 + signum)


def main():
    arguments = sys.argv[1:]
    if (
        len(arguments) not in {1, 2}
        or re.fullmatch(r"[0-9a-f]{64}", arguments[0]) is None
        or (len(arguments) == 2 and arguments[1] != "--compatibility-fingerprint-v1")
    ):
        raise ProbeFailure("用法：verify-running-core-schema.sh 完整容器ID [--compatibility-fingerprint-v1]", 2)
    timeout_value = os.environ.get("INKFORGE_SCHEMA_PROBE_TIMEOUT_SECONDS", "60")
    if re.fullmatch(r"[1-9][0-9]*", timeout_value) is None or not 1 <= int(timeout_value) <= 120:
        raise ProbeFailure("结构探针超时必须为 1 至 120 秒", 2)
    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGINT, interrupted)
    print(execute(arguments[0], arguments[1:], int(timeout_value)))


try:
    main()
except ProbeFailure as error:
    print(str(error), file=sys.stderr)
    sys.exit(error.status)
except Exception:
    # inspect 原文、命令 stderr 和异常 repr 都可能包含凭据，禁止作为诊断输出。
    print("隔离结构探针无法完成", file=sys.stderr)
    sys.exit(2)
PY
