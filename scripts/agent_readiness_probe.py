from __future__ import annotations

import io
import json
import sys
import urllib.error
import urllib.request
from typing import Any
from urllib.parse import urlsplit

DIAGNOSTIC_FIELDS = ("status", "checks", "backgroundTasks")
DIAGNOSTIC_PREFIX = "INKFORGE_AGENT_READINESS_DIAGNOSTIC="
HTTP_STATUS_PREFIX = "INKFORGE_AGENT_READINESS_HTTP_STATUS="


def _write_http_status(status_code: int) -> None:
    sys.stderr.write(f"{HTTP_STATUS_PREFIX}{status_code}\n")


def _write_diagnostic(payload: Any, status_code: int) -> None:
    if not isinstance(payload, dict):
        _write_http_status(status_code)
        return

    diagnostic = {key: payload[key] for key in DIAGNOSTIC_FIELDS if key in payload}
    sys.stderr.write(
        DIAGNOSTIC_PREFIX + json.dumps(diagnostic, ensure_ascii=False) + "\n"
    )


def main() -> int:
    if isinstance(sys.stderr, io.TextIOWrapper):
        sys.stderr.reconfigure(encoding="utf-8")

    if len(sys.argv) != 2:
        print("必须且只能提供一个就绪检查 URL", file=sys.stderr)
        return 2

    url = sys.argv[1]
    if urlsplit(url).scheme not in {"http", "https"}:
        print("就绪检查 URL 必须使用 http 或 https", file=sys.stderr)
        return 2

    try:
        response = urllib.request.urlopen(url, timeout=3)  # noqa: S310 - 已限制为 HTTP(S)
    except urllib.error.HTTPError as error:
        with error:
            status_code = error.code
            try:
                payload = json.load(error)
            except (json.JSONDecodeError, UnicodeDecodeError):
                _write_http_status(status_code)
            else:
                _write_diagnostic(payload, status_code)
        return 1

    with response:
        status_code = response.getcode()
        try:
            payload = json.load(response)
        except (json.JSONDecodeError, UnicodeDecodeError):
            _write_http_status(status_code)
            return 1

    if (
        status_code == 200
        and isinstance(payload, dict)
        and payload.get("status") == "ready"
    ):
        return 0

    _write_diagnostic(payload, status_code)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
