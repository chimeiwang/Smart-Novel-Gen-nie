package cn.inkforge.core.platform.db;

import com.zaxxer.hikari.HikariConfig;
import com.zaxxer.hikari.HikariDataSource;
import java.sql.Connection;
import java.sql.SQLException;
import java.sql.Statement;
import java.time.Duration;
import java.util.Objects;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;
import java.util.function.Function;
import javax.sql.DataSource;
import org.jooq.DSLContext;
import org.jooq.ExecuteContext;
import org.jooq.ExecuteListener;
import org.jooq.SQLDialect;
import org.jooq.conf.Settings;
import org.jooq.exception.DataAccessException;
import org.jooq.impl.DSL;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/** 唯一 PostgreSQL 连接池和 jOOQ 入口；从不建表或运行迁移。 */
public final class CoreDatabase implements AutoCloseable {

    private static final Logger LOGGER = LoggerFactory.getLogger(CoreDatabase.class);

    private final HikariDataSource dataSource;
    private final DSLContext dsl;
    private final ThreadLocal<DSLContext> transactionContext = new ThreadLocal<>();
    private final ExecutorService networkTimeoutExecutor;

    private CoreDatabase(HikariDataSource dataSource) {
        this.dataSource = dataSource;
        this.dsl = DSL.using(dataSource, SQLDialect.POSTGRES);
        this.networkTimeoutExecutor = Executors.newThreadPerTaskExecutor(
                Thread.ofVirtual().name("inkforge-postgres-cancel-", 0).factory());
    }

    public static CoreDatabase connect(PostgresConnectionSettings settings) {
        HikariConfig config = new HikariConfig();
        config.setPoolName("inkforge-core-postgres");
        config.setJdbcUrl(settings.jdbcUrl());
        config.setUsername(settings.username());
        config.setPassword(settings.password());
        config.setMaximumPoolSize(5);
        config.setMinimumIdle(0);
        config.setConnectionTimeout(5_000);
        config.setValidationTimeout(2_000);
        config.setIdleTimeout(60_000);
        config.setMaxLifetime(600_000);
        config.setInitializationFailTimeout(-1);
        config.setAutoCommit(true);
        return new CoreDatabase(new HikariDataSource(config));
    }

    public DataSource dataSource() {
        return dataSource;
    }

    public DSLContext dsl() {
        DSLContext current = transactionContext.get();
        return current == null ? dsl : current;
    }

    /**
     * 执行可跨模块复用的同步工作单元；同一线程中的嵌套调用加入现有事务，禁止各领域提前提交。
     */
    public <T> T transactionResult(Function<DSLContext, T> work) {
        Objects.requireNonNull(work);
        DSLContext current = transactionContext.get();
        if (current != null) return work.apply(current);
        return dsl.transactionResult(configuration -> {
            DSLContext transaction = DSL.using(configuration);
            transactionContext.set(transaction);
            try {
                return work.apply(transaction);
            } finally {
                transactionContext.remove();
            }
        });
    }

    public Connection connection() throws SQLException {
        return dataSource.getConnection();
    }

    /**
     * 为后台观察类查询执行有界只读事务。
     *
     * <p>PostgreSQL `statement_timeout`、JDBC query timeout 和连接 network timeout 同时生效。
     * network timeout 只修改当前借用连接，并在归还 Hikari 前恢复；显式取消会先命中当前 JDBC
     * Statement，必要时再硬中止且淘汰该连接。
     */
    public <T> T timedReadOnlyTransactionResult(
            Duration statementTimeout,
            Duration networkTimeout,
            DatabaseQueryCancellation cancellation,
            Function<DSLContext, T> work) {
        Objects.requireNonNull(cancellation);
        Objects.requireNonNull(work);
        int statementTimeoutMillis = positiveMillis(statementTimeout, "statementTimeout");
        int networkTimeoutMillis = positiveMillis(networkTimeout, "networkTimeout");
        if (statementTimeoutMillis >= networkTimeoutMillis) {
            throw new IllegalArgumentException("数据库查询超时顺序无效");
        }
        int jdbcQueryTimeoutSeconds = Math.toIntExact(
                Math.floorDiv((long) statementTimeoutMillis + 999L, 1_000L));

        try (Connection connection = dataSource.getConnection()) {
            int originalNetworkTimeout = connection.getNetworkTimeout();
            boolean originalReadOnly = connection.isReadOnly();
            boolean originalAutoCommit = connection.getAutoCommit();
            Throwable primaryFailure = null;
            AtomicReference<DatabaseQueryCancellation.Registration> statementRegistration =
                    new AtomicReference<>();
            ExecuteListener statementTracker = statementCancellationTracker(
                    cancellation, statementRegistration);
            DatabaseQueryCancellation.Registration abortRegistration =
                    cancellation.registerConnectionAbort(
                            () -> abortConnection(connection));
            try {
                connection.setNetworkTimeout(networkTimeoutExecutor, networkTimeoutMillis);
                connection.setReadOnly(true);
                connection.setAutoCommit(false);
                Settings settings = new Settings().withQueryTimeout(jdbcQueryTimeoutSeconds);
                DSLContext transaction = DSL.using(
                        DSL.using(connection, SQLDialect.POSTGRES, settings)
                                .configuration()
                                .derive(statementTracker));
                transaction.fetchValue(
                        "SELECT set_config('statement_timeout', ?, true)",
                        statementTimeoutMillis + "ms");
                T result = work.apply(transaction);
                connection.commit();
                return result;
            } catch (RuntimeException | Error exception) {
                primaryFailure = exception;
                rollback(connection, exception);
                throw exception;
            } catch (SQLException exception) {
                DataAccessException wrapped =
                        new DataAccessException("数据库有界只读事务失败", exception);
                primaryFailure = wrapped;
                rollback(connection, wrapped);
                throw wrapped;
            } finally {
                closeRegistration(statementRegistration.getAndSet(null));
                abortRegistration.close();
                restoreConnection(
                        connection,
                        originalNetworkTimeout,
                        originalReadOnly,
                        originalAutoCommit,
                        primaryFailure);
            }
        } catch (SQLException exception) {
            throw new DataAccessException("数据库有界只读事务失败", exception);
        }
    }

