package cn.inkforge.core.platform.http;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.web.servlet.AsyncHandlerInterceptor;

/** 在 Spring 已为 SseEmitter 安装 handler 后才启动连接 worker。 */
public final class ManagedSseEmitterInterceptor implements AsyncHandlerInterceptor {

    @Override
    public void afterConcurrentHandlingStarted(
            HttpServletRequest request, HttpServletResponse response, Object handler) {
        ManagedSseEmitter emitter = emitter(request);
        if (emitter != null) emitter.startAfterHandlerReady();
    }

    @Override
    public void afterCompletion(
            HttpServletRequest request,
            HttpServletResponse response,
            Object handler,
            Exception exception) {
        ManagedSseEmitter emitter = emitter(request);
        if (emitter != null) emitter.abort();
    }

    private static ManagedSseEmitter emitter(HttpServletRequest request) {
        Object value = request.getAttribute(ManagedSseEmitter.REQUEST_ATTRIBUTE);
        return value instanceof ManagedSseEmitter emitter ? emitter : null;
    }
}
