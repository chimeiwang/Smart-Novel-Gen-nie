from __future__ import annotations

AGENT_CAPABILITIES: dict[str, frozenset[str]] = {
    "设定": frozenset(
        {
            "novel.read",
            "character.read",
            "lore.read",
            "plot.read",
            "artifact.read",
            "proposal.lore",
            "control.proposal",
            "control.builder",
            "control.artifact",
        }
    ),
    "剧情": frozenset(
        {
            "novel.read",
            "character.read",
            "lore.read",
            "plot.read",
            "chapter.read",
            "artifact.read",
            "proposal.plot",
            "control.proposal",
            "control.builder",
            "control.artifact",
            "control.beat",
            "control.short_outline",
        }
    ),
    "写作": frozenset(
        {
            "novel.read",
            "character.read",
            "lore.read",
            "plot.read",
            "chapter.read",
            "style.read",
            "artifact.read",
            "control.artifact",
        }
    ),
    "校验": frozenset(
        {
            "novel.read",
            "character.read",
            "plot.read",
            "lore.read",
            "artifact.read",
            "control.artifact",
            "control.validation",
            "control.evaluation",
            "control.quality",
        }
    ),
    "编辑": frozenset(
        {
            "novel.read",
            "character.read",
            "plot.read",
            "chapter.read",
            "style.read",
            "artifact.read",
            "control.artifact",
            "control.evaluation",
        }
    ),
}
