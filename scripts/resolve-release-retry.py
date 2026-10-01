#!/usr/bin/env python3
"""只读核对原 main 构建并解析其唯一未过期发布清单制品。"""

from __future__ import annotations

import argparse
import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

REPOSITORY = "chimeiwang/Smart-Novel-Gen-nie"
API_ROOT = f"https://api.github.com/repos/{REPOSITORY}"
_SHA = re.compile(r"[0-9a-f]{40}\Z")
_REQUIRED_JOBS = ("ci", "publish-images")
_PARALLEL_CI_JOBS = ("ci-java", "ci-python", "ci-web")


def _positive_int(value: object) -> bool:
    return type(value) is int and value > 0


class GithubReader:
    def __init__(self, token: str) -> None:
        if not token or "\n" in token or "\r" in token:
            raise ValueError("GitHub 读取令牌无效")
        self._token = token

    def get(self, path: str) -> dict[str, Any]:
        if not path.startswith("/") or ".." in path:
            raise ValueError("GitHub API 路径无效")
        request = urllib.request.Request(  # noqa: S310 - API_ROOT 固定为 GitHub HTTPS
            API_ROOT + path,
            headers={
                "Authorization": f"Bearer {self._token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=20) as response:  # noqa: S310
                raw = response.read(4_000_001)
            if len(raw) > 4_000_000:
                raise ValueError("GitHub API 响应过大")
            document = json.loads(raw)
        except (urllib.error.URLError, OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ValueError("GitHub API 读取或解析失败") from exc
        if not isinstance(document, dict):
            raise ValueError("GitHub API 响应格式无效")
        return document


def _paginated(reader: GithubReader, path: str, field: str) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for page in range(1, 1001):
        response = reader.get(f"{path}?per_page=100&page={page}")
        total_count = response.get("total_count")
        items = response.get(field)
        if type(total_count) is not int or total_count < 0 or not isinstance(items, list):
            raise ValueError("GitHub 分页响应格式无效")
        if not all(isinstance(item, dict) for item in items):
            raise ValueError("GitHub 分页项目格式无效")
        results.extend(items)
        if len(results) >= total_count:
            if len(results) != total_count:
                raise ValueError("GitHub 分页数量不一致")
            return results
        if len(items) != 100:
            raise ValueError("GitHub 分页提前结束")
    raise ValueError("GitHub 分页超出安全上限")


def _latest_required_jobs(
    reader: GithubReader, run_id: int, run_attempt: object
) -> dict[str, dict[str, Any]]:
    if type(run_attempt) is not int or not 1 <= run_attempt <= 1000:
        raise ValueError("原构建重跑次数无效")
    latest: dict[str, dict[str, Any]] = {}
    for attempt in range(1, run_attempt + 1):
        jobs = _paginated(reader, f"/actions/runs/{run_id}/attempts/{attempt}/jobs", "jobs")
        for job_name in (*_REQUIRED_JOBS, *_PARALLEL_CI_JOBS):
            matched = [job for job in jobs if job.get("name") == job_name]
            if len(matched) > 1:
                raise ValueError(f"原构建 {job_name} 在同次执行中重复")
            if matched:
                latest[job_name] = matched[0]
    return latest


def resolve_retry(reader: GithubReader, run_id: int) -> dict[str, object]:
    if not _positive_int(run_id):
        raise ValueError("原构建运行 ID 无效")
    run = reader.get(f"/actions/runs/{run_id}")
    source_sha = run.get("head_sha")
    run_repository = run.get("repository")
    head_repository = run.get("head_repository")
    if (
        not _positive_int(run.get("id"))
        or run["id"] != run_id
        or not isinstance(run_repository, dict)
        or run_repository.get("full_name") != REPOSITORY
        or not isinstance(head_repository, dict)
        or head_repository.get("full_name") != REPOSITORY
        or run.get("event") != "push"
        or run.get("head_branch") != "main"
        or run.get("path")
        not in {
            ".github/workflows/build.yml",
            ".github/workflows/build.yml@main",
            ".github/workflows/build.yml@refs/heads/main",
        }
        or not isinstance(source_sha, str)
        or not _SHA.fullmatch(source_sha)
    ):
        raise ValueError("原构建来源不符合 main 发布约定")

    main_ref = reader.get("/git/ref/heads/main")
    ref_object = main_ref.get("object")
    if not isinstance(ref_object, dict) or ref_object.get("sha") != source_sha:
        raise ValueError("原构建源码不是当前 main HEAD")

    jobs = _latest_required_jobs(reader, run_id, run.get("run_attempt"))
    # 历史串行运行只有 ci；出现并行分支后必须核对完整集合，不能让旧汇总成功
    # 掩盖较新一次分支重跑的失败、取消或尚未完成。
    required_jobs = _REQUIRED_JOBS + (
        _PARALLEL_CI_JOBS if any(name in jobs for name in _PARALLEL_CI_JOBS) else ()
    )
    for job_name in required_jobs:
        job = jobs.get(job_name)
        if job is None or job.get("conclusion") != "success":
            raise ValueError(f"原构建 {job_name} 未唯一成功")

    artifacts = _paginated(reader, f"/actions/runs/{run_id}/artifacts", "artifacts")
    artifact_name = f"inkforge-release-{source_sha}-{run_id}"
    matched_artifacts = [item for item in artifacts if item.get("name") == artifact_name]
    if len(matched_artifacts) != 1:
        raise ValueError("原构建发布清单制品不唯一或不存在")
    artifact = matched_artifacts[0]
    if not _positive_int(artifact.get("id")) or artifact.get("expired") is not False:
        raise ValueError("原构建发布清单制品已过期或标识无效")
    workflow_run = artifact.get("workflow_run")
    if workflow_run is not None and (
        not isinstance(workflow_run, dict)
        or not _positive_int(workflow_run.get("id"))
        or workflow_run["id"] != run_id
    ):
        raise ValueError("原构建发布清单制品来源不匹配")
    return {"sourceSha": source_sha, "sourceRunId": run_id, "artifactId": artifact["id"]}


def main() -> int:
    parser = argparse.ArgumentParser(description="解析可独立重试的发布运行")
    parser.add_argument("--run-id", required=True, type=int)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    try:
        token = os.environ.get("GITHUB_TOKEN", "")
        github_output = os.environ.get("GITHUB_OUTPUT", "")
        if not github_output:
            raise ValueError("GitHub Actions 输出路径缺失")
        result = resolve_retry(GithubReader(token), args.run_id)
        with Path(args.output).open("x", encoding="utf-8") as output:
            json.dump(result, output, ensure_ascii=False, separators=(",", ":"))
            output.write("\n")
        with Path(github_output).open("a", encoding="utf-8") as output:
            output.write(f"source-sha={result['sourceSha']}\n")
            output.write(f"source-run-id={result['sourceRunId']}\n")
            output.write(f"artifact-id={result['artifactId']}\n")
    except (ValueError, OSError) as exc:
        parser.exit(1, f"独立重试解析失败：{exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
