from __future__ import annotations

import json
import os
import runpy
import stat
import subprocess
import sys
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization

GENERATED_FILENAMES = (
    "core-to-agent-private.pem",
    "core-to-agent-jwks.json",
    "agent-to-core-private.pem",
    "agent-to-core-jwks.json",
)


def _run_script(output_dir: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603
        [sys.executable, "scripts/generate_service_keys.py", "--output-dir", str(output_dir)],
        check=False,
        capture_output=True,
        text=True,
    )


def test_script_generates_two_pkcs8_private_keys_and_public_jwks(tmp_path: Path) -> None:
    output_dir = tmp_path / "keys"
    result = _run_script(output_dir)
    assert result.returncode == 0, result.stderr
    assert set(path.name for path in output_dir.iterdir()) == set(GENERATED_FILENAMES)

    for private_name in ("core-to-agent-private.pem", "agent-to-core-private.pem"):
        private_bytes = (output_dir / private_name).read_bytes()
        key = serialization.load_pem_private_key(private_bytes, password=None)
        assert key is not None
        if os.name != "nt":
            assert stat.S_IMODE((output_dir / private_name).stat().st_mode) == 0o600

    for jwks_name in ("core-to-agent-jwks.json", "agent-to-core-jwks.json"):
        jwks = json.loads((output_dir / jwks_name).read_text(encoding="utf-8"))
        assert len(jwks["keys"]) == 1
        assert jwks["keys"][0]["alg"] == "EdDSA"
        assert "d" not in jwks["keys"][0]

    core_jwks = json.loads(
        (output_dir / "core-to-agent-jwks.json").read_text(encoding="utf-8")
    )
    agent_jwks = json.loads(
        (output_dir / "agent-to-core-jwks.json").read_text(encoding="utf-8")
    )
    assert core_jwks["keys"][0]["kid"] == "core-api-v1"
    assert agent_jwks["keys"][0]["kid"] == "agent-service-v1"


def test_script_refuses_to_overwrite_and_output_never_contains_private_material(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "keys"
    first = _run_script(output_dir)
    before = {path.name: path.read_bytes() for path in output_dir.iterdir()}
    second = _run_script(output_dir)
    after = {path.name: path.read_bytes() for path in output_dir.iterdir()}

    assert first.returncode == 0
    assert second.returncode != 0
    assert before == after
    combined_output = first.stdout + first.stderr + second.stdout + second.stderr
    assert "PRIVATE KEY" not in combined_output
    assert not any(
        value.decode("ascii", errors="ignore") in combined_output for value in before.values()
    )


def test_generation_failure_never_publishes_a_partial_key_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_dir = tmp_path / "keys"
    namespace = runpy.run_path("scripts/generate_service_keys.py")
    generate_service_keys = namespace["generate_service_keys"]

    def fail_permission_restriction(path: Path) -> None:
        raise RuntimeError("模拟权限收敛失败")

    monkeypatch.setitem(
        generate_service_keys.__globals__,
        "_restrict_private_key",
        fail_permission_restriction,
    )
    with pytest.raises(RuntimeError, match="模拟权限收敛失败"):
        generate_service_keys(output_dir)

    assert not output_dir.exists()
    assert not list(tmp_path.glob(".keys.*"))
