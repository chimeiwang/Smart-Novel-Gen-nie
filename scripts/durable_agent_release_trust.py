#!/usr/bin/env python3
"""构建并离线验证 Durable Agent SSH 与 genesis 发布信任证据。"""

from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import json
import os
import re
import shutil
import stat
import sys
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from durable_agent_release_broker import (
    ORIGINAL_COMMAND,
)
from durable_agent_release_broker import (
    policy_sha256 as broker_policy_sha256,
)
from durable_agent_v2_release_receipt import (
    FORMAT as RECEIPT_FORMAT,
)
from durable_agent_v2_release_receipt import (
    ReceiptInvalid,
)
from durable_agent_v2_release_receipt import (
    validate as validate_receipt,
)
from durable_agent_v2_release_receipt import (
    verify as verify_receipt,
)

SSH_FORMAT = "inkforge-ssh-release-attestation/1"
BOOTSTRAP_FORMAT = "inkforge-release-bootstrap-attestation/1"
BOOTSTRAP_STATE_FORMAT = "inkforge-release-bootstrap-state/1"
ORGANIZATION_INVENTORY_FORMAT = "inkforge-github-organization-secret-inventory/1"
SSH_FILENAME = "ssh-release-attestation.json"
BOOTSTRAP_FILENAME = "release-bootstrap-attestation.json"
GITHUB_ARTIFACT_NAMES = {
    SSH_FORMAT: "durable-agent-v2-ssh-release-attestation",
    BOOTSTRAP_FORMAT: "durable-agent-v2-release-bootstrap-attestation",
}
GITHUB_WORKFLOW_PATHS = {
    SSH_FORMAT: ".github/workflows/durable-agent-v2-ssh-release-attestation.yml",
    BOOTSTRAP_FORMAT: ".github/workflows/durable-agent-v2-release-bootstrap.yml",
}
SSH_EVIDENCE_PAYLOAD_FILES = (
    "authorized_keys",
    "broker-executable",
    "execution-public-key.pub",
    "host-public-key.pub",
    "known_hosts",
    "retired-public-key-broad-v2.pub",
    "retired-public-key-server.pub",
    "upload-public-key.pub",
)
DOWNLOAD_LAYOUTS = {
    "bootstrap-attestation": (BOOTSTRAP_FILENAME, "SHA256SUMS"),
    "ssh-attestation": (SSH_FILENAME, "SHA256SUMS"),
    "ssh-evidence": (*SSH_EVIDENCE_PAYLOAD_FILES, "SHA256SUMS"),
}
MAX_EVIDENCE_BYTES = 1_048_576
MAX_TTL = timedelta(hours=24)
MAX_FUTURE_SKEW = timedelta(minutes=5)

HEX = frozenset("0123456789abcdef")
REPOSITORY_PATTERN = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+\Z")
HOST_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9.:-]{0,252}\Z")
USER_PATTERN = re.compile(r"[A-Za-z_][A-Za-z0-9_.-]{0,63}\Z")
KEY_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")
OPENSSH_KEY_PATTERN = re.compile(
    r"(?:(?<=^)|(?<=[ \t]))(ssh-ed25519) ([A-Za-z0-9+/]+={0,2})(?=$|[ \t])"
)

ACTIVE_EXECUTION_SECRET = "DURABLE_AGENT_V2_RELEASE_EXECUTION_SSH_PRIVATE_KEY"  # noqa: S105
ACTIVE_UPLOAD_SECRET = "DURABLE_AGENT_V2_RELEASE_UPLOAD_SSH_PRIVATE_KEY"  # noqa: S105
ACTIVE_SECRETS = (ACTIVE_EXECUTION_SECRET, ACTIVE_UPLOAD_SECRET)
RETIRED_SECRETS = (
    "DURABLE_AGENT_V2_RELEASE_SSH_PRIVATE_KEY",
    "SERVER_SSH_KEY",
)
EXECUTION_FORCED_COMMAND = "/usr/local/libexec/inkforge-release-broker execution"
UPLOAD_FORCED_COMMAND = "/usr/local/libexec/inkforge-release-broker upload"

SSH_PAYLOAD_KEYS = {
    "broker",
    "environment",
    "evidence",
    "expiresAt",
    "issuedAt",
    "keys",
    "repository",
    "secretPolicy",
    "server",
}
BOOTSTRAP_PAYLOAD_KEYS = {
    "environment",
    "expiresAt",
    "genesisReceipt",
    "issuedAt",
    "repository",
    "server",
    "sshReleaseAttestationSha256",
    "transition",
}


class TrustInvalid(ValueError):
    """证据不能建立发布 SSH 或 genesis 信任根。"""


@dataclass(frozen=True)
class SshEvidence:
    known_hosts: Path
    host_public_key: Path
    authorized_keys: Path
    retired_public_keys: tuple[Path, ...]
    execution_public_key: Path
    upload_public_key: Path
    environment_secrets: Path
    repository_secrets: Path
    organization_secrets: Path
    broker_executable: Path


