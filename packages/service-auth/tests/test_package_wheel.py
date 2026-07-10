from __future__ import annotations

import zipfile
from pathlib import Path

from hatchling.builders.wheel import WheelBuilder

PACKAGE_ROOT = Path(__file__).resolve().parents[1]


def test_service_auth_wheel_contains_type_marker(tmp_path: Path) -> None:
    builder = WheelBuilder(str(PACKAGE_ROOT))
    wheel_name = next(builder.build(directory=str(tmp_path), versions=["standard"]))
    wheel_path = tmp_path / wheel_name

    with zipfile.ZipFile(wheel_path) as wheel:
        names = set(wheel.namelist())

    assert "inkforge_service_auth/__init__.py" in names
    assert "inkforge_service_auth/service_auth.py" in names
    assert "inkforge_service_auth/py.typed" in names
