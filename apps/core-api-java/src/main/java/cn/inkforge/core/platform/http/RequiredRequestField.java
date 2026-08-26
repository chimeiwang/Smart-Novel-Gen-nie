package cn.inkforge.core.platform.http;

import java.util.List;
import java.util.Map;
import org.openapitools.jackson.nullable.JsonNullable;

/** 对“必须出现但允许 null”的 JSON 字段做框架无关的最终入口校验。 */
public final class RequiredRequestField {

    private RequiredRequestField() {}

    public static <T> T nullable(JsonNullable<T> value, String fieldName) {
        if (value == null || value.isUndefined()) {
            throw new ApiException(
                    422,
                    "VALIDATION_ERROR",
                    "请求参数校验失败",
                    List.of(Map.of(
                            "path", List.of("body", fieldName),
                            "message", "缺少必需字段",
                            "type", "missing")));
        }
        return value.orElse(null);
    }
}
