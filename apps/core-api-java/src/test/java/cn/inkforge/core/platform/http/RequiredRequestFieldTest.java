package cn.inkforge.core.platform.http;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import org.junit.jupiter.api.Test;
import org.openapitools.jackson.nullable.JsonNullable;

class RequiredRequestFieldTest {

    @Test
    void 缺失被拒绝而显式null被接受() {
        assertThatThrownBy(() -> RequiredRequestField.nullable(
                        JsonNullable.undefined(), "expectedUpdatedAt"))
                .isInstanceOfSatisfying(ApiException.class, error -> {
                    assertThat(error.code()).isEqualTo("VALIDATION_ERROR");
                    assertThat(error.statusCode()).isEqualTo(422);
                });
        Object explicitNull = RequiredRequestField.nullable(
                JsonNullable.of(null), "expectedUpdatedAt");
        assertThat(explicitNull).isNull();
    }
}
