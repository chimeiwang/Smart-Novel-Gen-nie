from __future__ import annotations

from pathlib import Path

from inkforge_service_auth import (
    ReplayPolicy,
    ReplayStore,
    ServiceTokenSigner,
    ServiceTokenVerifier,
)


def create_core_request_signer(
    *,
    private_key_path: str | Path,
    kid: str,
) -> ServiceTokenSigner:
    return ServiceTokenSigner.from_pkcs8_file(
        private_key_path,
        issuer="core-api",
        subject="core-api",
        audience="agent-service",
        kid=kid,
    )


def create_agent_callback_verifier(
    *,
    jwks_path: str | Path,
    replay_store: ReplayStore,
    replay_policy: ReplayPolicy = ReplayPolicy.ALL_SCOPES,
) -> ServiceTokenVerifier:
    return ServiceTokenVerifier.from_jwks_file(
        jwks_path,
        expected_issuer="agent-service",
        expected_subject="agent-service",
        audience="core-api",
        replay_store=replay_store,
        replay_policy=replay_policy,
    )
