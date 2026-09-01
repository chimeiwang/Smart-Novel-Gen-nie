"""本地 E2E provider gate 与 callback 透明代理。"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import sqlite3
import threading
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Literal

import httpx
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, ConfigDict, Field


def _now() -> str:
    return datetime.now(UTC).isoformat()


class ProviderIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid")

    idempotencyKey: str = Field(min_length=1, max_length=128)
    requestSha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class GateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["pass", "hold"]


class CallbackModeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["pass", "hold_before_forward", "drop_after_forward_once"]


class ReleaseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    abort: bool = False


class _Gate:
    def __init__(self) -> None:
        self.mode = "pass"
        self.reached = 0
        self.abort = False
        self.event = asyncio.Event()
        self.event.set()
        self.lock = asyncio.Lock()

    async def configure(self, mode: str) -> None:
        async with self.lock:
            self.mode = mode
            self.reached = 0
            self.abort = False
            self.event = asyncio.Event()
            if mode == "pass":
                self.event.set()

    async def wait(self) -> bool:
        async with self.lock:
            if self.mode not in {"hold", "hold_before_forward"}:
                return False
            self.reached += 1
            event = self.event
        await event.wait()
        async with self.lock:
            return self.abort

    async def release(self, *, abort: bool) -> None:
        async with self.lock:
            self.abort = abort
            self.mode = "pass"
            self.event.set()

    async def snapshot(self) -> dict[str, object]:
        async with self.lock:
            return {
                "mode": self.mode,
                "reached": self.reached,
                "released": self.event.is_set(),
                "abort": self.abort,
            }


class _Store:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(path, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        with self._connection:
            self._connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS provider_call (
                  idempotency_key TEXT PRIMARY KEY,
                  request_sha256 TEXT NOT NULL,
                  physical_calls INTEGER NOT NULL,
                  completed_calls INTEGER NOT NULL,
                  first_reached_at TEXT NOT NULL,
                  last_reached_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS callback_attempt (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  callback_kind TEXT NOT NULL,
                  run_id TEXT NOT NULL,
                  step_id TEXT NOT NULL,
                  job_id TEXT NOT NULL,
                  fencing_token INTEGER NOT NULL,
                  request_hash TEXT NOT NULL,
                  result_hash TEXT,
                  action TEXT NOT NULL,
                  core_status INTEGER,
                  receipt_status TEXT,
                  receipt_identity_matches INTEGER,
                  occurred_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS execution_submit_attempt (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  run_id TEXT,
                  step_id TEXT,
                  job_id TEXT,
                  fencing_token INTEGER,
                  request_hash TEXT,
                  body_sha256 TEXT NOT NULL,
                  agent_status INTEGER NOT NULL,
                  validation_errors_json TEXT NOT NULL,
                  occurred_at TEXT NOT NULL
                );
                """
            )

    def provider_reached(self, identity: ProviderIdentity) -> None:
        with self._lock, self._connection:
            row = self._connection.execute(
                "SELECT request_sha256 FROM provider_call WHERE idempotency_key = ?",
                (identity.idempotencyKey,),
            ).fetchone()
            if row is not None and row["request_sha256"] != identity.requestSha256:
                raise ValueError("供应商幂等键绑定了不同请求哈希")
            now = _now()
            self._connection.execute(
                """
                INSERT INTO provider_call (
                  idempotency_key, request_sha256, physical_calls, completed_calls,
                  first_reached_at, last_reached_at
                ) VALUES (?, ?, 1, 0, ?, ?)
                ON CONFLICT(idempotency_key) DO UPDATE SET
                  physical_calls = physical_calls + 1,
                  last_reached_at = excluded.last_reached_at
                """,
                (identity.idempotencyKey, identity.requestSha256, now, now),
            )

    def provider_completed(self, identity: ProviderIdentity) -> None:
        with self._lock, self._connection:
            updated = self._connection.execute(
                """
                UPDATE provider_call
                SET completed_calls = completed_calls + 1
                WHERE idempotency_key = ? AND request_sha256 = ?
                """,
                (identity.idempotencyKey, identity.requestSha256),
            ).rowcount
            if updated != 1:
                raise ValueError("供应商完成记录没有匹配的请求身份")

    def callback(
        self,
        *,
        kind: str,
        identity: dict[str, object],
        action: str,
        core_status: int | None = None,
        receipt_status: str | None = None,
        receipt_identity_matches: bool | None = None,
    ) -> None:
        with self._lock, self._connection:
            self._connection.execute(
                """
                INSERT INTO callback_attempt (
                  callback_kind, run_id, step_id, job_id, fencing_token,
                  request_hash, result_hash, action, core_status, receipt_status,
                  receipt_identity_matches, occurred_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    kind,
                    identity["runId"],
                    identity["stepId"],
                    identity["jobId"],
                    identity["fencingToken"],
                    identity["requestHash"],
                    identity.get("resultHash"),
                    action,
                    core_status,
                    receipt_status,
                    receipt_identity_matches,
                    _now(),
                ),
            )

    def execution_submit(
        self,
        *,
        identity: dict[str, object],
        body_sha256: str,
        agent_status: int,
        validation_errors: list[dict[str, object]],
    ) -> None:
        with self._lock, self._connection:
            self._connection.execute(
                """
                INSERT INTO execution_submit_attempt (
                  run_id, step_id, job_id, fencing_token, request_hash,
                  body_sha256, agent_status, validation_errors_json, occurred_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    identity.get("runId"),
                    identity.get("stepId"),
                    identity.get("jobId"),
                    identity.get("fencingToken"),
                    identity.get("requestHash"),
                    body_sha256,
                    agent_status,
                    json.dumps(
                        validation_errors,
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ),
                    _now(),
                ),
            )

    def snapshot(self) -> dict[str, object]:
        with self._lock:
            providers = [
                dict(row)
                for row in self._connection.execute(
                    "SELECT * FROM provider_call ORDER BY first_reached_at, idempotency_key"
                ).fetchall()
            ]
            callbacks = [
                dict(row)
                for row in self._connection.execute(
                    "SELECT * FROM callback_attempt ORDER BY id"
                ).fetchall()
            ]
            for callback in callbacks:
                matched = callback.get("receipt_identity_matches")
                if isinstance(matched, int):
                    callback["receipt_identity_matches"] = bool(matched)
            submissions = [
                {
                    **dict(row),
                    "validation_errors": json.loads(row["validation_errors_json"]),
                }
                for row in self._connection.execute(
                    "SELECT * FROM execution_submit_attempt ORDER BY id"
                ).fetchall()
            ]
            for submission in submissions:
                del submission["validation_errors_json"]
        return {
            "providerCalls": providers,
            "callbackAttempts": callbacks,
            "executionSubmitAttempts": submissions,
        }

    def reset(self) -> None:
        with self._lock, self._connection:
            self._connection.execute("DELETE FROM callback_attempt")
            self._connection.execute("DELETE FROM provider_call")
            self._connection.execute("DELETE FROM execution_submit_attempt")

    def close(self) -> None:
        with self._lock:
            self._connection.close()


