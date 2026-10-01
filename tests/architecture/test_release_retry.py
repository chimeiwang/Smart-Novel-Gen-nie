from __future__ import annotations

import importlib.util
import urllib.error
from copy import deepcopy
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _module() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "resolve_release_retry", ROOT / "scripts" / "resolve-release-retry.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


retry = _module()
SHA = "a" * 40
RUN_ID = 123


class Reader:
    def __init__(self) -> None:
        self.pages: dict[str, dict[str, object]] = {
            f"/actions/runs/{RUN_ID}": {
                "id": RUN_ID,
                "repository": {"full_name": retry.REPOSITORY},
                "head_repository": {"full_name": retry.REPOSITORY},
                "event": "push",
                "head_branch": "main",
                "path": ".github/workflows/build.yml@refs/heads/main",
                "head_sha": SHA,
                "run_attempt": 1,
                "conclusion": "failure",
            },
            "/git/ref/heads/main": {"object": {"sha": SHA}},
            f"/actions/runs/{RUN_ID}/attempts/1/jobs?per_page=100&page=1": {
                "total_count": 3,
                "jobs": [
                    {"name": "ci", "conclusion": "success"},
                    {"name": "publish-images", "conclusion": "success"},
                    {"name": "deploy", "conclusion": "failure"},
                ],
            },
            f"/actions/runs/{RUN_ID}/artifacts?per_page=100&page=1": {
                "total_count": 1,
                "artifacts": [
                    {
                        "name": f"inkforge-release-{SHA}-{RUN_ID}",
                        "id": 456,
                        "expired": False,
                        "workflow_run": {"id": RUN_ID},
                    }
                ],
            },
        }
        self.calls: list[str] = []

    def get(self, path: str) -> dict[str, object]:
        self.calls.append(path)
        return deepcopy(self.pages[path])


def test_原部署失败仍可解析唯一已验证制品() -> None:
    reader = Reader()
    assert retry.resolve_retry(reader, RUN_ID) == {
        "sourceSha": SHA,
        "sourceRunId": RUN_ID,
        "artifactId": 456,
    }
    assert "/git/ref/heads/main" in reader.calls


def _parallel_reader() -> Reader:
    reader = Reader()
    page = reader.pages[f"/actions/runs/{RUN_ID}/attempts/1/jobs?per_page=100&page=1"]
    page["jobs"].extend({"name": name, "conclusion": "success"}
                        for name in ("ci-java", "ci-python", "ci-web"))
    page["total_count"] = len(page["jobs"])
    return reader


def test_并行验证和稳定汇总均成功才允许发布重试() -> None:
    assert retry.resolve_retry(_parallel_reader(), RUN_ID)["artifactId"] == 456


@pytest.mark.parametrize("job_name", ["ci-java", "ci-python", "ci-web"])
@pytest.mark.parametrize("conclusion", ["failure", "cancelled", "skipped", None])
def test_旧汇总成功不能掩盖并行分支重跑未成功(job_name, conclusion) -> None:
    reader = _parallel_reader()
    reader.pages[f"/actions/runs/{RUN_ID}"]["run_attempt"] = 2
    reader.pages[f"/actions/runs/{RUN_ID}/attempts/2/jobs?per_page=100&page=1"] = {
        "total_count": 1, "jobs": [{"name": job_name, "conclusion": conclusion}],
    }
    with pytest.raises(ValueError, match=job_name):
        retry.resolve_retry(reader, RUN_ID)


@pytest.mark.parametrize("mutation", ["missing", "duplicate"])
def test_并行验证集合缺失或重复时拒绝发布(mutation) -> None:
    reader = _parallel_reader()
    page = reader.pages[f"/actions/runs/{RUN_ID}/attempts/1/jobs?per_page=100&page=1"]
    if mutation == "missing":
        page["jobs"] = [job for job in page["jobs"] if job["name"] != "ci-python"]
    else:
        page["jobs"].append({"name": "ci-python", "conclusion": "success"})
    page["total_count"] = len(page["jobs"])
    with pytest.raises(ValueError, match="ci-python"):
        retry.resolve_retry(reader, RUN_ID)


def test_并行运行仅重跑部署仍复用三个已成功分支() -> None:
    reader = _parallel_reader()
    reader.pages[f"/actions/runs/{RUN_ID}"]["run_attempt"] = 2
    reader.pages[f"/actions/runs/{RUN_ID}/attempts/2/jobs?per_page=100&page=1"] = {
        "total_count": 1, "jobs": [{"name": "deploy", "conclusion": "failure"}],
    }
    assert retry.resolve_retry(reader, RUN_ID)["artifactId"] == 456


def test_接受_github_官方示例使用的_main_工作流路径格式() -> None:
    reader = Reader()
    reader.pages[f"/actions/runs/{RUN_ID}"]["path"] = ".github/workflows/build.yml@main"
    assert retry.resolve_retry(reader, RUN_ID)["sourceSha"] == SHA


@pytest.mark.parametrize(
    "field,value",
    [
        ("event", "workflow_dispatch"),
        ("head_branch", "feature"),
        ("path", ".github/workflows/other.yml@refs/heads/main"),
        ("head_sha", "b" * 40),
        ("id", True),
    ],
)
def test_错误运行来源或过期主线被拒绝(field: str, value: object) -> None:
    reader = Reader()
    reader.pages[f"/actions/runs/{RUN_ID}"][field] = value
    with pytest.raises(ValueError):
        retry.resolve_retry(reader, RUN_ID)


