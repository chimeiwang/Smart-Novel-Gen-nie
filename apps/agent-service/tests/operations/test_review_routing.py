# ruff: noqa: E501

from inkforge_agents.operations.graph import ReviewResult, decide_review_outcome


def test_review_outcome_priority_is_block_then_revise_then_pass() -> None:
    outcome = decide_review_outcome(
        [
            ReviewResult(
                reviewer="校验",
                verdict="revise",
                summary="需要小修",
                revisionMode="patch",
                patches=[{"kind": "text_replace", "find": "甲", "replace": "乙"}],
            ),
            ReviewResult(reviewer="编辑", verdict="block", summary="方向错误"),
        ]
    )
    assert outcome.verdict == "block"
    assert outcome.revisionMode is None


def test_patch_only_reviews_remain_patch_and_keep_reviewer_order() -> None:
    patch = decide_review_outcome(
        [
            ReviewResult(
                reviewer="校验",
                verdict="revise",
                summary="错字",
                revisionMode="patch",
                patches=[{"kind": "text_replace", "find": "甲", "replace": "乙"}],
            ),
            ReviewResult(
                reviewer="编辑",
                verdict="revise",
                summary="病句",
                revisionMode="patch",
                patches=[{"kind": "text_replace", "find": "丙", "replace": "丁"}],
            ),
        ]
    )
    assert patch.revisionMode == "patch"
    assert len(patch.patches) == 2
    assert "校验：错字" in (patch.requiredChanges or "")
    assert "编辑：病句" in (patch.requiredChanges or "")


def test_reviewer_order_is_deterministic_when_parallel_results_are_returned_out_of_order() -> None:
    outcome = decide_review_outcome(
        [
            ReviewResult(
                reviewer="编辑",
                verdict="revise",
                summary="编辑意见",
                revisionMode="patch",
                patches=[{"kind": "text_replace", "find": "丙", "replace": "丁"}],
            ),
            ReviewResult(
                reviewer="校验",
                verdict="revise",
                summary="校验意见",
                revisionMode="patch",
                patches=[{"kind": "text_replace", "find": "甲", "replace": "乙"}],
            ),
        ],
        reviewer_order=("校验", "编辑"),
    )

    assert outcome.revisionMode == "patch"
    assert outcome.summary == "校验：校验意见\n编辑：编辑意见"
    assert [item.find for item in outcome.patches] == ["甲", "丙"]

    rewrite = decide_review_outcome(
        [
            ReviewResult(
                reviewer="校验", verdict="revise", summary="结构问题", revisionMode="rewrite"
            ),
            ReviewResult(reviewer="编辑", verdict="pass", summary="商业性通过"),
        ]
    )
    assert rewrite.revisionMode == "rewrite"
