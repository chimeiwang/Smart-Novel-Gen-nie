#!/bin/sh
set -eu

: "${DATABASE_URL:?必须设置 DATABASE_URL}"
expected="apps/core-api/src/inkforge_core/db/schema-contract.json"
temporary="$(mktemp)"
trap 'rm -f "$temporary"' EXIT
rm -f "$temporary"

uv run python scripts/export_schema_contract.py --database-url "$DATABASE_URL" --output "$temporary"
uv run python - "$expected" "$temporary" <<'PY'
import json
import sys
from pathlib import Path

expected = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
actual = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
if expected["fingerprint"] != actual["fingerprint"]:
    raise SystemExit("数据库结构指纹不一致")
print(f"数据库结构指纹一致：{actual['fingerprint']}")
PY
