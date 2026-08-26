package cn.inkforge.core.platform.db;

import com.zaxxer.hikari.HikariConfig;
import com.zaxxer.hikari.HikariDataSource;
import java.sql.Connection;
import java.sql.SQLException;
import java.util.Objects;
import java.util.function.Function;
import javax.sql.DataSource;
import org.jooq.DSLContext;
import org.jooq.SQLDialect;
import org.jooq.impl.DSL;

/** 唯一 PostgreSQL 连接池和 jOOQ 入口；从不建表或运行迁移。 */
public final class CoreDatabase implements AutoCloseable {

    private final HikariDataSource dataSource;
    private final DSLContext dsl;
    private final ThreadLocal<DSLContext> transactionContext = new ThreadLocal<>();

    private CoreDatabase(HikariDataSource dataSource) {
        this.dataSource = dataSource;
        this.dsl = DSL.using(dataSource, SQLDialect.POSTGRES);
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

    @Override
    public void close() {
        dataSource.close();
    }
}
