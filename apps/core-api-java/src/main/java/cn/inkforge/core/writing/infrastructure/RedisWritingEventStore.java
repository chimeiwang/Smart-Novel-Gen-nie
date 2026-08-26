package cn.inkforge.core.writing.infrastructure;

import cn.inkforge.core.platform.redis.CoreRedis;
import cn.inkforge.core.writing.application.WritingEventStore;
import cn.inkforge.core.writing.domain.WritingEvent;
import cn.inkforge.core.writing.domain.WritingEventSequenceGap;
import cn.inkforge.core.writing.domain.WritingEventSourceConflict;
import java.time.Clock;
import java.time.OffsetDateTime;
import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import tools.jackson.core.type.TypeReference;
import tools.jackson.databind.ObjectMapper;

/** 使用 Lua 原子保持来源幂等和任务内严格序号的 Redis Stream。 */
final class RedisWritingEventStore implements WritingEventStore {

    private static final int TTL_SECONDS = 86_400;
    private static final int REPLAY_BATCH = 1_000;
    private static final String APPEND_SCRIPT = """
            local existing = redis.call('GET', KEYS[2])
            if existing then
              return {'duplicate', existing}
            end
            local received = tonumber(ARGV[1])
            local last_raw = redis.call('GET', KEYS[3])
            local durable_baseline = tonumber(ARGV[7])
            local allow_rebase = ARGV[8] == '1'
            local expected = 1
            if last_raw then
              local last = tonumber(last_raw)
              if allow_rebase and last <= durable_baseline and received > durable_baseline then
                expected = received
              else
                expected = last + 1
              end
            elseif allow_rebase and received > durable_baseline then
              expected = received
            end
            if received ~= expected then
              return {'gap', tostring(expected)}
            end
            local id = redis.call(
              'XADD', KEYS[1], '*',
              'event', ARGV[2],
              'data', ARGV[3],
              'occurred_at', ARGV[4],
              'source_event_id', ARGV[5],
              'sequence', ARGV[1]
            )
            redis.call('SET', KEYS[2], id, 'EX', ARGV[6])
            redis.call('SET', KEYS[3], ARGV[1], 'EX', ARGV[6])
            redis.call('EXPIRE', KEYS[1], ARGV[6])
            return {'appended', id}
            """;

    private final CoreRedis redis;
    private final Clock clock;
    private final ObjectMapper json;

    RedisWritingEventStore(CoreRedis redis, Clock clock, ObjectMapper json) {
        this.redis = Objects.requireNonNull(redis);
        this.clock = Objects.requireNonNull(clock);
        this.json = Objects.requireNonNull(json);
    }

    @Override
    public boolean validateSource(
            String taskId,
            String sourceEventId,
            int sequence,
            String event,
            Map<String, Object> data) {
        String eventId = redis.get(sourceKey(taskId, sourceEventId));
        if (eventId == null) return true;
        WritingEvent existing = read(taskId, eventId);
        if (existing == null) throw new IllegalStateException("重复事件对应的短期流已失效，需要状态对账");
        if (!same(existing, sequence, event, data)) throw new WritingEventSourceConflict();
        return false;
    }

    @Override
    public boolean validate(
            String taskId,
            String sourceEventId,
            int sequence,
            String event,
            Map<String, Object> data,
            int durableBaseline,
            boolean allowRebase) {
        List<String> values = redis.getMany(List.of(
                sourceKey(taskId, sourceEventId), sequenceKey(taskId)));
        String eventId = values.get(0);
        if (eventId != null) {
            WritingEvent existing = read(taskId, eventId);
            if (existing == null) throw new IllegalStateException("重复事件对应的短期流已失效，需要状态对账");
            if (!same(existing, sequence, event, data)) throw new WritingEventSourceConflict();
            return false;
        }
        Integer last = values.get(1) == null ? null : Integer.valueOf(values.get(1));
        if (last == null && allowRebase && sequence <= durableBaseline) return false;
        int expected = expected(last, sequence, durableBaseline, allowRebase);
        if (sequence != expected) throw new WritingEventSequenceGap(expected, sequence);
        return true;
    }

