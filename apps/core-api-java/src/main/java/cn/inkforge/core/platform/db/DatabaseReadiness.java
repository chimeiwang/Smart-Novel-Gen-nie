package cn.inkforge.core.platform.db;

import java.sql.Connection;
import java.sql.ResultSet;
import java.sql.Statement;
import java.time.Duration;
import java.util.concurrent.locks.ReentrantLock;
import java.util.function.LongSupplier;

/** 复用主连接池并对昂贵结构检查做成功/失败分级缓存。 */
public final class DatabaseReadiness {

    private final CoreDatabase database;
    private final SchemaVerifier verifier;
    private final ReentrantLock schemaLock = new ReentrantLock();
    private final LongSupplier nanoTime;
    private final long successTtlNanos;
    private final long failureTtlNanos;
    private volatile Boolean schemaReady;
    private volatile long schemaCheckedAt;

    public DatabaseReadiness(CoreDatabase database, SchemaProfile profile) {
        this(database, profile, System::nanoTime, Duration.ofSeconds(30), Duration.ofSeconds(5));
    }

    DatabaseReadiness(
            CoreDatabase database,
            SchemaProfile profile,
            LongSupplier nanoTime,
            Duration successTtl,
            Duration failureTtl) {
        this.database = database;
        this.verifier = new SchemaVerifier(SchemaContracts.loadBundled(), profile);
        this.nanoTime = nanoTime;
        this.successTtlNanos = successTtl.toNanos();
        this.failureTtlNanos = failureTtl.toNanos();
    }

    public boolean checkConnection() {
        try (Connection connection = database.connection();
                Statement statement = connection.createStatement();
                ResultSet result = statement.executeQuery("SELECT 1")) {
            return result.next() && result.getInt(1) == 1;
        } catch (Exception exception) {
            return false;
        }
    }

    public boolean checkSchema() {
        Boolean cached = cachedResult();
        if (cached != null) {
            return cached;
        }
        schemaLock.lock();
        try {
            cached = cachedResult();
            if (cached != null) {
                return cached;
            }
            boolean ready;
            try (Connection connection = database.connection()) {
                ready = verifier.verify(connection, "public").ready();
            } catch (Exception exception) {
                ready = false;
            }
            schemaReady = ready;
            schemaCheckedAt = nanoTime.getAsLong();
            return ready;
        } finally {
            schemaLock.unlock();
        }
    }

    private Boolean cachedResult() {
        Boolean ready = schemaReady;
        if (ready == null) {
            return null;
        }
        long ttl = ready ? successTtlNanos : failureTtlNanos;
        return nanoTime.getAsLong() - schemaCheckedAt < ttl ? ready : null;
    }
}