def create_app() -> FastAPI:
    environment = os.environ.get("ENVIRONMENT", "")
    token = os.environ.get("E2E_EXECUTION_CONTROL_TOKEN", "")
    core_upstream = os.environ.get("E2E_CORE_UPSTREAM", "")
    agent_upstream = os.environ.get("E2E_AGENT_UPSTREAM", "")
    database_path = Path(os.environ.get("E2E_CONTROL_DATABASE", "/data/control.db"))
    if (
        environment != "test"
        or len(token.encode("utf-8")) < 32
        or not core_upstream.startswith("http://")
        or not agent_upstream.startswith("http://")
    ):
        raise RuntimeError("E2E 控制器缺少随机令牌或内部 Core/Agent 地址")
    store = _Store(database_path)
    provider_gate = _Gate()
    callback_gate = _Gate()
    execution_gate = _Gate()
    callback_mode = {"value": "pass", "dropRemaining": 0}
    callback_mode_lock = asyncio.Lock()
    core_http = httpx.AsyncClient(
        base_url=core_upstream,
        timeout=httpx.Timeout(30.0, connect=2.0),
        limits=httpx.Limits(max_connections=4, max_keepalive_connections=2),
        trust_env=False,
    )
    agent_http = httpx.AsyncClient(
        base_url=agent_upstream,
        timeout=httpx.Timeout(30.0, connect=2.0),
        limits=httpx.Limits(max_connections=4, max_keepalive_connections=2),
        trust_env=False,
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        try:
            yield
        finally:
            await core_http.aclose()
            await agent_http.aclose()
            store.close()

    app = FastAPI(
        title="InkForge Durable Agent V2 E2E 控制器",
        openapi_url=None,
        docs_url=None,
        redoc_url=None,
        lifespan=lifespan,
    )

    def authorize(value: str | None) -> None:
        if value != token:
            raise HTTPException(status_code=403, detail="E2E 控制令牌无效")

    def forwarded_headers(request: Request) -> dict[str, str]:
        return {
            key: value
            for key, value in request.headers.items()
            if key.lower()
            not in {"host", "content-length", "connection", "transfer-encoding"}
        }

    def response_headers(response: httpx.Response) -> dict[str, str]:
        return {
            key: value
            for key, value in response.headers.items()
            if key.lower()
            not in {"content-length", "connection", "transfer-encoding"}
        }

    @app.get("/health/live")
    async def live() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/internal/v1/health/{health_kind}")
    async def proxy_agent_health(
        health_kind: Literal["live", "ready"], request: Request
    ) -> Response:
        try:
            upstream_response = await agent_http.get(
                request.url.path,
                headers=forwarded_headers(request),
            )
        except httpx.HTTPError:
            return JSONResponse(status_code=503, content={"detail": "Agent 暂时不可用"})
        return Response(
            status_code=upstream_response.status_code,
            content=upstream_response.content,
            headers=response_headers(upstream_response),
        )

    @app.post("/internal/v1/runs")
    async def proxy_agent_post_transport_probe(request: Request) -> Response:
        body = await request.body()
        try:
            upstream_response = await agent_http.post(
                request.url.path,
                content=body,
                headers=forwarded_headers(request),
            )
        except httpx.HTTPError:
            return JSONResponse(status_code=503, content={"detail": "Agent 暂时不可用"})
        return Response(
            status_code=upstream_response.status_code,
            content=upstream_response.content,
            headers=response_headers(upstream_response),
        )

    @app.post("/control/provider/reached")
    async def provider_reached(
        body: ProviderIdentity,
        control_token: Annotated[str | None, Header(alias="X-InkForge-E2E-Token")] = None,
    ) -> dict[str, str]:
        authorize(control_token)
        try:
            store.provider_reached(body)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from None
        if await provider_gate.wait():
            raise HTTPException(status_code=503, detail="E2E provider gate 已中止")
        return {"status": "proceed"}

    @app.post("/control/provider/completed")
    async def provider_completed(
        body: ProviderIdentity,
        control_token: Annotated[str | None, Header(alias="X-InkForge-E2E-Token")] = None,
    ) -> dict[str, str]:
        authorize(control_token)
        try:
            store.provider_completed(body)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from None
        return {"status": "recorded"}

    @app.put("/control/provider-mode")
    async def set_provider_mode(
        body: GateRequest,
        control_token: Annotated[str | None, Header(alias="X-InkForge-E2E-Token")] = None,
    ) -> dict[str, str]:
        authorize(control_token)
        await provider_gate.configure(body.mode)
        return {"mode": body.mode}

    @app.put("/control/callback-mode")
    async def set_callback_mode(
        body: CallbackModeRequest,
        control_token: Annotated[str | None, Header(alias="X-InkForge-E2E-Token")] = None,
    ) -> dict[str, str]:
        authorize(control_token)
        async with callback_mode_lock:
            callback_mode["value"] = body.mode
            callback_mode["dropRemaining"] = (
                1 if body.mode == "drop_after_forward_once" else 0
            )
        await callback_gate.configure(
            "hold_before_forward" if body.mode == "hold_before_forward" else "pass"
        )
        return {"mode": body.mode}

    @app.put("/control/execution-mode")
    async def set_execution_mode(
        body: GateRequest,
        control_token: Annotated[str | None, Header(alias="X-InkForge-E2E-Token")] = None,
    ) -> dict[str, str]:
        authorize(control_token)
        await execution_gate.configure(body.mode)
        return {"mode": body.mode}

    @app.post("/control/provider-release")
    async def release_provider(
        body: ReleaseRequest,
        control_token: Annotated[str | None, Header(alias="X-InkForge-E2E-Token")] = None,
    ) -> dict[str, object]:
        authorize(control_token)
        await provider_gate.release(abort=body.abort)
        return {"released": True, "abort": body.abort}

    @app.post("/control/callback-release")
    async def release_callback(
        body: ReleaseRequest,
        control_token: Annotated[str | None, Header(alias="X-InkForge-E2E-Token")] = None,
    ) -> dict[str, object]:
        authorize(control_token)
        await callback_gate.release(abort=body.abort)
        async with callback_mode_lock:
            callback_mode["value"] = "pass"
        return {"released": True, "abort": body.abort}

    @app.post("/control/execution-release")
    async def release_execution(
        body: ReleaseRequest,
        control_token: Annotated[str | None, Header(alias="X-InkForge-E2E-Token")] = None,
    ) -> dict[str, object]:
        authorize(control_token)
        await execution_gate.release(abort=body.abort)
        return {"released": True, "abort": body.abort}

    @app.post("/control/reset")
    async def reset(
        control_token: Annotated[str | None, Header(alias="X-InkForge-E2E-Token")] = None,
    ) -> dict[str, str]:
        authorize(control_token)
        store.reset()
        await provider_gate.configure("pass")
        await callback_gate.configure("pass")
        await execution_gate.configure("pass")
        async with callback_mode_lock:
            callback_mode["value"] = "pass"
            callback_mode["dropRemaining"] = 0
        return {"status": "reset"}

    @app.get("/control/state")
    async def state(
        control_token: Annotated[str | None, Header(alias="X-InkForge-E2E-Token")] = None,
    ) -> dict[str, object]:
        authorize(control_token)
        async with callback_mode_lock:
            mode_snapshot = dict(callback_mode)
        return {
            **store.snapshot(),
            "providerGate": await provider_gate.snapshot(),
            "callbackGate": await callback_gate.snapshot(),
            "executionGate": await execution_gate.snapshot(),
            "callbackMode": mode_snapshot,
        }

    @app.post("/internal/v1/executions")
    async def proxy_execution_submit(request: Request) -> Response:
        """透明转发 Core 请求，只持久化安全身份与 422 loc/type。"""

        body = await request.body()
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            payload = {}
        identity = {
            key: payload.get(key) if isinstance(payload, dict) else None
            for key in ("runId", "stepId", "jobId", "fencingToken", "requestHash")
        }
        body_sha256 = hashlib.sha256(body).hexdigest()
        if await execution_gate.wait():
            store.execution_submit(
                identity=identity,
                body_sha256=body_sha256,
                agent_status=503,
                validation_errors=[],
            )
            return JSONResponse(
                status_code=503,
                content={"detail": "E2E execution submit 已在转发前中止"},
            )
        try:
            upstream_response = await agent_http.post(
                request.url.path,
                content=body,
                headers=forwarded_headers(request),
            )
        except httpx.HTTPError:
            return JSONResponse(status_code=503, content={"detail": "Agent 暂时不可用"})

        validation_errors: list[dict[str, object]] = []
        if upstream_response.status_code == 422:
            try:
                response_body = upstream_response.json()
            except ValueError:
                response_body = None
            details = response_body.get("detail") if isinstance(response_body, dict) else None
            if isinstance(details, list):
                for detail in details:
                    if not isinstance(detail, dict):
                        continue
                    location = detail.get("loc")
                    error_type = detail.get("type")
                    if (
                        isinstance(location, list)
                        and all(isinstance(item, (str, int)) for item in location)
                        and isinstance(error_type, str)
                    ):
                        validation_errors.append({"loc": location, "type": error_type})
        store.execution_submit(
            identity=identity,
            body_sha256=body_sha256,
            agent_status=upstream_response.status_code,
            validation_errors=validation_errors,
        )
        return Response(
            status_code=upstream_response.status_code,
            content=upstream_response.content,
            headers=response_headers(upstream_response),
        )

    @app.put("/internal/v1/executions/{job_id}/cancel")
    async def proxy_execution_cancel(job_id: str, request: Request) -> Response:
        body = await request.body()
        path = f"/internal/v1/executions/{job_id}/cancel"
        try:
            upstream_response = await agent_http.put(
                path,
                content=body,
                headers=forwarded_headers(request),
            )
        except httpx.HTTPError:
            return JSONResponse(status_code=503, content={"detail": "Agent 暂时不可用"})
        return Response(
            status_code=upstream_response.status_code,
            content=upstream_response.content,
            headers=response_headers(upstream_response),
        )

    @app.api_route(
        "/internal/v1/workflow-runs/{run_id}/steps/{step_id}/{callback_kind}",
        methods=["PUT"],
    )
    async def proxy_callback(
        run_id: str,
        step_id: str,
        callback_kind: Literal["progress", "result", "failure"],
        request: Request,
    ) -> Response:
        body = await request.body()
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            return JSONResponse(status_code=400, content={"detail": "回调 JSON 无效"})
        identity = {
            "runId": payload.get("runId"),
            "stepId": payload.get("stepId"),
            "jobId": payload.get("jobId"),
            "fencingToken": payload.get("fencingToken"),
            "requestHash": payload.get("requestHash"),
            "resultHash": payload.get("resultHash"),
        }
        if (
            identity["runId"] != run_id
            or identity["stepId"] != step_id
            or not isinstance(identity["jobId"], str)
            or not isinstance(identity["fencingToken"], int)
            or not isinstance(identity["requestHash"], str)
            or (
                callback_kind in {"result", "failure"}
                and not isinstance(identity["resultHash"], str)
            )
        ):
            return JSONResponse(status_code=409, content={"detail": "回调身份不一致"})

        terminal = callback_kind in {"result", "failure"}
        async with callback_mode_lock:
            current_mode = str(callback_mode["value"])
        if terminal and current_mode == "hold_before_forward":
            store.callback(kind=callback_kind, identity=identity, action="held_before_forward")
            if await callback_gate.wait():
                store.callback(
                    kind=callback_kind,
                    identity=identity,
                    action="aborted_before_forward",
                )
                return JSONResponse(status_code=503, content={"detail": "E2E callback 已中止"})

        path = request.url.path
        try:
            upstream_response = await core_http.put(
                path,
                content=body,
                headers=forwarded_headers(request),
            )
        except httpx.HTTPError:
            store.callback(kind=callback_kind, identity=identity, action="core_unavailable")
            return JSONResponse(status_code=503, content={"detail": "Core 暂时不可用"})
        receipt_status: str | None = None
        receipt_identity_matches: bool | None = None
        try:
            receipt = upstream_response.json()
            value = receipt.get("status") if isinstance(receipt, dict) else None
            receipt_status = value if isinstance(value, str) else None
            if isinstance(receipt, dict):
                receipt_identity_matches = (
                    receipt.get("protocolVersion") == "2.0"
                    and receipt.get("runId") == identity["runId"]
                    and receipt.get("stepId") == identity["stepId"]
                    and receipt.get("jobId") == identity["jobId"]
                    and receipt.get("fencingToken") == identity["fencingToken"]
                    and receipt.get("requestHash") == identity["requestHash"]
                )
        except ValueError:
            pass

        should_drop = False
        async with callback_mode_lock:
            remaining = callback_mode["dropRemaining"]
            if terminal and isinstance(remaining, int) and remaining > 0:
                callback_mode["dropRemaining"] = remaining - 1
                callback_mode["value"] = "pass"
                should_drop = True
        store.callback(
            kind=callback_kind,
            identity=identity,
            action="dropped_after_forward" if should_drop else "forwarded",
            core_status=upstream_response.status_code,
            receipt_status=receipt_status,
            receipt_identity_matches=receipt_identity_matches,
        )
        if should_drop:
            return JSONResponse(
                status_code=503,
                content={"detail": "E2E 已在 Core 回执后丢弃响应"},
            )
        return Response(
            status_code=upstream_response.status_code,
            content=upstream_response.content,
            headers=response_headers(upstream_response),
        )

    return app
