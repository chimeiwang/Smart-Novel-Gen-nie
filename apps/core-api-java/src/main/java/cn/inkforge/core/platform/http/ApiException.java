package cn.inkforge.core.platform.http;

import java.util.Map;

/** 业务层可抛出的稳定公共 API 异常，不接受底层异常作为 cause。 */
public final class ApiException extends RuntimeException {

    private final int statusCode;
    private final String code;
    private final Object details;
    private final Map<String, String> headers;

    public ApiException(int statusCode, String code, String message) {
        this(statusCode, code, message, null, Map.of());
    }

    public ApiException(int statusCode, String code, String message, Object details) {
        this(statusCode, code, message, details, Map.of());
    }

    public ApiException(
            int statusCode,
            String code,
            String message,
            Object details,
            Map<String, String> headers) {
        super(requireText(message, "错误消息"));
        if (statusCode < 400 || statusCode > 599) {
            throw new IllegalArgumentException("API 错误状态码无效");
        }
        this.statusCode = statusCode;
        this.code = requireText(code, "错误码");
        this.details = details;
        this.headers = Map.copyOf(headers == null ? Map.of() : headers);
    }

    public int statusCode() {
        return statusCode;
    }

    public String code() {
        return code;
    }

    public Object details() {
        return details;
    }

    public Map<String, String> headers() {
        return headers;
    }

    private static String requireText(String value, String label) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(label + "不能为空");
        }
        return value;
    }
}
