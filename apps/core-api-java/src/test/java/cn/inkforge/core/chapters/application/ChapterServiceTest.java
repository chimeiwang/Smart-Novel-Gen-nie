package cn.inkforge.core.chapters.application;

import static org.assertj.core.api.Assertions.assertThat;

import cn.inkforge.contracts.api.ChapterStatus;
import cn.inkforge.contracts.api.UpdateChapterRequest;
import cn.inkforge.contracts.api.WorkspaceChapter;
import java.time.OffsetDateTime;
import java.util.List;
import org.junit.jupiter.api.Test;

class ChapterServiceTest {

    @Test
    void 空白标题回退但正文必须逐字保存() {
        RecordingRepository repository = new RecordingRepository();
        ChapterService service = new ChapterService(repository);
        String content = "  第一行\n\n最后一行  ".repeat(10_000);

        service.update(
                "user-1",
                "chapter-1",
                new UpdateChapterRequest(
                        content,
                        OffsetDateTime.parse("2026-07-11T00:00:00Z"),
                        "   "));

        assertThat(repository.title).isEqualTo("未命名章节");
        assertThat(repository.content).isEqualTo(content);
    }

    private static final class RecordingRepository implements ChapterRepository {
        private String title;
        private String content;

        @Override
        public WorkspaceChapter create(String novelId, String userId) {
            throw new UnsupportedOperationException();
        }

        @Override
        public List<WorkspaceChapter> list(String novelId, String userId) {
            throw new UnsupportedOperationException();
        }

        @Override
        public WorkspaceChapter get(String chapterId, String userId) {
            throw new UnsupportedOperationException();
        }

        @Override
        public OffsetDateTime updateDraft(
                String chapterId,
                String userId,
                String title,
                String content,
                OffsetDateTime expectedUpdatedAt) {
            this.title = title;
            this.content = content;
            return expectedUpdatedAt;
        }

        @Override
        public OffsetDateTime upsertProgress(
                String chapterId,
                String userId,
                String content,
                OffsetDateTime expectedUpdatedAt) {
            throw new UnsupportedOperationException();
        }

        @Override
        public ChapterRecord transitionStatus(
                String chapterId,
                String userId,
                ChapterStatus status,
                OffsetDateTime expectedUpdatedAt) {
            throw new UnsupportedOperationException();
        }
    }
}
