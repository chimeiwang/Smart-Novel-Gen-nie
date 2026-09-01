package cn.inkforge.core.platform.http;

import cn.inkforge.serviceauth.ServiceAuthException;
import jakarta.servlet.http.HttpServletRequest;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.validation.FieldError;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.MissingServletRequestParameterException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.HttpRequestMethodNotSupportedException;
import org.springframework.web.method.annotation.MethodArgumentTypeMismatchException;
import org.springframework.web.multipart.MaxUploadSizeExceededException;
import org.springframework.web.servlet.NoHandlerFoundException;
import org.springframework.web.servlet.resource.NoResourceFoundException;
import org.springframework.web.context.request.async.AsyncRequestNotUsableException;
import tools.jackson.core.JacksonException;
import tools.jackson.databind.exc.UnrecognizedPropertyException;

/** 把业务、服务身份、参数校验和未知异常统一收口到冻结的 Python 错误信封。 */
@RestControllerAdvice
public final class ApiExceptionHandler {

    private static final Logger LOGGER = LoggerFactory.getLogger(ApiExceptionHandler.class);
    private static final Map<Integer, String> SERVICE_AUTH_MESSAGES = Map.of(
            401, "服务身份认证失败",
            403, "服务调用权限不足",
            409, "服务令牌已被使用",
            503, "服务请求重放保护暂不可用");

    @ExceptionHandler(ApiException.class)
    public ResponseEntity<ApiErrorResponse> api(ApiException exception, HttpServletRequest request) {
        return response(
                exception.statusCode(),
                exception.code(),
                exception.getMessage(),
                exception.details(),
                exception.headers(),
                request);
    }

    @ExceptionHandler(ServiceAuthException.class)
    public ResponseEntity<ApiErrorResponse> serviceAuth(
            ServiceAuthException exception, HttpServletRequest request) {
        return response(
                exception.statusCode(),
                exception.code(),
                SERVICE_AUTH_MESSAGES.getOrDefault(exception.statusCode(), "服务身份校验失败"),
                null,
                Map.of(),
                request);
    }

    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<ApiErrorResponse> bodyValidation(
            MethodArgumentNotValidException exception, HttpServletRequest request) {
        List<ValidationDetail> details = exception.getBindingResult().getFieldErrors().stream()
                .sorted(Comparator.comparing(FieldError::getField))
                .map(ApiExceptionHandler::fieldError)
                .toList();
        return validation(details, request);
    }

    @ExceptionHandler(HttpMessageNotReadableException.class)
    public ResponseEntity<ApiErrorResponse> unreadable(
            HttpMessageNotReadableException exception, HttpServletRequest request) {
        UnrecognizedPropertyException unknown = cause(
                exception, UnrecognizedPropertyException.class);
        if (unknown != null) {
            List<Object> path = jacksonPath(unknown);
            if (path.isEmpty() || !unknown.getPropertyName().equals(path.getLast())) {
                path.add(unknown.getPropertyName());
            }
            path.addFirst("body");
            return validation(
                    List.of(new ValidationDetail(path, "包含不允许的字段", "extra_forbidden")),
                    request);
        }
        return validation(
                List.of(new ValidationDetail(List.of("body"), "请求体不是有效 JSON", "json_invalid")),
                request);
    }

    @ExceptionHandler(MissingServletRequestParameterException.class)
    public ResponseEntity<ApiErrorResponse> missingQuery(
            MissingServletRequestParameterException exception, HttpServletRequest request) {
        return validation(
                List.of(new ValidationDetail(
                        List.of("query", exception.getParameterName()),
                        "缺少必需字段",
                        "missing")),
                request);
    }

    @ExceptionHandler(MethodArgumentTypeMismatchException.class)
    public ResponseEntity<ApiErrorResponse> queryType(
            MethodArgumentTypeMismatchException exception, HttpServletRequest request) {
        String type = exception.getRequiredType() != null
                        && Number.class.isAssignableFrom(box(exception.getRequiredType()))
                ? "int_parsing"
                : "validation_error";
        String message = "int_parsing".equals(type) ? "输入值必须是有效整数" : "输入值无效";
        return validation(
                List.of(new ValidationDetail(
                        List.of("query", exception.getName()), message, type)),
                request);
    }

    @ExceptionHandler(MaxUploadSizeExceededException.class)
    public ResponseEntity<ApiErrorResponse> uploadTooLarge(
            MaxUploadSizeExceededException exception, HttpServletRequest request) {
        if (request.getRequestURI().startsWith("/api/v1/styles/")) {
            return response(
                    413,
                    "STYLE_REFERENCE_TOO_LARGE",
                    "文件不能超过 50 MiB",
                    null,
                    Map.of(),
                    request);
        }
        return response(413, "PAYLOAD_TOO_LARGE", "上传文件过大", null, Map.of(), request);
    }

    @ExceptionHandler({NoResourceFoundException.class, NoHandlerFoundException.class})
    public ResponseEntity<ApiErrorResponse> notFound(
            Exception exception, HttpServletRequest request) {
        return response(404, "NOT_FOUND", "请求的资源不存在", null, Map.of(), request);
    }

    @ExceptionHandler(HttpRequestMethodNotSupportedException.class)
    public ResponseEntity<ApiErrorResponse> methodNotAllowed(
            HttpRequestMethodNotSupportedException exception, HttpServletRequest request) {
        Map<String, String> headers = exception.getSupportedHttpMethods() == null
                ? Map.of()
                : Map.of("Allow", exception.getSupportedHttpMethods().stream()
                        .map(Object::toString)
                        .sorted()
                        .collect(java.util.stream.Collectors.joining(", ")));
        return response(
                405,
                "HTTP_ERROR",
                "请求方法不被允许",
                null,
                headers,
                request);
    }

