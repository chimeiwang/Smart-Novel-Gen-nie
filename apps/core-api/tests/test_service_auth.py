from __future__ import annotations

from pathlib import Path

import pytest
from inkforge_core.service_auth import (
    create_agent_callback_verifier,
    create_core_request_signer,
)
from inkforge_service_auth import ServiceAuthenticationError


def test_core_exposes_only_fixed_direction_factories(tmp_path: Path) -> None:
    with pytest.raises(ServiceAuthenticationError):
        create_core_request_signer(
            private_key_path=tmp_path / "missing.pem",
            kid="core-v1",
        )
    with pytest.raises(ServiceAuthenticationError):
        create_agent_callback_verifier(
            jwks_path=tmp_path / "missing.jwks.json",
            replay_store=object(),
        )


def test_core_module_does_not_expose_browser_or_reverse_direction_factories() -> None:
    import inkforge_core.service_auth as service_auth

    assert not hasattr(service_auth, "create_browser_signer")
    assert not hasattr(service_auth, "create_agent_request_signer")
