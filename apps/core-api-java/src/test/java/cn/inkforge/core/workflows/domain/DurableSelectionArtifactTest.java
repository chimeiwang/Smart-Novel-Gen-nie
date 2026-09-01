package cn.inkforge.core.workflows.domain;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import cn.inkforge.core.platform.http.ApiException;
import java.time.OffsetDateTime;
import java.util.LinkedHashMap;
import org.junit.jupiter.api.Test;

final class DurableSelectionArtifactTest {

    private static final OffsetDateTime UPDATED_AT =
            OffsetDateTime.parse("2026-09-01T08:00:00+08:00");

    @Test
    void 只保存最小事实并从不可变Evidence重建完整Unicode候选与Diff() {
        String source = "甲😀乙\n丙丁";
        String selected = "😀乙";
        String replacement = "新段落";
        String candidate = "甲" + replacement + "\n丙丁";
        DurableSelectionArtifact.Stored stored = DurableSelectionArtifact.create(
                "bundle-1",
                "evidence-1",
                "chapter-1",
                UPDATED_AT,
                DurableSelectionArtifact.sha256(source),
                1,
                3,
                DurableSelectionArtifact.sha256(selected),
                replacement,
                DurableSelectionArtifact.sha256(replacement),
                DurableSelectionArtifact.sha256(candidate),
                "step-1",
                "a".repeat(64));

        assertThat(stored.payload())
                .doesNotContainKeys(
                        "selectedText",
                        "contextBefore",
                        "contextAfter",
                        "candidate",
                        "candidatePrefix",
                        "candidateSuffix");
        assertThat(stored.diff())
                .doesNotContainKeys("before", "after", "candidate", "prefix", "suffix");

        DurableSelectionArtifact.Materialized materialized =
                DurableSelectionArtifact.reconstruct(
                        stored.payload(),
                        stored.diff(),
                        evidence(source));

        assertThat(materialized.payload().get("selectedText")).isEqualTo(selected);
        assertThat(materialized.payload().get("candidate")).isEqualTo(candidate);
        assertThat(materialized.diff().get("before")).isEqualTo(source);
        assertThat(materialized.diff().get("after")).isEqualTo(candidate);
    }

    @Test
    void 任一候选哈希漂移都以结构化完整性错误拒绝() {
        String source = "甲😀乙\n丙丁";
        DurableSelectionArtifact.Stored stored = DurableSelectionArtifact.create(
                "bundle-1",
                "evidence-1",
                "chapter-1",
                UPDATED_AT,
                DurableSelectionArtifact.sha256(source),
                1,
                3,
                DurableSelectionArtifact.sha256("😀乙"),
                "新段落",
                DurableSelectionArtifact.sha256("新段落"),
                DurableSelectionArtifact.sha256("甲新段落\n丙丁"),
                "step-1",
                "a".repeat(64));
        var tampered = new LinkedHashMap<>(stored.payload());
        tampered.put("candidateSha256", "b".repeat(64));

        assertThatThrownBy(() -> DurableSelectionArtifact.reconstruct(
                        tampered, stored.diff(), evidence(source)))
                .isInstanceOfSatisfying(ApiException.class, exception ->
                        assertThat(exception.code())
                                .isEqualTo("ARTIFACT_REVISION_INTEGRITY_ERROR"));
    }

    private static DurableSelectionArtifact.Evidence evidence(String source) {
        return new DurableSelectionArtifact.Evidence(
                "bundle-1",
                "evidence-1",
                "chapter_content",
                "chapter-1",
                UPDATED_AT,
                source,
                DurableSelectionArtifact.sha256(source),
                1,
                3);
    }
}
