package cn.inkforge.core.workflows.domain;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import cn.inkforge.core.platform.http.ApiException;
import java.time.OffsetDateTime;
import java.util.LinkedHashMap;
import org.junit.jupiter.api.Test;

final class DurableOutlineSelectionArtifactTest {
    private static final OffsetDateTime UPDATED_AT =
            OffsetDateTime.parse("2026-09-05T08:00:00+08:00");

    @Test
    void 总纲Unicode选区使用独立持久Schema并重建完整Diff() {
        String source = "序章😀转折\n结局";
        String selected = "😀转折";
        String replacement = "新转折";
        String candidate = "序章" + replacement + "\n结局";
        var stored = create("outline_content", "outline-1", source, selected, replacement, candidate);

        assertThat(stored.payload())
                .containsEntry("schema", DurableOutlineSelectionArtifact.SCHEMA)
                .containsEntry("kind", "outline_draft")
                .containsEntry("operation", "rewrite_outline_selection")
                .doesNotContainKeys("selectedText", "candidate", "candidatePrefix", "candidateSuffix");
        var materialized = DurableOutlineSelectionArtifact.reconstruct(
                stored.payload(), stored.diff(), evidence("outline_content", "outline-1", source));
        assertThat(materialized.payload())
                .containsEntry("replacement", replacement)
                .containsEntry("candidate", candidate);
        assertThat(materialized.payload().get("target"))
                .isEqualTo(java.util.Map.of(
                        "mode", "outline_content_selection",
                        "resourceType", "outline_content",
                        "resourceId", "outline-1",
                        "baseUpdatedAt", UPDATED_AT.toString(),
                        "baseContentHash", DurableSelectionArtifact.sha256(source),
                        "selectionStart", 2,
                        "selectionEnd", 5,
                        "selectedTextHash", DurableSelectionArtifact.sha256(selected)));
        assertThat(materialized.diff())
                .containsEntry("before", source)
                .containsEntry("after", candidate)
                .containsEntry("mode", "outline_content_selection");
    }

    @Test
    void 节点选区编辑只改replacement并重算候选哈希() {
        String source = "甲😀乙";
        var base = create(
                "outline_node_content", "node-1", source, "😀", "旧", "甲旧乙", 1, 2);
        var edited = DurableOutlineSelectionArtifact.withCandidateHash(
                DurableOutlineSelectionArtifact.edit(base, "新🚀"),
                DurableSelectionArtifact.sha256("甲新🚀乙"));
        var materialized = DurableOutlineSelectionArtifact.reconstruct(
                edited.payload(), edited.diff(), evidence("outline_node_content", "node-1", source, 1, 2));

        assertThat(materialized.payload().get("target"))
                .isEqualTo(java.util.Map.of(
                        "mode", "outline_node_content_selection",
                        "resourceType", "outline_node_content",
                        "resourceId", "node-1",
                        "baseUpdatedAt", UPDATED_AT.toString(),
                        "baseContentHash", DurableSelectionArtifact.sha256(source),
                        "selectionStart", 1,
                        "selectionEnd", 2,
                        "selectedTextHash", DurableSelectionArtifact.sha256("😀")));
        assertThat(materialized.diff()).containsEntry("after", "甲新🚀乙");
    }

    @Test
    void 严格拒绝章节类型越界伪哈希和交叉资源Evidence() {
        String source = "甲😀乙";
        assertThatThrownBy(() -> create(
                        "chapter_content", "chapter-1", source, "😀", "新", "甲新乙"))
                .isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> create(
                        "outline_content", "outline-1", source, "😀",
                        "\u0085\uFEFF　", "甲\u0085\uFEFF　乙", 1, 2))
                .isInstanceOf(IllegalArgumentException.class);
        var stored = create("outline_content", "outline-1", source, "😀", "新", "甲新乙", 1, 2);
        assertThatThrownBy(() -> DurableOutlineSelectionArtifact.reconstruct(
                        stored.payload(), stored.diff(), evidence("outline_content", "outline-2", source, 1, 2)))
                .isInstanceOf(ApiException.class);
        var tampered = new LinkedHashMap<>(stored.payload());
        tampered.put("candidateSha256", "f".repeat(64));
        assertThatThrownBy(() -> DurableOutlineSelectionArtifact.reconstruct(
                        tampered, stored.diff(), evidence("outline_content", "outline-1", source, 1, 2)))
                .isInstanceOf(ApiException.class);
    }

    private static DurableOutlineSelectionArtifact.Stored create(
            String type, String id, String source, String selected, String replacement, String candidate) {
        return create(type, id, source, selected, replacement, candidate, 2, 5);
    }

    private static DurableOutlineSelectionArtifact.Stored create(
            String type, String id, String source, String selected, String replacement, String candidate,
            int start, int end) {
        return DurableOutlineSelectionArtifact.create(
                "bundle-1", "evidence-1", type, id, UPDATED_AT,
                DurableSelectionArtifact.sha256(source), start, end,
                DurableSelectionArtifact.sha256(selected), replacement,
                DurableSelectionArtifact.sha256(replacement),
                DurableSelectionArtifact.sha256(candidate), "step-1", "a".repeat(64));
    }

    private static DurableOutlineSelectionArtifact.Evidence evidence(
            String type, String id, String source) {
        return evidence(type, id, source, 2, 5);
    }

    private static DurableOutlineSelectionArtifact.Evidence evidence(
            String type, String id, String source, int start, int end) {
        return new DurableOutlineSelectionArtifact.Evidence(
                "bundle-1", "evidence-1", type, id, UPDATED_AT, source,
                DurableSelectionArtifact.sha256(source), start, end);
    }
}
