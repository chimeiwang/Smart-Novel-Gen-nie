package cn.inkforge.core.workflows.infrastructure;

import static org.assertj.core.api.Assertions.assertThat;

import cn.inkforge.contracts.api.EvidenceEvaluation;
import cn.inkforge.core.workflows.protocol.ExecutionCanonicalJson;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import tools.jackson.databind.ObjectMapper;

class WorkflowCallbackValuesTest {
    @Test
    void 缺省或显式空Patch不改变旧投影而结构化替换完整进入结果() {
        ObjectMapper json = new ObjectMapper();
        Map<String, Object> reference = new LinkedHashMap<>(Map.of("evidenceItemId", "evidence", "contentSha256", "a".repeat(64)));
        reference.put("range", null);
        Map<String, Object> finding = new LinkedHashMap<>(Map.of("dimension", "chapter_draft.local", "severity", "warning",
                "claim", "局部问题", "suggestion", "说明不能当作替换文本", "confidence", 0.9, "evidence", List.of(reference)));
        finding.put("candidateRange", null);
        Map<String, Object> expected = Map.of("contentVerdict", "issues_found", "findings", List.of(finding));
        var absent = json.convertValue(expected, EvidenceEvaluation.class);
        String oldHash = ExecutionCanonicalJson.sha256(expected);
        assertThat(json.valueToTree(WorkflowCallbackValues.reviewerOutput(absent)).path("findings").get(0).has("candidatePatch")).isFalse();
        assertThat(ExecutionCanonicalJson.sha256(WorkflowCallbackValues.reviewerOutput(absent))).isEqualTo(oldHash);
        finding.put("candidatePatch", null);
        var explicitNull = json.convertValue(expected, EvidenceEvaluation.class);
        assertThat(ExecutionCanonicalJson.sha256(WorkflowCallbackValues.reviewerOutput(explicitNull))).isEqualTo(oldHash);
        Map<String, Object> patch = Map.of("kind", "text_replace", "find", "  ", "replace", "完整Unicode😀\n替换");
        finding.put("candidatePatch", patch);
        var patched = json.convertValue(expected, EvidenceEvaluation.class);
        assertThat(ExecutionCanonicalJson.sha256(WorkflowCallbackValues.reviewerOutput(patched))).isEqualTo(ExecutionCanonicalJson.sha256(expected));
        assertThat(ExecutionCanonicalJson.sha256(WorkflowCallbackValues.reviewerOutput(patched))).isNotEqualTo(oldHash);
    }
}
