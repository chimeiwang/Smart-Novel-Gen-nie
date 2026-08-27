package cn.inkforge.core.identity.infrastructure;

import static cn.inkforge.core.db.generated.Tables.CREDITLEDGER;
import static cn.inkforge.core.db.generated.Tables.USER;
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import cn.inkforge.core.identity.application.PhoneAccountResult;
import cn.inkforge.core.identity.domain.PasswordCodec;
import cn.inkforge.core.platform.db.CoreDatabase;
import cn.inkforge.core.platform.db.PostgresConnectionSettings;
import cn.inkforge.core.platform.id.CuidV1Generator;
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import org.jooq.impl.DSL;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.testcontainers.containers.Container.ExecResult;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.postgresql.PostgreSQLContainer;
import org.testcontainers.utility.MountableFile;

@Testcontainers
class JooqPhoneAuthRepositoryTest {

    @Container
    private static final PostgreSQLContainer POSTGRES =
            new PostgreSQLContainer("pgvector/pgvector:0.8.0-pg14")
                    .withDatabaseName("novelwriterdev")
                    .withUsername("inkforge")
                    .withPassword("test-only-password");

    private static CoreDatabase database;
    private static JooqPhoneAuthRepository repository;

    @BeforeAll
    static void 重建冻结结构并幂等应用具名迁移() throws Exception {
        POSTGRES.copyFileToContainer(
                MountableFile.forClasspathResource("db/novelwriterdev-schema.sql"),
                "/tmp/novelwriterdev-schema.sql");
        POSTGRES.copyFileToContainer(
                MountableFile.forClasspathResource("migrations/20260827_user_phone_identity.sql"),
                "/tmp/20260827_user_phone_identity.sql");
        executeSql("/tmp/novelwriterdev-schema.sql");
        executeSql("/tmp/20260827_user_phone_identity.sql");
        executeSql("/tmp/20260827_user_phone_identity.sql");

        database = CoreDatabase.connect(PostgresConnectionSettings.parse(databaseUrl()));
        Clock clock = Clock.fixed(
                Instant.parse("2026-08-27T03:45:12.345Z"), ZoneOffset.UTC);
        repository = new JooqPhoneAuthRepository(
                database,
                new CuidV1Generator(clock),
                clock,
                new TestPasswordCodec(),
                () -> "server-only-random-secret-with-at-least-32-bytes");
    }

    @BeforeEach
    void 清理账号数据() {
        database.dsl().deleteFrom(USER).execute();
    }

    @AfterAll
    static void closeDatabase() {
        if (database != null) {
            database.close();
        }
    }

    @Test
    void 首次核验必须原子创建手机号身份账号和唯一奖励() {
        PhoneAccountResult result = repository.loginOrCreate(
                "+8613800138000", "2026-08-27", "challenge-0001");

        assertThat(result.newUser()).isTrue();
        assertThat(result.user().username())
                .startsWith("mobile_c")
                .doesNotContain("13800138000");
        assertThat(result.user().passwordHash()).startsWith("test-hash:");
        assertThat(repository.findById(result.user().id())).isEqualTo(result.user());
        assertThat(database.dsl().fetchCount(USER)).isEqualTo(1);
        assertThat(database.dsl().fetchCount(CREDITLEDGER)).isEqualTo(1);
        assertThat(database.dsl().fetchCount(DSL.table(DSL.name("UserPhoneIdentity"))))
                .isEqualTo(1);
        var identity = database.dsl().fetchSingle(
                DSL.table(DSL.name("UserPhoneIdentity")));
        assertThat(identity.get("phoneE164", String.class)).isEqualTo("+8613800138000");
        assertThat(identity.get("consentVersion", String.class)).isEqualTo("2026-08-27");
    }

    @Test
    void 同一手机号重复登录不得新建账号或重复发奖() {
        PhoneAccountResult first = repository.loginOrCreate(
                "+8613900139000", "2026-08-27", "challenge-first");
        PhoneAccountResult second = repository.loginOrCreate(
                "+8613900139000", "2026-08-27", "challenge-second");

        assertThat(first.newUser()).isTrue();
        assertThat(second.newUser()).isFalse();
        assertThat(second.user().id()).isEqualTo(first.user().id());
        assertThat(database.dsl().fetchCount(USER)).isEqualTo(1);
        assertThat(database.dsl().fetchCount(CREDITLEDGER)).isEqualTo(1);
    }

    @Test
    void 并发核验同一手机号只能产生一个账号和一笔奖励() throws Exception {
        int concurrency = 8;
        CountDownLatch ready = new CountDownLatch(concurrency);
        CountDownLatch start = new CountDownLatch(1);
        try (var executor = Executors.newFixedThreadPool(concurrency)) {
            List<Future<PhoneAccountResult>> futures = new ArrayList<>();
            for (int index = 0; index < concurrency; index++) {
                int request = index;
                futures.add(executor.submit(() -> {
                    ready.countDown();
                    start.await();
                    return repository.loginOrCreate(
                            "+8613700137000",
                            "2026-08-27",
                            "challenge-concurrent-" + request);
                }));
            }
            ready.await();
            start.countDown();
            List<PhoneAccountResult> results = new ArrayList<>();
            for (Future<PhoneAccountResult> future : futures) {
                results.add(future.get());
            }

            assertThat(results.stream().map(result -> result.user().id()).distinct())
                    .hasSize(1);
            assertThat(results.stream().filter(PhoneAccountResult::newUser)).hasSize(1);
            assertThat(database.dsl().fetchCount(USER)).isEqualTo(1);
            assertThat(database.dsl().fetchCount(CREDITLEDGER)).isEqualTo(1);
            assertThat(database.dsl().fetchCount(
                            DSL.table(DSL.name("UserPhoneIdentity"))))
                    .isEqualTo(1);
        }
    }

