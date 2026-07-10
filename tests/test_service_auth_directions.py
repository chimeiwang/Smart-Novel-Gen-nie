from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from inkforge_agents.service_auth import (
    create_agent_callback_signer,
    create_core_request_verifier,
)
from inkforge_contracts.jwt_claims import ServiceScope
from inkforge_core.service_auth import (
    create_agent_callback_verifier,
    create_core_request_signer,
)
from inkforge_service_auth import RedisReplayStore, canonical_json_body


class DirectionRedis:
    def __init__(self) -> None:
        self.keys: set[str] = set()

    async def set(self, key: str, value: str, *, nx: bool, ex: int) -> bool | None:
        assert value == "1"
        assert nx is True
        assert ex > 0
        if key in self.keys:
            return None
        self.keys.add(key)
        return True


def _write_pair(directory: Path, stem: str, kid: str) -> tuple[Path, Path]:
    private_key = Ed25519PrivateKey.generate()
    private_path = directory / f"{stem}.pem"
    private_path.write_bytes(
        private_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    public_bytes = private_key.public_key().public_bytes(
        serialization.Encoding.Raw,
        serialization.PublicFormat.Raw,
    )
    jwks_path = directory / f"{stem}.jwks.json"
    jwks_path.write_text(
        json.dumps(
            {
                "keys": [
                    {
                        "kty": "OKP",
                        "crv": "Ed25519",
                        "x": base64.urlsafe_b64encode(public_bytes)
                        .rstrip(b"=")
                        .decode("ascii"),
                        "kid": kid,
                        "use": "sig",
                        "alg": "EdDSA",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    return private_path, jwks_path


@pytest.mark.asyncio
async def test_core_to_agent_and_agent_to_core_use_independent_keys(tmp_path: Path) -> None:
    core_private, core_jwks = _write_pair(tmp_path, "core", "core-v1")
    agent_private, agent_jwks = _write_pair(tmp_path, "agent", "agent-v1")
    core_signer = create_core_request_signer(private_key_path=core_private, kid="core-v1")
    agent_verifier = create_core_request_verifier(
        jwks_path=core_jwks,
        replay_store=RedisReplayStore(DirectionRedis()),
    )
    agent_signer = create_agent_callback_signer(
        private_key_path=agent_private,
        kid="agent-v1",
    )
    core_verifier = create_agent_callback_verifier(
        jwks_path=agent_jwks,
        replay_store=RedisReplayStore(DirectionRedis()),
    )

    for signer, verifier, scope, path, idempotency_key in (
        (
            core_signer,
            agent_verifier,
            ServiceScope.AGENT_RUN,
            "/internal/v1/runs",
            "core-idem",
        ),
        (
            agent_signer,
            core_verifier,
            ServiceScope.CALLBACK_CHECKPOINT,
            "/internal/v1/callbacks/checkpoint",
            "agent-idem",
        ),
    ):
        body = canonical_json_body({"direction": idempotency_key})
        signed = signer.sign_request(
            body=body,
            http_method="POST",
            http_path=path,
            idempotency_key=idempotency_key,
            scope=(scope,),
            task_id="task-1",
            run_id="run-1",
            novel_id="novel-1",
            now=1_800_000_000,
        )
        claims = await verifier.verify_request(
            token=signed.token,
            body=body,
            http_method="POST",
            http_path=path,
            idempotency_key=idempotency_key,
            request_timestamp=signed.headers["X-InkForge-Timestamp"],
            body_sha256=signed.headers["X-InkForge-Body-SHA256"],
            required_scope=scope,
            task_id="task-1",
            run_id="run-1",
            novel_id="novel-1",
            now=1_800_000_000,
        )
        assert claims.scope == (scope,)

    assert core_signer.public_key.public_bytes_raw() != agent_signer.public_key.public_bytes_raw()