def _canonical(document: dict[str, Any]) -> bytes:
    return (
        json.dumps(
            document,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode()


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _require_hex(value: Any, length: int, label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != length
        or any(character not in HEX for character in value)
    ):
        raise TrustInvalid(f"{label} 格式无效")
    return value


def _require_exact_keys(value: Any, expected: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != expected:
        raise TrustInvalid(f"{label} 字段无效")
    return value


def _require_subject(
    payload: dict[str, Any],
    *,
    expected_repository: str,
    expected_environment: str,
    expected_host: str,
    expected_port: int,
    expected_user: str,
    expected_host_public_key_sha256: str | None = None,
) -> None:
    if REPOSITORY_PATTERN.fullmatch(expected_repository) is None:
        raise TrustInvalid("expected repository 格式无效")
    if expected_environment != "production":
        raise TrustInvalid("发布信任根只允许 production environment")
    if HOST_PATTERN.fullmatch(expected_host) is None:
        raise TrustInvalid("expected host 格式无效")
    if isinstance(expected_port, bool) or not 1 <= expected_port <= 65_535:
        raise TrustInvalid("expected port 格式无效")
    if USER_PATTERN.fullmatch(expected_user) is None:
        raise TrustInvalid("expected user 格式无效")
    if payload.get("repository") != expected_repository:
        raise TrustInvalid("attestation repository subject 漂移")
    if payload.get("environment") != expected_environment:
        raise TrustInvalid("attestation environment subject 漂移")
    expected_server: dict[str, Any] = {
        "host": expected_host,
        "port": expected_port,
        "user": expected_user,
    }
    if expected_host_public_key_sha256 is not None:
        expected_server["hostPublicKeySha256"] = _require_hex(
            expected_host_public_key_sha256, 64, "expected host public key SHA"
        )
    server = _require_exact_keys(payload.get("server"), set(expected_server), "server")
    if server != expected_server:
        raise TrustInvalid("attestation server subject 漂移")


def _parse_utc(value: Any, label: str) -> datetime:
    if not isinstance(value, str):
        raise TrustInvalid(f"{label} 必须是 UTC 时间字符串")
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    except ValueError as error:
        raise TrustInvalid(f"{label} 格式无效") from error
    return parsed


def _validate_window(payload: dict[str, Any], now: datetime) -> None:
    if now.tzinfo is None:
        raise TrustInvalid("verifier now 必须带时区")
    now = now.astimezone(UTC)
    issued = _parse_utc(payload.get("issuedAt"), "issuedAt")
    expires = _parse_utc(payload.get("expiresAt"), "expiresAt")
    if not issued < expires or expires - issued > MAX_TTL:
        raise TrustInvalid("attestation TTL 必须在 0 到 24 小时之间")
    if issued - now > MAX_FUTURE_SKEW:
        raise TrustInvalid("attestation 签发时间超出允许时钟偏差")
    if now >= expires:
        raise TrustInvalid("attestation 已过期")


def _stat_fingerprint(value: os.stat_result) -> tuple[int, int, int, int, int, int, int]:
    return (
        value.st_dev,
        value.st_ino,
        value.st_size,
        value.st_mode,
        value.st_mtime_ns,
        value.st_ctime_ns,
        value.st_nlink,
    )


def _validate_regular_stat(value: os.stat_result, label: str, *, private: bool) -> None:
    mode = stat.S_IMODE(value.st_mode)
    if not stat.S_ISREG(value.st_mode) or value.st_nlink != 1:
        raise TrustInvalid(f"{label} 必须是单链接普通文件")
    if value.st_size < 0 or value.st_size > MAX_EVIDENCE_BYTES:
        raise TrustInvalid(f"{label} 超出大小上限")
    if mode & (stat.S_ISUID | stat.S_ISGID | stat.S_ISVTX) or not mode & stat.S_IRUSR:
        raise TrustInvalid(f"{label} mode 无效")
    if private and mode & 0o077:
        raise TrustInvalid(f"{label} 权限必须禁止 group/other")
    if not private and mode & 0o022:
        raise TrustInvalid(f"{label} 不得由 group/other 写入")


def _read_regular(path: Path, label: str, *, private: bool = True) -> bytes:
    nofollow = getattr(os, "O_NOFOLLOW", None)
    if nofollow is None:
        raise TrustInvalid("当前平台缺少 O_NOFOLLOW，拒绝读取发布信任证据")
    flags = os.O_RDONLY | nofollow | getattr(os, "O_CLOEXEC", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        raise TrustInvalid(f"无法安全打开 {label}") from error
    try:
        before = os.fstat(descriptor)
        _validate_regular_stat(before, label, private=private)
        try:
            path_before = os.stat(path, follow_symlinks=False)
        except OSError as error:
            raise TrustInvalid(f"{label} 路径在读取前漂移") from error
        if _stat_fingerprint(path_before) != _stat_fingerprint(before):
            raise TrustInvalid(f"{label} 路径与已打开文件不一致")

        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(descriptor, min(1024 * 1024, MAX_EVIDENCE_BYTES + 1 - total))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            if total > MAX_EVIDENCE_BYTES:
                raise TrustInvalid(f"{label} 超出大小上限")
        payload = b"".join(chunks)

        after = os.fstat(descriptor)
        try:
            path_after = os.stat(path, follow_symlinks=False)
        except OSError as error:
            raise TrustInvalid(f"{label} 路径在读取后漂移") from error
        fingerprints = {
            _stat_fingerprint(before),
            _stat_fingerprint(path_before),
            _stat_fingerprint(after),
            _stat_fingerprint(path_after),
        }
        if len(fingerprints) != 1 or len(payload) != before.st_size:
            raise TrustInvalid(f"{label} 在读取期间漂移")
        return payload
    except OSError as error:
        raise TrustInvalid(f"无法稳定读取 {label}") from error
    finally:
        os.close(descriptor)


def normalize_downloaded_directory(directory: Path, kind: str) -> None:
    """将 artifact action 丢失的权限元数据安全收紧到 canonical 模式。"""

    expected = DOWNLOAD_LAYOUTS.get(kind)
    if expected is None:
        raise TrustInvalid("downloaded artifact kind 无效")
    if not directory.is_absolute():
        raise TrustInvalid("downloaded artifact 目录必须是绝对路径")
    nofollow = getattr(os, "O_NOFOLLOW", None)
    directory_flag = getattr(os, "O_DIRECTORY", None)
    if nofollow is None or directory_flag is None:
        raise TrustInvalid("当前平台缺少安全 artifact 目录打开能力")
    try:
        directory_descriptor = os.open(
            directory,
            os.O_RDONLY | nofollow | directory_flag | getattr(os, "O_CLOEXEC", 0),
        )
    except OSError as error:
        raise TrustInvalid("无法安全打开 downloaded artifact 目录") from error
    try:
        directory_before = os.fstat(directory_descriptor)
        directory_mode = stat.S_IMODE(directory_before.st_mode)
        if (
            not stat.S_ISDIR(directory_before.st_mode)
            or directory_before.st_uid != os.geteuid()
            or directory_mode & 0o022
            or directory_mode & (stat.S_ISUID | stat.S_ISGID | stat.S_ISVTX)
        ):
            raise TrustInvalid("downloaded artifact 目录身份或权限无效")
        names = set(os.listdir(directory_descriptor))
        if names != set(expected):
            raise TrustInvalid("downloaded artifact 文件白名单无效")
        for name in expected:
            try:
                descriptor = os.open(
                    name,
                    os.O_RDONLY | nofollow | getattr(os, "O_CLOEXEC", 0),
                    dir_fd=directory_descriptor,
                )
            except OSError as error:
                raise TrustInvalid(f"无法安全打开 downloaded artifact 文件：{name}") from error
            try:
                before = os.fstat(descriptor)
                _validate_regular_stat(before, f"downloaded artifact {name}", private=False)
                if before.st_uid != os.geteuid():
                    raise TrustInvalid(f"downloaded artifact 文件 owner 无效：{name}")
                path_before = os.stat(
                    name,
                    dir_fd=directory_descriptor,
                    follow_symlinks=False,
                )
                if _stat_fingerprint(path_before) != _stat_fingerprint(before):
                    raise TrustInvalid(f"downloaded artifact 文件路径漂移：{name}")
                os.fchmod(descriptor, 0o600)
                after = os.fstat(descriptor)
                path_after = os.stat(
                    name,
                    dir_fd=directory_descriptor,
                    follow_symlinks=False,
                )
                _validate_regular_stat(after, f"downloaded artifact {name}", private=True)
                stable_before = (
                    before.st_dev,
                    before.st_ino,
                    before.st_size,
                    before.st_mtime_ns,
                    before.st_nlink,
                )
                stable_after = (
                    after.st_dev,
                    after.st_ino,
                    after.st_size,
                    after.st_mtime_ns,
                    after.st_nlink,
                )
                if (
                    stable_before != stable_after
                    or _stat_fingerprint(path_after) != _stat_fingerprint(after)
                ):
                    raise TrustInvalid(f"downloaded artifact 文件在收紧权限时漂移：{name}")
            except OSError as error:
                raise TrustInvalid(f"无法稳定收紧 downloaded artifact 文件：{name}") from error
            finally:
                os.close(descriptor)
        if set(os.listdir(directory_descriptor)) != names:
            raise TrustInvalid("downloaded artifact 目录内容漂移")
        os.fchmod(directory_descriptor, 0o700)
        directory_after = os.fstat(directory_descriptor)
        if (
            directory_after.st_dev != directory_before.st_dev
            or directory_after.st_ino != directory_before.st_ino
            or stat.S_IMODE(directory_after.st_mode) != 0o700
        ):
            raise TrustInvalid("downloaded artifact 目录在收紧权限时漂移")
    except OSError as error:
        raise TrustInvalid("无法稳定收紧 downloaded artifact 目录") from error
    finally:
        os.close(directory_descriptor)


def _decode_json(payload: bytes, label: str) -> dict[str, Any]:
    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise TrustInvalid(f"{label} JSON key 重复：{key}")
            result[key] = value
        return result

    try:
        document = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=unique,
            parse_float=lambda _raw: (_ for _ in ()).throw(TrustInvalid(f"{label} 禁止浮点")),
            parse_constant=lambda raw: (_ for _ in ()).throw(
                TrustInvalid(f"{label} 包含非法数字：{raw}")
            ),
        )
    except TrustInvalid:
        raise
    except (UnicodeError, json.JSONDecodeError) as error:
        raise TrustInvalid(f"{label} 不是有效 UTF-8 JSON") from error
    if not isinstance(document, dict):
        raise TrustInvalid(f"{label} 顶层必须是对象")
    return document


def _normalized_openssh_key(payload: bytes, label: str) -> tuple[str, str]:
    try:
        lines = [
            line.strip()
            for line in payload.decode("ascii").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ]
    except UnicodeError as error:
        raise TrustInvalid(f"{label} 不是 ASCII OpenSSH 公钥") from error
    if len(lines) != 1:
        raise TrustInvalid(f"{label} 必须精确包含一个公钥")
    match = OPENSSH_KEY_PATTERN.search(lines[0])
    if match is None or match.start() != 0:
        raise TrustInvalid(f"{label} 只允许 ssh-ed25519 公钥")
    key_type, encoded = match.groups()
    try:
        raw = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error) as error:
        raise TrustInvalid(f"{label} base64 无效") from error
    canonical_encoded = base64.b64encode(raw).decode("ascii")
    normalized = f"{key_type} {canonical_encoded}"
    try:
        loaded = serialization.load_ssh_public_key(normalized.encode("ascii"))
    except (TypeError, ValueError) as error:
        raise TrustInvalid(f"{label} 不是有效 Ed25519 OpenSSH key blob") from error
    if not isinstance(loaded, Ed25519PublicKey):
        raise TrustInvalid(f"{label} 必须是 Ed25519 公钥")
    canonical_key = loaded.public_bytes(
        serialization.Encoding.OpenSSH,
        serialization.PublicFormat.OpenSSH,
    ).decode("ascii")
    if normalized != canonical_key:
        raise TrustInvalid(f"{label} OpenSSH 编码不 canonical")
    return normalized, _sha256(normalized.encode("ascii"))


def _public_key_hash(path: Path, label: str) -> tuple[str, str]:
    return _normalized_openssh_key(_read_regular(path, label), label)


def _verify_known_hosts(
    evidence: SshEvidence,
    *,
    host: str,
    port: int,
    expected_host_key_sha: str,
    expected_known_hosts_file: Path | None = None,
) -> str:
    payload = _read_regular(evidence.known_hosts, "known_hosts")
    if expected_known_hosts_file is not None:
        actual_payload = _read_regular(
            expected_known_hosts_file,
            "production known_hosts secret",
        )
        if actual_payload != payload:
            raise TrustInvalid("production known_hosts secret 与 signed evidence 不一致")
    _normalized, actual_key_sha = _public_key_hash(evidence.host_public_key, "host public key")
    if actual_key_sha != expected_host_key_sha:
        raise TrustInvalid("host public key SHA 与 attestation 不一致")
    token = host if port == 22 else f"[{host}]:{port}"
    matches: list[str] = []
    try:
        lines = payload.decode("ascii").splitlines()
    except UnicodeError as error:
        raise TrustInvalid("known_hosts 不是 ASCII") from error
    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if parts[0].startswith("@"):
            if len(parts) < 4:
                raise TrustInvalid("known_hosts marker 条目无效")
            hosts, key_type, encoded = parts[1:4]
            marker = parts[0]
        else:
            if len(parts) < 3:
                raise TrustInvalid("known_hosts 条目无效")
            hosts, key_type, encoded = parts[:3]
            marker = ""
        if token not in hosts.split(","):
            continue
        if marker or hosts.startswith("|") or "*" in hosts or "?" in hosts:
            raise TrustInvalid("具名 host proof 禁止 marker、散列或 wildcard")
        normalized, digest = _normalized_openssh_key(
            f"{key_type} {encoded}\n".encode("ascii"), "known_hosts host key"
        )
        del normalized
        matches.append(digest)
    if matches != [expected_host_key_sha]:
        raise TrustInvalid("known_hosts 未精确绑定一个 host/key 条目")
    return _sha256(payload)


def _authorized_key_entries(payload: bytes) -> list[tuple[str, str]]:
    try:
        lines = payload.decode("ascii").splitlines()
    except UnicodeError as error:
        raise TrustInvalid("authorized_keys 不是 ASCII") from error
    entries: list[tuple[str, str]] = []
    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        match = OPENSSH_KEY_PATTERN.search(line)
        if match is None:
            raise TrustInvalid("authorized_keys 包含无法审计的 key 条目")
        prefix = line[: match.start()].rstrip()
        key_type, encoded = match.groups()
        _normalized, digest = _normalized_openssh_key(
            f"{key_type} {encoded}\n".encode("ascii"), "authorized key"
        )
        entries.append((prefix, digest))
    return entries


def _verify_authorized_keys(
    evidence: SshEvidence,
    *,
    execution_sha: str,
    upload_sha: str,
    retired_shas: tuple[str, ...],
) -> str:
    payload = _read_regular(evidence.authorized_keys, "authorized_keys")
    entries = _authorized_key_entries(payload)
    execution_prefix = f'restrict,command="{EXECUTION_FORCED_COMMAND}"'
    upload_prefix = f'restrict,command="{UPLOAD_FORCED_COMMAND}"'
    execution_entries = [prefix for prefix, digest in entries if digest == execution_sha]
    upload_entries = [prefix for prefix, digest in entries if digest == upload_sha]
    if execution_entries != [execution_prefix]:
        raise TrustInvalid("execution key forced-command/restrict 不精确")
    if upload_entries != [upload_prefix]:
        raise TrustInvalid("upload key forced-command/restrict 不精确")
    present = {digest for _prefix, digest in entries}
    if present.intersection(retired_shas):
        raise TrustInvalid("authorized_keys 仍包含 retired release key")
    return _sha256(payload)


def _secret_inventory(
    path: Path,
    label: str,
    *,
    organization_repository: str | None = None,
) -> tuple[set[str], str]:
    payload = _read_regular(path, label)
    document = _decode_json(payload, label)
    if organization_repository is not None:
        parts = organization_repository.split("/")
        if len(parts) != 2 or any(not part or part in {".", ".."} for part in parts):
            raise TrustInvalid("organization inventory repository 格式无效")
        if set(document) != {"format", "owner", "secrets", "total_count"}:
            raise TrustInvalid("organization secret inventory 字段无效")
        if document.get("format") != ORGANIZATION_INVENTORY_FORMAT:
            raise TrustInvalid("organization secret inventory format 无效")
        owner = document.get("owner")
        if (
            not isinstance(owner, dict)
            or set(owner) != {"login", "type"}
            or owner.get("login") != parts[0]
            or owner.get("type") not in {"User", "Organization"}
        ):
            raise TrustInvalid("organization secret inventory owner 漂移")
        if payload != _canonical(document):
            raise TrustInvalid("organization secret inventory 必须是 canonical JSON")
    total = document.get("total_count")
    items = document.get("secrets")
    if (
        isinstance(total, bool)
        or not isinstance(total, int)
        or not isinstance(items, list)
        or total != len(items)
        or any(not isinstance(item, dict) for item in items)
    ):
        raise TrustInvalid(f"{label} 分页或计数不完整")
    names: list[str] = []
    for item in items:
        name = item.get("name")
        if not isinstance(name, str) or not name:
            raise TrustInvalid(f"{label} secret 名称无效")
        names.append(name)
    if len(names) != len(set(names)):
        raise TrustInvalid(f"{label} secret 名称重复")
    if organization_repository is not None:
        owner = document["owner"]
        if isinstance(owner, dict) and owner.get("type") == "User" and names:
            raise TrustInvalid("User owner 的 organization secret scope 必须不存在")
    return set(names), _sha256(payload)


def load_ssh_evidence_bundle(
    directory: Path,
    *,
    environment_secrets: Path,
    repository_secrets: Path,
    organization_secrets: Path,
) -> SshEvidence:
    if (
        not directory.is_absolute()
        or directory.is_symlink()
        or not directory.is_dir()
        or stat.S_IMODE(directory.stat().st_mode) != 0o700
    ):
        raise TrustInvalid("SSH evidence bundle 必须是 0700 普通绝对目录")
    expected_names = {*SSH_EVIDENCE_PAYLOAD_FILES, "SHA256SUMS"}
    actual_names = {path.name for path in directory.iterdir()}
    if actual_names != expected_names:
        raise TrustInvalid("SSH evidence bundle 文件白名单无效")
    payloads: dict[str, bytes] = {}
    for name in SSH_EVIDENCE_PAYLOAD_FILES:
        payloads[name] = _read_regular(
            directory / name,
            f"SSH evidence {name}",
            private=name != "broker-executable",
        )
    expected_checksums = "".join(
        f"{_sha256(payloads[name])}  {name}\n" for name in SSH_EVIDENCE_PAYLOAD_FILES
    ).encode("ascii")
    actual_checksums = _read_regular(
        directory / "SHA256SUMS", "SSH evidence SHA256SUMS"
    )
    if actual_checksums != expected_checksums:
        raise TrustInvalid("SSH evidence bundle SHA256SUMS 无效")
    return SshEvidence(
        known_hosts=directory / "known_hosts",
        host_public_key=directory / "host-public-key.pub",
        authorized_keys=directory / "authorized_keys",
        retired_public_keys=(
            directory / "retired-public-key-broad-v2.pub",
            directory / "retired-public-key-server.pub",
        ),
        execution_public_key=directory / "execution-public-key.pub",
        upload_public_key=directory / "upload-public-key.pub",
        environment_secrets=environment_secrets,
        repository_secrets=repository_secrets,
        organization_secrets=organization_secrets,
        broker_executable=directory / "broker-executable",
    )


def _verify_secret_layers(
    evidence: SshEvidence, *, repository: str
) -> tuple[str, str, str]:
    environment, environment_sha = _secret_inventory(
        evidence.environment_secrets, "environment secret inventory"
    )
    repository_names, repository_sha = _secret_inventory(
        evidence.repository_secrets, "repository secret inventory"
    )
    organization, organization_sha = _secret_inventory(
        evidence.organization_secrets,
        "organization secret inventory",
        organization_repository=repository,
    )
    active = set(ACTIVE_SECRETS)
    retired = set(RETIRED_SECRETS)
    if not active.issubset(environment) or environment.intersection(retired):
        raise TrustInvalid("environment secret scope 未完成新旧 key 切换")
    if repository_names.intersection(active | retired):
        raise TrustInvalid("repository scope 仍包含 release SSH secret")
    if organization.intersection(active | retired):
        raise TrustInvalid("organization scope 仍包含 release SSH secret")
    return environment_sha, repository_sha, organization_sha


def build_ssh_payload(
    *,
    repository: str,
    environment: str,
    host: str,
    port: int,
    user: str,
    issued_at: str,
    expires_at: str,
    evidence: SshEvidence,
    expected_known_hosts_file: Path | None = None,
) -> dict[str, Any]:
    execution_normalized, execution_sha = _public_key_hash(
        evidence.execution_public_key, "execution public key"
    )
    upload_normalized, upload_sha = _public_key_hash(
        evidence.upload_public_key, "upload public key"
    )
    del execution_normalized, upload_normalized
    retired = tuple(
        sorted(
            {
                _public_key_hash(path, "retired public key")[1]
                for path in evidence.retired_public_keys
            }
        )
    )
    if not retired:
        raise TrustInvalid("至少需要一把 retired release public key")
    if execution_sha == upload_sha or {execution_sha, upload_sha}.intersection(retired):
        raise TrustInvalid("active/retired release public key 必须相互不同")
    _host_normalized, host_key_sha = _public_key_hash(evidence.host_public_key, "host public key")
    del _host_normalized
    known_hosts_sha = _verify_known_hosts(
        evidence,
        host=host,
        port=port,
        expected_host_key_sha=host_key_sha,
        expected_known_hosts_file=expected_known_hosts_file,
    )
    authorized_sha = _verify_authorized_keys(
        evidence,
        execution_sha=execution_sha,
        upload_sha=upload_sha,
        retired_shas=retired,
    )
    environment_sha, repository_sha, organization_sha = _verify_secret_layers(
        evidence, repository=repository
    )
    broker_sha = _sha256(
        _read_regular(evidence.broker_executable, "broker executable", private=False)
    )
    payload: dict[str, Any] = {
        "broker": {
            "executableSha256": broker_sha,
            "executionForcedCommand": EXECUTION_FORCED_COMMAND,
            "policySha256": broker_policy_sha256(),
            "protocol": ORIGINAL_COMMAND,
            "uploadForcedCommand": UPLOAD_FORCED_COMMAND,
        },
        "environment": environment,
        "evidence": {
            "authorizedKeysSha256": authorized_sha,
            "environmentSecretsSha256": environment_sha,
            "knownHostsSha256": known_hosts_sha,
            "organizationSecretsSha256": organization_sha,
            "repositorySecretsSha256": repository_sha,
        },
        "expiresAt": expires_at,
        "issuedAt": issued_at,
        "keys": {
            "executionPublicKeySha256": execution_sha,
            "retiredPublicKeySha256": list(retired),
            "uploadPublicKeySha256": upload_sha,
        },
        "repository": repository,
        "secretPolicy": {
            "activeEnvironmentSecrets": list(ACTIVE_SECRETS),
            "retiredSecrets": list(RETIRED_SECRETS),
        },
        "server": {
            "host": host,
            "hostPublicKeySha256": host_key_sha,
            "port": port,
            "user": user,
        },
    }
    return payload


def validate_ssh_payload(
    payload: Any,
    *,
    evidence: SshEvidence,
    expected_repository: str,
    expected_environment: str,
    expected_host: str,
    expected_port: int,
    expected_user: str,
    now: datetime,
    expected_known_hosts_file: Path | None = None,
) -> dict[str, Any]:
    document = _require_exact_keys(payload, SSH_PAYLOAD_KEYS, "SSH payload")
    expected = build_ssh_payload(
        repository=expected_repository,
        environment=expected_environment,
        host=expected_host,
        port=expected_port,
        user=expected_user,
        issued_at=str(document["issuedAt"]),
        expires_at=str(document["expiresAt"]),
        evidence=evidence,
        expected_known_hosts_file=expected_known_hosts_file,
    )
    expected_host_key_sha = str(expected["server"]["hostPublicKeySha256"])
    _require_subject(
        document,
        expected_repository=expected_repository,
        expected_environment=expected_environment,
        expected_host=expected_host,
        expected_port=expected_port,
        expected_user=expected_user,
        expected_host_public_key_sha256=expected_host_key_sha,
    )
    _validate_window(document, now)
    if document != expected:
        raise TrustInvalid("SSH attestation 与外部证据交叉绑定不一致")
    return document


def build_bootstrap_payload(
    *,
    repository: str,
    environment: str,
    host: str,
    port: int,
    user: str,
    issued_at: str,
    expires_at: str,
    ssh_release_attestation_sha256: str,
    genesis_receipt: dict[str, Any],
) -> dict[str, Any]:
    _require_hex(ssh_release_attestation_sha256, 64, "SSH attestation SHA")
    try:
        validate_receipt(genesis_receipt, allow_genesis=True)
    except ReceiptInvalid as error:
        raise TrustInvalid(f"genesis receipt 无效：{error}") from error
    if genesis_receipt.get("format") != RECEIPT_FORMAT:
        raise TrustInvalid("genesis receipt format 无效")
    if genesis_receipt.get("previousReceiptSha256") is not None:
        raise TrustInvalid("genesis receipt previous 必须为 null")
    return {
        "environment": environment,
        "expiresAt": expires_at,
        "genesisReceipt": genesis_receipt,
        "issuedAt": issued_at,
        "repository": repository,
        "server": {"host": host, "port": port, "user": user},
        "sshReleaseAttestationSha256": ssh_release_attestation_sha256,
        "transition": {"from": "absent", "to": "prepared"},
    }


def validate_bootstrap_payload(
    payload: Any,
    *,
    expected_repository: str,
    expected_environment: str,
    expected_host: str,
    expected_port: int,
    expected_user: str,
    expected_ssh_attestation_sha256: str,
    now: datetime,
) -> dict[str, Any]:
    document = _require_exact_keys(payload, BOOTSTRAP_PAYLOAD_KEYS, "bootstrap payload")
    _require_subject(
        document,
        expected_repository=expected_repository,
        expected_environment=expected_environment,
        expected_host=expected_host,
        expected_port=expected_port,
        expected_user=expected_user,
    )
    _validate_window(document, now)
    expected_ssh = _require_hex(expected_ssh_attestation_sha256, 64, "expected SSH attestation SHA")
    if document.get("sshReleaseAttestationSha256") != expected_ssh:
        raise TrustInvalid("bootstrap 未绑定精确 SSH attestation")
    if document.get("transition") != {"from": "absent", "to": "prepared"}:
        raise TrustInvalid("bootstrap transition 只能从 absent 到 prepared")
    receipt = document.get("genesisReceipt")
    if not isinstance(receipt, dict):
        raise TrustInvalid("bootstrap genesis receipt 缺失")
    build_bootstrap_payload(
        repository=expected_repository,
        environment=expected_environment,
        host=expected_host,
        port=expected_port,
        user=expected_user,
        issued_at=str(document["issuedAt"]),
        expires_at=str(document["expiresAt"]),
        ssh_release_attestation_sha256=expected_ssh,
        genesis_receipt=receipt,
    )
    return document


def _unsigned_payload(format_name: str, payload: dict[str, Any]) -> bytes:
    return _canonical({"format": format_name, "payload": payload})


def _load_private_key(path: Path) -> Ed25519PrivateKey:
    payload = _read_regular(path, "attestation signing private key")
    try:
        key = serialization.load_pem_private_key(payload, password=None)
    except (TypeError, ValueError) as error:
        raise TrustInvalid("无法加载 Ed25519 signing key") from error
    if not isinstance(key, Ed25519PrivateKey):
        raise TrustInvalid("signing key 必须是 Ed25519")
    return key


def _load_public_key(path: Path) -> Ed25519PublicKey:
    payload = _read_regular(path, "attestation trusted public key")
    try:
        key = serialization.load_pem_public_key(payload)
    except (TypeError, ValueError) as error:
        raise TrustInvalid("无法加载 Ed25519 trusted public key") from error
    if not isinstance(key, Ed25519PublicKey):
        raise TrustInvalid("trusted public key 必须是 Ed25519")
    return key


def _signed_proof(
    format_name: str,
    payload: dict[str, Any],
    *,
    signing_private_key: Path,
    key_id: str,
) -> dict[str, Any]:
    if KEY_ID_PATTERN.fullmatch(key_id) is None:
        raise TrustInvalid("attestation key ID 格式无效")
    signature = _load_private_key(signing_private_key).sign(_unsigned_payload(format_name, payload))
    return {
        "keyId": key_id,
        "kind": "ed25519",
        "signature": base64.urlsafe_b64encode(signature).decode("ascii").rstrip("="),
    }


def _load_github_run(path: Path) -> dict[str, Any]:
    payload = _read_regular(path, "GitHub run API response")
    document = _decode_json(payload, "GitHub run API response")
    return document


def _github_run_identity(
    format_name: str,
    payload: dict[str, Any],
    run: dict[str, Any],
) -> dict[str, str]:
    def required(value: Any) -> str:
        if not isinstance(value, str) or not value:
            raise TrustInvalid("GitHub stable run identity 字段缺失")
        return value

    repository = run.get("repository")
    repository_name = repository.get("full_name") if isinstance(repository, dict) else None
    identity: dict[str, str] = {
        "event": required(run.get("event")),
        "headBranch": required(run.get("head_branch")),
        "headSha": required(run.get("head_sha")),
        "repository": required(repository_name),
        "runAttempt": str(run.get("run_attempt")),
        "runId": str(run.get("id")),
        "workflowPath": required(run.get("path")),
    }
    _require_hex(identity["headSha"], 40, "GitHub run head SHA")
    if identity["repository"] != payload.get("repository"):
        raise TrustInvalid("GitHub run repository 与 attestation subject 不一致")
    if identity["workflowPath"] != GITHUB_WORKFLOW_PATHS[format_name]:
        raise TrustInvalid("GitHub attestation workflow path 无效")
    if identity["headBranch"] != "main" or identity["event"] != "workflow_dispatch":
        raise TrustInvalid("GitHub attestation run 不是 main workflow_dispatch")
    for field, label in (
        ("runId", "GitHub run ID"),
        ("runAttempt", "GitHub run attempt"),
    ):
        value = identity[field]
        if not value.isdigit() or value.startswith("0"):
            raise TrustInvalid(f"{label} 无效")
    return identity


def _github_proof(
    format_name: str,
    payload: dict[str, Any],
    *,
    github_run_json: Path,
    artifact_name: str,
) -> dict[str, Any]:
    if artifact_name != GITHUB_ARTIFACT_NAMES[format_name]:
        raise TrustInvalid("GitHub attestation artifact 名称无效")
    run = _load_github_run(github_run_json)
    identity = _github_run_identity(format_name, payload, run)
    values = {
        "artifactName": artifact_name,
        "kind": "github-actions-run",
        "runIdentity": identity,
        "runIdentitySha256": _sha256(_canonical(identity)),
        "subjectSha256": _sha256(_unsigned_payload(format_name, payload)),
    }
    return values


def build_attestation(
    format_name: str,
    payload: dict[str, Any],
    *,
    signing_private_key: Path | None = None,
    key_id: str | None = None,
    github_run_json: Path | None = None,
    artifact_name: str | None = None,
) -> dict[str, Any]:
    if format_name not in {SSH_FORMAT, BOOTSTRAP_FORMAT}:
        raise TrustInvalid("attestation format 无效")
    signed = signing_private_key is not None or key_id is not None
    github = github_run_json is not None or artifact_name is not None
    if signed == github:
        raise TrustInvalid("必须且只能选择签名或 GitHub run provenance")
    if signed:
        if signing_private_key is None or key_id is None:
            raise TrustInvalid("签名 proof 参数不完整")
        proof = _signed_proof(
            format_name,
            payload,
            signing_private_key=signing_private_key,
            key_id=key_id,
        )
    else:
        if github_run_json is None or artifact_name is None:
            raise TrustInvalid("GitHub proof 参数不完整")
        proof = _github_proof(
            format_name,
            payload,
            github_run_json=github_run_json,
            artifact_name=artifact_name,
        )
    return {"format": format_name, "payload": payload, "proof": proof}


def _verify_proof(
    document: dict[str, Any],
    *,
    trusted_public_key: Path | None,
    expected_key_id: str | None,
    github_run_json: Path | None,
) -> None:
    proof = document["proof"]
    if not isinstance(proof, dict):
        raise TrustInvalid("attestation proof 无效")
    kind = proof.get("kind")
    unsigned = _unsigned_payload(document["format"], document["payload"])
    if kind == "ed25519":
        if set(proof) != {"keyId", "kind", "signature"}:
            raise TrustInvalid("Ed25519 proof 字段无效")
        if trusted_public_key is None or expected_key_id is None:
            raise TrustInvalid("缺少独立 trusted public key/key ID")
        if proof.get("keyId") != expected_key_id:
            raise TrustInvalid("attestation key ID 漂移")
        signature_text = proof.get("signature")
        if not isinstance(signature_text, str) or "=" in signature_text:
            raise TrustInvalid("attestation signature 编码无效")
        try:
            signature = base64.urlsafe_b64decode(signature_text + "=" * (-len(signature_text) % 4))
            if len(signature) != 64:
                raise ValueError("length")
            _load_public_key(trusted_public_key).verify(signature, unsigned)
        except (ValueError, binascii.Error, InvalidSignature) as error:
            raise TrustInvalid("attestation Ed25519 签名无效") from error
        if github_run_json is not None:
            raise TrustInvalid("签名 proof 不接受 GitHub run 自报")
        return
    if kind != "github-actions-run":
        raise TrustInvalid("attestation proof kind 无效")
    expected_keys = {
        "artifactName",
        "kind",
        "runIdentity",
        "runIdentitySha256",
        "subjectSha256",
    }
    if set(proof) != expected_keys or github_run_json is None:
        raise TrustInvalid("GitHub proof 缺少外部 run provenance")
    if proof.get("artifactName") != GITHUB_ARTIFACT_NAMES[document["format"]]:
        raise TrustInvalid("GitHub attestation artifact 名称漂移")
    run = _load_github_run(github_run_json)
    identity = _github_run_identity(document["format"], document["payload"], run)
    expected = {
        "artifactName": proof["artifactName"],
        "kind": "github-actions-run",
        "runIdentity": identity,
        "runIdentitySha256": _sha256(_canonical(identity)),
        "subjectSha256": _sha256(unsigned),
    }
    if proof != expected:
        raise TrustInvalid("GitHub run provenance 与 attestation 不一致")
    if (
        run.get("status") != "completed"
        or run.get("conclusion") != "success"
    ):
        raise TrustInvalid("GitHub run provenance 不是 completed success")
    if trusted_public_key is not None or expected_key_id is not None:
        raise TrustInvalid("GitHub proof 不接受签名参数混用")


def _artifact_filename(format_name: str) -> str:
    return SSH_FILENAME if format_name == SSH_FORMAT else BOOTSTRAP_FILENAME


def create_artifact(output: Path, document: dict[str, Any]) -> str:
    if not output.is_absolute() or os.path.lexists(output):
        raise TrustInvalid("attestation 输出目录必须是尚不存在的绝对路径")
    parent = output.parent.resolve(strict=True)
    if parent.is_symlink() or not parent.is_dir():
        raise TrustInvalid("attestation 输出父目录无效")
    output = parent / output.name
    try:
        output.mkdir(mode=0o700)
    except FileExistsError as error:
        raise TrustInvalid("attestation 输出目录已存在") from error
    os.chmod(output, 0o700)
    try:
        filename = _artifact_filename(str(document["format"]))
        payload = _canonical(document)
        digest = _sha256(payload)
        for name, content in (
            (filename, payload),
            ("SHA256SUMS", f"{digest}  {filename}\n".encode("ascii")),
        ):
            descriptor = os.open(output / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, "wb") as target:
                target.write(content)
                target.flush()
                os.fsync(target.fileno())
        descriptor = os.open(output, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        descriptor = os.open(parent, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        return digest
    except Exception:
        shutil.rmtree(output, ignore_errors=True)
        raise


def load_artifact(directory: Path, expected_sha256: str) -> tuple[dict[str, Any], str]:
    expected = _require_hex(expected_sha256, 64, "expected attestation SHA")
    if not directory.is_absolute() or directory.is_symlink() or not directory.is_dir():
        raise TrustInvalid("attestation artifact 目录无效")
    if stat.S_IMODE(directory.stat().st_mode) != 0o700:
        raise TrustInvalid("attestation artifact 目录权限必须为 0700")
    names = {path.name for path in directory.iterdir()}
    formats = {
        SSH_FILENAME: SSH_FORMAT,
        BOOTSTRAP_FILENAME: BOOTSTRAP_FORMAT,
    }
    candidates = [name for name in formats if name in names]
    if len(candidates) != 1 or names != {candidates[0], "SHA256SUMS"}:
        raise TrustInvalid("attestation artifact 文件白名单无效")
    filename = candidates[0]
    attestation = directory / filename
    checksums = directory / "SHA256SUMS"
    for path in (attestation, checksums):
        if path.is_symlink() or not path.is_file() or stat.S_IMODE(path.stat().st_mode) != 0o600:
            raise TrustInvalid("attestation artifact 文件或权限无效")
    payload = _read_regular(attestation, "attestation artifact")
    digest = _sha256(payload)
    if digest != expected:
        raise TrustInvalid("attestation artifact SHA 不一致")
    try:
        checksum_text = _read_regular(checksums, "attestation SHA256SUMS").decode("ascii")
    except UnicodeError as error:
        raise TrustInvalid("attestation SHA256SUMS 不是 ASCII") from error
    if checksum_text != f"{digest}  {filename}\n":
        raise TrustInvalid("attestation SHA256SUMS 无效")
    document = _decode_json(payload, "attestation")
    if set(document) != {"format", "payload", "proof"}:
        raise TrustInvalid("attestation envelope 字段无效")
    if document.get("format") != formats[filename]:
        raise TrustInvalid("attestation 文件名与 format 不一致")
    if payload != _canonical(document):
        raise TrustInvalid("attestation 不是 canonical JSON")
    return document, digest


def verify_attestation(
    directory: Path,
    expected_sha256: str,
    *,
    expected_repository: str,
    expected_environment: str,
    expected_host: str,
    expected_port: int,
    expected_user: str,
    now: datetime,
    ssh_evidence: SshEvidence | None = None,
    expected_ssh_attestation_sha256: str | None = None,
    trusted_public_key: Path | None = None,
    expected_key_id: str | None = None,
    github_run_json: Path | None = None,
    expected_known_hosts_file: Path | None = None,
) -> tuple[dict[str, Any], str]:
    document, digest = load_artifact(directory, expected_sha256)
    _verify_proof(
        document,
        trusted_public_key=trusted_public_key,
        expected_key_id=expected_key_id,
        github_run_json=github_run_json,
    )
    if document["format"] == SSH_FORMAT:
        if ssh_evidence is None:
            raise TrustInvalid("SSH attestation 缺少完整外部证据")
        validate_ssh_payload(
            document["payload"],
            evidence=ssh_evidence,
            expected_repository=expected_repository,
            expected_environment=expected_environment,
            expected_host=expected_host,
            expected_port=expected_port,
            expected_user=expected_user,
            now=now,
            expected_known_hosts_file=expected_known_hosts_file,
        )
    else:
        if expected_ssh_attestation_sha256 is None:
            raise TrustInvalid("bootstrap 缺少 SSH attestation SHA")
        validate_bootstrap_payload(
            document["payload"],
            expected_repository=expected_repository,
            expected_environment=expected_environment,
            expected_host=expected_host,
            expected_port=expected_port,
            expected_user=expected_user,
            expected_ssh_attestation_sha256=expected_ssh_attestation_sha256,
            now=now,
        )
    return document, digest


def build_bootstrap_state(
    *, state: str, attestation_sha256: str, genesis_receipt_sha256: str | None
) -> dict[str, Any]:
    _require_hex(attestation_sha256, 64, "bootstrap attestation SHA")
    if state not in {"prepared", "installed", "sealed"}:
        raise TrustInvalid("bootstrap state 无效")
    if state == "prepared":
        if genesis_receipt_sha256 is not None:
            raise TrustInvalid("prepared 状态不得预报 genesis receipt SHA")
    else:
        _require_hex(genesis_receipt_sha256, 64, "genesis receipt SHA")
    return {
        "attestationSha256": attestation_sha256,
        "format": BOOTSTRAP_STATE_FORMAT,
        "genesisReceiptSha256": genesis_receipt_sha256,
        "state": state,
    }


def validate_bootstrap_transition(previous: dict[str, Any] | None, current: dict[str, Any]) -> None:
    expected_keys = {
        "attestationSha256",
        "format",
        "genesisReceiptSha256",
        "state",
    }
    _require_exact_keys(current, expected_keys, "bootstrap state")
    normalized = build_bootstrap_state(
        state=str(current["state"]),
        attestation_sha256=str(current["attestationSha256"]),
        genesis_receipt_sha256=current["genesisReceiptSha256"],
    )
    if normalized != current:
        raise TrustInvalid("bootstrap state 规范化漂移")
    if previous is None:
        if current["state"] != "prepared":
            raise TrustInvalid("bootstrap 首个状态必须是 prepared")
        return
    _require_exact_keys(previous, expected_keys, "previous bootstrap state")
    normalized_previous = build_bootstrap_state(
        state=str(previous.get("state")),
        attestation_sha256=str(previous.get("attestationSha256")),
        genesis_receipt_sha256=previous.get("genesisReceiptSha256"),
    )
    if normalized_previous != previous:
        raise TrustInvalid("previous bootstrap state 规范化漂移")
    if previous.get("attestationSha256") != current["attestationSha256"]:
        raise TrustInvalid("bootstrap transition 禁止更换 attestation")
    transitions = {"prepared": "installed", "installed": "sealed"}
    if transitions.get(str(previous.get("state"))) != current["state"]:
        raise TrustInvalid("bootstrap state 只能单向逐步推进")
    previous_receipt = previous.get("genesisReceiptSha256")
    current_receipt = current["genesisReceiptSha256"]
    if previous["state"] == "installed" and previous_receipt != current_receipt:
        raise TrustInvalid("bootstrap sealed 禁止更换 genesis receipt")


def verify_receipt_chain(
    *,
    receipt_root: Path,
    bootstrap_payload: dict[str, Any],
    bootstrap_attestation_sha256: str,
    sealed_state: dict[str, Any],
    max_receipts: int = 1024,
) -> list[str]:
    if (
        not receipt_root.is_absolute()
        or receipt_root.is_symlink()
        or not receipt_root.is_dir()
        or stat.S_IMODE(receipt_root.stat().st_mode) != 0o700
    ):
        raise TrustInvalid("receipt root 必须是 0700 普通目录")
    expected_bootstrap_sha = _require_hex(
        bootstrap_attestation_sha256, 64, "bootstrap attestation SHA"
    )
    validate_bootstrap_transition(
        build_bootstrap_state(
            state="installed",
            attestation_sha256=expected_bootstrap_sha,
            genesis_receipt_sha256=sealed_state.get("genesisReceiptSha256"),
        ),
        sealed_state,
    )
    current_path = receipt_root / "current"
    if (
        current_path.is_symlink()
        or not current_path.is_file()
        or stat.S_IMODE(current_path.stat().st_mode) != 0o600
    ):
        raise TrustInvalid("receipt current 指针无效")
    try:
        current_lines = (
            _read_regular(current_path, "receipt current 指针").decode("ascii").splitlines()
        )
    except UnicodeError as error:
        raise TrustInvalid("receipt current 指针不是 ASCII") from error
    if len(current_lines) != 1:
        raise TrustInvalid("receipt current 指针格式无效")
    cursor = _require_hex(current_lines[0], 64, "current receipt SHA")
    seen: set[str] = set()
    chain: list[str] = []
    genesis_document: dict[str, Any] | None = None
    genesis_sha: str | None = None
    while True:
        if cursor in seen:
            raise TrustInvalid("release receipt 链存在环")
        if len(chain) >= max_receipts:
            raise TrustInvalid("release receipt 链超出有界长度")
        seen.add(cursor)
        chain.append(cursor)
        directory = receipt_root / cursor
        try:
            document, digest = verify_receipt(directory, cursor, allow_genesis=True)
        except ReceiptInvalid as error:
            raise TrustInvalid(f"release receipt 链节点无效：{error}") from error
        if digest != cursor:
            raise TrustInvalid("release receipt 目录名与内容 SHA 不一致")
        previous = document["previousReceiptSha256"]
        if previous is None:
            genesis_document = document
            genesis_sha = cursor
            break
        cursor = _require_hex(previous, 64, "previous receipt SHA")
    if genesis_document != bootstrap_payload.get("genesisReceipt"):
        raise TrustInvalid("receipt 链 genesis 与 bootstrap subject 不一致")
    if sealed_state.get("attestationSha256") != expected_bootstrap_sha:
        raise TrustInvalid("sealed state 未绑定 bootstrap attestation")
    if sealed_state.get("genesisReceiptSha256") != genesis_sha:
        raise TrustInvalid("sealed state 未绑定实际 genesis receipt")
    return chain


def _parse_now(value: str | None) -> datetime:
    if value is None:
        return datetime.now(UTC)
    return _parse_utc(value, "now")


def _evidence_from_arguments(arguments: argparse.Namespace) -> SshEvidence | None:
    bundle = arguments.ssh_evidence_dir
    direct_values = (
        arguments.known_hosts_file,
        arguments.host_public_key_file,
        arguments.authorized_keys_file,
        arguments.execution_public_key_file,
        arguments.upload_public_key_file,
        arguments.broker_executable,
    )
    inventories = (
        arguments.environment_secrets_json,
        arguments.repository_secrets_json,
        arguments.organization_secrets_json,
    )
    if bundle is not None:
        if any(value is not None for value in direct_values) or arguments.retired_public_key_file:
            raise TrustInvalid("SSH evidence bundle 不得与单文件参数混用")
        if any(value is None for value in inventories):
            raise TrustInvalid("SSH evidence bundle 缺少三层 live secret inventory")
        return load_ssh_evidence_bundle(
            bundle,
            environment_secrets=arguments.environment_secrets_json,
            repository_secrets=arguments.repository_secrets_json,
            organization_secrets=arguments.organization_secrets_json,
        )
    values = (
        *direct_values,
        *inventories,
    )
    if all(value is None for value in values) and not arguments.retired_public_key_file:
        return None
    if any(value is None for value in values) or not arguments.retired_public_key_file:
        raise TrustInvalid("SSH 外部证据参数必须完整")
    return SshEvidence(
        known_hosts=arguments.known_hosts_file,
        host_public_key=arguments.host_public_key_file,
        authorized_keys=arguments.authorized_keys_file,
        retired_public_keys=tuple(arguments.retired_public_key_file),
        execution_public_key=arguments.execution_public_key_file,
        upload_public_key=arguments.upload_public_key_file,
        environment_secrets=arguments.environment_secrets_json,
        repository_secrets=arguments.repository_secrets_json,
        organization_secrets=arguments.organization_secrets_json,
        broker_executable=arguments.broker_executable,
    )


def _add_evidence_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--ssh-evidence-dir", type=Path)
    parser.add_argument("--known-hosts-file", type=Path)
    parser.add_argument("--host-public-key-file", type=Path)
    parser.add_argument("--authorized-keys-file", type=Path)
    parser.add_argument("--retired-public-key-file", type=Path, action="append", default=[])
    parser.add_argument("--execution-public-key-file", type=Path)
    parser.add_argument("--upload-public-key-file", type=Path)
    parser.add_argument("--environment-secrets-json", type=Path)
    parser.add_argument("--repository-secrets-json", type=Path)
    parser.add_argument("--organization-secrets-json", type=Path)
    parser.add_argument("--broker-executable", type=Path)


def _add_subject_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--expected-repository", required=True)
    parser.add_argument("--expected-environment", default="production")
    parser.add_argument("--expected-host", required=True)
    parser.add_argument("--expected-port", type=int, required=True)
    parser.add_argument("--expected-user", required=True)
    parser.add_argument("--now")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    actions = parser.add_subparsers(dest="action", required=True)
    normalize = actions.add_parser("normalize-download")
    normalize.add_argument("--directory", type=Path, required=True)
    normalize.add_argument("--kind", choices=tuple(DOWNLOAD_LAYOUTS), required=True)

    create = actions.add_parser("create")
    create.add_argument("--format", choices=(SSH_FORMAT, BOOTSTRAP_FORMAT), required=True)
    create.add_argument("--payload-json", type=Path, required=True)
    create.add_argument("--output-dir", type=Path, required=True)
    create.add_argument("--signing-private-key", type=Path)
    create.add_argument("--key-id")
    create.add_argument("--github-run-json", type=Path)
    create.add_argument("--artifact-name")
    create.add_argument("--expected-ssh-attestation-sha256")
    _add_subject_arguments(create)
    _add_evidence_arguments(create)

    verify = actions.add_parser("verify")
    verify.add_argument("--attestation-dir", type=Path, required=True)
    verify.add_argument("--expected-sha256", required=True)
    verify.add_argument("--trusted-public-key", type=Path)
    verify.add_argument("--expected-key-id")
    verify.add_argument("--github-run-json", type=Path)
    verify.add_argument("--expected-known-hosts-file", type=Path)
    verify.add_argument("--expected-ssh-attestation-sha256")
    _add_subject_arguments(verify)
    _add_evidence_arguments(verify)
    return parser


def _validate_payload_for_arguments(
    format_name: str,
    payload: dict[str, Any],
    arguments: argparse.Namespace,
) -> None:
    if format_name == SSH_FORMAT:
        evidence = _evidence_from_arguments(arguments)
        if evidence is None:
            raise TrustInvalid("SSH attestation 缺少外部证据")
        validate_ssh_payload(
            payload,
            evidence=evidence,
            expected_repository=arguments.expected_repository,
            expected_environment=arguments.expected_environment,
            expected_host=arguments.expected_host,
            expected_port=arguments.expected_port,
            expected_user=arguments.expected_user,
            now=_parse_now(arguments.now),
        )
    else:
        if arguments.expected_ssh_attestation_sha256 is None:
            raise TrustInvalid("bootstrap 缺少 expected SSH attestation SHA")
        validate_bootstrap_payload(
            payload,
            expected_repository=arguments.expected_repository,
            expected_environment=arguments.expected_environment,
            expected_host=arguments.expected_host,
            expected_port=arguments.expected_port,
            expected_user=arguments.expected_user,
            expected_ssh_attestation_sha256=arguments.expected_ssh_attestation_sha256,
            now=_parse_now(arguments.now),
        )


def main() -> int:
    arguments = _parser().parse_args()
    try:
        if arguments.action == "normalize-download":
            normalize_downloaded_directory(arguments.directory, arguments.kind)
            print(f"release-trust-download-normalized:{arguments.kind}")
        elif arguments.action == "create":
            payload = _decode_json(
                _read_regular(arguments.payload_json, "attestation payload JSON"),
                "attestation payload",
            )
            _validate_payload_for_arguments(arguments.format, payload, arguments)
            document = build_attestation(
                arguments.format,
                payload,
                signing_private_key=arguments.signing_private_key,
                key_id=arguments.key_id,
                github_run_json=arguments.github_run_json,
                artifact_name=arguments.artifact_name,
            )
            digest = create_artifact(arguments.output_dir, document)
            print(f"release-attestation-created:{arguments.format}:{digest}")
        else:
            evidence = _evidence_from_arguments(arguments)
            document, digest = verify_attestation(
                arguments.attestation_dir,
                arguments.expected_sha256,
                expected_repository=arguments.expected_repository,
                expected_environment=arguments.expected_environment,
                expected_host=arguments.expected_host,
                expected_port=arguments.expected_port,
                expected_user=arguments.expected_user,
                now=_parse_now(arguments.now),
                ssh_evidence=evidence,
                expected_ssh_attestation_sha256=arguments.expected_ssh_attestation_sha256,
                trusted_public_key=arguments.trusted_public_key,
                expected_key_id=arguments.expected_key_id,
                github_run_json=arguments.github_run_json,
                expected_known_hosts_file=arguments.expected_known_hosts_file,
            )
            print(f"release-attestation-verified:{document['format']}:{digest}")
        return 0
    except TrustInvalid as error:
        print(f"release-trust-error:{error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
