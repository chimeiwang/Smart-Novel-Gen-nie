package cn.inkforge.core.platform.idempotency;

import static cn.inkforge.core.db.generated.Tables.NOVEL;
import static cn.inkforge.core.db.generated.Tables.WORKFLOWRUN;
import static cn.inkforge.core.db.generated.Tables.WRITINGRUNCOMMAND;
import static cn.inkforge.core.db.generated.Tables.WRITINGTASK;

import cn.inkforge.core.platform.http.ApiException;
import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import org.jooq.DSLContext;
import org.jooq.Record2;
import tools.jackson.core.type.TypeReference;
import tools.jackson.databind.ObjectMapper;

/**
 * WritingRunCommand 与 WorkflowRun 共用的持久幂等解析器。
 *
 * <p>这里有意扫描两张既有控制面表：clientRequestId 是用户级全局命名空间，不能因为命令种类或存储表不同而
 * 被重复使用。解析失败时只暴露稳定冲突，绝不把损坏的持久 JSON 泄漏到 API。
 */
public final class CommandIdempotencyStore {

    private static final Set<String> ENVELOPE_FIELDS = Set.of(
            "schemaVersion",
            "clientRequestId",
            "commandKind",
            "resourceIdentity",
            "normalizedBody",
            "requestFingerprint");

    private final ObjectMapper json;

    public CommandIdempotencyStore(ObjectMapper json) {
        this.json = Objects.requireNonNull(json);
    }

    public Resolution resolve(
            DSLContext transaction,
            String userId,
            String clientRequestId,
            String requestFingerprint) {
        Objects.requireNonNull(transaction);
        List<Resolution> matches = new ArrayList<>();
        List<Record2<String, String>> commandRows = transaction
                .select(WRITINGRUNCOMMAND.ID, WRITINGRUNCOMMAND.PAYLOADJSON)
                .from(WRITINGRUNCOMMAND)
                .join(WRITINGTASK)
                .on(WRITINGTASK.ID.eq(WRITINGRUNCOMMAND.TASKID))
                .join(NOVEL)
                .on(NOVEL.ID.eq(WRITINGTASK.NOVELID))
                .where(
                        NOVEL.USERID.eq(userId),
                        WRITINGRUNCOMMAND.IDEMPOTENCYKEY.in(
                                CommandIdempotency.envelopedKey(userId, clientRequestId),
                                CommandIdempotency.legacyKey(userId, clientRequestId)))
                .fetch();
        for (Record2<String, String> row : commandRows) {
            ParsedEnvelope parsed = parse(row.value2());
            if (parsed.invalid()) throw reused(clientRequestId);
            if (parsed.metadata() != null
                    && clientRequestId.equals(parsed.metadata().clientRequestId())) {
                matches.add(new Resolution(
                        RecordKind.WRITING_COMMAND, row.value1(), parsed.metadata()));
            }
        }

        List<Record2<String, String>> workflowRows = transaction
                .select(WORKFLOWRUN.ID, WORKFLOWRUN.INPUT)
                .from(WORKFLOWRUN)
                .where(WORKFLOWRUN.USERID.eq(userId), WORKFLOWRUN.INPUT.isNotNull())
                .fetch();
        for (Record2<String, String> row : workflowRows) {
            ParsedEnvelope parsed = parse(row.value2());
            if (parsed.invalid()
                    && clientRequestId.equals(parsed.declaredClientRequestId())) {
                throw reused(clientRequestId);
            }
            if (parsed.metadata() != null
                    && clientRequestId.equals(parsed.metadata().clientRequestId())) {
                matches.add(new Resolution(
                        RecordKind.WORKFLOW_RUN, row.value1(), parsed.metadata()));
            }
        }

        if (matches.isEmpty()) return null;
        if (matches.size() != 1) throw reused(clientRequestId);
        Resolution match = matches.getFirst();
        if (requestFingerprint != null
                && !requestFingerprint.equals(match.metadata().requestFingerprint())) {
            throw reused(clientRequestId);
        }
        return match;
    }

