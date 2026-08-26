package cn.inkforge.core.platform.http;

import jakarta.servlet.RequestDispatcher;
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.boot.webmvc.error.ErrorController;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/** 把 Spring 默认错误页收口到现有 Core 中文错误契约。 */
@RestController
public final class CoreErrorController implements ErrorController {

    @RequestMapping(value = "${server.error.path:${error.path:/error}}", produces = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<ApiErrorResponse> error(HttpServletRequest request) {
        int status = resolveStatus(request);
        String requestId = RequestIdFilter.requestId(request);
        ApiErrorResponse body;
        if (status == 404) {
            body = new ApiErrorResponse("NOT_FOUND", "请求的资源不存在", null, requestId);
        } else if (status >= 400 && status < 500) {
            body = new ApiErrorResponse("HTTP_ERROR", httpMessage(status), null, requestId);
        } else {
            status = status >= 400 && status < 600 ? status : 500;
            body = new ApiErrorResponse("INTERNAL_SERVER_ERROR", "服务器内部错误", null, requestId);
        }
        return ResponseEntity.status(status).contentType(MediaType.APPLICATION_JSON).body(body);
    }

    private static String httpMessage(int status) {
        return switch (status) {
            case 400 -> "请求格式错误";
            case 401 -> "身份认证失败";
            case 403 -> "没有访问权限";
            case 405 -> "请求方法不被允许";
            case 409 -> "请求状态冲突";
            case 422 -> "请求参数校验失败";
            default -> "请求处理失败";
        };
    }

    private static int resolveStatus(HttpServletRequest request) {
        Object rawStatus = request.getAttribute(RequestDispatcher.ERROR_STATUS_CODE);
        return rawStatus instanceof Integer value ? value : 500;
    }
}
