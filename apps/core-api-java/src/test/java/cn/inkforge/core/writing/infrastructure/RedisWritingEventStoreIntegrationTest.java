package cn.inkforge.core.writing.infrastructure;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import cn.inkforge.core.platform.redis.CoreRedis;
import cn.inkforge.core.writing.domain.WritingEventSequenceGap;
import cn.inkforge.core.writing.domain.WritingEventSourceConflict;
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.testcontainers.containers.GenericContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;
import tools.jackson.databind.json.JsonMapper;

@Testcontainers
class RedisWritingEventStoreIntegrationTest {

    @Container
    private static final GenericContainer<?> REDIS =
            new GenericContainer<>(DockerImageName.parse("redis:7.4-alpine"))
                    .withExposedPorts(6379);

    @Test
    void 来源幂等序号缺口和耐久重基必须由Redis原子判定() {
        try (CoreRedis redis = CoreRedis.connect(redisUrl())) {
            RedisWritingEventStore store = new RedisWritingEventStore(
                    redis,
                    Clock.fixed(Instant.parse("2026-08-25T10:00:00Z"), ZoneOffset.UTC),
                    JsonMapper.builder().build());
            String taskId = "redis-writing-" + UUID.randomUUID();
            Map<String, Object> data = new LinkedHashMap<>();
            data.put("agentId", "写作");
            data.put("detail", null);

            var first = store.appendAgent(
                    taskId, "source-1", 1, "agent_status", data, 0, true);
            var replay = store.appendAgent(
                    taskId, "source-1", 1, "agent_status", data, 0, true);

            assertThat(replay.id()).isEqualTo(first.id());
            assertThat(store.replay(taskId, null)).hasSize(1);
            assertThat(store.replay(taskId, first.id())).isEmpty();
            assertThatThrownBy(() -> store.appendAgent(
                            taskId,
                            "source-1",
                            1,
                            "agent_status",
                            Map.of("agentId", "编辑"),
                            0,
                            true))
                    .isInstanceOf(WritingEventSourceConflict.class);
            assertThatThrownBy(() -> store.appendAgent(
                            taskId, "source-3", 3, "agent_status", Map.of(), 0, true))
                    .isInstanceOfSatisfying(WritingEventSequenceGap.class, error ->
                            assertThat(error.expectedSequence()).isEqualTo(2));

            String rebasedTask = taskId + "-rebase";
            var rebased = store.appendAgent(
                    rebasedTask, "source-5", 5, "checkpoint", Map.of(), 4, true);
            assertThat(rebased.sequence()).isEqualTo(5);
        }
    }

    private static String redisUrl() {
        return "redis://" + REDIS.getHost() + ":" + REDIS.getMappedPort(6379) + "/0";
    }
}
