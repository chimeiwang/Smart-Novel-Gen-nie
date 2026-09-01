package cn.inkforge.core.platform.http;

import jakarta.servlet.http.HttpServletRequest;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.web.context.request.RequestContextHolder;
import org.springframework.web.context.request.ServletRequestAttributes;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

/** 由 MVC handler 初始化完成后的拦截器启动、并由请求和应用生命周期共同关闭的 SSE emitter。 */
public abstract class ManagedSseEmitter extends SseEmitter {

    static final String REQUEST_ATTRIBUTE = ManagedSseEmitter.class.getName() + ".session";
    private static final int CREATED = 0;
    private static final int STARTED = 1;
    private static final int ABORTED = 2;

    private final AtomicInteger lifecycle = new AtomicInteger(CREATED);
    private final AtomicBoolean responseCompleted = new AtomicBoolean();

    protected ManagedSseEmitter(long timeout) {
        super(timeout);
    }

    /** API 层在返回响应前把该 emitter 精确绑定到当前 Servlet 请求。 */
    public final SseEmitter armCurrentRequest() {
        if (!(RequestContextHolder.getRequestAttributes()
                instanceof ServletRequestAttributes attributes)) {
            throw new IllegalStateException("SSE emitter 只能绑定到当前 Servlet 请求");
        }
        arm(attributes.getRequest());
        return this;
    }

    final void arm(HttpServletRequest request) {
        Object existing = request.getAttribute(REQUEST_ATTRIBUTE);
        if (existing != null && existing != this) {
            throw new IllegalStateException("同一请求不能绑定多个 SSE emitter");
        }
        request.setAttribute(REQUEST_ATTRIBUTE, this);
    }

    final void startAfterHandlerReady() {
        if (!lifecycle.compareAndSet(CREATED, STARTED)) return;
        try {
            startManagedSession();
        } catch (RuntimeException exception) {
            lifecycle.set(ABORTED);
            try {
                responseCompleted.set(true);
                super.completeWithError(exception);
            } finally {
                abortManagedSession();
            }
        }
    }

    public final void abort() {
        int previous = lifecycle.getAndSet(ABORTED);
        if (previous != ABORTED) abortManagedSession();
    }

    /** 本地服务关闭必须显式结束已建立的异步响应，再释放连接资源。 */
    public final void shutdown() {
        int previous = lifecycle.getAndSet(ABORTED);
        if (previous == ABORTED) return;
        try {
            responseCompleted.set(true);
            super.complete();
        } finally {
            abortManagedSession();
        }
    }

    @Override
    public void complete() {
        responseCompleted.set(true);
        super.complete();
    }

    @Override
    public void completeWithError(Throwable failure) {
        responseCompleted.set(true);
        super.completeWithError(failure);
    }

    /** 只允许把已完成/已中止 session 的 IllegalStateException 归为正常断线。 */
    public final boolean isNoLongerWritable() {
        return responseCompleted.get() || lifecycle.get() == ABORTED;
    }

    protected abstract void startManagedSession();

    protected abstract void abortManagedSession();
}
