package cn.inkforge.contracts.api;

import static org.assertj.core.api.Assertions.assertThat;

import jakarta.validation.Validation;
import java.time.OffsetDateTime;
import java.util.List;
import org.junit.jupiter.api.Test;
import tools.jackson.databind.ObjectMapper;

class RequiredNullableContractTest {

    @Test
    void 必填可空字段必须拒绝缺失但接受显式null() {
        try (var factory = Validation.buildDefaultValidatorFactory()) {
            var validator = factory.getValidator();

            assertThat(validator.validate(new ChapterProgressRequest().content("正文")))
                    .extracting(value -> value.getPropertyPath().toString())
                    .contains("expectedUpdatedAt");
            assertThat(validator.validate(new ChapterProgressRequest("正文", null)))
                    .isEmpty();
        }
    }

    @Test
    void 响应中的必显可空字段不得被错误生成NotNull门禁() {
        try (var factory = Validation.buildDefaultValidatorFactory()) {
            var validator = factory.getValidator();
            DashboardNovel response = new DashboardNovel(
                    null,
                    List.of(),
                    "novel-1",
                    "作品",
                    null,
                    OffsetDateTime.parse("2026-08-25T00:00:00Z"));

            assertThat(validator.validate(response)).isEmpty();
        }
    }

    @Test
    void 响应中的非必填可空字段也必须保留显式null键() {
        DocumentVersionPayload response = new DocumentVersionPayload(
                "完整正文",
                "a".repeat(64),
                DocumentType.OUTLINE,
                DocumentVersionPayload.KindEnum.OUTLINE_DRAFT,
                VersionSource.MANUAL,
                1);

        var serialized = new ObjectMapper().valueToTree(response);

        assertThat(serialized.has("baseVersionId")).isTrue();
        assertThat(serialized.path("baseVersionId").isNull()).isTrue();
        assertThat(serialized.has("sourceTaskId")).isTrue();
        assertThat(serialized.path("sourceTaskId").isNull()).isTrue();
    }
}
