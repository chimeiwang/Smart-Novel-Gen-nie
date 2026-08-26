package cn.inkforge.core.platform.patch;

import org.openapitools.jackson.nullable.JsonNullable;
import java.util.function.Function;

/** PATCH 字段的三态值：缺失、显式 null、具体值。 */
public record PatchField<T>(boolean present, T value) {

    public static <T> PatchField<T> from(JsonNullable<T> value) {
        if (value == null || value.isUndefined()) {
            return new PatchField<>(false, null);
        }
        return new PatchField<>(true, value.orElse(null));
    }

    public <R> PatchField<R> map(Function<? super T, ? extends R> mapper) {
        if (!present) {
            return new PatchField<>(false, null);
        }
        return new PatchField<>(true, value == null ? null : mapper.apply(value));
    }
}
