from __future__ import annotations

import argparse
import json
from pathlib import Path

from inkforge_core.app import create_app


def main() -> None:
    parser = argparse.ArgumentParser(description="导出 Core API OpenAPI 契约")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    target = Path(args.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(create_app(testing=True).openapi(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
