package cn.inkforge.contracts.validation;

import jakarta.validation.ConstraintValidator;
import jakarta.validation.ConstraintValidatorContext;
import org.openapitools.jackson.nullable.JsonNullable;

/** 显式 null 是“已出现”，只有 null 包装器或 undefined 才是缺失字段。 */
public final class RequiredJsonNullableValidator
        implements ConstraintValidator<RequiredJsonNullable, JsonNullable<?>> {

    @Override
    public boolean isValid(
            JsonNullable<?> value, ConstraintValidatorContext context) {
        return value != null && !value.isUndefined();
    }
}
