from __future__ import annotations

from pathlib import Path

import pytest
from inkforge_agents.service_auth import (
    create_agent_callback_signer,
    create_core_request_verifier,
)
from inkforge_service_auth import ServiceAuthenticationError


def test_agent_exposes_only_fixed_direction_factories(tmp_path: Path) -> None:
    with pytest.raises(ServiceAuthenticationError):
        create_agent_callback_signer(
            private_key_path=tmp_path / "missing.pem",
            kid="agent-v1",
        )
    with pytest.raises(ServiceAuthenticationError):
        create_core_request_verifier(
            jwks_path=tmp_path / "missing.jwks.json",
            replay_store=object(),
        )


def test_agent_module_does_not_expose_database_or_reverse_direction_factories() -> None:
    import inkforge_agents.service_auth as service_auth

    assert not hasattr(service_auth, "DATABASE_URL")
    assert not hasattr(service_auth, "create_core_request_signer")
