package cn.inkforge.core.reviews.application;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyBoolean;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;

import cn.inkforge.contracts.api.ArtifactSelectionRef;
import cn.inkforge.core.lore.application.LoreRepository;
import cn.inkforge.core.lore.domain.ContentKind;
import cn.inkforge.core.lore.domain.EntityMutation;
import cn.inkforge.core.outlines.application.OutlineRepository;
import cn.inkforge.core.platform.id.CuidV1Generator;
import cn.inkforge.core.references.application.ReferenceRepository;
import java.time.Clock;
import java.time.Instant;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;

class AgentUpdatesExecutorTest {

    private final LoreRepository lore = mock(LoreRepository.class);
    private final OutlineRepository outlines = mock(OutlineRepository.class);
    private final ReferenceRepository references = mock(ReferenceRepository.class);
    private final AgentUpdatesExecutor executor = new AgentUpdatesExecutor(
            lore,
            outlines,
            references,
            new CuidV1Generator(Clock.fixed(
                    Instant.parse("2026-08-25T00:00:00Z"), ZoneOffset.UTC)),
            false);

    @Test
    void 用户选项必须只应用指定分区和数组下标() {
        Map<String, Object> updates = new LinkedHashMap<>();
        updates.put("characters", List.of(
                Map.of(
                        "action", "create",
                        "clientRequestId", "character-request-0001",
                        "name", "甲"),
                Map.of(
                        "action", "create",
                        "clientRequestId", "character-request-0002",
                        "name", "乙")));
        updates.put("worldSetting", "世界设定正文");
        updates.put("references", List.of(Map.of(
                "action", "create",
                "clientRequestId", "reference-request-0001",
                "title", "资料",
                "type", "other",
                "content", "内容")));
        Map<String, OffsetDateTime> baselines = new LinkedHashMap<>();
        baselines.put("worldSetting", null);

        int count = executor.apply(
                "novel-1",
                "user-1",
                updates,
                List.of(
                        new ArtifactSelectionRef("characters").index(1),
                        new ArtifactSelectionRef("worldSetting")),
                null,
                baselines);

        assertThat(count).isEqualTo(2);
        @SuppressWarnings("unchecked")
        ArgumentCaptor<List<EntityMutation>> mutations = ArgumentCaptor.forClass(List.class);
        verify(lore).applyEntityMutations(anyString(), anyString(), mutations.capture());
        assertThat(mutations.getValue()).singleElement()
                .satisfies(value -> {
                    assertThat(value.clientRequestId()).isEqualTo("character-request-0002");
                    assertThat(value.fields()).containsEntry("name", "乙");
                });
        verify(lore).saveContent(
                "novel-1", "user-1", ContentKind.WORLD_SETTING, "世界设定正文", null);
        verify(references, never()).create(
                anyString(), anyString(), anyString(), any(), anyBoolean());
    }

    @Test
    void 未选择任何可应用更新必须明确拒绝() {
        assertThatThrownBy(() -> executor.apply(
                        "novel-1",
                        "user-1",
                        Map.of("characters", List.of(Map.of(
                                "action", "create",
                                "clientRequestId", "character-request-0001",
                                "name", "甲"))),
                        new ArrayList<>(),
                        null,
                        null))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessage("没有选择任何可应用更新");
    }
}
