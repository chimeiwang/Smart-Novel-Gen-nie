from __future__ import annotations

import argparse
import base64
import json
import os
import subprocess
import tempfile
import uuid
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

GENERATED_FILENAMES = (
    "core-to-agent-private.pem",
    "core-to-agent-jwks.json",
    "agent-to-core-private.pem",
    "agent-to-core-jwks.json",
)


def _base64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _build_pair(prefix: str) -> tuple[bytes, bytes]:
    private_key = Ed25519PrivateKey.generate()
    private_bytes = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_bytes = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    jwks = {
        "keys": [
            {
                "kty": "OKP",
                "crv": "Ed25519",
                "x": _base64url(public_bytes),
                "kid": f"{prefix}-{uuid.uuid4()}",
                "use": "sig",
                "alg": "EdDSA",
            }
        ]
    }
    return private_bytes, json.dumps(jwks, ensure_ascii=False, indent=2).encode("utf-8") + b"\n"


def _restrict_private_key(path: Path) -> None:
    os.chmod(path, 0o600)
    if os.name != "nt":
        return
    user = os.environ.get("USERNAME")
    system_root = os.environ.get("SystemRoot")
    if not user:
        raise RuntimeError("无法确定当前 Windows 用户，私钥权限未收敛")
    if not system_root:
        raise RuntimeError("无法确定 Windows 系统目录，私钥权限未收敛")
    icacls = Path(system_root) / "System32" / "icacls.exe"
    completed = subprocess.run(  # noqa: S603 - 程序路径和参数结构均由本脚本固定
        [
            str(icacls),
            str(path),
            "/inheritance:r",
            "/grant:r",
            f"{user}:(R,W)",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise RuntimeError("无法收敛 Windows 私钥访问控制列表")


def generate_service_keys(output_dir: Path) -> None:
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(exist_ok=False)
    core_private, core_jwks = _build_pair("core")
    agent_private, agent_jwks = _build_pair("agent")
    payloads = {
        "core-to-agent-private.pem": (core_private, True),
        "core-to-agent-jwks.json": (core_jwks, False),
        "agent-to-core-private.pem": (agent_private, True),
        "agent-to-core-jwks.json": (agent_jwks, False),
    }
    temporary_paths: list[Path] = []
    published_paths: list[Path] = []
    try:
        for name, (content, private) in payloads.items():
            descriptor, temporary_name = tempfile.mkstemp(prefix=f".{name}.", dir=output_dir)
            temporary_path = Path(temporary_name)
            temporary_paths.append(temporary_path)
            try:
                with os.fdopen(descriptor, "wb") as handle:
                    handle.write(content)
                    handle.flush()
                    os.fsync(handle.fileno())
                if private:
                    _restrict_private_key(temporary_path)
            except Exception:
                try:
                    os.close(descriptor)
                except OSError:
                    pass
                raise
        for temporary_path, name in zip(temporary_paths, payloads, strict=True):
            destination = output_dir / name
            if destination.exists():
                raise FileExistsError("发布期间发现同名服务密钥文件，拒绝覆盖")
            os.replace(temporary_path, destination)
            published_paths.append(destination)
        temporary_paths.clear()
    except Exception:
        for path in temporary_paths:
            path.unlink(missing_ok=True)
        for path in published_paths:
            path.unlink(missing_ok=True)
        try:
            output_dir.rmdir()
        except OSError:
            pass
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description="生成核心服务与智能体服务的 Ed25519 密钥")
    parser.add_argument("--output-dir", required=True, type=Path, help="密钥输出目录")
    arguments = parser.parse_args()
    try:
        generate_service_keys(arguments.output_dir)
    except (FileExistsError, OSError, RuntimeError) as exc:
        parser.exit(1, f"生成失败：{exc}\n")
    print(f"已生成两套服务密钥：{arguments.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
