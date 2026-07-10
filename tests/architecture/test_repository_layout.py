import tomllib
from collections.abc import Mapping
from pathlib import Path
from typing import cast

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
WORKSPACE_MEMBERS = (
    ("apps/core-api", "src/inkforge_core"),
    ("apps/agent-service", "src/inkforge_agents"),
    ("packages/service-contracts", "src/inkforge_contracts"),
)
EXPECTED_WORKSPACE_MEMBER_PATHS = tuple(member for member, _ in WORKSPACE_MEMBERS)


def read_pyproject(path: Path) -> Mapping[str, object]:
    with path.open("rb") as manifest_file:
        return cast(dict[str, object], tomllib.load(manifest_file))


def require_table(table: Mapping[str, object], key: str) -> Mapping[str, object]:
    value = table.get(key)

    assert isinstance(value, dict), f"缺少 TOML 表：{key}"
    return cast(dict[str, object], value)


def require_string_tuple(table: Mapping[str, object], key: str) -> tuple[str, ...]:
    value = table.get(key)

    assert isinstance(value, list), f"{key} 必须配置为字符串列表"
    assert all(isinstance(item, str) for item in value), f"{key} 只能包含字符串"
    return tuple(cast(list[str], value))


def test_pytest_uses_strict_configuration() -> None:
    root_manifest = read_pyproject(REPOSITORY_ROOT / "pyproject.toml")
    tool_config = require_table(root_manifest, "tool")
    pytest_config = require_table(tool_config, "pytest")
    ini_options = require_table(pytest_config, "ini_options")
    addopts = require_string_tuple(ini_options, "addopts")

    assert "--strict-config" in addopts, "pytest 必须启用 --strict-config"
    assert "--strict-markers" in addopts, "pytest 必须启用 --strict-markers"


def test_root_manifest_declares_exact_workspace_members() -> None:
    root_manifest = read_pyproject(REPOSITORY_ROOT / "pyproject.toml")
    tool_config = require_table(root_manifest, "tool")
    uv_config = require_table(tool_config, "uv")
    workspace_config = require_table(uv_config, "workspace")
    members = require_string_tuple(workspace_config, "members")

    assert members == EXPECTED_WORKSPACE_MEMBER_PATHS, "根工作区成员清单与架构约定不一致"


@pytest.mark.parametrize("member_path", [member for member, _ in WORKSPACE_MEMBERS])
def test_workspace_member_manifest_exists(member_path: str) -> None:
    manifest = REPOSITORY_ROOT / member_path / "pyproject.toml"

    assert manifest.is_file(), f"缺少工作区成员清单：{manifest}"


@pytest.mark.parametrize(
    ("member_path", "package_path"),
    WORKSPACE_MEMBERS,
)
def test_workspace_member_uses_src_package_layout(
    member_path: str,
    package_path: str,
) -> None:
    package_directory = REPOSITORY_ROOT / member_path / package_path

    assert package_directory.is_dir(), f"缺少 src 包目录：{package_directory}"


@pytest.mark.parametrize(
    ("member_path", "package_path"),
    WORKSPACE_MEMBERS,
)
def test_workspace_member_uses_hatchling_build_configuration(
    member_path: str,
    package_path: str,
) -> None:
    member_root = REPOSITORY_ROOT / member_path
    member_manifest = read_pyproject(member_root / "pyproject.toml")
    build_system = require_table(member_manifest, "build-system")

    assert build_system.get("build-backend") == "hatchling.build", (
        f"工作区成员必须使用 hatchling.build：{member_path}"
    )

    tool_config = require_table(member_manifest, "tool")
    hatch_config = require_table(tool_config, "hatch")
    build_config = require_table(hatch_config, "build")
    targets_config = require_table(build_config, "targets")
    wheel_config = require_table(targets_config, "wheel")
    wheel_packages = require_string_tuple(wheel_config, "packages")

    assert wheel_packages == (package_path,), f"wheel 包路径与 src 布局不一致：{member_path}"

    package_initializer = member_root / package_path / "__init__.py"
    assert package_initializer.is_file(), f"缺少包初始化文件：{package_initializer}"
