package cn.inkforge.core.platform.http;

/** 浏览器公共 API 的统一错误响应。 */
public record ApiErrorResponse(String code, String message, Object details, String requestId) {}
