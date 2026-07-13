from inkforge_agents.operations.definitions import OPERATION_DEFINITIONS


def test_all_creative_operations_have_authoritative_definitions() -> None:
    assert set(OPERATION_DEFINITIONS) == {
        "answer_question",
        "create_lore",
        "revise_lore",
        "create_outline",
        "revise_outline",
        "plan_chapter",
        "write_chapter",
        "rewrite_scene",
        "review_chapter",
        "manage_foreshadowing",
    }
    assert OPERATION_DEFINITIONS["write_chapter"].primaryAgent == "写作"
    assert OPERATION_DEFINITIONS["write_chapter"].reviewers == ("校验", "编辑")
    assert OPERATION_DEFINITIONS["write_chapter"].textArtifactKind == "chapter_draft"
    assert OPERATION_DEFINITIONS["answer_question"].requiresArtifact is False


def test_every_persisted_operation_requires_user_approval() -> None:
    for definition in OPERATION_DEFINITIONS.values():
        if definition.requiresArtifact:
            assert definition.requiresUserApproval is True
            assert definition.artifactPolicy != "none"