    @ExceptionHandler(AsyncRequestNotUsableException.class)
    public void asyncClientDisconnected(HttpServletRequest request) {
        // 响应在 Servlet 容器上报断线后已经不可再写；只做安全分类，禁止尝试追加 JSON 错误信封。
        LOGGER.atDebug()
                .addKeyValue("requestId", RequestIdFilter.requestId(request))
                .addKeyValue("code", "ASYNC_CLIENT_DISCONNECTED")
                .log("客户端在异步响应期间断开连接");
    }

    @ExceptionHandler(Exception.class)
    public ResponseEntity<ApiErrorResponse> unexpected(
            Exception exception, HttpServletRequest request) {
        LOGGER.atError()
                .addKeyValue("requestId", RequestIdFilter.requestId(request))
                .addKeyValue("code", "INTERNAL_SERVER_ERROR")
                .addKeyValue("exceptionType", exception.getClass().getSimpleName())
                // 公共响应保持净化；服务端必须保留完整堆栈，不能把未知故障压成不可诊断的一行日志。
                .setCause(exception)
                .log("接口发生未处理异常");
        return response(
                500,
                "INTERNAL_SERVER_ERROR",
                "服务器内部错误",
                null,
                Map.of(),
                request);
    }

    private static ResponseEntity<ApiErrorResponse> validation(
            List<ValidationDetail> details, HttpServletRequest request) {
        return response(
                422,
                "VALIDATION_ERROR",
                "请求参数校验失败",
                details,
                Map.of(),
                request);
    }

    private static ResponseEntity<ApiErrorResponse> response(
            int status,
            String code,
            String message,
            Object details,
            Map<String, String> headers,
            HttpServletRequest request) {
        HttpHeaders responseHeaders = new HttpHeaders();
        headers.forEach(responseHeaders::set);
        responseHeaders.setContentType(MediaType.APPLICATION_JSON);
        String requestId = RequestIdFilter.requestId(request);
        responseHeaders.set(RequestIdFilter.HEADER, requestId);
        return ResponseEntity.status(status)
                .headers(responseHeaders)
                .body(new ApiErrorResponse(code, message, details, requestId));
    }

    private static ValidationDetail fieldError(FieldError error) {
        List<Object> path = new ArrayList<>();
        path.add("body");
        path.addAll(propertyPath(error.getField()));
        String annotation = error.getCode();
        if ("RequiredJsonNullable".equals(annotation)) {
            return new ValidationDetail(path, "缺少必需字段", "missing");
        }
        if (("NotNull".equals(annotation) || "NotBlank".equals(annotation))
                && error.getRejectedValue() == null) {
            return new ValidationDetail(path, "缺少必需字段", "missing");
        }
        if ("NotBlank".equals(annotation)) {
            return new ValidationDetail(path, "输入文本过短", "string_too_short");
        }
        if ("Size".equals(annotation) && error.getRejectedValue() instanceof String text) {
            if (text.length() > 4096) {
                return new ValidationDetail(path, "输入文本过长", "string_too_long");
            }
            return new ValidationDetail(path, "输入文本长度无效", "string_too_short");
        }
        if ("Pattern".equals(annotation)) {
            return new ValidationDetail(path, "输入值无效", "string_pattern_mismatch");
        }
        return new ValidationDetail(path, "输入值无效", "validation_error");
    }

    private static List<Object> propertyPath(String field) {
        List<Object> result = new ArrayList<>();
        for (String component : field.split("\\.")) {
            int bracket = component.indexOf('[');
            if (bracket < 0) {
                result.add(component);
                continue;
            }
            result.add(component.substring(0, bracket));
            int cursor = bracket;
            while (cursor >= 0) {
                int end = component.indexOf(']', cursor);
                if (end < 0) {
                    break;
                }
                String index = component.substring(cursor + 1, end);
                result.add(index.matches("[0-9]+") ? Integer.parseInt(index) : index);
                cursor = component.indexOf('[', end + 1);
            }
        }
        return result;
    }

    private static List<Object> jacksonPath(JacksonException exception) {
        List<Object> result = new ArrayList<>();
        for (JacksonException.Reference reference : exception.getPath()) {
            if (reference.getPropertyName() != null) {
                result.add(reference.getPropertyName());
            } else if (reference.getIndex() >= 0) {
                result.add(reference.getIndex());
            }
        }
        return result;
    }

    private static <T extends Throwable> T cause(Throwable value, Class<T> expected) {
        Throwable current = value;
        for (int depth = 0; current != null && depth < 12; depth++) {
            if (expected.isInstance(current)) {
                return expected.cast(current);
            }
            current = current.getCause();
        }
        return null;
    }

    private static Class<?> box(Class<?> type) {
        if (!type.isPrimitive()) {
            return type;
        }
        if (type == int.class) {
            return Integer.class;
        }
        if (type == long.class) {
            return Long.class;
        }
        if (type == double.class) {
            return Double.class;
        }
        if (type == float.class) {
            return Float.class;
        }
        if (type == short.class) {
            return Short.class;
        }
        if (type == byte.class) {
            return Byte.class;
        }
        return type;
    }

    public record ValidationDetail(List<Object> path, String message, String type) {

        public ValidationDetail {
            path = List.copyOf(path);
        }
    }
}
