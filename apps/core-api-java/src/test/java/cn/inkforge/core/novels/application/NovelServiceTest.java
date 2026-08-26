package cn.inkforge.core.novels.application;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import cn.inkforge.contracts.api.CreateNovelRequest;
import cn.inkforge.contracts.api.CreateNovelResponse;
import cn.inkforge.contracts.api.ShortMediumSourceKind;
import cn.inkforge.contracts.api.StoryLengthProfile;
import cn.inkforge.core.novels.domain.NovelCreation;
import cn.inkforge.core.platform.http.ApiException;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.openapitools.jackson.nullable.JsonNullable;

class NovelServiceTest {

    @Test
    void 中短篇创建归一化元数据并只把opening写入全文草稿() {
        NovelRepository repository = mock(NovelRepository.class);
        when(repository.create(any())).thenReturn(
                new CreateNovelResponse("chapter-1", "novel-1"));
        NovelService service = new NovelService(repository);
        CreateNovelRequest request = new CreateNovelRequest(
                "  新作品  ", StoryLengthProfile.SHORT_MEDIUM);
        request.setTargetTotalWordCount(JsonNullable.of(20_000));
        request.setClientRequestId(JsonNullable.of("request-12345678"));
        request.setSourceKind(ShortMediumSourceKind.OPENING);
        request.setSourceText(JsonNullable.of("  固定开头  "));
        request.setProtagonist(JsonNullable.of("  林川  "));
        request.setFirstChapterGoal(JsonNullable.of("  主角离开故乡  "));

        CreateNovelResponse response = service.create("user-1", request);

        ArgumentCaptor<NovelCreation> creation =
                ArgumentCaptor.forClass(NovelCreation.class);
        verify(repository).create(creation.capture());
        NovelCreation value = creation.getValue();
        assertThat(response.getNovelId()).isEqualTo("novel-1");
        assertThat(value.name()).isEqualTo("新作品");
        assertThat(value.firstChapterTitle()).isEqualTo("全文");
        assertThat(value.chapterContent()).isEqualTo("  固定开头  ");
        assertThat(value.outlineContent()).isEmpty();
        assertThat(value.storyProgress()).isEqualTo("第一章目标：主角离开故乡");
        assertThat(value.notes())
                .isEqualTo("主角起点：林川\n第一章目标：主角离开故乡");
    }

    @Test
    void 长篇创建使用默认目标字数且拒绝中短篇素材字段() {
        NovelRepository repository = mock(NovelRepository.class);
        when(repository.create(any())).thenReturn(
                new CreateNovelResponse("chapter-1", "novel-1"));
        NovelService service = new NovelService(repository);
        CreateNovelRequest valid = new CreateNovelRequest(
                "作品", StoryLengthProfile.LONG_SERIAL);
        service.create("user-1", valid);
        ArgumentCaptor<NovelCreation> creation =
                ArgumentCaptor.forClass(NovelCreation.class);
        verify(repository).create(creation.capture());
        assertThat(creation.getValue().targetTotalWordCount()).isEqualTo(1_000_000);
        assertThat(creation.getValue().firstChapterTitle()).isEqualTo("第一章");

        CreateNovelRequest invalid = new CreateNovelRequest(
                "作品", StoryLengthProfile.LONG_SERIAL);
        invalid.setSourceText(JsonNullable.of("不应携带"));
        assertThatThrownBy(() -> service.create("user-1", invalid))
                .isInstanceOfSatisfying(ApiException.class, exception ->
                        assertThat(exception.code()).isEqualTo("VALIDATION_ERROR"));

        CreateNovelRequest invalidTarget = new CreateNovelRequest(
                "作品", StoryLengthProfile.LONG_SERIAL);
        invalidTarget.setTargetTotalWordCount(JsonNullable.of(0));
        assertThatThrownBy(() -> service.create("user-1", invalidTarget))
                .isInstanceOfSatisfying(ApiException.class, exception ->
                        assertThat(exception.code()).isEqualTo("VALIDATION_ERROR"));
    }

    @Test
    void 中短篇要求完整来源身份和目标字数范围() {
        NovelService service = new NovelService(mock(NovelRepository.class));
        CreateNovelRequest request = new CreateNovelRequest(
                "作品", StoryLengthProfile.SHORT_MEDIUM);
        request.setClientRequestId(JsonNullable.of("request-12345678"));
        request.setSourceKind(ShortMediumSourceKind.IDEA);
        request.setSourceText(JsonNullable.of("灵感"));
        request.setTargetTotalWordCount(JsonNullable.of(5_999));

        assertThatThrownBy(() -> service.create("user-1", request))
                .isInstanceOfSatisfying(ApiException.class, exception -> {
                    assertThat(exception.statusCode()).isEqualTo(422);
                    assertThat(exception.code()).isEqualTo("VALIDATION_ERROR");
                });
    }

    @Test
    void 归一化后为空的小说名被拒绝() {
        NovelService service = new NovelService(mock(NovelRepository.class));
        CreateNovelRequest request = new CreateNovelRequest(
                "   ", StoryLengthProfile.LONG_SERIAL);

        assertThatThrownBy(() -> service.create("user-1", request))
                .isInstanceOfSatisfying(ApiException.class, exception ->
                        assertThat(exception.code()).isEqualTo("NOVEL_NAME_REQUIRED"));
    }
}
