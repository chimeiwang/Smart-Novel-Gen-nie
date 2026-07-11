from __future__ import annotations

from ..providers.base import ModelProvider, ModelTurnRequest, ModelTurnResult


class ModelRuntime:
    def __init__(self, provider: ModelProvider) -> None:
        self._provider = provider

    async def run_turn(self, request: ModelTurnRequest) -> ModelTurnResult:
        return await self._provider.complete_turn(request)
