package cn.inkforge.contracts.validation;

import jakarta.validation.Constraint;
import jakarta.validation.Payload;
import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

/** 要求 JSON 字段出现，但允许其显式值为 {@code null}。 */
@Documented
@Constraint(validatedBy = RequiredJsonNullableValidator.class)
@Target({ElementType.FIELD, ElementType.METHOD, ElementType.PARAMETER, ElementType.TYPE_USE})
@Retention(RetentionPolicy.RUNTIME)
public @interface RequiredJsonNullable {

    String message() default "字段必须出现";

    Class<?>[] groups() default {};

    Class<? extends Payload>[] payload() default {};
}
