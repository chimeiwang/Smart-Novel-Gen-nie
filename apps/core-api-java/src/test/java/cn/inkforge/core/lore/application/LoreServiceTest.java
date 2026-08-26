package cn.inkforge.core.lore.application;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import cn.inkforge.contracts.api.CharacterResponse;
import cn.inkforge.contracts.api.ContentRequest;
import cn.inkforge.contracts.api.UpdateCharacterRequest;
import cn.inkforge.contracts.api.WritingBibleRequest;
import cn.inkforge.core.lore.domain.LoreEntityKind;
import cn.inkforge.core.lore.domain.LoreEntityPatch;
import cn.inkforge.core.lore.domain.LoreEntitySnapshot;
import cn.inkforge.core.platform.http.ApiException;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.openapitools.jackson.nullable.JsonNullable;

class LoreServiceTest {

    private static final OffsetDateTime VERSION =
            OffsetDateTime.of(2026, 8, 6, 1, 2, 3, 0, ZoneOffset.UTC);

    @Test
    void 人物补丁区分字段缺失和显式空值() {
        LoreRepository repository = mock(LoreRepository.class);
        LoreService service = new LoreService(repository);
        UpdateCharacterRequest request = new UpdateCharacterRequest(VERSION);
        request.setFactionId(JsonNullable.of(null));
        when(repository.updateEntity(
                        eq("novel-1"),
                        eq("user-1"),
                        eq(LoreEntityKind.CHARACTERS),
                        eq("character-1"),
                        any(),
                        eq(VERSION)))
                .thenReturn(new LoreEntitySnapshot(
                        LoreEntityKind.CHARACTERS,
                        "character-1",
                        Map.of("name", "角色", "currentStatus", "active"),
                        VERSION,
                        VERSION));

        CharacterResponse response = service.updateCharacter(
                "user-1", "novel-1", "character-1", request);

        ArgumentCaptor<LoreEntityPatch> patch =
                ArgumentCaptor.forClass(LoreEntityPatch.class);
        verify(repository).updateEntity(
                eq("novel-1"),
                eq("user-1"),
                eq(LoreEntityKind.CHARACTERS),
                eq("character-1"),
                patch.capture(),
                eq(VERSION));
        assertThat(patch.getValue().fields()).containsEntry("factionId", null);
        assertThat(patch.getValue().fields()).doesNotContainKey("name");
        assertThat(response.getFactionId()).isNull();
    }

    @Test
    void 故事进展按Unicode字符拒绝超长内容且不截断() {
        LoreRepository repository = mock(LoreRepository.class);
        LoreService service = new LoreService(repository);
        ContentRequest request = new ContentRequest();
        request.setContent(JsonNullable.of("😀".repeat(30_001)));
        request.setExpectedUpdatedAt(JsonNullable.of(null));

        assertThatThrownBy(() -> service.saveStoryProgress(
                        "user-1", "novel-1", request))
                .isInstanceOfSatisfying(ApiException.class, exception -> {
                    assertThat(exception.code()).isEqualTo("STORY_PROGRESS_TOO_LONG");
                    assertThat(exception.statusCode()).isEqualTo(422);
                });
    }

    @Test
    void 作品圣经拒绝中短篇模式() {
        LoreService service = new LoreService(mock(LoreRepository.class));
        WritingBibleRequest request = new WritingBibleRequest();
        request.setExpectedUpdatedAt(JsonNullable.of(null));
        request.setStoryLengthProfile(JsonNullable.of(
                WritingBibleRequest.StoryLengthProfileEnum.SHORT_MEDIUM));

        assertThatThrownBy(() -> service.saveWritingBible(
                        "user-1", "novel-1", request))
                .isInstanceOfSatisfying(ApiException.class, exception ->
                        assertThat(exception.code())
                                .isEqualTo("WRITING_BIBLE_PROFILE_MISMATCH"));
    }

    @Test
    void 作品圣经空补丁被拒绝() {
        LoreService service = new LoreService(mock(LoreRepository.class));
        WritingBibleRequest request = new WritingBibleRequest();
        request.setExpectedUpdatedAt(JsonNullable.of(null));

        assertThatThrownBy(() -> service.saveWritingBible(
                        "user-1", "novel-1", request))
                .isInstanceOfSatisfying(ApiException.class, exception ->
                        assertThat(exception.code()).isEqualTo("EMPTY_UPDATE"));
    }
}