    private ParsedEnvelope parse(String payloadJson) {
        Map<String, Object> payload = object(payloadJson);
        if (payload == null || !payload.containsKey("_inkforgeCommand")) {
            return ParsedEnvelope.absent();
        }
        Object raw = payload.get("_inkforgeCommand");
        String declared = raw instanceof Map<?, ?> value
                        && value.get("clientRequestId") instanceof String text
                ? text
                : null;
        if (!(raw instanceof Map<?, ?> value)) {
            return ParsedEnvelope.invalid(declared);
        }
        Map<String, Object> metadata = stringMap(value);
        boolean valid = metadata != null
                && metadata.keySet().equals(ENVELOPE_FIELDS)
                && Integer.valueOf(1).equals(metadata.get("schemaVersion"))
                && metadata.get("clientRequestId") instanceof String client
                && !client.isEmpty()
                && client.length() <= 128
                && metadata.get("commandKind") instanceof String commandKind
                && !commandKind.isEmpty()
                && metadata.get("resourceIdentity") instanceof Map<?, ?> resource
                && stringMap(resource) != null
                && metadata.get("normalizedBody") instanceof Map<?, ?> body
                && stringMap(body) != null
                && metadata.get("requestFingerprint") instanceof String fingerprint
                && fingerprint.matches("[0-9a-f]{64}");
        if (!valid) return ParsedEnvelope.invalid(declared);
        @SuppressWarnings("unchecked")
        Map<String, Object> resourceIdentity =
                new LinkedHashMap<>((Map<String, Object>) metadata.get("resourceIdentity"));
        @SuppressWarnings("unchecked")
        Map<String, Object> normalizedBody =
                new LinkedHashMap<>((Map<String, Object>) metadata.get("normalizedBody"));
        return ParsedEnvelope.valid(new Metadata(
                (String) metadata.get("clientRequestId"),
                (String) metadata.get("commandKind"),
                Collections.unmodifiableMap(resourceIdentity),
                Collections.unmodifiableMap(normalizedBody),
                (String) metadata.get("requestFingerprint")));
    }

    private Map<String, Object> object(String value) {
        if (value == null) return null;
        try {
            Object parsed = json.readValue(value, new TypeReference<Object>() {});
            return parsed instanceof Map<?, ?> map ? stringMap(map) : null;
        } catch (RuntimeException exception) {
            return null;
        }
    }

    private static Map<String, Object> stringMap(Map<?, ?> value) {
        Map<String, Object> result = new LinkedHashMap<>();
        for (Map.Entry<?, ?> entry : value.entrySet()) {
            if (!(entry.getKey() instanceof String key)) return null;
            result.put(key, entry.getValue());
        }
        return result;
    }

    public static ApiException reused(String clientRequestId) {
        return new ApiException(
                409,
                "IDEMPOTENCY_KEY_REUSED",
                "同一幂等标识已绑定其他请求",
                Map.of("clientRequestId", clientRequestId));
    }

    public enum RecordKind {
        WRITING_COMMAND,
        WORKFLOW_RUN
    }

    public record Metadata(
            String clientRequestId,
            String commandKind,
            Map<String, Object> resourceIdentity,
            Map<String, Object> normalizedBody,
            String requestFingerprint) {}

    public record Resolution(RecordKind recordKind, String recordId, Metadata metadata) {}

    private record ParsedEnvelope(
            Metadata metadata, boolean invalid, String declaredClientRequestId) {

        private static ParsedEnvelope absent() {
            return new ParsedEnvelope(null, false, null);
        }

        private static ParsedEnvelope valid(Metadata value) {
            return new ParsedEnvelope(value, false, value.clientRequestId());
        }

        private static ParsedEnvelope invalid(String declared) {
            return new ParsedEnvelope(null, true, declared);
        }
    }
}
