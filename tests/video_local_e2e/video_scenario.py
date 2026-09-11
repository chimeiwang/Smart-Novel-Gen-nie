"""通过 Java Core 公共 API 执行新 Episode 视频生产链的固定业务场景。"""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
import subprocess
import time
import uuid
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parents[2]
BROWSER_CHECK = Path(__file__).with_name("browser_check.mjs")
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


def request_id(label: str) -> str:
    return f"video-e2e-{label}-{uuid.uuid4()}"


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def api_error(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return f"HTTP_{response.status_code}"
    if not isinstance(body, dict):
        return f"HTTP_{response.status_code}"
    detail = body.get("detail")
    if isinstance(detail, dict):
        code = detail.get("code")
        message = detail.get("message")
    else:
        code = body.get("code")
        message = body.get("message")
    return "/".join(str(item) for item in (code, message) if isinstance(item, str)) or (
        f"HTTP_{response.status_code}"
    )


class PublicApi:
    def __init__(self, base_url: str) -> None:
        self.client = httpx.Client(
            base_url=base_url,
            timeout=httpx.Timeout(30, connect=10),
            trust_env=False,
        )

    def close(self) -> None:
        self.client.close()

    def json(
        self,
        method: str,
        path: str,
        *,
        expected: int,
        body: object | None = None,
        params: dict[str, object] | None = None,
        files: dict[str, tuple[str, bytes, str]] | None = None,
        data: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        response = self.client.request(
            method,
            path,
            json=body if files is None else None,
            params=params,
            files=files,
            data=data,
        )
        if response.status_code != expected:
            raise AssertionError(
                f"公共 API {method} {path} 返回 {response.status_code}/"
                f"{api_error(response)}，预期 {expected}"
            )
        value = response.json()
        if not isinstance(value, dict):
            raise AssertionError(f"公共 API {method} {path} 没有返回 JSON 对象")
        return value

    def content(self, path: str, *, expected: int = 200) -> bytes:
        response = self.client.get(path)
        if response.status_code != expected:
            raise AssertionError(
                f"公共 API GET {path} 返回 {response.status_code}/{api_error(response)}"
            )
        return response.content


class EpisodeAcceptance:
    def __init__(self, directory: Path, state: dict[str, Any], *, browser: bool) -> None:
        self.directory = directory
        self.state = state
        self.browser = browser
        self.api = PublicApi(str(state["coreUrl"]))
        self.evidence_dir = Path(str(state["evidenceDirectory"]))
        self.evidence_dir.mkdir(parents=True, exist_ok=True)
        self.username = "video_e2e_" + secrets.token_hex(6)
        self.password = "Video-E2e!" + secrets.token_urlsafe(18)
        self.novel_id = ""
        self.project_id = ""
        self.episode_a_id = ""
        self.episode_b_id = ""
        self.export_task_id = ""
        self.baseline_b1_id = ""
        self.result: dict[str, Any] = {
            "schemaVersion": "inkforge-video-local-e2e/1.0",
            "simulationOnly": True,
            "seedanceApiKeyPresent": False,
            "productionDatabaseTouched": False,
            "isolation": {
                "databaseEndpoint": f"127.0.0.1:{state['ports']['postgres']}",
                "redisEndpoint": f"127.0.0.1:{state['ports']['redis']}",
                "executionRedisEndpoint": f"127.0.0.1:{state['ports']['executionRedis']}",
                "containers": sorted(state["containers"].values()),
            },
            "startedAt": datetime.now(UTC).isoformat(),
            "browser": {"enabled": browser, "checkpoints": []},
        }

    def run(self) -> Path:
        try:
            foundation = self.bootstrap()
            scenario_a = self.scenario_a(foundation)
            self.result["scenarioA"] = scenario_a
            self.browser_checkpoint("a")
            scenario_b = self.scenario_b(foundation, scenario_a)
            self.result["scenarioB"] = scenario_b
            self.browser_checkpoint("b")
            scenario_c = self.scenario_c(scenario_a, scenario_b)
            self.result["scenarioC"] = scenario_c
            self.browser_checkpoint("c")
            self.verify_database_facts()
            self.result["completedAt"] = datetime.now(UTC).isoformat()
            self.result["status"] = "passed"
            return self.write_evidence()
        except BaseException as exception:
            self.result["completedAt"] = datetime.now(UTC).isoformat()
            self.result["status"] = "failed"
            self.result["failure"] = {
                "type": exception.__class__.__name__,
                "message": str(exception),
            }
            self.write_evidence()
            raise
        finally:
            self.api.close()

    def write_evidence(self) -> Path:
        path = self.evidence_dir / "evidence.json"
        temporary = path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(self.result, ensure_ascii=False, indent=2) + "\n")
        temporary.replace(path)
        return path

    def bootstrap(self) -> dict[str, Any]:
        registered = self.api.json(
            "POST",
            "/api/v1/auth/register",
            expected=201,
            body={
                "username": self.username,
                "password": self.password,
                "confirmPassword": self.password,
            },
        )
        me = self.api.json("GET", "/api/v1/auth/me", expected=200)
        require(registered["id"] == me["id"], "注册后的认证 Cookie 没有恢复同一用户")
        novel = self.api.json(
            "POST",
            "/api/v1/novels",
            expected=201,
            body={"name": "雨夜书信", "storyLengthProfile": "long_serial"},
        )
        self.novel_id = str(novel["novelId"])
        chapter_12 = self.update_chapter(
            str(novel["chapterId"]),
            "第12章 雨夜",
            "大雨压住旧城的灯。沈砚在顾家庭院外取出一封信，几次想敲门。",
        )
        created = self.api.json(
            "POST", f"/api/v1/novels/{self.novel_id}/chapters", expected=201
        )
        chapter_13 = self.update_chapter(
            str(created["chapter"]["id"]),
            "第13章 门内",
            "顾晚听见门响，隔着门问是谁。三日前，她曾在同一盏灯下拒绝过沈砚。",
        )
        location = self.api.json(
            "POST",
            f"/api/v1/novels/{self.novel_id}/locations",
            expected=201,
            body={
                "clientRequestId": request_id("location"),
                "name": "顾家庭院",
                "type": "宅院",
                "climate": "雨夜",
                "description": "青砖、木门和一盏暖黄门灯",
            },
        )
        project = self.api.json(
            "POST",
            f"/api/v1/video/novels/{self.novel_id}/projects",
            expected=201,
            body={
                "title": "雨夜书信 · 连续短剧",
                "mode": "series",
                "targetAspectRatio": "9:16",
                "targetLanguage": "zh-CN",
            },
        )
        self.project_id = str(project["id"])
        uploaded = self.api.json(
            "POST",
            f"/api/v1/video/projects/{self.project_id}/assets",
            expected=201,
            files={"file": ("rain-courtyard.png", PNG, "image/png")},
            data={
                "name": "顾家庭院雨夜定妆",
                "modality": "image",
                "duty": "scene",
                "sourceKind": "user_upload",
            },
        )
        asset = self.api.json(
            "PATCH",
            f"/api/v1/video/assets/{uploaded['id']}/rights",
            expected=200,
            body={"rightsStatus": "confirmed"},
        )
        require(asset["lockedAt"] is not None, "已确认权利的定妆素材没有锁定")
        canon = self.api.json(
            "POST",
            f"/api/v1/video/projects/{self.project_id}/visual-canons",
            expected=201,
            body={
                "clientRequestId": request_id("canon-candidate"),
                "expectedRevision": 0,
                "settingKind": "location",
                "settingId": location["id"],
                "duty": "scene",
                "variantKey": "rain-night",
                "label": "雨夜庭院定妆",
                "candidateAssetId": asset["id"],
                "includeFeatures": ["青砖", "木门", "暖黄门灯", "雨幕"],
                "excludeFeatures": ["白天", "现代霓虹"],
                "defaultStrength": 82,
            },
        )
        approved = self.api.json(
            "POST",
            f"/api/v1/video/visual-canons/{canon['id']}/approve",
            expected=200,
            body={
                "clientRequestId": request_id("canon-approve"),
                "expectedRevision": canon["revision"],
                "candidateAssetId": asset["id"],
            },
        )
        require(approved["currentVersionId"] is not None, "定妆批准没有创建正式版本")
        capability = self.api.json(
            "GET", "/api/v1/video/production-capabilities", expected=200
        )
        require(capability["executionMode"] == "simulated", "隔离验收没有运行在 simulated")
        require(capability["providerEnabled"] is False, "隔离验收意外启用了真实供应商")
        return {
            "userId": registered["id"],
            "chapter12": chapter_12,
            "chapter13": chapter_13,
            "locationId": location["id"],
            "assetId": asset["id"],
            "assetSha256": asset["sha256"],
            "canonVersionId": approved["currentVersionId"],
            "capability": capability,
        }

    def update_chapter(self, chapter_id: str, title: str, content: str) -> dict[str, Any]:
        current = self.api.json("GET", f"/api/v1/chapters/{chapter_id}", expected=200)
        self.api.json(
            "PATCH",
            f"/api/v1/chapters/{chapter_id}",
            expected=200,
            body={
                "title": title,
                "content": content,
                "expectedUpdatedAt": current["updatedAt"],
            },
        )
        return self.api.json("GET", f"/api/v1/chapters/{chapter_id}", expected=200)

    def create_episode(self, title: str) -> dict[str, Any]:
        return self.api.json(
            "POST",
            f"/api/v1/video/projects/{self.project_id}/episodes",
            expected=201,
            body={
                "clientRequestId": request_id("episode"),
                "title": title,
                "creativeIntent": "连续短剧，保留明确的剧情时间和承接事实",
                "targetDurationSeconds": 30,
            },
        )

    def source_set(self, episode_id: str, chapters: list[dict[str, Any]]) -> dict[str, Any]:
        detail = self.episode(episode_id)
        return self.api.json(
            "POST",
            f"/api/v1/video/episodes/{episode_id}/source-sets",
            expected=201,
            body={
                "clientRequestId": request_id("sources"),
                "expectedRevision": detail["episode"]["revision"],
                "basedOnVersionId": None,
                "sources": [
                    {
                        "chapterId": chapter["id"],
                        "expectedUpdatedAt": chapter["updatedAt"],
                        "sourceHash": sha256_text(chapter["content"]),
                        "ranges": [{"start": 0, "end": len(chapter["content"])}],
                    }
                    for chapter in chapters
                ],
            },
        )

    def episode(self, episode_id: str) -> dict[str, Any]:
        return self.api.json("GET", f"/api/v1/video/episodes/{episode_id}", expected=200)

    def approve_script(
        self,
        episode_id: str,
        source_set_id: str,
        document: dict[str, Any],
        *,
        base_version_id: str | None = None,
    ) -> dict[str, Any]:
        detail = self.episode(episode_id)
        draft = self.api.json(
            "PUT",
            f"/api/v1/video/episodes/{episode_id}/script/draft",
            expected=200,
            body={
                "clientRequestId": request_id("script-save"),
                "expectedRevision": detail["scriptDraft"]["revision"],
                "sourceSetVersionId": source_set_id,
                "baseScriptVersionId": base_version_id,
                "document": document,
            },
        )
        current = self.episode(episode_id)
        confirmation = self.api.json(
            "POST",
            f"/api/v1/video/episodes/{episode_id}/script/confirmations",
            expected=201,
            body={
                "clientRequestId": request_id("script-prepare"),
                "expectedDraftRevision": draft["revision"],
                "expectedEpisodeRevision": current["episode"]["revision"],
            },
        )
        version = self.api.json(
            "POST",
            (
                f"/api/v1/video/episodes/{episode_id}/script/confirmations/"
                f"{confirmation['artifactId']}/approve"
            ),
            expected=201,
            body={
                "clientRequestId": request_id("script-approve"),
                "expectedArtifactRevision": confirmation["artifactRevision"],
                "expectedDraftRevision": confirmation["draftRevision"],
                "expectedEpisodeRevision": confirmation["episodeRevision"],
                "confirmationHash": confirmation["confirmationHash"],
            },
        )
        require(version["document"] == confirmation["document"], "正式剧本不是确认时的确切文档")
        return version

    def approve_storyboard(
        self,
        episode_id: str,
        script: dict[str, Any],
        canon_version_id: str,
        capability: dict[str, Any],
    ) -> dict[str, Any]:
        scene = script["document"]["scenes"][0]
        lines = scene["lines"]
        shots = []
        for index, (title, action, prompt) in enumerate(
            (
                (
                    "门外握信",
                    "雨水落在沈砚握紧又松开的手上，信封边缘被雨打湿。",
                    "雨夜古宅门外，中景，手持轻微晃动，人物握住信封迟疑，保持雨幕和暖黄门灯定妆。",
                ),
                (
                    "门缝交信",
                    "木门打开一线，信封从门缝递入，顾晚的手停在半空。",
                    "雨夜古宅门缝特写，信封在两只手之间，静态机位，保持青砖木门与暖黄灯光定妆。",
                ),
            )
        ):
            line = lines[min(index, len(lines) - 1)]
            shots.append(
                {
                    "id": None,
                    "tempKey": f"shot_a_{index + 1}",
                    "lineage": [],
                    "scriptSceneId": scene["id"],
                    "scriptLineIds": [line["id"]],
                    "title": title,
                    "action": action,
                    "framing": "medium" if index == 0 else "detail",
                    "cameraMovement": "handheld" if index == 0 else "static",
                    "durationMs": 4_000,
                    "productionIntent": {
                        "provider": capability["provider"],
                        "model": capability["model"],
                        "generationMode": "reference",
                        "executionMode": "simulated",
                        "feeConfirmed": False,
                        "prompt": prompt,
                        "ratio": "9:16",
                        "durationSeconds": 4,
                        "resolution": "720p",
                        "generateAudio": True,
                        "watermark": False,
                        "outputFormat": "mp4",
                        "references": [
                            {"canonVersionId": canon_version_id, "strength": 82}
                        ],
                    },
                }
            )
        initial = self.api.json(
            "GET", f"/api/v1/video/episodes/{episode_id}/storyboard/draft", expected=200
        )
        draft = self.api.json(
            "PUT",
            f"/api/v1/video/episodes/{episode_id}/storyboard/draft",
            expected=200,
            body={
                "clientRequestId": request_id("storyboard-save"),
                "expectedRevision": initial["revision"],
                "scriptVersionId": script["id"],
                "baseStoryboardVersionId": None,
                "document": {
                    "schemaVersion": "video-episode-storyboard/1.0",
                    "shots": shots,
                },
            },
        )
        current = self.episode(episode_id)
        confirmation = self.api.json(
            "POST",
            f"/api/v1/video/episodes/{episode_id}/storyboard/confirmations",
            expected=201,
            body={
                "clientRequestId": request_id("storyboard-prepare"),
                "expectedDraftRevision": draft["revision"],
                "expectedEpisodeRevision": current["episode"]["revision"],
            },
        )
        version = self.api.json(
            "POST",
            (
                f"/api/v1/video/episodes/{episode_id}/storyboard/confirmations/"
                f"{confirmation['artifactId']}/approve"
            ),
            expected=201,
            body={
                "clientRequestId": request_id("storyboard-approve"),
                "expectedArtifactRevision": confirmation["artifactRevision"],
                "expectedDraftRevision": confirmation["draftRevision"],
                "expectedEpisodeRevision": confirmation["episodeRevision"],
                "confirmationHash": confirmation["confirmationHash"],
            },
        )
        require(len(version["shots"]) == 2, "正式分镜没有保留两个逐镜身份")
        require(
            len({shot["shotId"] for shot in version["shots"]}) == 2,
            "正式分镜的稳定镜头身份发生碰撞",
        )
        return version

    def create_baseline(
        self,
        episode_id: str,
        script_id: str,
        storyboard: dict[str, Any],
        *,
        based_on: str | None,
        adoptions: list[dict[str, str]],
        keyframe_asset_id: str | None,
    ) -> dict[str, Any]:
        detail = self.episode(episode_id)
        keyframes = (
            [
                {
                    "shotVersionId": shot["id"],
                    "role": "initial_state",
                    "assetId": keyframe_asset_id,
                }
                for shot in storyboard["shots"]
            ]
            if keyframe_asset_id
            else []
        )
        return self.api.json(
            "POST",
            f"/api/v1/video/episodes/{episode_id}/production-baselines",
            expected=201,
            body={
                "clientRequestId": request_id("baseline"),
                "expectedEpisodeRevision": detail["episode"]["revision"],
                "expectedProductionRevision": detail["episode"]["productionRevision"],
                "basedOnBaselineId": based_on,
                "scriptVersionId": script_id,
                "storyboardVersionId": storyboard["id"],
                "shotAdoptions": adoptions,
                "keyframes": keyframes,
            },
        )

    def wait_task(
        self,
        path: str,
        *,
        terminal: set[str],
        success: str,
        timeout: float,
    ) -> dict[str, Any]:
        deadline = time.monotonic() + timeout
        last: dict[str, Any] = {}
        while time.monotonic() < deadline:
            last = self.api.json("GET", path, expected=200)
            if last.get("status") in terminal:
                require(
                    last["status"] == success,
                    f"耐久任务以 {last['status']}/{last.get('lastErrorCode')} 结束",
                )
                return last
            time.sleep(0.4)
        raise AssertionError(f"耐久任务没有在 {timeout:.0f} 秒内结束：{last.get('status')}")

    def render_and_adopt(
        self, episode_id: str, baseline: dict[str, Any]
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        completed: list[dict[str, Any]] = []
        adoptions: list[dict[str, Any]] = []
        for baseline_shot in baseline["shots"]:
            task = self.api.json(
                "POST",
                (
                    f"/api/v1/video/episodes/{episode_id}/production-baselines/"
                    f"{baseline['id']}/shots/{baseline_shot['shotId']}/render-tasks"
                ),
                expected=202,
                body={"clientRequestId": request_id("render"), "feeConfirmed": False},
            )
            finished = self.wait_task(
                f"/api/v1/video/episodes/{episode_id}/render-tasks/{task['id']}",
                terminal={"succeeded", "failed", "expired", "cancelled", "submission_unknown"},
                success="succeeded",
                timeout=150,
            )
            require(finished["mediaKind"] == "simulated_placeholder", "模拟 Take 媒体类型不诚实")
            require(
                str(finished["providerTaskId"]).startswith("simulated-"),
                "模拟任务没有使用本地身份",
            )
            candidates = self.api.json(
                "GET",
                f"/api/v1/video/episodes/{episode_id}/takes",
                expected=200,
                params={"targetShotVersionId": baseline_shot["shotVersionId"], "limit": 20},
            )
            take = next(
                (
                    item
                    for item in candidates["takes"]
                    if item["id"] == finished["takeId"]
                    and item["sourceBaselineId"] == baseline["id"]
                ),
                None,
            )
            require(take is not None, "成功任务没有形成可查询的同基线 Take")
            hashes = [
                reference["sha256"]
                for reference in baseline_shot["inputSnapshot"]["references"]
            ]
            detail = self.episode(episode_id)
            adoption = self.api.json(
                "POST",
                f"/api/v1/video/episodes/{episode_id}/take-adoptions",
                expected=201,
                body={
                    "clientRequestId": request_id("adoption"),
                    "expectedProductionRevision": detail["episode"]["productionRevision"],
                    "targetShotVersionId": baseline_shot["shotVersionId"],
                    "sourceTakeId": take["id"],
                    "sourceBaselineId": baseline["id"],
                    "comparison": {
                        "sourceBaselineId": baseline["id"],
                        "targetShotVersionId": baseline_shot["shotVersionId"],
                        "directInputsUnchanged": True,
                        "referenceHashesChecked": hashes,
                        "summary": "已核对人物动作、雨夜场景、参考图哈希与目标镜头版本，素材适用。",
                    },
                },
            )
            completed.append({"task": finished, "take": take})
            adoptions.append(
                {"shotVersionId": baseline_shot["shotVersionId"], "adoptionId": adoption["id"]}
            )
        return completed, adoptions

    def post_production(
        self,
        episode_id: str,
        baseline: dict[str, Any],
        rendered: list[dict[str, Any]],
    ) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], Path]:
        delivery_revision = self.episode(episode_id)["episode"]["deliveryRevision"]
        require(delivery_revision == 1, "首份交付前 deliveryRevision 应为 1")
        take_by_shot = {
            item["take"]["sourceShotVersionId"]: item["take"] for item in rendered
        }
        first, second = baseline["shots"]
        first_take = take_by_shot[first["shotVersionId"]]
        second_take = take_by_shot[second["shotVersionId"]]
        edit_head = self.api.json(
            "GET",
            (
                f"/api/v1/video/episodes/{episode_id}/production-baselines/"
                f"{baseline['id']}/edit-versions"
            ),
            expected=200,
        )
        edit = self.api.json(
            "POST",
            (
                f"/api/v1/video/episodes/{episode_id}/production-baselines/"
                f"{baseline['id']}/edit-versions"
            ),
            expected=201,
            body={
                "clientRequestId": request_id("edit"),
                "expectedHeadRevision": edit_head["headRevision"],
                "basedOnVersionId": None,
                "clips": [
                    {
                        "tempKey": "clip-a-1",
                        "adoptionId": first["adoptionId"],
                        "takeId": first_take["id"],
                        "sourceInMs": 0,
                        "sourceOutMs": 1_500,
                        "sourceAudioMode": "keep",
                        "transitionAfter": "cut",
                        "transitionDurationMs": 0,
                    },
                    {
                        "tempKey": "clip-a-2",
                        "adoptionId": first["adoptionId"],
                        "takeId": first_take["id"],
                        "sourceInMs": 1_500,
                        "sourceOutMs": 4_000,
                        "sourceAudioMode": "mute",
                        "transitionAfter": "cut",
                        "transitionDurationMs": 0,
                    },
                    {
                        "tempKey": "clip-a-3",
                        "adoptionId": second["adoptionId"],
                        "takeId": second_take["id"],
                        "sourceInMs": 0,
                        "sourceOutMs": 4_000,
                        "sourceAudioMode": "keep",
                        "transitionAfter": "cut",
                        "transitionDurationMs": 0,
                    },
                ],
                "omissions": [],
            },
        )
        require(len({clip["clipId"] for clip in edit["clips"]}) == 3, "粗剪 clipId 不独立")
        require(
            [clip["takeId"] for clip in edit["clips"]].count(first_take["id"]) == 2,
            "粗剪没有保留同一 Take 的重复片段",
        )
        mix_head = self.api.json(
            "GET",
            (
                f"/api/v1/video/episodes/{episode_id}/production-baselines/"
                f"{baseline['id']}/mix-versions"
            ),
            expected=200,
        )
        mix = self.api.json(
            "POST",
            (
                f"/api/v1/video/episodes/{episode_id}/production-baselines/"
                f"{baseline['id']}/mix-versions"
            ),
            expected=201,
            body={
                "clientRequestId": request_id("mix"),
                "expectedHeadRevision": mix_head["headRevision"],
                "basedOnVersionId": None,
                "editVersionId": edit["id"],
                "audioClips": [],
                "subtitleCues": [
                    {
                        "shotVersionId": first["shotVersionId"],
                        "scriptLineId": first["inputSnapshot"]["scriptLineIds"][0],
                        "startMs": 100,
                        "endMs": 1_200,
                        "speaker": None,
                        "text": "雨落在信封上。",
                    },
                    {
                        "shotVersionId": second["shotVersionId"],
                        "scriptLineId": second["inputSnapshot"]["scriptLineIds"][0],
                        "startMs": 4_200,
                        "endMs": 5_600,
                        "speaker": None,
                        "text": "门缝里的手停住了。",
                    },
                ],
            },
        )
        task = self.api.json(
            "POST",
            (
                f"/api/v1/video/episodes/{episode_id}/production-baselines/"
                f"{baseline['id']}/export-tasks"
            ),
            expected=202,
            body={
                "clientRequestId": request_id("export"),
                "editVersionId": edit["id"],
                "mixVersionId": mix["id"],
                "resolution": "720p",
                "framesPerSecond": 24,
                "burnSubtitles": False,
            },
        )
        finished = self.wait_task(
            (
                f"/api/v1/video/episodes/{episode_id}/production-baselines/"
                f"{baseline['id']}/export-tasks/{task['id']}"
            ),
            terminal={"succeeded", "failed"},
            success="succeeded",
            timeout=180,
        )
        require(finished["export"] is not None, "成功导出任务没有交付记录")
        content = self.api.content(

                f"/api/v1/video/episodes/{episode_id}/production-baselines/"
                f"{baseline['id']}/exports/{finished['export']['id']}/content"

        )
        require(len(content) > 1_000, "交付 MP4 内容为空或明显无效")
        require(
            hashlib.sha256(content).hexdigest() == finished["export"]["asset"]["sha256"],
            "交付文件与冻结素材哈希不一致",
        )
        delivery_path = self.evidence_dir / "scenario-a-delivery.mp4"
        temporary = delivery_path.with_suffix(".mp4.tmp")
        temporary.write_bytes(content)
        temporary.replace(delivery_path)
        require(
            hashlib.sha256(delivery_path.read_bytes()).hexdigest()
            == finished["export"]["asset"]["sha256"],
            "证据目录中的交付文件与冻结素材哈希不一致",
        )
        episode = self.episode(episode_id)
        require(
            episode["episode"]["latestDeliveryVersionId"] == finished["export"]["id"],
            "剧集聚合的当前交付没有指向刚归档的成片",
        )
        require(
            episode["episode"]["deliveryRevision"] == delivery_revision + 1,
            "首份交付没有只递增一次 deliveryRevision",
        )
        return edit, mix, finished, delivery_path

    def scenario_a(self, foundation: dict[str, Any]) -> dict[str, Any]:
        episode = self.create_episode("雨夜交信")
        self.episode_a_id = str(episode["id"])
        sources = self.source_set(
            self.episode_a_id, [foundation["chapter12"], foundation["chapter13"]]
        )
        source_chapters = [item["chapterId"] for item in sources["sources"]]
        require(
            source_chapters
            == [foundation["chapter12"]["id"], foundation["chapter13"]["id"]],
            "场景 A 没有按明确顺序冻结跨第 12／13 章来源",
        )
        script = self.approve_script(
            self.episode_a_id,
            sources["id"],
            {
                "schemaVersion": "video-episode-script/1.0",
                "overview": {
                    "summary": "沈砚冒雨把信送到顾家门前，顾晚隔门接信。",
                    "creativeIntent": "用动作和门缝表现两人的迟疑。",
                    "targetDurationSeconds": 30,
                },
                "scenes": [
                    {
                        "id": None,
                        "tempKey": "scene_a_handoff",
                        "title": "雨夜交信",
                        "locationLabel": "顾家庭院门外",
                        "timeLabel": "深夜，大雨",
                        "narrativeTime": "当晚",
                        "characterIds": [],
                        "lines": [
                            {
                                "id": None,
                                "tempKey": "line_a_wait",
                                "kind": "action",
                                "speakerId": None,
                                "text": "沈砚在门外握紧信封，雨水顺着指节落下。",
                                "sourceRefs": [],
                            },
                            {
                                "id": None,
                                "tempKey": "line_a_handoff",
                                "kind": "action",
                                "speakerId": None,
                                "text": "木门打开一线，他把信递入，顾晚接住信。",
                                "sourceRefs": [],
                            },
                        ],
                    }
                ],
                "endingStates": [
                    {
                        "key": "letter_handoff",
                        "description": "顾晚已经接过沈砚的信，尚未拆开。",
                        "entityIds": [],
                        "narrativeTime": "雨夜交信之后",
                    }
                ],
                "dependencies": [],
            },
        )
        storyboard = self.approve_storyboard(
            self.episode_a_id,
            script,
            foundation["canonVersionId"],
            foundation["capability"],
        )
        baseline_b0 = self.create_baseline(
            self.episode_a_id,
            script["id"],
            storyboard,
            based_on=None,
            adoptions=[],
            keyframe_asset_id=foundation["assetId"],
        )
        require(
            all(shot["status"] == "pending" for shot in baseline_b0["shots"]),
            "B0 应只冻结输入并保持逐镜待生产",
        )
        require(
            all(
                shot["inputSnapshot"]["schemaVersion"] == "video-production-shot-input/1.2"
                and len(shot["inputSnapshot"]["keyframes"]) == 1
                for shot in baseline_b0["shots"]
            ),
            "B0 没有冻结逐镜关键帧版本与素材哈希",
        )
        rendered, adoptions = self.render_and_adopt(self.episode_a_id, baseline_b0)
        baseline_b1 = self.create_baseline(
            self.episode_a_id,
            script["id"],
            storyboard,
            based_on=baseline_b0["id"],
            adoptions=adoptions,
            keyframe_asset_id=None,
        )
        self.baseline_b1_id = str(baseline_b1["id"])
        require(
            all(shot["status"] == "adopted" for shot in baseline_b1["shots"]),
            "B1 没有显式冻结全部 Take Adoption",
        )
        edit, mix, export_task, delivery_path = self.post_production(
            self.episode_a_id, baseline_b1, rendered
        )
        self.export_task_id = str(export_task["id"])
        return {
            "episodeId": self.episode_a_id,
            "sourceSetId": sources["id"],
            "sourceChapterIds": source_chapters,
            "scriptVersionId": script["id"],
            "storyboardVersionId": storyboard["id"],
            "stableShotIds": [shot["shotId"] for shot in storyboard["shots"]],
            "baselineB0Id": baseline_b0["id"],
            "baselineB1Id": baseline_b1["id"],
            "renderTasks": [item["task"]["id"] for item in rendered],
            "takeIds": [item["take"]["id"] for item in rendered],
            "allMediaKinds": sorted({item["task"]["mediaKind"] for item in rendered}),
            "adoptionIds": [item["adoptionId"] for item in adoptions],
            "editVersionId": edit["id"],
            "editClipIds": [clip["clipId"] for clip in edit["clips"]],
            "editUsesKeepAndMute": {clip["sourceAudioMode"] for clip in edit["clips"]}
            == {"keep", "mute"},
            "mixVersionId": mix["id"],
            "subtitleLineIds": [cue["scriptLineId"] for cue in mix["subtitleCues"]],
            "exportTaskId": export_task["id"],
            "deliveryId": export_task["export"]["id"],
            "deliveryInputHash": export_task["export"]["inputHash"],
            "deliveryAssetSha256": export_task["export"]["asset"]["sha256"],
            "deliveryEvidenceFile": str(delivery_path),
            "deliveryRevision": self.episode(self.episode_a_id)["episode"][
                "deliveryRevision"
            ],
        }

    def scenario_b(
        self, foundation: dict[str, Any], scenario_a: dict[str, Any]
    ) -> dict[str, Any]:
        episode = self.create_episode("拆信")
        self.episode_b_id = str(episode["id"])
        sources = self.source_set(self.episode_b_id, [foundation["chapter13"]])
        producer = self.api.json(
            "GET",
            (
                f"/api/v1/video/episodes/{self.episode_a_id}/script/versions/"
                f"{scenario_a['scriptVersionId']}"
            ),
            expected=200,
        )
        script = self.approve_script(
            self.episode_b_id,
            sources["id"],
            {
                "schemaVersion": "video-episode-script/1.0",
                "overview": {
                    "summary": "顾晚准备拆信，同时穿插三日前拒绝沈砚的回忆。",
                    "creativeIntent": "现实线承接交信事实，回忆使用独立剧情时间。",
                    "targetDurationSeconds": 30,
                },
                "scenes": [
                    {
                        "id": None,
                        "tempKey": "scene_b_open",
                        "title": "顾晚拆信",
                        "locationLabel": "顾家书房",
                        "timeLabel": "同一雨夜",
                        "narrativeTime": "交信之后",
                        "characterIds": [],
                        "lines": [
                            {
                                "id": None,
                                "tempKey": "line_b_open",
                                "kind": "action",
                                "speakerId": None,
                                "text": "顾晚把尚未拆开的信放在灯下，手指压住封口。",
                                "sourceRefs": [],
                            }
                        ],
                    },
                    {
                        "id": None,
                        "tempKey": "scene_b_flashback",
                        "title": "三日前回忆",
                        "locationLabel": "顾家庭院",
                        "timeLabel": "黄昏",
                        "narrativeTime": "三日前，独立回忆",
                        "characterIds": [],
                        "lines": [
                            {
                                "id": None,
                                "tempKey": "line_b_flashback",
                                "kind": "narration",
                                "speakerId": None,
                                "text": "三日前，顾晚在门灯下拒绝了沈砚。",
                                "sourceRefs": [],
                            }
                        ],
                    },
                ],
                "endingStates": [],
                "dependencies": [
                    {
                        "producerEpisodeId": self.episode_a_id,
                        "producerScriptVersionId": producer["id"],
                        "producerStateKey": "letter_handoff",
                        "consumerSceneId": "scene_b_open",
                        "consumerLineId": "line_b_open",
                        "narrativeTime": "雨夜交信之后",
                        "description": "顾晚在开信场必须已经持有第一集交来的信。",
                    }
                ],
            },
        )
        detail = self.episode(self.episode_b_id)
        require(len(detail["dependencies"]) == 1, "第二集没有冻结第一集的确切状态依赖")
        scenes = script["document"]["scenes"]
        flashback = next(scene for scene in scenes if scene["title"] == "三日前回忆")
        dependency = detail["dependencies"][0]
        require(
            dependency["consumerSceneId"] != flashback["id"],
            "三日前回忆被错误绑定到上一集结尾状态",
        )
        return {
            "episodeId": self.episode_b_id,
            "sourceSetId": sources["id"],
            "sharedChapter13WithEpisodeA": foundation["chapter13"]["id"]
            in scenario_a["sourceChapterIds"],
            "scriptVersionId": script["id"],
            "dependencyId": dependency["id"],
            "producerScriptVersionId": dependency["producerScriptVersionId"],
            "consumerSceneId": dependency["consumerSceneId"],
            "flashbackSceneId": flashback["id"],
            "flashbackNarrativeTime": flashback["narrativeTime"],
        }

    def scenario_c(
        self, scenario_a: dict[str, Any], scenario_b: dict[str, Any]
    ) -> dict[str, Any]:
        old_version = self.api.json(
            "GET",
            (
                f"/api/v1/video/episodes/{self.episode_a_id}/script/versions/"
                f"{scenario_a['scriptVersionId']}"
            ),
            expected=200,
        )
        document = deepcopy(old_version["document"])
        document["overview"]["summary"] = "沈砚原本要交信，最后在顾晚接住前把信收回。"
        document["scenes"][0]["lines"][1]["text"] = (
            "木门打开一线，顾晚伸手时，沈砚把信收回怀中。"
        )
        document["endingStates"][0]["description"] = "沈砚已经收回信，顾晚没有拿到信。"
        revised = self.approve_script(
            self.episode_a_id,
            old_version["sourceSetVersionId"],
            document,
            base_version_id=old_version["id"],
        )
        require(revised["versionNo"] == 2, "第一集修订没有形成正式剧本 v2")
        impact_page = self.api.json(
            "GET",
            f"/api/v1/video/episodes/{self.episode_b_id}/impact-reviews",
            expected=200,
            params={"status": "pending", "limit": 20},
        )
        require(len(impact_page["reviews"]) == 1, "第一集状态变化没有形成第二集待处理影响")
        impact = self.api.json(
            "GET",
            (
                f"/api/v1/video/episodes/{self.episode_b_id}/impact-reviews/"
                f"{impact_page['reviews'][0]['id']}"
            ),
            expected=200,
        )
        require(len(impact["report"]["items"]) == 1, "影响报告包含非直接依赖项")
        item = impact["report"]["items"][0]
        require(
            item["consumerSceneId"] == scenario_b["consumerSceneId"],
            "影响没有精确指向第二集开信场",
        )
        require(
            item["consumerSceneId"] != scenario_b["flashbackSceneId"],
            "独立回忆被错误列入上一集状态变化影响",
        )
        require("收回信" in item["afterState"]["description"], "影响报告没有显示新状态")
        old_baseline = self.api.json(
            "GET",
            (
                f"/api/v1/video/episodes/{self.episode_a_id}/production-baselines/"
                f"{scenario_a['baselineB1Id']}"
            ),
            expected=200,
        )
        old_delivery = self.api.json(
            "GET",
            (
                f"/api/v1/video/episodes/{self.episode_a_id}/production-baselines/"
                f"{scenario_a['baselineB1Id']}/exports/{scenario_a['deliveryId']}"
            ),
            expected=200,
        )
        old_edit = self.api.json(
            "GET",
            (
                f"/api/v1/video/episodes/{self.episode_a_id}/production-baselines/"
                f"{scenario_a['baselineB1Id']}/edit-versions/{scenario_a['editVersionId']}"
            ),
            expected=200,
        )
        old_mix = self.api.json(
            "GET",
            (
                f"/api/v1/video/episodes/{self.episode_a_id}/production-baselines/"
                f"{scenario_a['baselineB1Id']}/mix-versions/{scenario_a['mixVersionId']}"
            ),
            expected=200,
        )
        require(
            old_baseline["scriptVersionId"] == old_version["id"],
            "批准剧本 v2 改写了旧制作基线",
        )
        require(
            old_delivery["inputHash"] == scenario_a["deliveryInputHash"],
            "旧交付读取结果发生漂移",
        )
        require(
            old_edit["id"] == scenario_a["editVersionId"]
            and old_mix["id"] == scenario_a["mixVersionId"],
            "剧本 v2 之后旧后期版本不可读",
        )
        current_b = self.episode(self.episode_b_id)
        flashback = next(
            scene
            for scene in current_b["currentScriptVersion"]["document"]["scenes"]
            if scene["id"] == scenario_b["flashbackSceneId"]
        )
        return {
            "episodeAVersion2Id": revised["id"],
            "impactReviewId": impact["id"],
            "impactRevision": impact["revision"],
            "impactItemIds": [item["itemId"]],
            "impactConsumerSceneId": item["consumerSceneId"],
            "beforeState": item["beforeState"]["description"],
            "afterState": item["afterState"]["description"],
            "flashbackStillReadable": flashback["title"] == "三日前回忆",
            "oldBaselineReadable": old_baseline["id"] == scenario_a["baselineB1Id"],
            "oldEditReadable": old_edit["id"] == scenario_a["editVersionId"],
            "oldMixReadable": old_mix["id"] == scenario_a["mixVersionId"],
            "oldDeliveryReadable": old_delivery["id"] == scenario_a["deliveryId"],
        }

    def browser_checkpoint(self, checkpoint: str) -> None:
        if not self.browser:
            return
        private = self.directory / "browser-input.json"
        private.write_text(
            json.dumps(
                {
                    "webUrl": self.state["webUrl"],
                    "username": self.username,
                    "password": self.password,
                    "novelId": self.novel_id,
                    "projectId": self.project_id,
                    "episodeAId": self.episode_a_id,
                    "episodeBId": self.episode_b_id,
                    "baselineB1Id": self.baseline_b1_id,
                    "exportTaskId": self.export_task_id,
                },
                ensure_ascii=False,
            )
            + "\n"
        )
        private.chmod(0o600)
        screenshot = self.evidence_dir / f"browser-{checkpoint}.png"
        completed = subprocess.run(  # noqa: S603 - 固定仓内 Playwright 验收脚本
            [
                str(Path(shutil_which_node())),
                str(BROWSER_CHECK),
                str(private),
                checkpoint,
                str(screenshot),
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
            timeout=120,
        )
        if completed.returncode:
            raise AssertionError(
                f"浏览器检查点 {checkpoint} 失败\n{completed.stderr.strip()}"
            )
        receipt = json.loads(completed.stdout)
        require(isinstance(receipt, dict), "浏览器回执不是对象")
        self.result["browser"]["checkpoints"].append(receipt)

    def verify_database_facts(self) -> None:
        docker = str(self.state["docker"])
        postgres = str(self.state["containers"]["postgres"])
        sql = """
CREATE OR REPLACE FUNCTION pg_temp.legacy_adaptation_count() RETURNS bigint
LANGUAGE plpgsql AS $$
DECLARE result bigint;
BEGIN
  IF to_regclass('public."VideoChapterAdaptation"') IS NULL THEN
    RETURN 0;
  END IF;
  EXECUTE 'SELECT count(*) FROM public."VideoChapterAdaptation"' INTO result;
  RETURN result;
END $$;
SELECT json_build_object(
  'episodes', (SELECT count(*) FROM public."VideoEpisode"),
  'scriptVersions', (SELECT count(*) FROM public."VideoEpisodeScriptVersion"),
  'storyboardVersions', (SELECT count(*) FROM public."VideoStoryboardVersion"),
  'baselines', (SELECT count(*) FROM public."VideoProductionBaseline"),
  'episodeRenderTasks', (
    SELECT count(*) FROM public."VideoShotRenderTask" WHERE "videoEpisodeId" IS NOT NULL
  ),
  'takes', (
    SELECT count(*) FROM public."VideoShotTake" WHERE "videoEpisodeId" IS NOT NULL
  ),
  'adoptions', (SELECT count(*) FROM public."VideoTakeAdoption"),
  'editVersions', (
    SELECT count(*) FROM public."VideoEpisodeEditVersion" WHERE "videoEpisodeId" IS NOT NULL
  ),
  'mixVersions', (
    SELECT count(*) FROM public."VideoEpisodeMixVersion" WHERE "videoEpisodeId" IS NOT NULL
  ),
  'deliveries', (
    SELECT count(*) FROM public."VideoEpisodeExport" WHERE "videoEpisodeId" IS NOT NULL
  ),
  'pendingImpacts', (SELECT count(*) FROM public."VideoImpactReview" WHERE status='pending'),
  'legacyAdaptations', pg_temp.legacy_adaptation_count()
);
"""
        completed = subprocess.run(  # noqa: S603 - 只读查询当前随机命名隔离数据库
            [
                docker,
                "exec",
                "-i",
                postgres,
                "psql",
                "-X",
                "-q",
                "-A",
                "-t",
                "-U",
                "inkforge_e2e",
                "-d",
                "novelwriterdev",
            ],
            cwd=ROOT,
            input=sql,
            text=True,
            capture_output=True,
            check=False,
            timeout=30,
        )
        if completed.returncode:
            raise AssertionError("无法读取隔离 PostgreSQL 的最终业务事实")
        facts = json.loads(completed.stdout)
        expected = {
            "episodes": 2,
            "scriptVersions": 3,
            "storyboardVersions": 1,
            "baselines": 2,
            "episodeRenderTasks": 2,
            "takes": 2,
            "adoptions": 2,
            "editVersions": 1,
            "mixVersions": 1,
            "deliveries": 1,
            "pendingImpacts": 1,
            "legacyAdaptations": 0,
        }
        require(facts == expected, f"隔离数据库最终事实不符合固定场景：{facts}")
        self.result["databaseFacts"] = facts


def shutil_which_node() -> str:
    import shutil

    node = shutil.which("node")
    if node is not None:
        return node
    for candidate in (Path("/opt/homebrew/bin/node"), Path("/usr/local/bin/node")):
        if candidate.is_file():
            return str(candidate)
    raise RuntimeError("本机缺少 Node.js")


def run_scenario(directory: Path, state: dict[str, Any], *, browser: bool) -> Path:
    return EpisodeAcceptance(directory, state, browser=browser).run()
