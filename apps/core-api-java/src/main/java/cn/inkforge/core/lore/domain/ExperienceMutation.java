package cn.inkforge.core.lore.domain;

import java.time.OffsetDateTime;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Objects;

/** ReviewArtifact 内单条人物经历命令。 */
public record ExperienceMutation(
        MutationAction action,
        Map<String, Object> fields,
        String entityId,
        String characterId,
        String characterName,
        String clientRequestId,
        OffsetDateTime expectedUpdatedAt) {

    public ExperienceMutation {
        Objects.requireNonNull(action);
        Objects.requireNonNull(fields);
        fields = Collections.unmodifiableMap(new LinkedHashMap<>(fields));
    }
}
