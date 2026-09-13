package cn.inkforge.core.platform.db;

import static org.assertj.core.api.Assertions.assertThat;

import org.jooq.Field;
import org.junit.jupiter.api.Test;

class ReviewArtifactRowProjectionTest {

    @Test
    void 写作投影保留完整审核记录且不依赖视频能力() {
        assertThat(ReviewArtifactRowProjection.fields())
                .extracting(Field::getName)
                .containsExactly(
                        "id", "novelId", "chapterId", "taskId", "workflowRunId", "artifactKey",
                        "kind", "status", "title", "summary", "payloadJson", "diffJson",
                        "createdByAgent", "updatedByAgent", "reviewerAgent", "revision", "appliedAt",
                        "createdAt", "updatedAt");
    }

    @Test
    void 调用方不能修改其他查询使用的字段定义() {
        Field<?>[] first = ReviewArtifactRowProjection.fields();
        first[0] = null;
        assertThat(ReviewArtifactRowProjection.fields()[0].getName()).isEqualTo("id");
    }
}