    @Override
    public WritingEvent appendAgent(
            String taskId,
            String sourceEventId,
            int sequence,
            String event,
            Map<String, Object> data,
            int durableBaseline,
            boolean allowRebase) {
        OffsetDateTime occurredAt = OffsetDateTime.now(clock);
        List<String> result = redis.evalStrings(
                APPEND_SCRIPT,
                List.of(
                        streamKey(taskId),
                        sourceKey(taskId, sourceEventId),
                        sequenceKey(taskId)),
                List.of(
                        Integer.toString(sequence),
                        event,
                        encode(data),
                        occurredAt.toString(),
                        sourceEventId,
                        Integer.toString(TTL_SECONDS),
                        Integer.toString(durableBaseline),
                        allowRebase ? "1" : "0"));
        if (result.size() != 2) throw new IllegalStateException("Redis 写作事件结果无效");
        if ("gap".equals(result.get(0))) {
            throw new WritingEventSequenceGap(Integer.parseInt(result.get(1)), sequence);
        }
        if ("duplicate".equals(result.get(0))) {
            WritingEvent existing = read(taskId, result.get(1));
            if (existing == null) throw new IllegalStateException("重复事件对应的短期流已失效，需要状态对账");
            if (!same(existing, sequence, event, data)) throw new WritingEventSourceConflict();
            return existing;
        }
        if (!"appended".equals(result.get(0))) {
            throw new IllegalStateException("Redis 写作事件结果无效");
        }
        return new WritingEvent(
                result.get(1),
                event,
                Collections.unmodifiableMap(new LinkedHashMap<>(data)),
                occurredAt,
                sourceEventId,
                sequence);
    }

    @Override
    public List<WritingEvent> replay(String taskId, String lastEventId) {
        List<WritingEvent> result = new ArrayList<>();
        String cursor = lastEventId;
        while (true) {
            List<CoreRedis.StreamEntry> batch = redis.streamRangeAfter(
                    streamKey(taskId), cursor, REPLAY_BATCH);
            for (CoreRedis.StreamEntry entry : batch) result.add(decode(entry));
            if (batch.size() < REPLAY_BATCH) return List.copyOf(result);
            cursor = batch.getLast().id();
        }
    }

    private WritingEvent read(String taskId, String eventId) {
        List<CoreRedis.StreamEntry> values = redis.streamRange(
                streamKey(taskId), eventId, eventId, 1);
        return values.isEmpty() ? null : decode(values.getFirst());
    }

    private WritingEvent decode(CoreRedis.StreamEntry entry) {
        Map<String, String> fields = entry.fields();
        try {
            Object parsed = json.readValue(
                    required(fields, "data"), new TypeReference<Object>() {});
            if (!(parsed instanceof Map<?, ?> map)) throw new IllegalArgumentException();
            Map<String, Object> data = new LinkedHashMap<>();
            for (Map.Entry<?, ?> item : map.entrySet()) {
                if (!(item.getKey() instanceof String key)) throw new IllegalArgumentException();
                data.put(key, item.getValue());
            }
            String source = fields.get("source_event_id");
            String sequence = fields.get("sequence");
            return new WritingEvent(
                    entry.id(),
                    required(fields, "event"),
                    data,
                    OffsetDateTime.parse(required(fields, "occurred_at")),
                    source == null || source.isEmpty() ? null : source,
                    sequence == null || sequence.isEmpty() ? null : Integer.valueOf(sequence));
        } catch (RuntimeException exception) {
            throw new IllegalStateException("Redis 写作事件格式无效");
        }
    }

    private String encode(Map<String, Object> data) {
        return json.writeValueAsString(data);
    }

    private static String required(Map<String, String> fields, String key) {
        String value = fields.get(key);
        if (value == null) throw new IllegalArgumentException();
        return value;
    }

    private static boolean same(
            WritingEvent existing,
            int sequence,
            String event,
            Map<String, Object> data) {
        return existing.sourceEventId() != null
                && Objects.equals(existing.sequence(), sequence)
                && existing.event().equals(event)
                && existing.data().equals(data);
    }

    private static int expected(
            Integer last, int sequence, int durableBaseline, boolean allowRebase) {
        if (allowRebase
                && sequence > durableBaseline
                && (last == null || last <= durableBaseline)) return sequence;
        return last == null ? 1 : last + 1;
    }

    private static String streamKey(String taskId) {
        return "writing:events:" + taskId;
    }

    private static String sourceKey(String taskId, String sourceEventId) {
        return "writing:event-source:" + taskId + ":" + sourceEventId;
    }

    private static String sequenceKey(String taskId) {
        return "writing:event-sequence:" + taskId;
    }
}
