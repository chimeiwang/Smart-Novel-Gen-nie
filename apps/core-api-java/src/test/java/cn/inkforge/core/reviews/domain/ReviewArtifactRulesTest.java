package cn.inkforge.core.reviews.domain;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import cn.inkforge.core.platform.http.ApiException;
import java.time.OffsetDateTime;
import java.util.LinkedHashMap;
import java.util.Map;
import org.junit.jupiter.api.Test;

class ReviewArtifactRulesTest {

    @Test
    void 状态机只允许冻结的有向流转且applied不可重新打开() {
        assertThat(ReviewArtifactRules.canTransition("draft", "under_review")).isTrue();
        assertThat(ReviewArtifactRules.canTransition("awaiting_user", "applying")).isTrue();
        assertThat(ReviewArtifactRules.canTransition("applying", "applied")).isTrue();
        assertThat(ReviewArtifactRules.canTransition("applied", "draft")).isFalse();
        assertThatThrownBy(() -> ReviewArtifactRules.requireTransition("draft", "applied"))
                .isInstanceOfSatisfying(ApiException.class, error ->
                        assertThat(error.code()).isEqualTo("ARTIFACT_STATUS_CONFLICT"));
    }

    @Test
    void payload必须绑定kind且Agent不能注入Core控制字段() {
        assertThatThrownBy(() -> ReviewArtifactRules.requireAgentPayload(
                        "chapter_draft", Map.of("kind", "outline_draft")))
                .isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> ReviewArtifactRules.requireAgentPayload(
                        "chapter_draft",
                        Map.of("kind", "chapter_draft", "_inkforgeControl", Map.of())))
                .isInstanceOf(IllegalArgumentException.class);
    }

    @Test
    void 选区冻结必须按Unicode码点生成完整候选与可审核Diff() {
        String source = "甲😀乙丙";
        OffsetDateTime updatedAt = OffsetDateTime.parse("2026-08-25T00:00:00Z");
        Map<String, Object> target = new LinkedHashMap<>();
        target.put("mode", "replace_selection");
        target.put("resourceType", "chapter_content");
        target.put("resourceId", "chapter-1");
        target.put("baseUpdatedAt", updatedAt.toString());
        target.put("baseContentHash", ReviewArtifactRules.sha256(source));
        target.put("selectionStart", 1);
        target.put("selectionEnd", 3);
        target.put("selectedTextHash", ReviewArtifactRules.sha256("😀乙"));
        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("kind", "chapter_draft");
        payload.put("target", target);
        payload.put("replacement", "新😀段");

        SelectionMaterialization result = ReviewArtifactRules.materializeSelection(
                payload,
                "chapter_draft",
                new SelectionSource(
                        "chapter_content", "chapter-1", source, updatedAt));

        assertThat(result.payload())
                .containsEntry("selectedText", "😀乙")
                .containsEntry("candidatePrefix", "甲")
                .containsEntry("candidateSuffix", "丙")
                .containsEntry("candidate", "甲新😀段丙");
        assertThat(result.diff())
                .containsEntry("type", "selection")
                .containsEntry("before", source)
                .containsEntry("after", "甲新😀段丙");
    }

    @Test
    void 选区来源版本变化必须明确冲突而不是自动变基() {
        OffsetDateTime updatedAt = OffsetDateTime.parse("2026-08-25T00:00:00Z");
        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("kind", "outline_draft");
        payload.put("target", Map.ofEntries(
                Map.entry("mode", "outline_content_selection"),
                Map.entry("resourceType", "outline_content"),
                Map.entry("resourceId", "outline-1"),
                Map.entry("baseUpdatedAt", updatedAt.toString()),
                Map.entry("baseContentHash", ReviewArtifactRules.sha256("旧正文")),
                Map.entry("selectionStart", 0),
                Map.entry("selectionEnd", 1),
                Map.entry("selectedTextHash", ReviewArtifactRules.sha256("旧"))));
        payload.put("replacement", "新");

        assertThatThrownBy(() -> ReviewArtifactRules.materializeSelection(
                        payload,
                        "outline_draft",
                        new SelectionSource(
                                "outline_content", "outline-1", "已变化", updatedAt)))
                .isInstanceOfSatisfying(ApiException.class, error ->
                        assertThat(error.code())
                                .isEqualTo("ARTIFACT_SOURCE_VERSION_CONFLICT"));
    }
}
