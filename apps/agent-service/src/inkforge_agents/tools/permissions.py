from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ToolPermission:
    readOnly: bool
    concurrencySafe: bool
    requiresConfirmation: bool
    capability: str
    agentIds: frozenset[str] | None = None

    def allows(self, agent_id: str, capabilities: set[str] | frozenset[str]) -> bool:
        return self.capability in capabilities and (
            self.agentIds is None or agent_id in self.agentIds
        )


def read_only_permission(capability: str, agent_ids: set[str] | None = None) -> ToolPermission:
    return ToolPermission(
        readOnly=True,
        concurrencySafe=True,
        requiresConfirmation=False,
        capability=capability,
        agentIds=frozenset(agent_ids) if agent_ids else None,
    )


def proposal_permission(capability: str, agent_ids: set[str] | None = None) -> ToolPermission:
    return ToolPermission(
        readOnly=False,
        concurrencySafe=False,
        requiresConfirmation=True,
        capability=capability,
        agentIds=frozenset(agent_ids) if agent_ids else None,
    )


def control_permission(capability: str, agent_ids: set[str] | None = None) -> ToolPermission:
    return ToolPermission(
        readOnly=True,
        concurrencySafe=False,
        requiresConfirmation=False,
        capability=capability,
        agentIds=frozenset(agent_ids) if agent_ids else None,
    )
