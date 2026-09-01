package cn.inkforge.core.platform.http;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;

class ManagedSseEmitterInterceptorTest {

    @Test
    void 只有HandlerReady边界启动且完成与重复回调只关闭一次() {
        ManagedSseEmitterInterceptor interceptor = new ManagedSseEmitterInterceptor();
        MockHttpServletRequest request = new MockHttpServletRequest();
        MockHttpServletResponse response = new MockHttpServletResponse();
        RecordingEmitter emitter = new RecordingEmitter();
        emitter.arm(request);

        assertThat(emitter.starts).hasValue(0);
        assertThat(emitter.aborts).hasValue(0);

        interceptor.afterConcurrentHandlingStarted(request, response, new Object());
        interceptor.afterConcurrentHandlingStarted(request, response, new Object());

        assertThat(emitter.starts).hasValue(1);
        assertThat(emitter.aborts).hasValue(0);

        interceptor.afterCompletion(request, response, new Object(), null);
        interceptor.afterCompletion(request, response, new Object(), null);

        assertThat(emitter.starts).hasValue(1);
        assertThat(emitter.aborts).hasValue(1);
    }

    @Test
    void 同步完成先于异步启动时只关闭且不得迟到启动() {
        ManagedSseEmitterInterceptor interceptor = new ManagedSseEmitterInterceptor();
        MockHttpServletRequest request = new MockHttpServletRequest();
        MockHttpServletResponse response = new MockHttpServletResponse();
        RecordingEmitter emitter = new RecordingEmitter();
        emitter.arm(request);

        interceptor.afterCompletion(request, response, new Object(), null);
        interceptor.afterConcurrentHandlingStarted(request, response, new Object());

        assertThat(emitter.starts).hasValue(0);
        assertThat(emitter.aborts).hasValue(1);
    }

    private static final class RecordingEmitter extends ManagedSseEmitter {

        private final AtomicInteger starts = new AtomicInteger();
        private final AtomicInteger aborts = new AtomicInteger();

        private RecordingEmitter() {
            super(0L);
        }

        @Override
        protected void startManagedSession() {
            starts.incrementAndGet();
        }

        @Override
        protected void abortManagedSession() {
            aborts.incrementAndGet();
        }
    }
}