def test_原_ci_或发布任务失败不能重试() -> None:
    for job_name in ("ci", "publish-images"):
        reader = Reader()
        jobs = reader.pages[f"/actions/runs/{RUN_ID}/attempts/1/jobs?per_page=100&page=1"]["jobs"]
        next(job for job in jobs if job["name"] == job_name)["conclusion"] = "failure"
        with pytest.raises(ValueError, match=job_name):
            retry.resolve_retry(reader, RUN_ID)


def test_只重跑失败部署时沿用最近实际执行的成功依赖任务() -> None:
    reader = Reader()
    reader.pages[f"/actions/runs/{RUN_ID}"]["run_attempt"] = 2
    reader.pages[f"/actions/runs/{RUN_ID}/attempts/2/jobs?per_page=100&page=1"] = {
        "total_count": 1,
        "jobs": [{"name": "deploy", "conclusion": "failure"}],
    }

    assert retry.resolve_retry(reader, RUN_ID)["artifactId"] == 456
    assert f"/actions/runs/{RUN_ID}/attempts/1/jobs?per_page=100&page=1" in reader.calls
    assert f"/actions/runs/{RUN_ID}/attempts/2/jobs?per_page=100&page=1" in reader.calls


@pytest.mark.parametrize("job_name", ["ci", "publish-images"])
def test_更新一次重跑的必需任务失败覆盖旧成功(job_name: str) -> None:
    reader = Reader()
    reader.pages[f"/actions/runs/{RUN_ID}"]["run_attempt"] = 2
    reader.pages[f"/actions/runs/{RUN_ID}/attempts/2/jobs?per_page=100&page=1"] = {
        "total_count": 1,
        "jobs": [{"name": job_name, "conclusion": "failure"}],
    }

    with pytest.raises(ValueError, match=job_name):
        retry.resolve_retry(reader, RUN_ID)


def test_同次执行重复必需_job_与布尔重跑次数被拒绝() -> None:
    reader = Reader()
    first = f"/actions/runs/{RUN_ID}/attempts/1/jobs?per_page=100&page=1"
    reader.pages[first]["jobs"].append({"name": "ci", "conclusion": "success"})
    reader.pages[first]["total_count"] = 4
    with pytest.raises(ValueError, match="重复"):
        retry.resolve_retry(reader, RUN_ID)

    reader = Reader()
    reader.pages[f"/actions/runs/{RUN_ID}"]["run_attempt"] = True
    with pytest.raises(ValueError, match="重跑次数"):
        retry.resolve_retry(reader, RUN_ID)


def test_制品过期重复或伪造运行均被拒绝() -> None:
    path = f"/actions/runs/{RUN_ID}/artifacts?per_page=100&page=1"
    for mutation in ("expired", "duplicate", "wrong_run", "boolean_id"):
        reader = Reader()
        page = reader.pages[path]
        artifact = page["artifacts"][0]
        if mutation == "expired":
            artifact["expired"] = True
        elif mutation == "duplicate":
            page["artifacts"].append(deepcopy(artifact))
            page["total_count"] = 2
        elif mutation == "wrong_run":
            artifact["workflow_run"] = {"id": 999}
        else:
            artifact["id"] = True
        with pytest.raises(ValueError):
            retry.resolve_retry(reader, RUN_ID)


def test_分页后仍检查全部任务和全部同名制品() -> None:
    reader = Reader()
    jobs_path = f"/actions/runs/{RUN_ID}/attempts/1/jobs?per_page=100&page=1"
    existing_jobs = reader.pages[jobs_path]["jobs"]
    reader.pages[jobs_path] = {
        "total_count": 101,
        "jobs": [{"name": f"other-{index}", "conclusion": "success"} for index in range(100)],
    }
    reader.pages[f"/actions/runs/{RUN_ID}/attempts/1/jobs?per_page=100&page=2"] = {
        "total_count": 101,
        "jobs": [{"name": "ci", "conclusion": "success"}],
    }
    with pytest.raises(ValueError, match="publish-images"):
        retry.resolve_retry(reader, RUN_ID)
    assert existing_jobs


def test_第二页同名制品不能绕过唯一性检查() -> None:
    reader = Reader()
    first = f"/actions/runs/{RUN_ID}/artifacts?per_page=100&page=1"
    second = f"/actions/runs/{RUN_ID}/artifacts?per_page=100&page=2"
    original = reader.pages[first]["artifacts"][0]
    reader.pages[first] = {
        "total_count": 101,
        "artifacts": [
            {"name": f"other-{index}", "id": index + 1, "expired": False} for index in range(99)
        ]
        + [original],
    }
    reader.pages[second] = {"total_count": 101, "artifacts": [deepcopy(original)]}

    with pytest.raises(ValueError, match="不唯一"):
        retry.resolve_retry(reader, RUN_ID)


def test_github_http_错误不暴露令牌或响应(monkeypatch: pytest.MonkeyPatch) -> None:
    token = "fake-sensitive-token"  # noqa: S105 - 测试用虚构标记

    def fail_request(*args: object, **kwargs: object) -> object:
        del args, kwargs
        raise urllib.error.HTTPError("https://api.github.com", 403, token, None, None)

    monkeypatch.setattr(retry.urllib.request, "urlopen", fail_request)
    with pytest.raises(ValueError) as failure:
        retry.GithubReader(token).get(f"/actions/runs/{RUN_ID}")
    assert token not in str(failure.value)


def test_布尔运行_id_被拒绝() -> None:
    with pytest.raises(ValueError, match="运行 ID"):
        retry.resolve_retry(Reader(), True)
