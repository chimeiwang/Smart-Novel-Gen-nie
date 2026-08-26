package cn.inkforge.core.writing.domain;

import cn.inkforge.core.db.generated.tables.records.WritingruncommandRecord;
import cn.inkforge.core.db.generated.tables.records.WritingtaskRecord;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import tools.jackson.core.type.TypeReference;
import tools.jackson.databind.ObjectMapper;

/** 只接受可证明归属且没有活动命令占用的长篇持久检查点。 */
public final class WritingRecoverability {

    private static final Set<String> TERMINAL_COMMANDS = Set.of("succeeded", "failed");
    private static final Set<String> RUNTIME_ONLY_FIELDS = Set.of(
            "runtime", "novelData", "streamCallbacks", "eventCallbacks", "controlEvents");

    private WritingRecoverability() {}

    public static Map<String, Object> resolve(
            WritingtaskRecord task,
            List<WritingruncommandRecord> commands,
            ObjectMapper json) {
        if (!Set.of("active", "waiting_call").contains(task.getPhase().getLiteral())
                || task.getGraphstatejson() == null
                || commands.stream().anyMatch(command ->
                        Objects.equals(command.getTaskid(), task.getId())
                                && !TERMINAL_COMMANDS.contains(command.getStatus()))) {
            return null;
        }
        Map<String, Object> snapshot = object(task.getGraphstatejson(), json);
        if (snapshot == null
                || snapshot.keySet().stream().anyMatch(RUNTIME_ONLY_FIELDS::contains)
                || !Objects.equals(snapshot.get("taskId"), task.getId())
                || !Objects.equals(snapshot.get("novelId"), task.getNovelid())
                || !Objects.equals(snapshot.get("chapterId"), task.getChapterid())
                || !(snapshot.get("userId") instanceof String userId)
                || userId.isEmpty()
                || !(snapshot.get("targetWordCount") instanceof Number)
                || !(snapshot.get("conversationHistory") instanceof List<?>)) {
            return null;
        }
        Object sequence = snapshot.get("eventSequence");
        Object operationValue = snapshot.get("currentOperation");
        Object stage = snapshot.get("operationStage");
        Object callbackJobId = snapshot.get("callbackJobId");
        if (!(sequence instanceof Number number)
                || sequence instanceof Double
                || sequence instanceof Float
                || number.longValue() < 0
                || !Objects.equals(snapshot.get("phase"), task.getPhase().getLiteral())
                || !(operationValue instanceof Map<?, ?> operation)
                || !(operation.get("kind") instanceof String operationKind)
                || !(stage instanceof String stageValue)
                || stageValue.isBlank()
                || !(callbackJobId instanceof String jobId)) {
            return null;
        }
        WritingruncommandRecord source = commands.stream()
                .filter(command -> jobId.equals(command.getId()))
                .findFirst()
                .orElse(null);
        if (source == null
                || !Objects.equals(source.getTaskid(), task.getId())
                || !TERMINAL_COMMANDS.contains(source.getStatus())
                || !Objects.equals(commandOperation(source, json), operationKind)) {
            return null;
        }
        return snapshot;
    }

    private static String commandOperation(
            WritingruncommandRecord command, ObjectMapper json) {
        Map<String, Object> payload = object(command.getPayloadjson(), json);
        if (payload == null) return null;
        Object jobValue = payload.getOrDefault("job", payload);
        return jobValue instanceof Map<?, ?> job && job.get("operation") instanceof String value
                ? value
                : null;
    }

    private static Map<String, Object> object(String serialized, ObjectMapper json) {
        try {
            Object parsed = json.readValue(serialized, new TypeReference<Object>() {});
            if (!(parsed instanceof Map<?, ?> map)) return null;
            Map<String, Object> result = new LinkedHashMap<>();
            for (Map.Entry<?, ?> entry : map.entrySet()) {
                if (!(entry.getKey() instanceof String key)) return null;
                result.put(key, entry.getValue());
            }
            return result;
        } catch (RuntimeException exception) {
            return null;
        }
    }
}
