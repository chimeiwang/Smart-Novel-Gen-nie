from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PYTHON_CLI_SOURCE = ROOT / "tools" / "inkforge-cli" / "src"
CONTRACT = ROOT / "contracts" / "cli" / "command-registry.json"


def _document() -> dict[str, Any]:
    sys.path.insert(0, str(PYTHON_CLI_SOURCE))
    from inkforge_cli.registry import get_command_registry

    commands: list[dict[str, Any]] = []
    for spec in get_command_registry().values():
        commands.append(
            {
                "name": spec.name,
                "pythonHandler": (
                    f"{spec.handler.__module__}:{spec.handler.__qualname__}"
                ),
                "inputMode": spec.inputMode,
                "outputMode": spec.outputMode,
                "fileOutput": {
                    "kind": spec.fileOutput.kind,
                    "field": spec.fileOutput.field,
                    "mediaType": spec.fileOutput.media_type,
                },
                "mutation": spec.mutation,
                "requiresIdentity": spec.requiresIdentity,
                "requiresClientRequestId": spec.requiresClientRequestId,
            }
        )
    return {
        "schemaVersion": "inkforge-cli-command-registry/1.0",
        "source": "tools/inkforge-cli/src/inkforge_cli/registry.py",
        "commands": commands,
    }


def _bytes(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="导出 Java CLI 迁移命令基线")
    parser.add_argument("--check", action="store_true")
    arguments = parser.parse_args()
    expected = _bytes(_document())
    if arguments.check:
        if not CONTRACT.is_file() or CONTRACT.read_bytes() != expected:
            print("CLI 命令基线与当前 Python registry 不一致")
            return 1
        return 0
    CONTRACT.parent.mkdir(parents=True, exist_ok=True)
    CONTRACT.write_bytes(expected)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
