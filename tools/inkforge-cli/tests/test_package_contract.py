from pathlib import Path


def test_cli_package_declares_inkforge_entrypoint() -> None:
    package_root = Path(__file__).parents[1]
    pyproject = package_root / "pyproject.toml"

    assert pyproject.exists()
    assert 'inkforge = "inkforge_cli.cli:main"' in pyproject.read_text(encoding="utf-8")
