package cn.inkforge.core.reviews.domain;

import cn.inkforge.contracts.api.ArtifactSelectionRef;
import cn.inkforge.contracts.api.ReviewArtifactDecisionRequest;
import cn.inkforge.core.platform.idempotency.CommandIdempotency;
import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.openapitools.jackson.nullable.JsonNullable;
import tools.jackson.databind.ObjectMapper;

/** 审核决定的规范化正文与指纹；保留 Python 历史上对可空字段的精确处理。 */
public record ReviewDecisionIdentity(Map<String, Object> normalizedBody, String fingerprint) {

    public ReviewDecisionIdentity {
        normalizedBody = Collections.unmodifiableMap(new LinkedHashMap<>(normalizedBody));
    }

    public static ReviewDecisionIdentity create(
            String artifactId,
            ReviewArtifactDecisionRequest request,
            ObjectMapper json) {
        Map<String, Object> body = new LinkedHashMap<>();
        // V1 已上线指纹不能改变；只有显式 V2 才把引擎身份纳入规范正文。
        if (request.getEngineVersion()
                == ReviewArtifactDecisionRequest.EngineVersionEnum.NUMBER_2) {
            body.put("engineVersion", 2);
        }
        body.put("expectedRevision", request.getExpectedRevision());
        body.put("decision", request.getDecision().getValue());
        body.put("editedContent", nullable(request.getEditedContent()));
        String editedReplacement = nullable(request.getEditedReplacement());
        // Python 上线该字段时约定：未提供或 null 都不改变旧请求的指纹。
        if (editedReplacement != null) body.put("editedReplacement", editedReplacement);
        List<ArtifactSelectionRef> refs = nullable(request.getSelectedUpdateRefs());
        body.put("selectedUpdateRefs", refs == null ? null : selectionRefs(refs));
        body.put("userMessage", nullable(request.getUserMessage()));
        String fingerprint = CommandIdempotency.requestFingerprint(
                "artifact_decision",
                Map.of("artifactId", artifactId),
                body,
                json);
        return new ReviewDecisionIdentity(body, fingerprint);
    }

    private static List<Map<String, Object>> selectionRefs(List<ArtifactSelectionRef> refs) {
        List<Map<String, Object>> result = new ArrayList<>(refs.size());
        for (ArtifactSelectionRef ref : refs) {
            Map<String, Object> value = new LinkedHashMap<>();
            value.put("section", ref.getSection());
            value.put("index", nullable(ref.getIndex()));
            result.add(Collections.unmodifiableMap(value));
        }
        return Collections.unmodifiableList(result);
    }

    private static <T> T nullable(JsonNullable<T> value) {
        return value == null || value.isUndefined() ? null : value.orElse(null);
    }
}
