"""启动隔离 Compose 并验证 Durable Agent V2 最小跨进程闭环。"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).parents[2]
COMPOSE_FILE = ROOT / "infra" / "compose.durable-agent-v2-e2e.yaml"
SSE_TIMEOUT = httpx.Timeout(45.0, connect=10.0, write=10.0, pool=10.0)
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def _safe_error(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return f"HTTP_{response.status_code}"
    if not isinstance(body, dict):
        return f"HTTP_{response.status_code}"
    code = body.get("code")
    if isinstance(code, str):
        return code
    detail = body.get("detail")
    if isinstance(detail, dict) and isinstance(detail.get("code"), str):
        return str(detail["code"])
    return f"HTTP_{response.status_code}"


def _canonical_sha256(value: object) -> str | None:
    if not isinstance(value, dict):
        return None
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _runtime_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str) or not value or value == "none":
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


def _runtime_has_fresh_successful_health(value: dict[str, object]) -> bool:
    started_at = _runtime_timestamp(value.get("startedAt"))
    checked_at = _runtime_timestamp(value.get("healthCheckedAt"))
    return (
        value.get("status") == "running"
        and value.get("health") == "healthy"
        and value.get("healthCheckExitCode") == 0
        and started_at is not None
        and checked_at is not None
        and checked_at >= started_at
    )


def _safe_usage_summary(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        return {}
    fields = (
        "usageStatus",
        "providerAttempts",
        "protocolCorrections",
        "wallTimeMillis",
        "inputTokens",
        "cachedTokens",
        "promptCacheMissTokens",
        "completionTokens",
        "reasoningTokens",
        "visibleOutputTokens",
        "costMicros",
    )
    return {
        field: field_value
        for field in fields
        if isinstance((field_value := value.get(field)), (str, int))
        and not isinstance(field_value, bool)
    }


def _safe_billing_evidence(
    raw: object,
    *,
    step_usage: object,
    expected_run_id: str,
    expected_step_id: str | None,
    expected_user_id: str,
    initial_balance_micros: int | None,
) -> dict[str, object]:
    billing = raw if isinstance(raw, dict) else {}
    reservation_value = billing.get("reservation")
    reservation = reservation_value if isinstance(reservation_value, dict) else {}
    token_value = billing.get("tokenUsage")
    token_usage = token_value if isinstance(token_value, dict) else {}
    reservation_usage = reservation.get("usage")
    safe_usage = _safe_usage_summary(reservation_usage)

    token_fields_match = bool(safe_usage) and all(
        token_usage.get(token_field) == safe_usage.get(usage_field)
        for usage_field, token_field in (
            ("inputTokens", "promptTokens"),
            ("cachedTokens", "cachedTokens"),
            ("promptCacheMissTokens", "promptCacheMissTokens"),
            ("completionTokens", "completionTokens"),
            ("reasoningTokens", "reasoningTokens"),
        )
    )
    input_tokens = safe_usage.get("inputTokens")
    completion_tokens = safe_usage.get("completionTokens")
    if (
        not isinstance(input_tokens, int)
        or isinstance(input_tokens, bool)
        or not isinstance(completion_tokens, int)
        or isinstance(completion_tokens, bool)
        or token_usage.get("totalTokens") != input_tokens + completion_tokens
    ):
        token_fields_match = False

    final_balance = billing.get("userBalanceMicros")
    balance_delta = (
        final_balance - initial_balance_micros
        if isinstance(final_balance, int)
        and not isinstance(final_balance, bool)
        and isinstance(initial_balance_micros, int)
        and not isinstance(initial_balance_micros, bool)
        else None
    )
    reservation_usage_sha256 = _canonical_sha256(reservation_usage)
    step_usage_sha256 = _canonical_sha256(step_usage)
    reservation_request_id = reservation.get("requestId")
    return {
        "reservationCount": billing.get("reservationCount"),
        "reservation": {
            "status": reservation.get("status"),
            "reservedMicros": reservation.get("reservedMicros"),
            "chargedMicros": reservation.get("chargedMicros"),
            "settledAtPresent": reservation.get("settledAtPresent") is True,
            "runBindingMatches": bool(expected_run_id)
            and reservation.get("runId") == expected_run_id,
            "stepBindingMatches": isinstance(expected_step_id, str)
            and bool(expected_step_id)
            and reservation.get("stepId") == expected_step_id,
            "userBindingMatches": bool(expected_user_id)
            and reservation.get("userId") == expected_user_id,
            "usageSha256": reservation_usage_sha256,
            "usageMatchesStep": reservation_usage_sha256 is not None
            and reservation_usage_sha256 == step_usage_sha256,
            "usage": safe_usage,
        },
        "tokenUsageCount": billing.get("tokenUsageCount"),
        "tokenUsage": {
            "requestBindingMatches": isinstance(reservation_request_id, str)
            and bool(reservation_request_id)
            and token_usage.get("requestId") == reservation_request_id,
            "runBindingMatches": bool(expected_run_id)
            and token_usage.get("runId") == expected_run_id,
            "stepBindingMatches": isinstance(expected_step_id, str)
            and bool(expected_step_id)
            and token_usage.get("taskId") == expected_step_id,
            "userBindingMatches": bool(expected_user_id)
            and token_usage.get("userId") == expected_user_id,
            "modelIsFake": token_usage.get("model") == "fake",
            "tokenFieldsMatchUsage": token_fields_match,
        },
        "creditLedgerCount": billing.get("creditLedgerCount"),
        "balanceDeltaMicros": balance_delta,
        "balanceUnchanged": balance_delta == 0,
        "stepUsageSha256": step_usage_sha256,
    }


def _assert_fake_billing_evidence(value: object) -> None:
    billing = value if isinstance(value, dict) else {}
    reservation_value = billing.get("reservation")
    reservation = reservation_value if isinstance(reservation_value, dict) else {}
    token_value = billing.get("tokenUsage")
    token_usage = token_value if isinstance(token_value, dict) else {}
    required = {
        "reservationCount": billing.get("reservationCount") == 1,
        "reservation.status": reservation.get("status") == "settled",
        "reservation.reservedMicros": reservation.get("reservedMicros") == 0,
        "reservation.chargedMicros": reservation.get("chargedMicros") == 0,
        "reservation.settledAtPresent": reservation.get("settledAtPresent") is True,
        "reservation.runBindingMatches": reservation.get("runBindingMatches") is True,
        "reservation.stepBindingMatches": reservation.get("stepBindingMatches") is True,
        "reservation.userBindingMatches": reservation.get("userBindingMatches") is True,
        "reservation.usageMatchesStep": reservation.get("usageMatchesStep") is True,
        "tokenUsageCount": billing.get("tokenUsageCount") == 1,
        "tokenUsage.requestBindingMatches": token_usage.get("requestBindingMatches")
        is True,
        "tokenUsage.runBindingMatches": token_usage.get("runBindingMatches") is True,
        "tokenUsage.stepBindingMatches": token_usage.get("stepBindingMatches") is True,
        "tokenUsage.userBindingMatches": token_usage.get("userBindingMatches") is True,
        "tokenUsage.modelIsFake": token_usage.get("modelIsFake") is True,
        "tokenUsage.tokenFieldsMatchUsage": token_usage.get("tokenFieldsMatchUsage")
        is True,
        "creditLedgerCount": billing.get("creditLedgerCount") == 0,
        "balanceUnchanged": billing.get("balanceUnchanged") is True,
    }
    failed = [field for field, matched in required.items() if not matched]
    if failed:
        raise AssertionError("Fake 问答计费证据不符合：" + ",".join(failed))


def _assert_agent_restart_receipts(receipts: list[str]) -> None:
    """旧连接可随进程退出消失；live replayer 只需取得一个合法终态回执。"""

    if sorted(receipts) not in (["accepted"], ["accepted", "duplicate"]):
        raise AssertionError(f"Agent 重启 callback receipt 无效：{receipts}")


@dataclass(frozen=True, slots=True)
class Scenario:
    name: str
    run_id: str
    session_id: str
    client_request_id: str
    provider_identity: dict[str, Any]
    database_facts: dict[str, Any]


class ComposeStack:
    def __init__(self, evidence_dir: Path) -> None:
        self.project = f"inkforge-dav2-{secrets.token_hex(5)}"
        self.docker = shutil.which("docker")
        if self.docker is None:
            raise RuntimeError("本机缺少 Docker")
        self.temp_dir = Path(tempfile.mkdtemp(prefix="inkforge-dav2-e2e-"))
        os.chmod(self.temp_dir, 0o700)
        self.keys_dir = self.temp_dir / "keys"
        self.release_guard_dir = self.temp_dir / "release-guard"
        self.core_port = _port()
        self.control_port = _port()
        self.control_token = secrets.token_urlsafe(36)
        self.environment = {
            **os.environ,
            "E2E_POSTGRES_PASSWORD": secrets.token_urlsafe(32),
            "E2E_EXECUTION_CONTROL_TOKEN": self.control_token,
            "E2E_JWT_SECRET": secrets.token_urlsafe(48),
            "E2E_CONTROL_PORT": str(self.control_port),
            "E2E_CORE_PORT": str(self.core_port),
            "E2E_KEYS_DIR": str(self.keys_dir),
            "E2E_RELEASE_GUARD_DIR": str(self.release_guard_dir),
            "E2E_IMAGE_TAG": "durable-v2-e2e",
        }
        self.evidence_dir = evidence_dir
        self._started = False
        self.last_service_restart: dict[str, object] = {}

    def _write_release_guard(
        self,
        *,
        state: str,
        user_id: str | None = None,
        novel_id: str | None = None,
    ) -> None:
        from scripts.durable_agent_v2_release_manifest import (
            execution_manifest_fingerprint,
        )

        self.release_guard_dir.mkdir(mode=0o755, exist_ok=True)
        os.chmod(self.release_guard_dir, 0o755)  # noqa: S103 - 容器只读挂载需可遍历
        fields: dict[str, object] = {
            "canaryScopeSha256": None,
            "committedReceiptSha256": None,
            "controlBundleSha256": None,
            "executionManifestFingerprint": None,
            "expiresAt": None,
            "format": "inkforge-durable-agent-v2-release-guard/1",
            "issuedAt": None,
            "leaseId": None,
            "lockId": None,
            "manifestSha256": None,
            "runAttempt": None,
            "runId": None,
            "state": state,
        }
        if state == "committed":
            if user_id is None or novel_id is None:
                raise ValueError("committed E2E guard 缺少精确 scope")
            scope = hashlib.sha256(
                json.dumps(
                    {"novelId": novel_id, "userId": user_id},
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            ).hexdigest()
            fields.update(
                {
                    "canaryScopeSha256": scope,
                    "committedReceiptSha256": hashlib.sha256(
                        b"isolated-e2e-receipt"
                    ).hexdigest(),
                    "controlBundleSha256": hashlib.sha256(
                        b"isolated-e2e-control"
                    ).hexdigest(),
                    "executionManifestFingerprint": execution_manifest_fingerprint(
                        ROOT / "contracts" / "agent-execution" / "manifest.json"
                    ),
                    "issuedAt": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
                    "leaseId": hashlib.sha256(b"isolated-e2e-lease").hexdigest(),
                    "lockId": hashlib.sha256(b"isolated-e2e-lock").hexdigest(),
                    "manifestSha256": hashlib.sha256(
                        b"isolated-e2e-release-manifest"
                    ).hexdigest(),
                    "runAttempt": "1",
                    "runId": "1",
                }
            )
        payload = (
            json.dumps(
                fields,
                ensure_ascii=False,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        ).encode("utf-8")
        path = self.release_guard_dir / "guard.json"
        temporary = self.release_guard_dir / ".guard.json.partial"
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o444)
        with os.fdopen(descriptor, "wb") as output:
            output.write(payload)
            output.flush()
            os.fsync(output.fileno())
        os.chmod(temporary, 0o444)
        os.replace(temporary, path)
        descriptor = os.open(self.release_guard_dir, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    def activate_durable_scope(self, *, user_id: str, novel_id: str) -> None:
        self._write_release_guard(state="committed", user_id=user_id, novel_id=novel_id)
        self.environment.update(
            {
                "E2E_DURABLE_ROUTE_MODE": "allowlist",
                "E2E_DURABLE_USER_ID": user_id,
                "E2E_DURABLE_NOVEL_ID": novel_id,
            }
        )
        self.run(
            ["up", "--detach", "--wait", "--no-deps", "--force-recreate", "core-api"],
            timeout=180,
        )

    def prepare_keys(self) -> None:
        if self.keys_dir.exists():
            return
        from scripts.generate_service_keys import generate_service_keys

        generate_service_keys(self.keys_dir)

    @property
    def command(self) -> list[str]:
        return [
            self.docker,
            "compose",
            "-p",
            self.project,
            "-f",
            str(COMPOSE_FILE),
        ]

    def run(
        self,
        arguments: list[str],
        *,
        timeout: float = 600,
        check: bool = True,
        input_text: str | None = None,
    ) -> subprocess.CompletedProcess[str]:
        completed = subprocess.run(  # noqa: S603 - 固定 Docker Compose argv
            [*self.command, *arguments],
            cwd=ROOT,
            env=self.environment,
            text=True,
            capture_output=True,
            input=input_text,
            timeout=timeout,
            check=False,
        )
        if check and completed.returncode != 0:
            stderr = completed.stderr.encode("utf-8", errors="replace")
            raise RuntimeError(
                f"Compose 动作失败：{arguments[0]}，退出码 {completed.returncode}"
                + (
                    f"，stderrBytes={len(stderr)}，"
                    f"stderrSha256={hashlib.sha256(stderr).hexdigest()}"
                    if stderr
                    else ""
                )
            )
        return completed

    def start(self, *, build: bool) -> None:
        self.prepare_keys()
        self._write_release_guard(state="off")
        arguments = ["up"]
        if build:
            arguments.append("--build")
        self.run([*arguments, "--detach", "--wait"], timeout=1_800)
        self._started = True
        # 具名迁移在 initdb 已执行；这里再跑一次，真实证明隔离库幂等。
        self.run(
            [
                "exec",
                "-T",
                "postgres",
                "psql",
                "-v",
                "ON_ERROR_STOP=1",
                "-U",
                "inkforge_e2e",
                "-d",
                "novelwriterdev",
                "-f",
                "/docker-entrypoint-initdb.d/002-durable-agent-v2.sql",
            ],
            timeout=180,
        )

    def build_agent(self) -> None:
        self.prepare_keys()
        self.run(["build", "agent-service"], timeout=1_800)

    def image_facts(self) -> dict[str, object]:
        agent_image = f"inkforge-agent-service:{self.environment['E2E_IMAGE_TAG']}"
        core_image = f"inkforge-core-api:{self.environment['E2E_IMAGE_TAG']}"
        image_ids: dict[str, str] = {}
        for name, image in (("agent", agent_image), ("core", core_image)):
            completed = subprocess.run(  # noqa: S603 - 固定只读 Docker inspect
                [self.docker, "image", "inspect", image, "--format", "{{.Id}}"],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            if completed.returncode != 0:
                raise RuntimeError(f"缺少本地 {name} E2E 镜像")
            image_ids[name] = completed.stdout.strip()

        relative_paths = (
            "execution/journal.py",
            "queue/repository.py",
        )
        host_root = ROOT / "apps" / "agent-service" / "src" / "inkforge_agents"
        host_hashes = {
            path: hashlib.sha256((host_root / path).read_bytes()).hexdigest()
            for path in relative_paths
        }
        program = (
            "import hashlib,json,pathlib,inkforge_agents;"
            "r=pathlib.Path(inkforge_agents.__file__).parent;"
            f"p={relative_paths!r};"
            "print(json.dumps({n:hashlib.sha256((r/n).read_bytes()).hexdigest() for n in p}))"
        )
        completed = subprocess.run(  # noqa: S603 - 固定无网络镜像源码哈希
            [
                self.docker,
                "run",
                "--rm",
                "--network",
                "none",
                "--read-only",
                "--entrypoint",
                "python",
                agent_image,
                "-c",
                program,
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
            timeout=30,
        )
        if completed.returncode != 0:
            raise RuntimeError("无法读取本地 Agent E2E 镜像源码哈希")
        image_hashes = json.loads(completed.stdout)
        if image_hashes != host_hashes:
            mismatched = sorted(
                path for path in relative_paths if image_hashes.get(path) != host_hashes[path]
            )
            raise RuntimeError(f"Agent E2E 镜像源码哈希不一致：{mismatched}")
        return {
            "agentImageId": image_ids["agent"],
            "coreImageId": image_ids["core"],
            "agentSourceSha256": host_hashes,
            "agentImageSourceSha256": image_hashes,
            "agentSourceMatchesImage": True,
        }

    def psql(self, sql: str, *, variables: dict[str, str] | None = None) -> str:
        variable_arguments = [
            argument
            for key, value in (variables or {}).items()
            for argument in ("--set", f"{key}={value}")
        ]
        completed = self.run(
            [
                "exec",
                "-T",
                "postgres",
                "psql",
                "-X",
                "-q",
                "-A",
                "-t",
                "-U",
                "inkforge_e2e",
                "-d",
                "novelwriterdev",
                *variable_arguments,
                "-f",
                "-",
            ],
            timeout=30,
            input_text=sql,
        )
        return completed.stdout.strip()

    def redis(self, *arguments: str) -> list[str]:
        completed = self.run(
            ["exec", "-T", "execution-redis", "redis-cli", "--raw", *arguments],
            timeout=30,
        )
        return completed.stdout.splitlines()

    def restart(self, service: str) -> None:
        self.run(["restart", service], timeout=120)

    def service_runtime(self, service: str) -> dict[str, object]:
        container_id = self.run(["ps", "-q", service], timeout=30).stdout.strip()
        if not container_id or "\n" in container_id:
            raise RuntimeError(f"无法唯一定位 {service} 容器")
        completed = subprocess.run(  # noqa: S603 - 固定只读容器运行事实
            [
                self.docker,
                "inspect",
                container_id,
                "--format",
                (
                    "{{.Id}}|{{.RestartCount}}|{{.State.StartedAt}}|"
                    "{{.State.Status}}|"
                    "{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}|"
                    "{{if .State.Health}}{{range .State.Health.Log}}"
                    "{{.End}}@{{.ExitCode}},{{end}}{{else}}none{{end}}"
                ),
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
            timeout=30,
        )
        if completed.returncode != 0:
            raise RuntimeError(f"无法读取 {service} 容器运行事实")
        identity, restart_count, started_at, status, health, health_checks = (
            completed.stdout.strip().split("|", 5)
        )
        latest_health_check = health_checks.rstrip(",").rsplit(",", 1)[-1]
        health_checked_at: str | None = None
        health_check_exit_code: int | None = None
        if latest_health_check not in {"", "none"}:
            health_checked_at, separator, raw_exit_code = latest_health_check.rpartition(
                "@"
            )
            if not separator or not health_checked_at:
                raise RuntimeError(f"无法读取 {service} 最近 healthcheck 事实")
            try:
                health_check_exit_code = int(raw_exit_code)
            except ValueError:
                raise RuntimeError(
                    f"无法读取 {service} 最近 healthcheck 退出码"
                ) from None
        return {
            "containerId": identity,
            "restartCount": int(restart_count),
            "startedAt": started_at,
            "status": status,
            "health": health,
            "healthCheckedAt": health_checked_at,
            "healthCheckExitCode": health_check_exit_code,
        }

    def restart_and_wait(self, service: str) -> dict[str, object]:
        before = self.service_runtime(service)
        self.last_service_restart = {
            "service": service,
            "before": before,
            "after": None,
        }
        self.restart(service)
        deadline = time.monotonic() + 180
        after = self.service_runtime(service)
        while (
            after["containerId"] == before["containerId"]
            and (
                after["startedAt"] == before["startedAt"]
                or not _runtime_has_fresh_successful_health(after)
            )
            and time.monotonic() < deadline
        ):
            time.sleep(0.2)
            after = self.service_runtime(service)
        runtime = {"service": service, "before": before, "after": after}
        self.last_service_restart = runtime
        before_restart_count = before.get("restartCount")
        after_restart_count = after.get("restartCount")
        if (
            after["containerId"] != before["containerId"]
            or not isinstance(before_restart_count, int)
            or not isinstance(after_restart_count, int)
            or after_restart_count < before_restart_count
            or after["startedAt"] == before["startedAt"]
            or not _runtime_has_fresh_successful_health(after)
        ):
            raise AssertionError(f"{service} 重启运行事实无效")
        return runtime

    def wait_redis(self) -> None:
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            try:
                if self.redis("PING") == ["PONG"]:
                    return
            except RuntimeError:
                pass
            time.sleep(0.2)
        raise RuntimeError("execution Redis 重启后没有恢复")

    def wait_service_healthy(
        self,
        service: str,
        *,
        expected_container_id: object,
        expected_started_at: object,
        minimum_health_checked_at: object | None = None,
        timeout: float = 180,
    ) -> dict[str, object]:
        minimum_health_time = _runtime_timestamp(minimum_health_checked_at)
        if minimum_health_checked_at is not None and minimum_health_time is None:
            raise AssertionError(f"{service} 依赖恢复门禁时间无效")
        deadline = time.monotonic() + timeout
        last: dict[str, object] = {}
        while time.monotonic() < deadline:
            last = self.service_runtime(service)
            if (
                last.get("containerId") != expected_container_id
                or last.get("startedAt") != expected_started_at
            ):
                raise AssertionError(f"{service} 在依赖恢复期间被意外重建或重启")
            current_health_time = _runtime_timestamp(last.get("healthCheckedAt"))
            health_is_fresh = (
                minimum_health_time is None
                or (
                    current_health_time is not None
                    and current_health_time >= minimum_health_time
                )
            )
            if (
                last.get("status") == "running"
                and last.get("health") == "healthy"
                and last.get("healthCheckExitCode") == 0
                and health_is_fresh
            ):
                return last
            time.sleep(0.2)
        raise AssertionError(
            f"{service} 未在依赖恢复门限内重新 healthy："
            f"status={last.get('status')},health={last.get('health')},"
            f"healthCheckExitCode={last.get('healthCheckExitCode')},"
            f"healthFresh={health_is_fresh if last else False}"
        )

    def _project_resources(
        self,
        kind: str,
        *,
        identifier_format: str,
    ) -> tuple[int, list[str]]:
        list_arguments = [self.docker, kind, "ls"]
        if kind == "container":
            list_arguments.append("--all")
        result = subprocess.run(  # noqa: S603 - 固定只读 Docker label 查询
            [
                *list_arguments,
                "--filter",
                f"label=com.docker.compose.project={self.project}",
                "--format",
                identifier_format,
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
            timeout=30,
        )
        return (
            result.returncode,
            [line for line in result.stdout.splitlines() if line],
        )

    def container_ids(self) -> list[str]:
        _exit_code, identifiers = self._project_resources(
            "container",
            identifier_format="{{.ID}}",
        )
        return identifiers

    def cleanup(self) -> dict[str, object]:
        try:
            down = self.run(
                ["down", "--volumes", "--remove-orphans", "--timeout", "10"],
                timeout=180,
                check=False,
            )
            down_code = down.returncode
        except (OSError, subprocess.SubprocessError):
            down_code = -1
        try:
            container_query, residual_containers = self._project_resources(
                "container",
                identifier_format="{{.ID}}",
            )
            network_query, residual_networks = self._project_resources(
                "network",
                identifier_format="{{.ID}}",
            )
            volume_query, residual_volumes = self._project_resources(
                "volume",
                identifier_format="{{.Name}}",
            )
        except (OSError, subprocess.SubprocessError):
            container_query = network_query = volume_query = -1
            residual_containers = []
            residual_networks = []
            residual_volumes = []
        shutil.rmtree(self.temp_dir, ignore_errors=True)
        return {
            "composeDownExitCode": down_code,
            "resourceQueryExitCodes": {
                "containers": container_query,
                "networks": network_query,
                "volumes": volume_query,
            },
            "residualContainerCount": len(residual_containers),
            "residualNetworkCount": len(residual_networks),
            "residualVolumeCount": len(residual_volumes),
            "temporaryKeyDirectoryRemoved": not self.temp_dir.exists(),
        }


class ResourceSampler:
    def __init__(self, stack: ComposeStack) -> None:
        self._stack = stack
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._started = False
        self.samples = 0
        self.max_memory_bytes: dict[str, int] = {}

    def start(self) -> None:
        self._started = True
        self._thread.start()

    def stop(self) -> None:
        if not self._started:
            return
        self._stop.set()
        self._thread.join(timeout=5)

    def _run(self) -> None:
        while not self._stop.wait(1.0):
            ids = self._stack.container_ids()
            if not ids:
                continue
            completed = subprocess.run(  # noqa: S603 - 固定只读 Docker stats
                [
                    self._stack.docker,
                    "stats",
                    "--no-stream",
                    "--format",
                    "{{json .}}",
                    *ids,
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            if completed.returncode != 0:
                continue
            self.samples += 1
            for line in completed.stdout.splitlines():
                try:
                    value = json.loads(line)
                    name = str(value["Name"])
                    memory = _parse_bytes(str(value["MemUsage"]).split("/", 1)[0].strip())
                except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                    continue
                self.max_memory_bytes[name] = max(
                    memory, self.max_memory_bytes.get(name, 0)
                )


def _parse_bytes(value: str) -> int:
    units = {
        "B": 1,
        "KiB": 1024,
        "MiB": 1024**2,
        "GiB": 1024**3,
        "kB": 1000,
        "MB": 1000**2,
        "GB": 1000**3,
    }
    for unit in sorted(units, key=len, reverse=True):
        if value.endswith(unit):
            return round(float(value.removesuffix(unit).strip()) * units[unit])
    raise ValueError("未知 docker stats 内存单位")


class Acceptance:
    def __init__(self, stack: ComposeStack) -> None:
        self.stack = stack
        self.core = httpx.Client(
            base_url=f"http://127.0.0.1:{stack.core_port}",
            timeout=10,
            trust_env=False,
        )
        self.control = httpx.Client(
            base_url=f"http://127.0.0.1:{stack.control_port}",
            headers={"X-InkForge-E2E-Token": stack.control_token},
            timeout=10,
            trust_env=False,
        )
        self.user_id = ""
        self.novel_id = ""
        self.chapter_id = ""
        self.initial_credit_balance_micros: int | None = None
        self.safe_diagnostics: dict[str, object] = {}

    def close(self) -> None:
        self.core.close()
        self.control.close()

    def request(
        self,
        method: str,
        path: str,
        *,
        expected: int,
        json_body: dict[str, object] | None = None,
    ) -> httpx.Response:
        response = self.core.request(method, path, json=json_body)
        if response.status_code != expected:
            raise AssertionError(
                f"公共 API {method} {path} 返回 {response.status_code}/"
                f"{_safe_error(response)}，预期 {expected}"
            )
        return response

    def control_request(
        self,
        method: str,
        path: str,
        body: dict[str, object] | None = None,
    ) -> dict[str, object]:
        response = self.control.request(method, path, json=body)
        if response.status_code != 200:
            raise AssertionError(f"E2E 控制器返回 {response.status_code}")
        value = response.json()
        if not isinstance(value, dict):
            raise AssertionError("E2E 控制器响应不是对象")
        return value

    def bootstrap(self) -> None:
        password = "E2e!" + secrets.token_urlsafe(20)
        username = "e2e_" + secrets.token_hex(6)
        registered = self.request(
            "POST",
            "/api/v1/auth/register",
            expected=201,
            json_body={
                "username": username,
                "password": password,
                "confirmPassword": password,
            },
        ).json()
        self.user_id = str(registered["id"])
        me = self.request("GET", "/api/v1/auth/me", expected=200).json()
        if me["id"] != self.user_id:
            raise AssertionError("JWT Cookie 没有恢复同一测试用户")
        balance = self.stack.psql(
            """
            SELECT "creditBalanceMicros" FROM public."User"
            WHERE id = :'e2e_user_id';
            """,
            variables={"e2e_user_id": self.user_id},
        )
        try:
            self.initial_credit_balance_micros = int(balance)
        except ValueError:
            raise AssertionError("测试用户初始余额证据无效") from None

        created = self.request(
            "POST",
            "/api/v1/novels",
            expected=201,
            json_body={"name": "Durable V2 E2E", "storyLengthProfile": "long_serial"},
        ).json()
        self.novel_id = str(created["novelId"])
        self.chapter_id = str(created["chapterId"])
        chapter = self.request(
            "GET", f"/api/v1/chapters/{self.chapter_id}", expected=200
        ).json()
        content = "第一段：风穿过旧城。\n第二段：人物确认了不可变的章节事实。"
        self.request(
            "PATCH",
            f"/api/v1/chapters/{self.chapter_id}",
            expected=200,
            json_body={
                "title": "隔离验收章节",
                "content": content,
                "expectedUpdatedAt": chapter["updatedAt"],
            },
        )

    def create_session(self, label: str) -> str:
        response = self.request(
            "POST",
            "/api/v1/writing/sessions",
            expected=201,
            json_body={
                "novelId": self.novel_id,
                "chapterId": self.chapter_id,
                "title": label,
            },
        ).json()
        return str(response["id"])

    def run_body(
        self,
        *,
        session_id: str,
        client_request_id: str,
        instruction: str,
    ) -> dict[str, object]:
        return {
            "clientRequestId": client_request_id,
            "workflow": "long_serial",
            "novelId": self.novel_id,
            "chapterId": self.chapter_id,
            "writingSessionId": session_id,
            "operation": "answer_question",
            "target": {"type": "chapter", "id": self.chapter_id},
            "scope": {"kind": "chapter", "chapterId": self.chapter_id},
            "targetWordCount": 1000,
            "userInstruction": instruction,
        }

    def start_run(self, body: dict[str, object], *, expected: int = 202) -> httpx.Response:
        return self.request(
            "POST", "/api/v1/writing/runs", expected=expected, json_body=body
        )

    def wait_terminal(self, run_id: str, *, timeout: float = 45) -> dict[str, object]:
        deadline = time.monotonic() + timeout
        last: dict[str, object] = {}
        while time.monotonic() < deadline:
            response = self.request(
                "GET", f"/api/v1/writing/runs/{run_id}", expected=200
            )
            value = response.json()
            if not isinstance(value, dict):
                raise AssertionError("Run 状态响应不是对象")
            last = value
            if value.get("status") in {"completed", "failed", "cancelled"}:
                return value
            time.sleep(0.2)
        raise AssertionError(f"Run 未在门限内进入终态：{last.get('status')}")

    def control_state(self) -> dict[str, object]:
        return self.control_request("GET", "/control/state")

    @staticmethod
    def _sse_frames(response: httpx.Response) -> Iterator[dict[str, object]]:
        frame: dict[str, str] = {}
        data_lines: list[str] = []
        for line in response.iter_lines():
            if line == "":
                if frame or data_lines:
                    raw_data = "\n".join(data_lines)
                    try:
                        data: object = json.loads(raw_data)
                    except json.JSONDecodeError:
                        data = raw_data
                    yield {
                        "id": frame.get("id"),
                        "event": frame.get("event", "message"),
                        "data": data,
                    }
                frame = {}
                data_lines = []
                continue
            if line.startswith(":"):
                continue
            field, separator, value = line.partition(":")
            if separator and value.startswith(" "):
                value = value[1:]
            if field == "data":
                data_lines.append(value)
            elif field in {"id", "event"}:
                frame[field] = value
        if frame or data_lines:
            raw_data = "\n".join(data_lines)
            try:
                data = json.loads(raw_data)
            except json.JSONDecodeError:
                data = raw_data
            yield {
                "id": frame.get("id"),
                "event": frame.get("event", "message"),
                "data": data,
            }

    def wait_provider_gate(self, *, timeout: float = 30) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            state = self.control_state()
            gate = state.get("providerGate")
            if isinstance(gate, dict) and int(gate.get("reached", 0)) >= 1:
                return
            time.sleep(0.1)
        raise AssertionError("Provider gate 没有在门限内到达")

    def wait_execution_gate(self, *, timeout: float = 30) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            state = self.control_state()
            gate = state.get("executionGate")
            if isinstance(gate, dict) and int(gate.get("reached", 0)) >= 1:
                return
            time.sleep(0.1)
        raise AssertionError("Execution submit gate 没有在门限内到达")

    def wait_callback_gate(
        self,
        run_id: str,
        *,
        minimum_reached: int,
        timeout: float = 45,
    ) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            state = self.control_state()
            gate = state.get("callbackGate")
            attempts = state.get("callbackAttempts")
            matching = (
                [
                    item
                    for item in attempts
                    if isinstance(item, dict)
                    and item.get("run_id") == run_id
                    and item.get("callback_kind") in {"result", "failure"}
                    and item.get("action") == "held_before_forward"
                ]
                if isinstance(attempts, list)
                else []
            )
            if (
                isinstance(gate, dict)
                and int(gate.get("reached", 0)) >= minimum_reached
                and len(matching) >= minimum_reached
            ):
                return
            time.sleep(0.1)
        raise AssertionError(
            f"Callback gate 没有收到 {minimum_reached} 次 matching terminal"
        )

    def first_snapshot_and_disconnect(
        self, run_id: str
    ) -> tuple[dict[str, object], dict[str, int]]:
        started = time.monotonic()
        timing: dict[str, int] = {}
        try:
            with self.core.stream(
                "GET",
                f"/api/v1/writing/runs/{run_id}/events",
                headers={"Accept": "text/event-stream"},
                timeout=SSE_TIMEOUT,
            ) as response:
                timing["connectStartToHeadersMillis"] = round(
                    (time.monotonic() - started) * 1_000
                )
                if response.status_code != 200:
                    raise AssertionError(f"首次 SSE 返回 {response.status_code}")
                try:
                    frame = next(self._sse_frames(response))
                except StopIteration:
                    raise AssertionError("首次 SSE 没有 run_snapshot") from None
                timing["connectStartToFirstFrameMillis"] = round(
                    (time.monotonic() - started) * 1_000
                )
        except httpx.TimeoutException:
            self.safe_diagnostics["sseInitial"] = {
                **timing,
                "connectStartToTimeoutMillis": round(
                    (time.monotonic() - started) * 1_000
                ),
            }
            raise
        if frame.get("event") != "run_snapshot":
            raise AssertionError("首次 SSE 首帧不是 run_snapshot")
        cursor = frame.get("id")
        if not isinstance(cursor, str) or not cursor.isdecimal():
            raise AssertionError("首次 SSE snapshot 没有数字 cursor")
        data = frame.get("data")
        if (
            not isinstance(data, dict)
            or data.get("runId") != run_id
            or data.get("engineVersion") != 2
            or data.get("baseSequence") != int(cursor)
        ):
            raise AssertionError("首次 SSE snapshot 资源绑定无效")
        self.safe_diagnostics["sseInitial"] = timing
        return frame, timing

    def reconnect_sse_and_release_provider(
        self, run_id: str, cursor: str
    ) -> tuple[list[dict[str, object]], dict[str, int]]:
        started = time.monotonic()
        timing: dict[str, int] = {}
        try:
            with self.core.stream(
                "GET",
                f"/api/v1/writing/runs/{run_id}/events",
                headers={
                    "Accept": "text/event-stream",
                    "Last-Event-ID": cursor,
                },
                timeout=SSE_TIMEOUT,
            ) as response:
                timing["connectStartToHeadersMillis"] = round(
                    (time.monotonic() - started) * 1_000
                )
                if response.status_code != 200:
                    raise AssertionError(f"重连 SSE 返回 {response.status_code}")
                frames = self._sse_frames(response)
                try:
                    snapshot = next(frames)
                except StopIteration:
                    raise AssertionError("重连 SSE 没有 run_snapshot") from None
                timing["connectStartToFirstFrameMillis"] = round(
                    (time.monotonic() - started) * 1_000
                )
                if snapshot.get("event") != "run_snapshot":
                    raise AssertionError("重连 SSE 首帧不是 run_snapshot")
                self.control_request(
                    "POST", "/control/provider-release", {"abort": False}
                )
                result = [snapshot, *frames]
        except httpx.TimeoutException:
            self.safe_diagnostics["sseReconnect"] = {
                **timing,
                "connectStartToTimeoutMillis": round(
                    (time.monotonic() - started) * 1_000
                ),
            }
            raise
        self.safe_diagnostics["sseReconnect"] = timing
        return result, timing

    def public_session_facts(
        self, session_id: str, run_id: str, result_id: str
    ) -> dict[str, object]:
        detail = self.request(
            "GET", f"/api/v1/writing/sessions/{session_id}", expected=200
        ).json()
        messages = detail.get("messages") if isinstance(detail, dict) else None
        if not isinstance(messages, list) or len(messages) != 2:
            raise AssertionError("公共会话回读没有且仅有一问一答")
        roles = [item.get("role") for item in messages if isinstance(item, dict)]
        if roles != ["user", "agent"]:
            raise AssertionError("公共会话消息顺序或角色无效")
        answer = messages[1]
        if not isinstance(answer, dict) or answer.get("id") != result_id:
            raise AssertionError("SSE completed.resultId 未指向公共回答消息")
        metadata = answer.get("metadata")
        source = metadata.get("source") if isinstance(metadata, dict) else None
        if not isinstance(source, dict) or source.get("runId") != run_id:
            raise AssertionError("公共回答消息没有绑定当前 V2 Run")
        return {
            "messageCount": 2,
            "roles": roles,
            "answerMessageId": result_id,
            "answerRunId": run_id,
        }

    def journal_facts(self, step_id: str) -> dict[str, object]:
        values = self.stack.redis("HGETALL", f"inkforge:executions:{step_id}")
        entry = dict(zip(values[::2], values[1::2], strict=True))
        raw_fence = entry.get("fencing_token")
        try:
            fencing_token = int(raw_fence) if raw_fence is not None else None
        except ValueError:
            fencing_token = None
        return {
            "present": bool(entry),
            "state": entry.get("state"),
            "callbackDelivery": entry.get("callback_delivery"),
            "requestHash": entry.get("request_hash"),
            "resultHash": entry.get("result_hash"),
            "jobId": entry.get("job_id"),
            "fencingToken": fencing_token,
            "terminalPayloadPresent": "terminal_payload" in entry,
        }

    def wait_delivered_journal(
        self,
        step_id: str,
        *,
        timeout: float = 30,
    ) -> dict[str, object]:
        deadline = time.monotonic() + timeout
        last: dict[str, object] = {}
        while time.monotonic() < deadline:
            last = self.journal_facts(step_id)
            self.safe_diagnostics["executionJournal"] = {
                "stepId": step_id,
                **last,
            }
            if (
                last.get("present") is True
                and last.get("state") == "result"
                and last.get("callbackDelivery") == "delivered"
                and last.get("terminalPayloadPresent") is False
            ):
                return last
            time.sleep(0.1)
        raise AssertionError(
            "terminal journal 未在门限内压缩为 delivered tombstone："
            f"state={last.get('state')},delivery={last.get('callbackDelivery')}"
        )

    @staticmethod
    def assert_callback_attempt_bindings(
        *,
        run_id: str,
        step: dict[str, object],
        journal: dict[str, object],
        attempts: list[dict[str, object]],
    ) -> None:
        expected = (
            run_id,
            step.get("id"),
            journal.get("jobId"),
            step.get("fencingToken"),
            step.get("requestHash"),
            step.get("resultHash"),
        )
        for attempt in attempts:
            actual = (
                attempt.get("run_id"),
                attempt.get("step_id"),
                attempt.get("job_id"),
                attempt.get("fencing_token"),
                attempt.get("request_hash"),
                attempt.get("result_hash"),
            )
            if actual != expected:
                raise AssertionError("terminal callback 与 Core/journal 身份绑定不一致")
            if attempt.get("action") in {"forwarded", "dropped_after_forward"} and (
                attempt.get("core_status") != 200
                or attempt.get("receipt_identity_matches") is not True
                or attempt.get("receipt_status") not in {"accepted", "duplicate"}
            ):
                raise AssertionError("terminal callback 的 Core 回执或身份无效")

    def database_facts(self, run_id: str, session_id: str) -> dict[str, object]:
        sql = """
        SELECT json_build_object(
          'run', (SELECT json_build_object(
            'status', status::text,
            'operation', operation,
            'engineVersion', "engineVersion",
            'lastEventSequence', "lastEventSequence",
            'errorCode', "errorCode",
            'cancelRequestId', "cancelRequestId",
            'cancelRequestedAtPresent', "cancelRequestedAt" IS NOT NULL,
            'writingSessionId', "writingSessionId"
          ) FROM public."WorkflowRun" WHERE id = :'e2e_run_id'),
          'steps', (SELECT json_agg(json_build_object(
            'id', id,
            'status', status::text,
            'purpose', purpose,
            'attemptCount', "attemptCount",
            'fencingToken', "fencingToken",
            'requestHash', "requestHash",
            'providerAttempts', ("usageJson"::jsonb->>'providerAttempts')::int,
            'usageRaw', "usageJson"::jsonb,
            'resultHash', "resultHash"
            ,'errorCode', "errorCode"
          ) ORDER BY ordinal) FROM public."WorkflowStep"
            WHERE "runId" = :'e2e_run_id'),
          'messageRoles', (SELECT json_object_agg(role, amount) FROM (
            SELECT role, count(*)::int AS amount
            FROM public."WritingMessage" WHERE "sessionId" = :'e2e_session_id'
            GROUP BY role ORDER BY role
          ) AS role_counts),
          'artifactCount', (SELECT count(*)::int FROM public."ReviewArtifact"
            WHERE "workflowRunId" = :'e2e_run_id'),
          'evaluationCount', (SELECT count(*)::int FROM public."WorkflowEvaluation"
            WHERE "runId" = :'e2e_run_id'),
          'billingRaw', json_build_object(
            'reservationCount', (SELECT count(*)::int
              FROM public."WorkflowBillingReservation"
              WHERE "runId" = :'e2e_run_id'),
            'reservation', (SELECT json_build_object(
              'runId', "runId",
              'stepId', "stepId",
              'userId', "userId",
              'requestId', "requestId",
              'status', status,
              'reservedMicros', "reservedMicros",
              'chargedMicros', "chargedMicros",
              'usage', "usageJson"::jsonb,
              'settledAtPresent', "settledAt" IS NOT NULL
            ) FROM public."WorkflowBillingReservation"
              WHERE "runId" = :'e2e_run_id'
              ORDER BY "createdAt", id LIMIT 1),
            'tokenUsageCount', (SELECT count(*)::int FROM public."TokenUsage"
              WHERE "runId" = :'e2e_run_id'),
            'tokenUsage', (SELECT json_build_object(
              'requestId', "requestId",
              'runId', "runId",
              'taskId', "taskId",
              'userId', "userId",
              'model', model,
              'promptTokens', "promptTokens",
              'cachedTokens', "cachedTokens",
              'promptCacheMissTokens', "promptCacheMissTokens",
              'completionTokens', "completionTokens",
              'reasoningTokens', "reasoningTokens",
              'totalTokens', "totalTokens"
            ) FROM public."TokenUsage"
              WHERE "runId" = :'e2e_run_id'
              ORDER BY "createdAt", id LIMIT 1),
            'creditLedgerCount', (SELECT count(*)::int FROM public."CreditLedger"
              WHERE "requestId" IN (
                SELECT "requestId" FROM public."WorkflowBillingReservation"
                WHERE "runId" = :'e2e_run_id'
              )),
            'userBalanceMicros', (SELECT "creditBalanceMicros" FROM public."User"
              WHERE id = (SELECT "userId" FROM public."WorkflowRun"
                WHERE id = :'e2e_run_id'))
          ),
          'completedEventCount', (SELECT count(*)::int FROM public."WorkflowEvent"
            WHERE "runId" = :'e2e_run_id' AND "eventType" = 'completed'),
          'events', (SELECT json_agg(json_build_object(
            'sequence', sequence,
            'eventType', "eventType"
          ) ORDER BY sequence) FROM public."WorkflowEvent"
            WHERE "runId" = :'e2e_run_id')
        )::text;
        """
        value = json.loads(
            self.stack.psql(
                sql,
                variables={"e2e_run_id": run_id, "e2e_session_id": session_id},
            )
        )
        if not isinstance(value, dict):
            raise AssertionError("数据库证据不是对象")
        steps = value.get("steps")
        step_usage: object = None
        expected_step_id: str | None = None
        if isinstance(steps, list) and len(steps) == 1 and isinstance(steps[0], dict):
            step = steps[0]
            step_usage = step.pop("usageRaw", None)
            raw_step_id = step.get("id")
            expected_step_id = raw_step_id if isinstance(raw_step_id, str) else None
            step["usageSha256"] = _canonical_sha256(step_usage)
            step["usage"] = _safe_usage_summary(step_usage)
        billing = _safe_billing_evidence(
            value.pop("billingRaw", None),
            step_usage=step_usage,
            expected_run_id=run_id,
            expected_step_id=expected_step_id,
            expected_user_id=self.user_id,
            initial_balance_micros=self.initial_credit_balance_micros,
        )
        value["billing"] = billing
        # 必须早于 journal 取证和任何业务断言写入失败报告的脱敏诊断集合。
        self.safe_diagnostics["billing"] = billing
        if expected_step_id is not None:
            journal = self.journal_facts(expected_step_id)
            value["journal"] = journal
            self.safe_diagnostics["executionJournal"] = {
                "stepId": expected_step_id,
                **journal,
            }
        return value

    def assert_scenario_facts(
        self,
        *,
        run_id: str,
        session_id: str,
        provider_before: set[str],
    ) -> tuple[dict[str, object], dict[str, object]]:
        state = self.control_state()
        providers = state["providerCalls"]
        if not isinstance(providers, list):
            raise AssertionError("providerCalls 证据无效")
        new = [
            item
            for item in providers
            if isinstance(item, dict)
            and str(item["idempotency_key"]) not in provider_before
        ]
        if len(new) != 1:
            raise AssertionError(f"场景新增 Provider 身份数量不是 1：{len(new)}")
        provider = new[0]
        if provider["physical_calls"] != 1 or provider["completed_calls"] != 1:
            raise AssertionError("Provider 发生重复调用或没有完整返回")
        facts = self.database_facts(run_id, session_id)
        if facts["run"] != {
            "status": "completed",
            "operation": "answer_question",
            "engineVersion": 2,
            "lastEventSequence": facts["run"]["lastEventSequence"],
            "errorCode": None,
            "cancelRequestId": None,
            "cancelRequestedAtPresent": False,
            "writingSessionId": session_id,
        }:
            raise AssertionError("Run 权威事实不符合 answer_question 完成态")
        steps = facts["steps"]
        if not isinstance(steps, list) or len(steps) != 1:
            raise AssertionError("问答必须只有一个模型 Step")
        step = steps[0]
        if (
            step["status"] != "completed"
            or step["purpose"] != "generation"
            or step["attemptCount"] != 1
            or step["fencingToken"] != 1
            or not isinstance(step["requestHash"], str)
            or step["providerAttempts"] != 1
            or not step["resultHash"]
        ):
            raise AssertionError("问答 Step 终态或供应商计数无效")
        if facts["messageRoles"] != {"agent": 1, "user": 1}:
            raise AssertionError("问答会话没有且仅有一问一答")
        for field in ("artifactCount", "evaluationCount"):
            if facts[field] != 0:
                raise AssertionError(f"Fake 问答产生了意外副作用：{field}")
        _assert_fake_billing_evidence(facts.get("billing"))
        if facts["completedEventCount"] != 1:
            raise AssertionError("Run 必须只有一个 completed Event")
        journal = self.wait_delivered_journal(str(step["id"]))
        facts["journal"] = journal
        if (
            journal.get("requestHash") != step.get("requestHash")
            or journal.get("resultHash") != step.get("resultHash")
            or journal.get("fencingToken") != step.get("fencingToken")
            or not isinstance(journal.get("jobId"), str)
        ):
            raise AssertionError("Core Step 与 delivered journal 身份不一致")
        return facts, provider

    def provider_keys(self) -> set[str]:
        providers = self.provider_facts()
        return {
            str(item["idempotency_key"])
            for item in providers
        }

    def provider_facts(self) -> list[dict[str, object]]:
        providers = self.control_state().get("providerCalls")
        if not isinstance(providers, list) or not all(
            isinstance(item, dict) for item in providers
        ):
            raise AssertionError("Provider 调用证据无效")
        return providers

    def happy_and_idempotency(self) -> Scenario:
        self.control_request("PUT", "/control/provider-mode", {"mode": "hold"})
        session_id = self.create_session("happy-idempotency")
        request_id = "e2e-happy-idempotency-0001"
        body = self.run_body(
            session_id=session_id,
            client_request_id=request_id,
            instruction="请只依据当前章节说明人物此刻确认了什么。",
        )
        before = self.provider_keys()
        started = self.start_run(body).json()
        run_id = str(started["runId"])
        self.wait_provider_gate()
        first_snapshot, first_timing = self.first_snapshot_and_disconnect(run_id)
        cursor = first_snapshot["id"]
        if not isinstance(cursor, str):
            raise AssertionError("首次 SSE cursor 类型无效")
        reconnect_frames, reconnect_timing = self.reconnect_sse_and_release_provider(
            run_id, cursor
        )
        terminal = self.wait_terminal(run_id)
        if terminal["status"] != "completed":
            error = terminal.get("error")
            code = error.get("code") if isinstance(error, dict) else None
            facts = self.database_facts(run_id, session_id)
            steps = facts.get("steps")
            step_error = (
                steps[0].get("errorCode")
                if isinstance(steps, list) and steps and isinstance(steps[0], dict)
                else None
            )
            event_types = [
                event.get("eventType")
                for event in facts.get("events", [])
                if isinstance(event, dict)
            ]
            raise AssertionError(
                "happy path 没有完成："
                f"status={terminal['status']},publicErrorCode={code},"
                f"runErrorCode={facts['run'].get('errorCode')},"
                f"stepErrorCode={step_error},events={event_types}"
            )
        facts, provider = self.assert_scenario_facts(
            run_id=run_id,
            session_id=session_id,
            provider_before=before,
        )
        completed_frames = [
            frame for frame in reconnect_frames if frame.get("event") == "completed"
        ]
        if len(completed_frames) != 1:
            raise AssertionError("SSE 重连没有且仅有一个 completed 事件")
        completed_data = completed_frames[0].get("data")
        payload = (
            completed_data.get("payload") if isinstance(completed_data, dict) else None
        )
        result_id = payload.get("resultId") if isinstance(payload, dict) else None
        if not isinstance(result_id, str):
            raise AssertionError("SSE completed 事件缺少回答 resultId")
        session_facts = self.public_session_facts(session_id, run_id, result_id)
        sse_facts = {
            "firstSnapshotCursor": cursor,
            "reconnectSnapshotCursor": reconnect_frames[0]["id"],
            "reconnectEvents": [frame["event"] for frame in reconnect_frames],
            "completedResultId": result_id,
            "initialTiming": first_timing,
            "reconnectTiming": reconnect_timing,
        }

        replay = self.start_run(body).json()
        if replay["runId"] != run_id:
            raise AssertionError("相同幂等请求没有返回原 Run")
        changed = {**body, "userInstruction": "同一幂等键但不同问题"}
        conflict = self.core.post("/api/v1/writing/runs", json=changed)
        if conflict.status_code != 409 or _safe_error(conflict) != "IDEMPOTENCY_KEY_REUSED":
            raise AssertionError("相同幂等键不同请求没有稳定冲突")
        replay_facts = self.database_facts(run_id, session_id)
        if replay_facts != facts:
            raise AssertionError("幂等重放改变了数据库业务事实")
        current_provider = next(
            item
            for item in self.control_state()["providerCalls"]
            if item["idempotency_key"] == provider["idempotency_key"]
        )
        if current_provider["physical_calls"] != 1:
            raise AssertionError("幂等重放重复调用 Provider")
        if self.public_session_facts(session_id, run_id, result_id) != session_facts:
            raise AssertionError("幂等重放改变了公共会话消息")
        return Scenario(
            name="happy_path_and_idempotency",
            run_id=run_id,
            session_id=session_id,
            client_request_id=request_id,
            provider_identity=provider,
            database_facts={
                **facts,
                "publicSession": session_facts,
                "sse": sse_facts,
            },
        )

    def callback_receipt_loss(self) -> Scenario:
        self.control_request(
            "PUT",
            "/control/callback-mode",
            {"mode": "drop_after_forward_once"},
        )
        session_id = self.create_session("callback-receipt-loss")
        request_id = "e2e-callback-loss-0001"
        before = self.provider_keys()
        started = self.start_run(
            self.run_body(
                session_id=session_id,
                client_request_id=request_id,
                instruction="请概括当前章节中明确出现的环境事实。",
            )
        ).json()
        run_id = str(started["runId"])
        terminal = self.wait_terminal(run_id)
        if terminal["status"] != "completed":
            raise AssertionError("callback 回执丢失场景没有完成")
        facts, provider = self.assert_scenario_facts(
            run_id=run_id,
            session_id=session_id,
            provider_before=before,
        )
        deadline = time.monotonic() + 15
        matching: list[dict[str, object]] = []
        while time.monotonic() < deadline:
            attempts = self.control_state()["callbackAttempts"]
            matching = [
                item
                for item in attempts
                if item["run_id"] == run_id
                and item["callback_kind"] == "result"
            ]
            if len(matching) >= 2:
                break
            time.sleep(0.1)
        actions = [item["action"] for item in matching]
        receipts = [item["receipt_status"] for item in matching]
        self.safe_diagnostics["callbackReceiptLoss"] = {
            "runId": run_id,
            "callbackAttempts": matching,
        }
        if actions[:2] != ["dropped_after_forward", "forwarded"]:
            raise AssertionError(f"callback 回执丢失/重放顺序无效：{actions}")
        if receipts[:2] != ["accepted", "duplicate"]:
            raise AssertionError(f"Core callback 幂等回执无效：{receipts}")
        self.assert_callback_attempt_bindings(
            run_id=run_id,
            step=facts["steps"][0],
            journal=facts["journal"],
            attempts=matching[:2],
        )
        return Scenario(
            name="callback_committed_receipt_lost",
            run_id=run_id,
            session_id=session_id,
            client_request_id=request_id,
            provider_identity=provider,
            database_facts={**facts, "callbackAttempts": matching[:2]},
        )

    def agent_restart_replays_terminal_journal(self) -> Scenario:
        self.control_request(
            "PUT", "/control/callback-mode", {"mode": "hold_before_forward"}
        )
        session_id = self.create_session("agent-restart-terminal-replay")
        request_id = "e2e-agent-restart-0001"
        before = self.provider_keys()
        started = self.start_run(
            self.run_body(
                session_id=session_id,
                client_request_id=request_id,
                instruction="请说明当前章节中已经明确发生的一个决定。",
            )
        ).json()
        run_id = str(started["runId"])
        self.wait_callback_gate(run_id, minimum_reached=1)
        runtime = self.stack.restart_and_wait("agent-service")
        self.wait_callback_gate(run_id, minimum_reached=2, timeout=60)
        self.control_request("POST", "/control/callback-release", {"abort": False})
        terminal = self.wait_terminal(run_id, timeout=60)
        if terminal["status"] != "completed":
            raise AssertionError("Agent 重启后 terminal journal 没有收敛")
        facts, provider = self.assert_scenario_facts(
            run_id=run_id,
            session_id=session_id,
            provider_before=before,
        )
        deadline = time.monotonic() + 20
        matching: list[dict[str, object]] = []
        while time.monotonic() < deadline:
            attempts = self.control_state()["callbackAttempts"]
            matching = [
                item
                for item in attempts
                if isinstance(item, dict)
                and item.get("run_id") == run_id
                and item.get("callback_kind") == "result"
            ]
            forwarded = [
                item for item in matching if item.get("action") == "forwarded"
            ]
            if forwarded:
                break
            time.sleep(0.1)
        held = [
            item for item in matching if item.get("action") == "held_before_forward"
        ]
        forwarded = [item for item in matching if item.get("action") == "forwarded"]
        receipts = [
            receipt
            for item in forwarded
            if isinstance((receipt := item.get("receipt_status")), str)
        ]
        self.safe_diagnostics["agentRestart"] = {
            "runId": run_id,
            "serviceRestart": runtime,
            "callbackAttempts": matching,
            "executionJournal": facts["journal"],
        }
        if len(held) < 2:
            raise AssertionError("Agent 重启前后没有形成两次 terminal callback 尝试")
        _assert_agent_restart_receipts(receipts)
        self.assert_callback_attempt_bindings(
            run_id=run_id,
            step=facts["steps"][0],
            journal=facts["journal"],
            attempts=matching,
        )
        return Scenario(
            name="agent_restart_terminal_journal_replay",
            run_id=run_id,
            session_id=session_id,
            client_request_id=request_id,
            provider_identity=provider,
            database_facts={
                **facts,
                "serviceRestart": runtime,
                "callbackAttempts": matching,
            },
        )

    def core_restart_before_terminal_callback(self) -> Scenario:
        self.control_request(
            "PUT", "/control/callback-mode", {"mode": "hold_before_forward"}
        )
        session_id = self.create_session("core-restart-before-callback")
        request_id = "e2e-core-restart-0001"
        before = self.provider_keys()
        started = self.start_run(
            self.run_body(
                session_id=session_id,
                client_request_id=request_id,
                instruction="请概括当前章节中已经确认的地点事实。",
            )
        ).json()
        run_id = str(started["runId"])
        self.wait_callback_gate(run_id, minimum_reached=1)
        runtime = self.stack.restart_and_wait("core-api")
        self.control_request("POST", "/control/callback-release", {"abort": False})
        terminal = self.wait_terminal(run_id, timeout=60)
        if terminal["status"] != "completed":
            raise AssertionError("Core 重启后 callback 没有收敛")
        facts, provider = self.assert_scenario_facts(
            run_id=run_id,
            session_id=session_id,
            provider_before=before,
        )
        attempts = [
            item
            for item in self.control_state()["callbackAttempts"]
            if isinstance(item, dict)
            and item.get("run_id") == run_id
            and item.get("callback_kind") == "result"
        ]
        self.safe_diagnostics["coreRestart"] = {
            "runId": run_id,
            "serviceRestart": runtime,
            "callbackAttempts": attempts,
            "executionJournal": facts["journal"],
        }
        if not any(
            item.get("action") == "forwarded"
            and item.get("receipt_status") in {"accepted", "duplicate"}
            for item in attempts
        ):
            raise AssertionError("Core 重启后没有合法 terminal callback receipt")
        self.assert_callback_attempt_bindings(
            run_id=run_id,
            step=facts["steps"][0],
            journal=facts["journal"],
            attempts=attempts,
        )
        return Scenario(
            name="core_restart_before_terminal_callback",
            run_id=run_id,
            session_id=session_id,
            client_request_id=request_id,
            provider_identity=provider,
            database_facts={
                **facts,
                "serviceRestart": runtime,
                "callbackAttempts": attempts,
            },
        )

    def cancel_before_agent_submit(self) -> Scenario:
        self.control_request("PUT", "/control/execution-mode", {"mode": "hold"})
        session_id = self.create_session("cancel-before-agent-submit")
        request_id = "e2e-cancel-before-submit-0001"
        before = self.provider_facts()
        started = self.start_run(
            self.run_body(
                session_id=session_id,
                client_request_id=request_id,
                instruction="这个问题不应抵达模型。",
            )
        ).json()
        run_id = str(started["runId"])
        self.wait_execution_gate()
        self.request(
            "POST",
            f"/api/v1/writing/runs/{run_id}/cancel",
            expected=202,
            json_body={"clientRequestId": "e2e-cancel-command-0001"},
        )
        self.control_request("POST", "/control/execution-release", {"abort": True})
        terminal = self.wait_terminal(run_id, timeout=60)
        if terminal["status"] != "cancelled":
            raise AssertionError("submit 前取消没有保持 cancelled 终态")
        if self.provider_facts() != before:
            raise AssertionError("submit 前取消仍调用了 Provider")
        facts = self.database_facts(run_id, session_id)
        self.safe_diagnostics["cancelBeforeSubmit"] = {
            "runId": run_id,
            "database": facts,
        }
        run = facts.get("run")
        if (
            not isinstance(run, dict)
            or run.get("status") != "cancelled"
            or run.get("operation") != "answer_question"
            or run.get("engineVersion") != 2
            or run.get("writingSessionId") != session_id
            or run.get("cancelRequestedAtPresent") is not True
            or not isinstance(run.get("cancelRequestId"), str)
        ):
            raise AssertionError("submit 前取消的 Run 权威身份或取消事实无效")
        steps = facts.get("steps")
        if (
            not isinstance(steps, list)
            or len(steps) != 1
            or not isinstance(steps[0], dict)
            or steps[0].get("status") != "skipped"
            or steps[0].get("attemptCount") != 1
            or steps[0].get("fencingToken") != 1
            or not isinstance(steps[0].get("requestHash"), str)
            or steps[0].get("providerAttempts") not in {None, 0}
            or steps[0].get("resultHash") is not None
            or steps[0].get("errorCode") != "RUN_CANCELLED"
        ):
            raise AssertionError("submit 前取消没有把唯一 Step 收敛为 skipped")
        journal = facts.get("journal")
        if not isinstance(journal, dict) or journal.get("present") is not False:
            raise AssertionError("submit 前取消意外创建了 Agent execution journal")
        if facts.get("messageRoles") != {"user": 1}:
            raise AssertionError("取消场景生成了成功 Agent 消息或丢失用户消息")
        if facts.get("artifactCount") != 0 or facts.get("evaluationCount") != 0:
            raise AssertionError("取消场景产生了 Artifact 或 Evaluation")
        billing = facts.get("billing")
        if not isinstance(billing, dict) or {
            "reservationCount": billing.get("reservationCount"),
            "tokenUsageCount": billing.get("tokenUsageCount"),
            "creditLedgerCount": billing.get("creditLedgerCount"),
            "balanceUnchanged": billing.get("balanceUnchanged"),
        } != {
            "reservationCount": 0,
            "tokenUsageCount": 0,
            "creditLedgerCount": 0,
            "balanceUnchanged": True,
        }:
            raise AssertionError("submit 前取消产生了计费副作用")
        events = facts.get("events")
        event_types = [
            item.get("eventType")
            for item in events
            if isinstance(item, dict)
        ] if isinstance(events, list) else []
        if (
            event_types.count("cancelled") != 1
            or any(value in {"completed", "failed"} for value in event_types)
        ):
            raise AssertionError("取消场景事件终态无效")
        event_sequences = [
            item.get("sequence")
            for item in events
            if isinstance(item, dict)
        ] if isinstance(events, list) else []
        if event_sequences != list(range(1, len(event_sequences) + 1)) or run.get(
            "lastEventSequence"
        ) != len(event_sequences):
            raise AssertionError("取消场景 Event sequence 不连续")
        raw_attempts = self.control_state().get("executionSubmitAttempts")
        attempts = [
            item
            for item in raw_attempts
            if isinstance(item, dict) and item.get("run_id") == run_id
        ] if isinstance(raw_attempts, list) else []
        self.safe_diagnostics["cancelBeforeSubmit"] = {
            "runId": run_id,
            "database": facts,
            "executionSubmitAttempts": attempts,
        }
        step = steps[0]
        if (
            len(attempts) != 1
            or attempts[0].get("agent_status") != 503
            or attempts[0].get("run_id") != run_id
            or attempts[0].get("step_id") != step.get("id")
            or attempts[0].get("fencing_token") != step.get("fencingToken")
            or attempts[0].get("request_hash") != step.get("requestHash")
            or attempts[0].get("validation_errors") != []
        ):
            raise AssertionError("submit gate 没有且仅有一次转发前中止")
        return Scenario(
            name="cancel_before_agent_submit",
            run_id=run_id,
            session_id=session_id,
            client_request_id=request_id,
            provider_identity={"physical_calls": 0, "completed_calls": 0},
            database_facts={**facts, "executionSubmitAttempts": attempts},
        )

    def aof_restart(self, scenarios: list[Scenario]) -> dict[str, object]:
        def persistence_facts() -> tuple[dict[str, str], dict[str, str]]:
            persistence = dict(
                line.split(":", 1)
                for line in self.stack.redis("INFO", "persistence")
                if ":" in line
            )
            config_lines = self.stack.redis(
                "CONFIG",
                "GET",
                "appendonly",
                "appendfsync",
                "aof-load-truncated",
                "maxmemory-policy",
            )
            config = dict(zip(config_lines[::2], config_lines[1::2], strict=True))
            if (
                persistence.get("aof_enabled") != "1"
                or persistence.get("aof_last_write_status") != "ok"
                or config
                != {
                    "aof-load-truncated": "no",
                    "appendfsync": "always",
                    "appendonly": "yes",
                    "maxmemory-policy": "noeviction",
                }
            ):
                raise AssertionError("execution Redis AOF 配置或写状态无效")
            return persistence, config

        before: dict[str, dict[str, object]] = {}
        database_before: dict[str, str | None] = {}
        for scenario in scenarios:
            step_id = str(scenario.database_facts["steps"][0]["id"])
            entry = self.journal_facts(step_id)
            if (
                entry.get("state") != "result"
                or entry.get("callbackDelivery") != "delivered"
                or entry.get("terminalPayloadPresent") is not False
            ):
                raise AssertionError("delivered journal 没有压缩成安全 tombstone")
            before[step_id] = entry
            database_before[scenario.run_id] = _canonical_sha256(
                self.database_facts(scenario.run_id, scenario.session_id)
            )
        provider_before = self.control_state().get("providerCalls")
        persistence_before, config_before = persistence_facts()
        self.safe_diagnostics["executionRedisAof"] = {
            "tombstonesBefore": before,
            "databaseFactsSha256Before": database_before,
            "providerCallFactsCaptured": isinstance(provider_before, list),
        }

        agent_before = self.stack.service_runtime("agent-service")
        runtime = self.stack.restart_and_wait("execution-redis")
        redis_after = runtime.get("after")
        if not isinstance(redis_after, dict):
            raise AssertionError("execution Redis 重启后运行事实无效")
        redis_started_at = redis_after.get("startedAt")
        if not isinstance(redis_started_at, str):
            raise AssertionError("execution Redis 重启后缺少 StartedAt")
        self.safe_diagnostics["executionRedisAof"] = {
            **self.safe_diagnostics["executionRedisAof"],
            "serviceRestart": runtime,
            "agentRecovery": {"before": agent_before, "after": None},
        }
        try:
            agent_after = self.stack.wait_service_healthy(
                "agent-service",
                expected_container_id=agent_before.get("containerId"),
                expected_started_at=agent_before.get("startedAt"),
                minimum_health_checked_at=redis_started_at,
            )
        except AssertionError:
            try:
                failed_agent_after: dict[str, object] = self.stack.service_runtime(
                    "agent-service"
                )
            except (
                AssertionError,
                OSError,
                RuntimeError,
                ValueError,
                subprocess.SubprocessError,
            ):
                failed_agent_after = {"collectionStatus": "unavailable"}
            self.safe_diagnostics["executionRedisAof"] = {
                **self.safe_diagnostics["executionRedisAof"],
                "agentRecovery": {
                    "before": agent_before,
                    "after": failed_agent_after,
                },
            }
            raise
        persistence_after, config_after = persistence_facts()
        after: dict[str, dict[str, object]] = {}
        for step_id in before:
            after[step_id] = self.journal_facts(step_id)
        if after != before:
            raise AssertionError("execution Redis 重启后 tombstone 漂移或丢失")
        provider_after = self.control_state().get("providerCalls")
        if provider_after != provider_before:
            raise AssertionError("execution Redis 重启后 Provider 调用事实发生变化")
        database_after = {
            scenario.run_id: _canonical_sha256(
                self.database_facts(scenario.run_id, scenario.session_id)
            )
            for scenario in scenarios
        }
        if database_after != database_before:
            raise AssertionError("execution Redis 重启后 Core 业务事实发生变化")
        self.safe_diagnostics["executionRedisAof"] = {
            "serviceRestart": runtime,
            "agentRecovery": {"before": agent_before, "after": agent_after},
            "tombstonesBefore": before,
            "tombstonesAfter": after,
            "databaseFactsSha256Before": database_before,
            "databaseFactsSha256After": database_after,
            "providerFactsUnchanged": True,
        }
        return {
            "serviceRestart": runtime,
            "agentRecovery": {"before": agent_before, "after": agent_after},
            "persistenceBefore": {
                "aofEnabled": persistence_before.get("aof_enabled"),
                "aofLastWriteStatus": persistence_before.get(
                    "aof_last_write_status"
                ),
            },
            "persistenceAfter": {
                "aofEnabled": persistence_after.get("aof_enabled"),
                "aofLastWriteStatus": persistence_after.get("aof_last_write_status"),
            },
            "configBefore": config_before,
            "configAfter": config_after,
            "tombstonesBefore": before,
            "tombstonesAfter": after,
            "databaseFactsSha256Before": database_before,
            "databaseFactsSha256After": database_after,
            "providerFactsUnchanged": True,
        }


def _evidence_dir(argument: Path | None) -> Path:
    if argument is None:
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        return ROOT / "output" / "durable-agent-v2-e2e" / (
            timestamp + "-" + secrets.token_hex(4)
        )
    if not argument.is_absolute():
        raise ValueError("证据目录必须是绝对路径")
    return argument


def run(
    evidence_dir: Path,
    *,
    phase: str,
    infrastructure_retry: int,
    reuse_built_images: bool,
    rebuild_agent: bool,
) -> dict[str, object]:
    if evidence_dir.exists():
        raise FileExistsError("证据目录已存在，拒绝覆盖")
    evidence_dir.mkdir(parents=True, mode=0o700)
    stack = ComposeStack(evidence_dir)
    sampler = ResourceSampler(stack)
    acceptance: Acceptance | None = None
    report: dict[str, object] = {
        "schemaVersion": "inkforge-durable-agent-v2-compose-e2e/1",
        "startedAt": datetime.now(UTC).isoformat(),
        "scope": "local-isolated-fake-provider",
        "productionAccessed": False,
        "developmentDatabaseAccessed": False,
        "realProviderAccessed": False,
        "twoCoreTwoGiBHostGate": "not_proven",
        "status": "failed",
        "phase": phase,
        "infrastructureRetry": infrastructure_retry,
        "reusedBuiltImages": reuse_built_images,
        "rebuiltAgentImage": rebuild_agent,
        "composeProject": stack.project,
        "composeFileSha256": hashlib.sha256(COMPOSE_FILE.read_bytes()).hexdigest(),
        "scenarios": [],
    }
    cleanup: dict[str, object] = {}
    try:
        if rebuild_agent:
            stack.build_agent()
            report["images"] = stack.image_facts()
        stack.start(build=not reuse_built_images and not rebuild_agent)
        if "images" not in report:
            report["images"] = stack.image_facts()
        sampler.start()
        acceptance = Acceptance(stack)
        acceptance.control_request("POST", "/control/reset")
        acceptance.bootstrap()
        stack.activate_durable_scope(
            user_id=acceptance.user_id,
            novel_id=acceptance.novel_id,
        )
        scenarios: list[Scenario] = []

        def record_scenario(scenario: Scenario) -> None:
            scenarios.append(scenario)
            report_scenarios = report["scenarios"]
            if not isinstance(report_scenarios, list):
                raise AssertionError("E2E 报告 scenarios 容器无效")
            report_scenarios.append(
                {
                    "name": scenario.name,
                    "runId": scenario.run_id,
                    "clientRequestId": scenario.client_request_id,
                    "provider": scenario.provider_identity,
                    "database": scenario.database_facts,
                }
            )

        record_scenario(acceptance.happy_and_idempotency())
        if phase == "minimum":
            record_scenario(acceptance.callback_receipt_loss())
            record_scenario(acceptance.agent_restart_replays_terminal_journal())
            record_scenario(acceptance.core_restart_before_terminal_callback())
            record_scenario(acceptance.cancel_before_agent_submit())
        if phase == "minimum":
            report["executionRedisAof"] = acceptance.aof_restart(scenarios[:-1])
        report["status"] = "passed"
    except Exception as exc:
        report["failureType"] = type(exc).__name__
        report["failureSummary"] = str(exc)[-1_000:]
        if acceptance is not None:
            try:
                control_state = acceptance.control_state()
                report["failureDiagnostics"] = {
                    "providerCalls": control_state.get("providerCalls", []),
                    "callbackAttempts": control_state.get("callbackAttempts", []),
                    "executionSubmitAttempts": control_state.get(
                        "executionSubmitAttempts", []
                    ),
                    "lastServiceRestart": stack.last_service_restart,
                    **acceptance.safe_diagnostics,
                }
            except (AssertionError, httpx.HTTPError):
                report["failureDiagnostics"] = {
                    "providerCalls": [],
                    "callbackAttempts": [],
                    "executionSubmitAttempts": [],
                    "collectionStatus": "unavailable",
                }
        raise
    finally:
        if acceptance is not None:
            acceptance.close()
        sampler.stop()
        report["resources"] = {
            "sampleCount": sampler.samples,
            "maxMemoryBytesByContainer": sampler.max_memory_bytes,
            "interpretation": (
                "仅为本机容器限制内短时采样，不证明真实 2 核 2 GB 整机稳定性"
            ),
        }
        cleanup = stack.cleanup()
        report["cleanup"] = cleanup
        resource_queries = cleanup.get("resourceQueryExitCodes")
        cleanup_valid = not (
            cleanup.get("composeDownExitCode") != 0
            or cleanup["residualContainerCount"] != 0
            or cleanup.get("residualNetworkCount") != 0
            or cleanup.get("residualVolumeCount") != 0
            or not cleanup["temporaryKeyDirectoryRemoved"]
            or resource_queries
            != {"containers": 0, "networks": 0, "volumes": 0}
        )
        cleanup["valid"] = cleanup_valid
        if not cleanup_valid:
            report["status"] = "failed"
            report.setdefault("failureType", "CleanupFailure")
            report.setdefault("failureSummary", "隔离 Compose 资源清理证据无效")
        report["finishedAt"] = datetime.now(UTC).isoformat()
        destination = evidence_dir / "report.json"
        destination.write_text(
            json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.chmod(destination, 0o600)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="运行 Durable Agent V2 本地 Compose 验收")
    parser.add_argument("--evidence-dir", type=Path)
    parser.add_argument(
        "--phase",
        choices=("happy", "minimum"),
        default="minimum",
        help=(
            "happy 只验成功/幂等/SSE；minimum 继续验 callback 丢回执、"
            "Agent/Core 重启、submit 前取消与 AOF"
        ),
    )
    parser.add_argument(
        "--infrastructure-retry",
        choices=(0, 1),
        default=0,
        type=int,
        help="只记录经批准的本地基础设施显式重试次数，不自动循环",
    )
    parser.add_argument(
        "--reuse-built-images",
        action="store_true",
        help="只复用同 tag 已构建的本地测试镜像；测试控制器源码仍以只读挂载加载",
    )
    parser.add_argument(
        "--rebuild-agent",
        action="store_true",
        help="只重建 Agent，并在启动前校验 journal/queue 源码与镜像哈希精确一致",
    )
    arguments = parser.parse_args()
    try:
        evidence_dir = _evidence_dir(arguments.evidence_dir)
        report = run(
            evidence_dir,
            phase=arguments.phase,
            infrastructure_retry=arguments.infrastructure_retry,
            reuse_built_images=arguments.reuse_built_images,
            rebuild_agent=arguments.rebuild_agent,
        )
    except (
        FileExistsError,
        OSError,
        RuntimeError,
        AssertionError,
        ValueError,
        httpx.HTTPError,
    ) as exc:
        raise SystemExit(f"验收失败：{type(exc).__name__}；证据目录已保留") from None
    print(
        json.dumps(
            {
                "status": report["status"],
                "evidenceDir": str(evidence_dir),
                "twoCoreTwoGiBHostGate": report["twoCoreTwoGiBHostGate"],
            },
            ensure_ascii=False,
        )
    )
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
