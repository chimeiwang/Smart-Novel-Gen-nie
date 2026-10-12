"""用 Java 实际序列化请求验证 Python 严格执行契约。"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
from copy import deepcopy
from datetime import datetime
from pathlib import Path

from inkforge_contracts.execution import (
    EvidenceItem,
    EvidenceManifest,
    EvidenceManifestItem,
    ExecutionStepRequest,
    canonical_execution_json_bytes,
)
from pydantic import ValidationError

ROOT = Path(__file__).parents[2]
JAVA_TEST = (
    "JooqWorkflowDispatchRepositoryTest#"
    "输出AnswerQuestion实际ExecutionStepRequest跨语言临时Fixture"
)


def _safe_errors(error: ValidationError) -> list[dict[str, object]]:
    return [
        {"loc": list(item["loc"]), "type": item["type"]}
        for item in error.errors(include_url=False, include_context=False, include_input=False)
    ]


def _sha256(value: object) -> str:
    return hashlib.sha256(canonical_execution_json_bytes(value)).hexdigest()


def _without_none(value: object) -> object:
    if isinstance(value, dict):
        return {key: _without_none(item) for key, item in value.items() if item is not None}
    if isinstance(value, list):
        return [_without_none(item) for item in value]
    return value


def _java_offset_datetime_text(value: str) -> str:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    result = parsed.strftime("%Y-%m-%dT%H:%M")
    if parsed.second or parsed.microsecond:
        result += f":{parsed.second:02d}"
    if parsed.microsecond:
        result += f".{parsed.microsecond:06d}".rstrip("0")
    offset = parsed.utcoffset()
    if offset is None:
        raise ValueError("协议时间缺少 UTC offset")
    seconds = int(offset.total_seconds())
    if seconds == 0:
        return result + "Z"
    sign = "+" if seconds >= 0 else "-"
    absolute = abs(seconds)
    hours, remainder = divmod(absolute, 3600)
    minutes, trailing_seconds = divmod(remainder, 60)
    suffix = f"{sign}{hours:02d}:{minutes:02d}"
    if trailing_seconds:
        suffix += f":{trailing_seconds:02d}"
    return result + suffix


def _safe_evidence_diagnostics(body: bytes) -> dict[str, object]:
    raw = json.loads(body)
    bundle = raw["evidenceBundle"]
    manifest = EvidenceManifest.model_validate(bundle["manifest"])
    items = [EvidenceItem.model_validate(item) for item in bundle["items"]]
    expected_items = [
        EvidenceManifestItem(
            itemId=item.id,
            ordinal=item.ordinal,
            resourceType=item.resourceType,
            resourceId=item.resourceId,
            exists=item.exists,
            resourceRevision=item.resourceRevision,
            resourceUpdatedAt=item.resourceUpdatedAt,
            contentType=item.contentType,
            contentSha256=item.contentSha256,
            byteCount=item.byteCount,
            range=item.range,
            metadata=item.metadata,
        )
        for item in items
    ]
    normalized = manifest.model_dump(mode="json", by_alias=True, exclude_none=True)
    java_text_shape = deepcopy(normalized)
    for item in java_text_shape["items"]:
        timestamp = item.get("resourceUpdatedAt")
        if isinstance(timestamp, str):
            item["resourceUpdatedAt"] = _java_offset_datetime_text(timestamp)
    return {
        "validatorBranch": "EvidenceBundle.manifestSha256",
        "bundleBindingMatches": (
            manifest.bundleId == bundle["id"]
            and manifest.bundleVersion == bundle["version"]
        ),
        "manifestItemsMatch": manifest.items == expected_items,
        "totalBytesMatch": bundle["totalBytes"]
        == sum(item.byteCount for item in items),
        "storedManifestSha256": bundle["manifestSha256"],
        "rawWireManifestSha256": _sha256(_without_none(bundle["manifest"])),
        "pythonNormalizedManifestSha256": _sha256(normalized),
        "javaShortTimestampReproductionSha256": _sha256(java_text_shape),
        "storedMatchesJavaShortTimestampReproduction": (
            bundle["manifestSha256"] == _sha256(java_text_shape)
        ),
    }


def _maven_environment() -> dict[str, str]:
    environment = dict(os.environ)
    brew_java = Path("/opt/homebrew/opt/openjdk@21/libexec/openjdk.jdk/Contents/Home")
    if brew_java.is_dir():
        environment["JAVA_HOME"] = str(brew_java)
        environment["PATH"] = f"/opt/homebrew/opt/openjdk@21/bin:{environment['PATH']}"
    return environment


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="inkforge-execution-wire-") as directory:
        fixture = Path(directory) / "execution-step-request.json"
        completed = subprocess.run(  # noqa: S603 - 固定仓库 Maven Wrapper argv
            [
                str(ROOT / "mvnw"),
                "-pl",
                "apps/core-api-java",
                "-am",
                f"-Dtest={JAVA_TEST}",
                "-Dsurefire.failIfNoSpecifiedTests=false",
                f"-Dinkforge.execution.fixture.path={fixture}",
                "--no-transfer-progress",
                "test",
            ],
            cwd=ROOT,
            env=_maven_environment(),
            check=False,
        )
        if completed.returncode != 0 or not fixture.is_file():
            print(
                json.dumps(
                    {
                        "status": "java_fixture_failed",
                        "mavenExitCode": completed.returncode,
                        "fixtureCreated": fixture.is_file(),
                    },
                    ensure_ascii=False,
                )
            )
            return 1
        body = fixture.read_bytes()
        try:
            request = ExecutionStepRequest.model_validate_json(body)
        except ValidationError as error:
            print(
                json.dumps(
                    {
                        "status": "python_validation_failed",
                        "bodySha256": hashlib.sha256(body).hexdigest(),
                        "errors": _safe_errors(error),
                        "evidenceDiagnostics": _safe_evidence_diagnostics(body),
                    },
                    ensure_ascii=False,
                )
            )
            return 1
        print(
            json.dumps(
                {
                    "status": "passed",
                    "bodySha256": hashlib.sha256(body).hexdigest(),
                    "requestHash": request.requestHash,
                    "operation": request.operation,
                    "evidenceItemCount": len(request.evidenceBundle.items),
                },
                ensure_ascii=False,
            )
        )
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
