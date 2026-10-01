#!/usr/bin/env python3
"""生成和核验绑定固定 GHCR 仓库及源码运行的镜像清单。"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path
from typing import Any

REPOSITORY = "chimeiwang/Smart-Novel-Gen-nie"
REGISTRY_PREFIX = "ghcr.io/chimeiwang/smart-novel-gen-nie"
SERVICES = ("web", "core-api", "agent-service")
_SHA = re.compile(r"[0-9a-f]{40}\Z")
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")


def _positive_int(value: object) -> bool:
    return type(value) is int and value > 0


def _unique_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("发布清单包含重复 JSON 键")
        result[key] = value
    return result


def validate_manifest(
    document: object,
    expected_sha: str,
    expected_run_id: int,
    expected_repository: str = REPOSITORY,
) -> dict[str, Any]:
    """按精确字段和当前可信来源校验清单，不接受调用方指定仓库漂移。"""

    if expected_repository != REPOSITORY:
        raise ValueError("发布清单仓库不符合固定约定")
    if not isinstance(expected_sha, str) or not _SHA.fullmatch(expected_sha):
        raise ValueError("发布清单预期源码 SHA 无效")
    if not _positive_int(expected_run_id):
        raise ValueError("发布清单预期运行 ID 无效")
    if type(document) is not dict or set(document) != {
        "schemaVersion",
        "repository",
        "sourceSha",
        "sourceRunId",
        "images",
    }:
        raise ValueError("发布清单顶层字段无效")
    if type(document["schemaVersion"]) is not int or document["schemaVersion"] != 1:
        raise ValueError("发布清单版本无效")
    if document["repository"] != REPOSITORY:
        raise ValueError("发布清单仓库不符合固定约定")
    if document["sourceSha"] != expected_sha:
        raise ValueError("发布清单源码 SHA 不匹配")
    if not _positive_int(document["sourceRunId"]) or document["sourceRunId"] != expected_run_id:
        raise ValueError("发布清单运行 ID 不匹配")
    images = document["images"]
    if type(images) is not dict or set(images) != set(SERVICES):
        raise ValueError("发布清单镜像服务集合无效")
    for service in SERVICES:
        item = images[service]
        if type(item) is not dict or set(item) != {"repository", "digest", "imageId", "sizeBytes"}:
            raise ValueError(f"发布清单 {service} 镜像字段无效")
        if item["repository"] != f"{REGISTRY_PREFIX}/{service}":
            raise ValueError(f"发布清单 {service} 镜像仓库无效")
        if not isinstance(item["digest"], str) or not _DIGEST.fullmatch(item["digest"]):
            raise ValueError(f"发布清单 {service} digest 无效")
        if not isinstance(item["imageId"], str) or not _DIGEST.fullmatch(item["imageId"]):
            raise ValueError(f"发布清单 {service} image ID 无效")
        if not _positive_int(item["sizeBytes"]):
            raise ValueError(f"发布清单 {service} 镜像大小无效")
    return document


def load_manifest(
    path: str | Path,
    expected_sha: str,
    expected_run_id: int,
    expected_repository: str = REPOSITORY,
) -> dict[str, Any]:
    try:
        raw = Path(path).read_text(encoding="utf-8")
        document = json.loads(raw, object_pairs_hook=_unique_keys)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("发布清单文件无法读取或解析") from exc
    return validate_manifest(document, expected_sha, expected_run_id, expected_repository)


def _docker_inspect(reference: str, service: str) -> dict[str, Any]:
    try:
        completed = subprocess.run(  # noqa: S603 - 参数先经固定仓库和摘要校验
            ["docker", "image", "inspect", reference],  # noqa: S607
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
        inspected = json.loads(completed.stdout, object_pairs_hook=_unique_keys)
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError) as exc:
        raise ValueError(f"发布清单 {service} 本地镜像检查失败") from exc
    if not isinstance(inspected, list) or len(inspected) != 1 or not isinstance(inspected[0], dict):
        raise ValueError(f"发布清单 {service} 本地镜像信息无效")
    return inspected[0]


def _image_from_docker(service: str, source_sha: str, digest: str) -> dict[str, object]:
    repository = f"{REGISTRY_PREFIX}/{service}"
    digest_reference = f"{repository}@{digest}"
    try:
        subprocess.run(  # noqa: S603 - 只拉取固定仓库的已校验摘要
            ["docker", "pull", digest_reference],  # noqa: S607
            check=True,
            capture_output=True,
            text=True,
            timeout=900,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise ValueError(f"发布清单 {service} GHCR digest 拉取失败") from exc
    tagged = _docker_inspect(f"{repository}:{source_sha}", service)
    pulled = _docker_inspect(digest_reference, service)
    image_id = tagged.get("Id")
    size = tagged.get("Size")
    repo_digests = pulled.get("RepoDigests")
    if (
        not isinstance(image_id, str)
        or not _DIGEST.fullmatch(image_id)
        or not _positive_int(size)
        or pulled.get("Id") != image_id
        or not isinstance(repo_digests, list)
        or digest_reference not in repo_digests
    ):
        raise ValueError(f"发布清单 {service} 构建镜像与 GHCR digest 不匹配")
    return {"repository": repository, "digest": digest, "imageId": image_id, "sizeBytes": size}


def create_manifest(
    source_sha: str,
    source_run_id: int,
    repository: str,
    digests: dict[str, str],
) -> dict[str, Any]:
    if (
        repository != REPOSITORY
        or not isinstance(source_sha, str)
        or not _SHA.fullmatch(source_sha)
    ):
        raise ValueError("发布清单来源仓库或 SHA 无效")
    if not _positive_int(source_run_id) or set(digests) != set(SERVICES):
        raise ValueError("发布清单来源运行或服务集合无效")
    for service in SERVICES:
        if not isinstance(digests[service], str) or not _DIGEST.fullmatch(digests[service]):
            raise ValueError(f"发布清单 {service} digest 无效")
    document = {
        "schemaVersion": 1,
        "repository": REPOSITORY,
        "sourceSha": source_sha,
        "sourceRunId": source_run_id,
        "images": {
            service: _image_from_docker(service, source_sha, digests[service])
            for service in SERVICES
        },
    }
    return validate_manifest(document, source_sha, source_run_id)


def main() -> int:
    parser = argparse.ArgumentParser(description="创建或校验固定 GHCR 发布清单")
    subcommands = parser.add_subparsers(dest="command", required=True)
    create = subcommands.add_parser("create")
    create.add_argument("--source-sha", required=True)
    create.add_argument("--source-run-id", required=True, type=int)
    create.add_argument("--repository", required=True)
    create.add_argument("--output", required=True)
    for service in SERVICES:
        create.add_argument(f"--{service}-digest", required=True)
    validate = subcommands.add_parser("validate")
    validate.add_argument("--manifest", required=True)
    validate.add_argument("--source-sha", required=True)
    validate.add_argument("--source-run-id", required=True, type=int)
    validate.add_argument("--repository", required=True)
    args = parser.parse_args()
    try:
        if args.command == "create":
            digests = {
                service: getattr(args, service.replace("-", "_") + "_digest")
                for service in SERVICES
            }
            document = create_manifest(
                args.source_sha, args.source_run_id, args.repository, digests
            )
            with Path(args.output).open("x", encoding="utf-8") as output:
                json.dump(document, output, ensure_ascii=False, separators=(",", ":"))
                output.write("\n")
        else:
            load_manifest(args.manifest, args.source_sha, args.source_run_id, args.repository)
    except (ValueError, OSError) as exc:
        parser.exit(1, f"发布清单检查失败：{exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
