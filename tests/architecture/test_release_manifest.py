from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _module() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "release_manifest", ROOT / "scripts" / "release_manifest.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


release = _module()
SHA = "a" * 40
DIGESTS = {
    service: f"sha256:{str(index) * 64}"
    for index, service in enumerate(("web", "core-api", "agent-service"), start=1)
}


def _manifest() -> dict[str, object]:
    return {
        "schemaVersion": 1,
        "repository": release.REPOSITORY,
        "sourceSha": SHA,
        "sourceRunId": 123,
        "images": {
            service: {
                "repository": f"{release.REGISTRY_PREFIX}/{service}",
                "digest": digest,
                "imageId": f"sha256:{'f' * 64}",
                "sizeBytes": 1000,
            }
            for service, digest in DIGESTS.items()
        },
    }


def test_清单严格接受三服务和固定来源() -> None:
    document = _manifest()
    assert release.validate_manifest(document, SHA, 123) is document


@pytest.mark.parametrize(
    "change",
    [
        lambda d: d.update(schemaVersion=True),
        lambda d: d.update(sourceSha="b" * 40),
        lambda d: d.update(sourceRunId=True),
        lambda d: d.update(unexpected=1),
        lambda d: d["images"].pop("web"),
        lambda d: d["images"]["web"].update(repository="ghcr.io/other/web"),
        lambda d: d["images"]["web"].update(digest="sha256:bad"),
        lambda d: d["images"]["web"].update(imageId="sha256:bad"),
        lambda d: d["images"]["web"].update(sizeBytes=True),
        lambda d: d["images"]["web"].update(extra="x"),
    ],
)
def test_篡改清单被拒绝(change: object) -> None:
    document = _manifest()
    change(document)  # type: ignore[operator]
    with pytest.raises(ValueError, match="发布清单"):
        release.validate_manifest(document, SHA, 123)


def test_重复_json_键即使值相同也被拒绝(tmp_path: Path) -> None:
    path = tmp_path / "release.json"
    content = json.dumps(_manifest(), separators=(",", ":"))
    path.write_text(content.replace('"schemaVersion":1', '"schemaVersion":1,"schemaVersion":1'))
    with pytest.raises(ValueError, match="重复 JSON 键"):
        release.load_manifest(path, SHA, 123)


def test_调用方不能换成任意仓库() -> None:
    with pytest.raises(ValueError, match="仓库"):
        release.validate_manifest(_manifest(), SHA, 123, "other/repository")


def test_创建时从_ghcr_digest_拉取并绑定本地构建标签(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []

    def fake_run(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        del kwargs
        calls.append(argv)
        if argv[1] == "pull":
            return subprocess.CompletedProcess(argv, 0, "", "")
        image = argv[-1]
        service = next(service for service in release.SERVICES if f"/{service}" in image)
        repo = f"{release.REGISTRY_PREFIX}/{service}"
        payload = [
            {
                "Id": f"sha256:{'f' * 64}",
                "Size": 1000,
                "RepoDigests": ([f"{repo}@{DIGESTS[service]}"] if "@" in image else []),
            }
        ]
        return subprocess.CompletedProcess(argv, 0, json.dumps(payload), "")

    monkeypatch.setattr(release.subprocess, "run", fake_run)
    document = release.create_manifest(SHA, 123, release.REPOSITORY, DIGESTS)
    assert document["images"] == _manifest()["images"]
    assert len([call for call in calls if call[:2] == ["docker", "pull"]]) == 3
    assert all(call[0] == "docker" for call in calls)


def test_创建时拒绝_digest_实际指向其他镜像(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        del kwargs
        if argv[1] == "pull":
            return subprocess.CompletedProcess(argv, 0, "", "")
        image_id = "e" * 64 if "@" in argv[-1] else "f" * 64
        service = "web"
        payload = [
            {
                "Id": f"sha256:{image_id}",
                "Size": 1000,
                "RepoDigests": [f"{release.REGISTRY_PREFIX}/{service}@{DIGESTS[service]}"],
            }
        ]
        return subprocess.CompletedProcess(argv, 0, json.dumps(payload), "")

    monkeypatch.setattr(release.subprocess, "run", fake_run)
    with pytest.raises(ValueError, match="构建镜像与 GHCR digest 不匹配"):
        release.create_manifest(SHA, 123, release.REPOSITORY, DIGESTS)
