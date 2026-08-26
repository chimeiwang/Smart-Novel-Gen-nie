package cn.inkforge.core.writing.infrastructure;

import cn.inkforge.core.writing.application.WritingEventStore;
import cn.inkforge.core.writing.domain.WritingEvent;
import cn.inkforge.core.writing.domain.WritingEventSequenceGap;
import cn.inkforge.core.writing.domain.WritingEventSourceConflict;
import java.time.Clock;
import java.time.OffsetDateTime;
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;

/** 仅供领域测试使用的同步内存事件流。 */
final class InMemoryWritingEventStore implements WritingEventStore {

    private final Clock clock;
    private final Map<String, List<WritingEvent>> events = new HashMap<>();
    private final Map<String, WritingEvent> sources = new HashMap<>();
    private final Map<String, Integer> sequences = new HashMap<>();

    InMemoryWritingEventStore(Clock clock) {
        this.clock = Objects.requireNonNull(clock);
    }

    @Override
    public synchronized boolean validateSource(
            String taskId,
            String sourceEventId,
            int sequence,
            String event,
            Map<String, Object> data) {
        WritingEvent existing = sources.get(sourceKey(taskId, sourceEventId));
        if (existing == null) return true;
        if (!same(existing, sequence, event, data)) throw new WritingEventSourceConflict();
        return false;
    }

    @Override
    public synchronized boolean validate(
            String taskId,
            String sourceEventId,
            int sequence,
            String event,
            Map<String, Object> data,
            int durableBaseline,
            boolean allowRebase) {
        WritingEvent existing = sources.get(sourceKey(taskId, sourceEventId));
        if (existing != null) {
            if (!same(existing, sequence, event, data)) throw new WritingEventSourceConflict();
            return false;
        }
        Integer last = sequences.get(taskId);
        if (last == null && allowRebase && sequence <= durableBaseline) return false;
        int expected = expected(last, sequence, durableBaseline, allowRebase);
        if (sequence != expected) throw new WritingEventSequenceGap(expected, sequence);
        return true;
    }

    @Override
    public synchronized WritingEvent appendAgent(
            String taskId,
            String sourceEventId,
            int sequence,
            String event,
            Map<String, Object> data,
            int durableBaseline,
            boolean allowRebase) {
        WritingEvent existing = sources.get(sourceKey(taskId, sourceEventId));
        if (existing != null) {
            if (!same(existing, sequence, event, data)) throw new WritingEventSourceConflict();
            return existing;
        }
        int expected = expected(
                sequences.get(taskId), sequence, durableBaseline, allowRebase);
        if (sequence != expected) throw new WritingEventSequenceGap(expected, sequence);
        List<WritingEvent> taskEvents = events.computeIfAbsent(taskId, ignored -> new ArrayList<>());
        WritingEvent created = new WritingEvent(
                Integer.toString(taskEvents.size() + 1),
                event,
                Collections.unmodifiableMap(new LinkedHashMap<>(data)),
                OffsetDateTime.now(clock),
                sourceEventId,
                sequence);
        taskEvents.add(created);
        sources.put(sourceKey(taskId, sourceEventId), created);
        sequences.put(taskId, sequence);
        return created;
    }

    @Override
    public synchronized List<WritingEvent> replay(
            String taskId, String lastEventId) {
        List<WritingEvent> values = events.getOrDefault(taskId, List.of());
        if (lastEventId == null) return List.copyOf(values);
        int cursor = Integer.parseInt(lastEventId);
        return values.stream()
                .filter(event -> Integer.parseInt(event.id()) > cursor)
                .toList();
    }

    private static int expected(
            Integer last, int sequence, int durableBaseline, boolean allowRebase) {
        if (allowRebase
                && sequence > durableBaseline
                && (last == null || last <= durableBaseline)) {
            return sequence;
        }
        return last == null ? 1 : last + 1;
    }

    private static boolean same(
            WritingEvent existing,
            int sequence,
            String event,
            Map<String, Object> data) {
        return existing.sourceEventId() != null
                && existing.sequence() == sequence
                && existing.event().equals(event)
                && existing.data().equals(data);
    }

    private static String sourceKey(String taskId, String sourceEventId) {
        return taskId + '\0' + sourceEventId;
    }
}
