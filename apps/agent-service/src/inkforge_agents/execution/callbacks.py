"""V2 execution 向 Core 发送严格、签名且幂等的阶段与终态回调。"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

import httpx
from inkforge_contracts.execution import (
    ExecutionCallbackKind,
    ExecutionCallbackReceipt,
    ExecutionStepFailure,
    ExecutionStepProgress,
    ExecutionStepResult,
    execution_callback_path,
)
from inkforge_contracts.jwt_claims import ServiceScope
from inkforge_service_auth import SignedServiceRequest, canonical_json_body

ExecutionCallback = ExecutionStepProgress | ExecutionStepResult | ExecutionStepFailure


class ExecutionRequestSigner(Protocol):
    def sign_request(
        self,
        *,
        body: bytes,
        http_method: str,
        http_path: str,
        query_string: bytes,
        idempotency_key: str,
        scope: Sequence[ServiceScope],
        task_id: str,
        run_id: str,
        novel_id: str | None,
    ) -> SignedServiceRequest: ...


class ExecutionCallbackError(RuntimeError):
    def __init__(self, code: str, *, retryable: bool) -> None:
        self.code = code
        self.retryable = retryable
        super().__init__(code)


class ExecutionCallbackClient:
    def __init__(self, http: httpx.AsyncClient, signer: ExecutionRequestSigner) -> None:
        self._http = http
        self._signer = signer

    async def send_progress(
        self,
        progress: ExecutionStepProgress,
    ) -> ExecutionCallbackReceipt:
        return await self._send(
            progress,
            callback_kind="progress",
            scope=ServiceScope.EXECUTION_PROGRESS,
            idempotency_key=progress.progressId,
        )

    async def send_result(
        self,
        result: ExecutionStepResult,
    ) -> ExecutionCallbackReceipt:
        return await self._send(
            result,
            callback_kind="result",
            scope=ServiceScope.EXECUTION_RESULT,
            idempotency_key=f"result:{result.resultHash}",
        )

    async def send_failure(
        self,
        failure: ExecutionStepFailure,
    ) -> ExecutionCallbackReceipt:
        return await self._send(
            failure,
            callback_kind="failure",
            scope=ServiceScope.EXECUTION_RESULT,
            idempotency_key=f"failure:{failure.resultHash}",
        )

    async def _send(
        self,
        callback: ExecutionCallback,
        *,
        callback_kind: ExecutionCallbackKind,
        scope: ServiceScope,
        idempotency_key: str,
    ) -> ExecutionCallbackReceipt:
        path = execution_callback_path(
            run_id=callback.runId,
            step_id=callback.stepId,
            callback_kind=callback_kind,
        )
        payload = callback.model_dump(mode="json", by_alias=True, exclude_none=True)
        body = canonical_json_body(payload)
        signed = self._signer.sign_request(
            body=body,
            http_method="PUT",
            http_path=path,
            query_string=b"",
            idempotency_key=idempotency_key,
            scope=(scope,),
            task_id=callback.stepId,
            run_id=callback.runId,
            novel_id=callback.novelId,
        )
        try:
            response = await self._http.request(
                "PUT",
                path,
                content=body,
                headers={**signed.headers, "Content-Type": "application/json"},
            )
        except httpx.HTTPError:
            raise ExecutionCallbackError(
                "EXECUTION_CALLBACK_UNAVAILABLE",
                retryable=True,
            ) from None
        if response.status_code >= 500:
            raise ExecutionCallbackError(
                "EXECUTION_CALLBACK_UNAVAILABLE",
                retryable=True,
            )
        if response.status_code in {408, 425, 429}:
            raise ExecutionCallbackError(
                "EXECUTION_CALLBACK_UNAVAILABLE",
                retryable=True,
            )
        if 400 <= response.status_code < 500:
            raise ExecutionCallbackError(
                "EXECUTION_CALLBACK_REJECTED",
                retryable=False,
            )
        if response.status_code != 200:
            # 201/202/204、重定向或其他非约定状态都不能证明 Core 已提交；
            # 终态仍留在 journal，由独立 replayer 继续对账。
            raise ExecutionCallbackError(
                "EXECUTION_CALLBACK_RECEIPT_INVALID",
                retryable=True,
            )
        try:
            receipt = ExecutionCallbackReceipt.model_validate_json(response.content)
        except ValueError:
            raise ExecutionCallbackError(
                "EXECUTION_CALLBACK_RECEIPT_INVALID",
                retryable=True,
            ) from None
        expected = (
            callback.runId,
            callback.stepId,
            callback.jobId,
            callback.fencingToken,
            callback.requestHash,
        )
        actual = (
            receipt.runId,
            receipt.stepId,
            receipt.jobId,
            receipt.fencingToken,
            receipt.requestHash,
        )
        if actual != expected:
            raise ExecutionCallbackError(
                "EXECUTION_CALLBACK_RECEIPT_MISMATCH",
                retryable=False,
            )
        return receipt