    @Override
    public void close() {
        dataSource.close();
        networkTimeoutExecutor.shutdownNow();
        try {
            if (!networkTimeoutExecutor.awaitTermination(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("数据库取消执行器未在期限内停止");
            }
        } catch (InterruptedException exception) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("等待数据库取消执行器停止时被中断", exception);
        }
    }

    private ExecuteListener statementCancellationTracker(
            DatabaseQueryCancellation cancellation,
            AtomicReference<DatabaseQueryCancellation.Registration> registration) {
        return new ExecuteListener() {
            @Override
            public void executeStart(ExecuteContext context) {
                Statement statement = context.statement();
                if (statement == null) return;
                DatabaseQueryCancellation.Registration next =
                        cancellation.registerStatementCancel(
                                () -> scheduleStatementCancel(statement));
                if (!registration.compareAndSet(null, next)) {
                    next.close();
                    throw new IllegalStateException("JDBC Statement 取消句柄重叠");
                }
            }

            @Override
            public void end(ExecuteContext context) {
                closeRegistration(registration.getAndSet(null));
            }
        };
    }

    private void scheduleStatementCancel(Statement statement) {
        try {
            networkTimeoutExecutor.execute(() -> {
                try {
                    statement.cancel();
                } catch (SQLException exception) {
                    LOGGER.atWarn()
                            .addKeyValue("errorCode", "DATABASE_QUERY_STATEMENT_CANCEL_FAILED")
                            .addKeyValue("exceptionType", exception.getClass().getName())
                            .setCause(exception)
                            .log("JDBC Statement 取消失败");
                }
            });
        } catch (RejectedExecutionException exception) {
            throw new IllegalStateException("数据库取消执行器已关闭", exception);
        }
    }

    private void abortConnection(Connection connection) {
        try {
            connection.abort(networkTimeoutExecutor);
        } catch (SQLException exception) {
            LOGGER.atError()
                    .addKeyValue("errorCode", "DATABASE_QUERY_CONNECTION_ABORT_FAILED")
                    .addKeyValue("exceptionType", exception.getClass().getName())
                    .setCause(exception)
                    .log("JDBC Connection 硬中止失败");
        } finally {
            // abort 由 JDBC 在共享 executor 上执行；先显式淘汰借用句柄，禁止延迟的硬中止命中已重新借出的连接。
            dataSource.evictConnection(connection);
        }
    }

    private void restoreConnection(
            Connection connection,
            int originalNetworkTimeout,
            boolean originalReadOnly,
            boolean originalAutoCommit,
            Throwable primaryFailure) {
        try {
            if (connection.isClosed()) return;
            connection.setNetworkTimeout(networkTimeoutExecutor, originalNetworkTimeout);
            connection.setAutoCommit(originalAutoCommit);
            connection.setReadOnly(originalReadOnly);
        } catch (SQLException exception) {
            if (primaryFailure != null) {
                primaryFailure.addSuppressed(exception);
                return;
            }
            throw new DataAccessException("恢复数据库连接超时状态失败", exception);
        }
    }

    private static void rollback(Connection connection, Throwable primaryFailure) {
        try {
            if (!connection.isClosed()) connection.rollback();
        } catch (SQLException rollbackFailure) {
            primaryFailure.addSuppressed(rollbackFailure);
        }
    }

    private static void closeRegistration(DatabaseQueryCancellation.Registration registration) {
        if (registration != null) registration.close();
    }

    private static int positiveMillis(Duration value, String field) {
        if (value == null || value.isZero() || value.isNegative()) {
            throw new IllegalArgumentException(field + " 必须大于 0");
        }
        long millis = value.toMillis();
        if (millis < 1 || millis > Integer.MAX_VALUE) {
            throw new IllegalArgumentException(field + " 超出 JDBC 可表示范围");
        }
        return Math.toIntExact(millis);
    }
}
