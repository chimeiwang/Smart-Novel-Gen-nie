package cn.inkforge.core.identity.infrastructure;

import static cn.inkforge.core.db.generated.Tables.CREDITLEDGER;
import static cn.inkforge.core.db.generated.Tables.USER;
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import cn.inkforge.core.identity.domain.AuthUser;
import cn.inkforge.core.identity.domain.DuplicateUsernameException;
import cn.inkforge.core.platform.db.CoreDatabase;
import cn.inkforge.core.platform.db.PostgresConnectionSettings;
import cn.inkforge.core.platform.id.CuidV1Generator;
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import org.jooq.impl.DSL;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import org.testcontainers.containers.Container.ExecResult;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.postgresql.PostgreSQLContainer;
import org.testcontainers.utility.MountableFile;

@Testcontainers
class JooqAuthRepositoryTest {

    @Container
    private static final PostgreSQLContainer POSTGRES =
            new PostgreSQLContainer("pgvector/pgvector:0.8.0-pg14")
                    .withDatabaseName("inkforge_identity_test")
                    .withUsername("inkforge")
                    .withPassword("test-only-password");

    private static CoreDatabase database;
    private static JooqAuthRepository repository;

    @BeforeAll
    static void 重建冻结结构() throws Exception {
        POSTGRES.copyFileToContainer(
                MountableFile.forClasspathResource("db/novelwriterdev-schema.sql"),
                "/tmp/novelwriterdev-schema.sql");
        ExecResult result = POSTGRES.execInContainer(
                "psql",
                "-v",
                "ON_ERROR_STOP=1",
                "-U",
                POSTGRES.getUsername(),
                "-d",
                POSTGRES.getDatabaseName(),
                "-f",
                "/tmp/novelwriterdev-schema.sql");
        assertThat(result.getExitCode()).as(result.getStderr()).isZero();
        database = CoreDatabase.connect(PostgresConnectionSettings.parse(databaseUrl()));
        repository = new JooqAuthRepository(
                database,
                new CuidV1Generator(Clock.systemUTC()),
                Clock.fixed(Instant.parse("2026-08-24T12:34:56.789Z"), ZoneOffset.UTC));
    }

    @AfterAll
    static void closeDatabase() {
        if (database != null) {
            database.close();
        }
    }

    @Test
    void 注册必须在同一事务写用户与赠送流水() {
        AuthUser user = repository.register("alice", "$2b$12$hash");

        assertThat(user.id()).matches("^c[a-z0-9]{24}$");
        assertThat(user.username()).isEqualTo("alice");
        assertThat(user.creditBalanceMicros()).isEqualTo(1_000_000_000L);
        assertThat(repository.findByUsername("alice")).isEqualTo(user);
        assertThat(repository.findById(user.id())).isEqualTo(user);
        assertThat(database.dsl().selectCount().from(USER).where(USER.ID.eq(user.id())).fetchOne(0, int.class))
                .isEqualTo(1);
        var ledger = database.dsl().selectFrom(CREDITLEDGER)
                .where(CREDITLEDGER.USERID.eq(user.id()))
                .fetchSingle();
        assertThat(ledger.getType()).isEqualTo("signup_bonus");
        assertThat(ledger.getAmountmicros()).isEqualTo(1_000_000_000L);
        assertThat(ledger.getBalanceaftermicros()).isEqualTo(1_000_000_000L);
        assertThat(ledger.getNote()).isEqualTo("注册赠送 1000 积分");
        assertThat(ledger.getPrompttokens()).isZero();
        assertThat(ledger.getCompletiontokens()).isZero();
        assertThat(ledger.getCachedtokens()).isZero();
        assertThat(ledger.getTotaltokens()).isZero();
    }

    @Test
    void 只有精确用户名唯一约束才转换为重名错误() {
        repository.register("duplicate", "$2b$12$first");

        assertThatThrownBy(() -> repository.register("duplicate", "$2b$12$second"))
                .isInstanceOf(DuplicateUsernameException.class);
    }

    @Test
    void 流水插入失败必须回滚用户() {
        database.dsl().execute("""
                CREATE OR REPLACE FUNCTION java_fail_signup_ledger() RETURNS trigger AS $$
                BEGIN
                  IF NEW.note = '注册赠送 1000 积分' THEN
                    RAISE EXCEPTION '模拟流水失败';
                  END IF;
                  RETURN NEW;
                END;
                $$ LANGUAGE plpgsql
                """);
        database.dsl().execute("""
                CREATE TRIGGER java_fail_signup_ledger
                BEFORE INSERT ON "CreditLedger"
                FOR EACH ROW EXECUTE FUNCTION java_fail_signup_ledger()
                """);
        try {
            assertThatThrownBy(() -> repository.register("rollback_user", "$2b$12$hash"))
                    .isInstanceOf(RuntimeException.class)
                    .isNotInstanceOf(DuplicateUsernameException.class);
            assertThat(database.dsl().fetchExists(
                            DSL.selectOne().from(USER).where(USER.USERNAME.eq("rollback_user"))))
                    .isFalse();
        } finally {
            database.dsl().execute("DROP TRIGGER java_fail_signup_ledger ON \"CreditLedger\"");
            database.dsl().execute("DROP FUNCTION java_fail_signup_ledger()");
        }
    }

    private static String databaseUrl() {
        return "postgresql://"
                + POSTGRES.getUsername()
                + ":"
                + POSTGRES.getPassword()
                + "@127.0.0.1:"
                + POSTGRES.getMappedPort(5432)
                + "/"
                + POSTGRES.getDatabaseName();
    }
}
