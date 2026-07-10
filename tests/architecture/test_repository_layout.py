from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
WORKSPACE_MEMBERS = (
    ("apps/core-api", "src/inkforge_core"),
    ("apps/agent-service", "src/inkforge_agents"),
    ("packages/service-contracts", "src/inkforge_contracts"),
)


@pytest.mark.parametrize("member_path", [member for member, _ in WORKSPACE_MEMBERS])
def test_workspace_member_manifest_exists(member_path: str) -> None:
    manifest = REPOSITORY_ROOT / member_path / "pyproject.toml"

    assert manifest.is_file(), f"Missing workspace member manifest: {manifest}"


@pytest.mark.parametrize(
    ("member_path", "package_path"),
    WORKSPACE_MEMBERS,
)
def test_workspace_member_uses_src_package_layout(
    member_path: str,
    package_path: str,
) -> None:
    package_directory = REPOSITORY_ROOT / member_path / package_path

    assert package_directory.is_dir(), f"Missing src package directory: {package_directory}"