    @Test
    void 奖励写入失败必须回滚账号和手机号身份() {
        database.dsl().execute("""
                CREATE OR REPLACE FUNCTION java_fail_phone_signup_ledger() RETURNS trigger AS $$
                BEGIN
                  IF NEW.note = '注册赠送 1000 积分' THEN
                    RAISE EXCEPTION '模拟手机号注册奖励失败';
                  END IF;
                  RETURN NEW;
                END;
                $$ LANGUAGE plpgsql
                """);
        database.dsl().execute("""
                CREATE TRIGGER java_fail_phone_signup_ledger
                BEFORE INSERT ON "CreditLedger"
                FOR EACH ROW EXECUTE FUNCTION java_fail_phone_signup_ledger()
                """);
        try {
            assertThatThrownBy(() -> repository.loginOrCreate(
                            "+8613600136000", "2026-08-27", "challenge-rollback"))
                    .isInstanceOf(RuntimeException.class);
            assertThat(database.dsl().fetchCount(USER)).isZero();
            assertThat(database.dsl().fetchCount(
                            DSL.table(DSL.name("UserPhoneIdentity"))))
                    .isZero();
        } finally {
            database.dsl().execute(
                    "DROP TRIGGER java_fail_phone_signup_ledger ON \"CreditLedger\"");
            database.dsl().execute("DROP FUNCTION java_fail_phone_signup_ledger()");
        }
    }

    @Test
    void 正式库迁移必须要求精确确认且确认后保持幂等() throws Exception {
        ExecResult createDatabase = POSTGRES.execInContainer(
                "createdb", "-U", POSTGRES.getUsername(), "novelwriter");
        assertThat(createDatabase.getExitCode()).as(createDatabase.getStderr()).isZero();

        ExecResult restoreBaseline = POSTGRES.execInContainer(
                "psql",
                "-v",
                "ON_ERROR_STOP=1",
                "-U",
                POSTGRES.getUsername(),
                "-d",
                "novelwriter",
                "-f",
                "/tmp/novelwriterdev-schema.sql");
        assertThat(restoreBaseline.getExitCode()).as(restoreBaseline.getStderr()).isZero();

        ExecResult unconfirmed = POSTGRES.execInContainer(
                "psql",
                "-v",
                "ON_ERROR_STOP=1",
                "-U",
                POSTGRES.getUsername(),
                "-d",
                "novelwriter",
                "-f",
                "/tmp/20260827_user_phone_identity.sql");
        assertThat(unconfirmed.getExitCode()).isNotZero();
        assertThat(unconfirmed.getStderr()).contains("正式库手机号身份迁移缺少精确确认令牌");

        for (int attempt = 0; attempt < 2; attempt++) {
            ExecResult confirmed = POSTGRES.execInContainer(
                    "env",
                    "PGOPTIONS=-c inkforge.user_phone_identity_production=novelwriter:20260827:apply",
                    "psql",
                    "-v",
                    "ON_ERROR_STOP=1",
                    "-U",
                    POSTGRES.getUsername(),
                    "-d",
                    "novelwriter",
                    "-f",
                    "/tmp/20260827_user_phone_identity.sql");
            assertThat(confirmed.getExitCode()).as(confirmed.getStderr()).isZero();
        }

        ExecResult constraints = POSTGRES.execInContainer(
                "psql",
                "-At",
                "-U",
                POSTGRES.getUsername(),
                "-d",
                "novelwriter",
                "-c",
                "SELECT count(*) FROM pg_constraint "
                        + "WHERE conrelid = 'public.\"UserPhoneIdentity\"'::regclass");
        assertThat(constraints.getExitCode()).as(constraints.getStderr()).isZero();
        assertThat(constraints.getStdout().strip()).isEqualTo("7");
    }

    private static void executeSql(String path) throws Exception {
        ExecResult result = POSTGRES.execInContainer(
                "psql",
                "-v",
                "ON_ERROR_STOP=1",
                "-U",
                POSTGRES.getUsername(),
                "-d",
                POSTGRES.getDatabaseName(),
                "-f",
                path);
        assertThat(result.getExitCode()).as(result.getStderr()).isZero();
    }

    private static String databaseUrl() {
        return "postgresql://"
                + POSTGRES.getUsername()
                + ":"
                + POSTGRES.getPassword()
                + "@"
                + POSTGRES.getHost()
                + ":"
                + POSTGRES.getMappedPort(5432)
                + "/"
                + POSTGRES.getDatabaseName();
    }

    private static final class TestPasswordCodec implements PasswordCodec {

        @Override
        public String hash(String password) {
            return "test-hash:" + password;
        }

        @Override
        public boolean matches(String password, String passwordHash) {
            return passwordHash.equals(hash(password));
        }
    }
}
