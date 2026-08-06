from __future__ import annotations

from typing import Any

import pytest
from fastapi import FastAPI
from inkforge_core import app as app_module
from inkforge_core.config import create_testing_settings
from inkforge_core.reviews import decision_orchestrator as decision_module


class _UnusedRepository:
    def __init__(self, session_factory: object) -> None:
        del session_factory


class _RecordingReferences:
    def __init__(self) -> None:
        self.index_enabled: list[bool] = []

    async def apply_reference_mutations(
        self,
        novel_id: str,
        user_id: str,
        mutations: list[object],
        *,
        index_enabled: bool = False,
    ) -> list[dict[str, Any]]:
        del novel_id, user_id, mutations
        self.index_enabled.append(index_enabled)
        return []


@pytest.mark.asyncio
@pytest.mark.parametrize("index_enabled", [True, False])
async def test_default_decision_dependencies_forward_rag_configuration(
    monkeypatch: pytest.MonkeyPatch,
    index_enabled: bool,
) -> None:
    references = _RecordingReferences()
    monkeypatch.setattr(decision_module, "LoreRepository", _UnusedRepository)
    monkeypatch.setattr(decision_module, "OutlineRepository", _UnusedRepository)
    monkeypatch.setattr(decision_module, "ReferenceRepository", lambda _factory: references)

    dependencies = decision_module._build_dependencies(  # noqa: SLF001
        object(),
        reference_index_enabled=index_enabled,
    )
    updates_executor = dependencies.service._applier._updates_executor  # type: ignore[attr-defined]  # noqa: SLF001

    await updates_executor.apply(
        "novel-1",
        "user-1",
        {
            "references": [
                {
                    "action": "create",
                    "clientRequestId": "reference-create-0001",
                    "title": "参考资料",
                    "type": "note",
                    "content": "正文",
                }
            ]
        },
    )

    assert references.index_enabled == [index_enabled]


@pytest.mark.parametrize("index_enabled", [True, False])
def test_app_passes_effective_rag_configuration_to_decision_orchestrator(
    monkeypatch: pytest.MonkeyPatch,
    index_enabled: bool,
) -> None:
    captured: list[bool] = []

    class _RecordingOrchestrator:
        def __init__(
            self,
            session_factory: object,
            **kwargs: object,
        ) -> None:
            del session_factory
            captured.append(bool(kwargs["reference_index_enabled"]))

    monkeypatch.setattr(
        app_module,
        "ReviewDecisionOrchestrator",
        _RecordingOrchestrator,
    )
    settings = create_testing_settings().model_copy(
        update={"rag_index_enabled": index_enabled}
    )
    app = FastAPI()
    app.state.settings = settings
    app.state.database_session_factory = object()
    app.state.agent_client = object()

    app_module._configure_business_services(app, settings)  # noqa: SLF001

    assert captured == [index_enabled]
