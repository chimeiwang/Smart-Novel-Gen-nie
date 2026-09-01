package cn.inkforge.core.platform.db;

import java.util.Objects;
import java.util.Optional;
import java.util.concurrent.atomic.AtomicBoolean;

/**
 * 一次数据库查询的显式取消句柄。
 *
 * <p>语句取消与连接硬中止是两个独立阶段；请求可以早于 JDBC 句柄注册，后到的句柄会立即执行已请求的取消。
 * 这个完成门只证明已向 JDBC 请求取消，调用方仍必须独立证明原查询线程已退出。
 */
public final class DatabaseQueryCancellation {

    private final Phase statement = new Phase();
    private final Phase connection = new Phase();

    public Registration registerStatementCancel(Runnable action) {
        return statement.register(action);
    }

    public Registration registerConnectionAbort(Runnable action) {
        return connection.register(action);
    }

    public CancellationRequest requestStatementCancel() {
        return statement.request();
    }

    public CancellationRequest requestConnectionAbort() {
        return connection.request();
    }

    public boolean cancellationRequested() {
        return statement.requested() || connection.requested();
    }

    public Optional<Throwable> cancellationFailure() {
        Throwable statementFailure = statement.failure();
        return Optional.ofNullable(statementFailure == null ? connection.failure() : statementFailure);
    }

    public interface Registration extends AutoCloseable {
        @Override
        void close();
    }

    public record CancellationRequest(boolean firstRequest, boolean actionRegistered) {}

    private static final class Phase {

        private final Object lock = new Object();
        private boolean requested;
        private ActionRegistration active;
        private volatile Throwable failure;

        private Registration register(Runnable action) {
            Objects.requireNonNull(action);
            ActionRegistration registration = new ActionRegistration(action);
            boolean invokeImmediately;
            synchronized (lock) {
                if (active != null) {
                    throw new IllegalStateException("数据库查询取消句柄重复注册");
                }
                active = registration;
                invokeImmediately = requested;
            }
            if (invokeImmediately) invoke(registration);
            return () -> {
                synchronized (lock) {
                    if (active == registration) active = null;
                }
            };
        }

        private CancellationRequest request() {
            ActionRegistration registration;
            boolean firstRequest;
            synchronized (lock) {
                firstRequest = !requested;
                requested = true;
                registration = active;
            }
            if (registration != null) invoke(registration);
            return new CancellationRequest(firstRequest, registration != null);
        }

        private void invoke(ActionRegistration registration) {
            if (!registration.invoked.compareAndSet(false, true)) return;
            try {
                registration.action.run();
            } catch (RuntimeException | Error exception) {
                failure = exception;
            }
        }

        private boolean requested() {
            synchronized (lock) {
                return requested;
            }
        }

        private Throwable failure() {
            return failure;
        }
    }

    private static final class ActionRegistration {

        private final Runnable action;
        private final AtomicBoolean invoked = new AtomicBoolean();

        private ActionRegistration(Runnable action) {
            this.action = action;
        }
    }
}
