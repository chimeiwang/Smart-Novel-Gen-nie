package cn.inkforge.core.references.infrastructure;

import static cn.inkforge.core.db.generated.Tables.NOVEL;
import static cn.inkforge.core.db.generated.Tables.RAGCHUNK;
import static cn.inkforge.core.db.generated.Tables.RAGDOCUMENT;
import static cn.inkforge.core.db.generated.Tables.REFERENCEMATERIAL;
import static cn.inkforge.core.db.generated.Tables.USER;
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import cn.inkforge.core.db.generated.enums.Ragdocumentstatus;
import cn.inkforge.core.platform.db.CoreDatabase;
import cn.inkforge.core.platform.db.PostgresConnectionSettings;
import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.platform.id.CommandResourceId;
import cn.inkforge.core.platform.id.CuidV1Generator;
import cn.inkforge.core.platform.patch.PatchField;
import cn.inkforge.core.references.domain.RagDispatchRecord;
import cn.inkforge.core.references.domain.RagDispatchStatus;
import cn.inkforge.core.references.domain.RagJobIdentity;
import cn.inkforge.core.references.domain.RagRules;
import cn.inkforge.core.references.domain.ReferenceData;
import cn.inkforge.core.references.domain.ReferencePatch;
import java.math.BigDecimal;
import java.time.Clock;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.List;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import org.testcontainers.containers.Container.ExecResult;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.postgresql.PostgreSQLContainer;
import org.testcontainers.utility.MountableFile;

@Testcontainers
class JooqReferenceRepositoryTest {

    private static final LocalDateTime INITIAL =
            LocalDateTime.parse("2026-08-24T10:00:00.000");
    private static final Clock CLOCK = Clock.fixed(
            Instant.parse("2026-08-25T04:00:00.123Z"), ZoneOffset.UTC);

    @Container
    private static final PostgreSQLContainer POSTGRES =
            new PostgreSQLContainer("pgvector/pgvector:0.8.0-pg14")
                    .withDatabaseName("inkforge_references_test")
                    .withUsername("inkforge")
                    .withPassword("test-only-password");

    private static CoreDatabase database;
    private static JooqReferenceRepository repository;
    private final List<String> users = new ArrayList<>();

    @BeforeAll
    static void 重建冻结结构() throws Exception {
        POSTGRES.copyFileToContainer(
                MountableFile.forClasspathResource("db/novelwriterdev-schema.sql"),
                "/tmp/novelwriterdev-schema.sql");
        ExecResult result = POSTGRES.execInContainer(
                "psql", "-v", "ON_ERROR_STOP=1",
                "-U", POSTGRES.getUsername(),
                "-d", POSTGRES.getDatabaseName(),
                "-f", "/tmp/novelwriterdev-schema.sql");
        assertThat(result.getExitCode()).as(result.getStderr()).isZero();
        database = CoreDatabase.connect(PostgresConnectionSettings.parse(databaseUrl()));
        repository = new JooqReferenceRepository(
                database, new CuidV1Generator(CLOCK), CLOCK);
    }

    @AfterEach
    void cleanup() {
        if (!users.isEmpty()) {
            // User -> Novel 是 ON DELETE SET NULL，必须先删小说才能让资料与索引级联清理。
            database.dsl().deleteFrom(NOVEL).where(NOVEL.USERID.in(users)).execute();
            database.dsl().deleteFrom(USER).where(USER.ID.in(users)).execute();
        }
    }

    @AfterAll
    static void closeDatabase() {
        if (database != null) database.close();
    }

    @Test
    void 创建必须确定性逐字保存历史敏感重放且列表稳定隔离归属() {
        String owner = user("reference-owner-1");
        String stranger = user("reference-stranger-1");
        String novel = novel("reference-novel-1", owner);
        ReferenceData data = new ReferenceData(
                "  原标题  ", "note", "  第一行\r\n😀最后一行  ", null);

        var created = repository.create(
                novel, owner, "reference-request-0001", data, true);
        var replayed = repository.create(
                novel, owner, "reference-request-0001", data, true);

        assertThat(created.reference().id()).isEqualTo(CommandResourceId.derive(
                "reference", owner, novel, "reference-request-0001"));
        assertThat(created.effective()).isTrue();
        assertThat(replayed.effective()).isFalse();
        assertThat(created.reference().title()).isEqualTo("  原标题  ");
        assertThat(created.reference().content()).isEqualTo("  第一行\r\n😀最后一行  ");
        assertThat(created.reference().contentHash()).isEqualTo(RagRules.sha256(data.content()));
        assertThat(created.reference().errorMessage()).isEqualTo("等待重新索引");
        assertThat(repository.list(novel, owner)).extracting(value -> value.id())
                .containsExactly(created.reference().id());
        assertCode(() -> repository.list(novel, stranger), "NOVEL_FORBIDDEN");
        assertCode(
                () -> repository.create(
                        novel,
                        owner,
                        "reference-request-0001",
                        new ReferenceData("冲突", "note", data.content(), null),
                        true),
                "RESOURCE_CREATE_CONFLICT");

        var titleChanged = repository.update(
                novel,
                owner,
                created.reference().id(),
                patch(new PatchField<>(true, "新标题"), absent(), absent(), absent()),
                created.reference().updatedAt(),
                true);
        assertThat(titleChanged.indexRefreshRequired()).isFalse();
        assertThat(titleChanged.indexGeneration()).isEqualTo(created.indexGeneration());
        assertThat(titleChanged.reference().contentHash()).isEqualTo(created.reference().contentHash());
        assertCode(
                () -> repository.create(
                        novel, owner, "reference-request-0001", data, true),
                "RESOURCE_CREATE_CONFLICT");
    }

    @Test
    void 正文更新必须先CAS再清空旧块推进代次且删除返回精确影响() {
        String owner = user("reference-owner-2");
        String novel = novel("reference-novel-2", owner);
        var created = repository.create(
                novel,
                owner,
                "reference-request-0002",
                new ReferenceData("标题", "book", "旧正文", null),
                true);
        RagJobIdentity identity = RagJobIdentity.create(
                created.reference().id(),
                created.reference().contentHash(),
                created.indexGeneration());
        repository.replaceIndex(
                novel,
                created.reference().id(),
                identity.taskId(),
                identity.runId(),
                created.reference().contentHash(),
                List.of(List.of(BigDecimal.ONE, BigDecimal.ZERO)));
        assertThat(database.dsl().fetchCount(RAGCHUNK)).isEqualTo(1);

        var changed = repository.update(
                novel,
                owner,
                created.reference().id(),
                patch(absent(), absent(), new PatchField<>(true, "  新正文\r\n😀  "), absent()),
                created.reference().updatedAt(),
                true);
        assertThat(changed.indexRefreshRequired()).isTrue();
        assertThat(changed.indexGeneration()).isAfter(created.indexGeneration());
        assertThat(changed.reference().content()).isEqualTo("  新正文\r\n😀  ");
        assertThat(changed.reference().contentHash())
                .isEqualTo(RagRules.sha256("  新正文\r\n😀  "));
        assertThat(database.dsl().fetchCount(RAGCHUNK)).isZero();
        assertCode(
                () -> repository.update(
                        novel,
                        owner,
                        created.reference().id(),
                        patch(absent(), absent(), new PatchField<>(true, "陈旧写入"), absent()),
                        created.reference().updatedAt(),
                        true),
                "REFERENCE_VERSION_CONFLICT");

        RagJobIdentity changedIdentity = RagJobIdentity.create(
                changed.reference().id(),
                changed.reference().contentHash(),
                changed.indexGeneration());
        repository.replaceIndex(
                novel,
                changed.reference().id(),
                changedIdentity.taskId(),
                changedIdentity.runId(),
                changed.reference().contentHash(),
                List.of(List.of(BigDecimal.ONE)));
        var deleted = repository.delete(
                novel,
                owner,
                changed.reference().id(),
                changed.reference().updatedAt());
        assertThat(deleted.ragDocuments()).isEqualTo(1);
        assertThat(deleted.ragChunks()).isEqualTo(1);
        assertThat(database.dsl().fetchCount(REFERENCEMATERIAL)).isZero();
        assertThat(database.dsl().fetchCount(RAGDOCUMENT)).isZero();
        assertThat(database.dsl().fetchCount(RAGCHUNK)).isZero();
    }

    @Test
    void 索引上下文成功失败回调必须绑定当前任务身份并保持终态幂等() {
        String owner = user("reference-owner-3");
        String novel = novel("reference-novel-3", owner);
        var created = repository.create(
                novel,
                owner,
                "reference-request-0003",
                new ReferenceData("标题", "web", "上下文正文", "https://example.test/source"),
                true);
        var pending = repository.prepareReindex(
                novel, owner, created.reference().id(), created.reference().contentHash());
        assertThat(pending.indexGeneration()).isEqualTo(created.indexGeneration());
        RagJobIdentity identity = RagJobIdentity.create(
                created.reference().id(), pending.contentHash(), pending.indexGeneration());

        var context = repository.requireIndexContext(
                novel,
                owner,
                created.reference().id(),
                identity.taskId(),
                identity.runId(),
                pending.contentHash());
        assertThat(context.content()).isEqualTo("上下文正文");
        assertCode(
                () -> repository.requireIndexContext(
                        novel,
                        owner,
                        created.reference().id(),
                        identity.taskId(),
                        "wrong-run",
                        pending.contentHash()),
                "RAG_INDEX_STALE");

        var ready = repository.replaceIndex(
                novel,
                created.reference().id(),
                identity.taskId(),
                identity.runId(),
                pending.contentHash(),
                List.of(List.of(BigDecimal.ONE, BigDecimal.ZERO)));
        var replay = repository.replaceIndex(
                novel,
                created.reference().id(),
                identity.taskId(),
                identity.runId(),
                pending.contentHash(),
                List.of(List.of(BigDecimal.ZERO, BigDecimal.ONE)));
        assertThat(ready.ragStatus()).isEqualTo("ready");
        assertThat(replay.ragStatus()).isEqualTo("ready");
        assertThat(database.dsl().fetchCount(RAGCHUNK)).isEqualTo(1);
        assertCode(
                () -> repository.markIndexFailed(
                        novel,
                        created.reference().id(),
                        identity.taskId(),
                        identity.runId(),
                        pending.contentHash(),
                        "内部详情不得外泄"),
                "RAG_INDEX_TERMINAL_CONFLICT");
    }

    @Test
    void 后台领取只返回当前哈希且终止状态只能落在同一代次() {
        String owner = user("reference-owner-4");
        String novel = novel("reference-novel-4", owner);
        var created = repository.create(
                novel,
                owner,
                "reference-request-0004",
                new ReferenceData("标题", "custom", "正文", null),
                true);

        assertThat(repository.listPending(20))
                .extracting(RagDispatchRecord::referenceId)
                .containsExactly(created.reference().id());
        RagDispatchRecord record = repository.listPending(20).getFirst();
        repository.markDispatchTerminal(record, RagDispatchStatus.QUEUED);
        assertThat(database.dsl().select(RAGDOCUMENT.STATUS)
                        .from(RAGDOCUMENT)
                        .where(RAGDOCUMENT.SOURCEID.eq(created.reference().id()))
                        .fetchSingle(RAGDOCUMENT.STATUS))
                .isEqualTo(Ragdocumentstatus.disabled);
        repository.markDispatchTerminal(record, RagDispatchStatus.FAILED);
        assertThat(database.dsl().select(RAGDOCUMENT.STATUS)
                        .from(RAGDOCUMENT)
                        .where(RAGDOCUMENT.SOURCEID.eq(created.reference().id()))
                        .fetchSingle(RAGDOCUMENT.STATUS))
                .isEqualTo(Ragdocumentstatus.failed);
    }

    private String user(String id) {
        users.add(id);
        database.dsl().insertInto(USER)
                .set(USER.ID, id)
                .set(USER.USERNAME, id)
                .set(USER.PASSWORDHASH, "test")
                .set(USER.CREATEDAT, INITIAL)
                .set(USER.UPDATEDAT, INITIAL)
                .execute();
        return id;
    }

    private static String novel(String id, String owner) {
        database.dsl().insertInto(NOVEL)
                .set(NOVEL.ID, id)
                .set(NOVEL.NAME, id)
                .set(NOVEL.USERID, owner)
                .set(NOVEL.CREATEDAT, INITIAL)
                .set(NOVEL.UPDATEDAT, INITIAL)
                .execute();
        return id;
    }

    private static ReferencePatch patch(
            PatchField<String> title,
            PatchField<String> type,
            PatchField<String> content,
            PatchField<String> sourceUrl) {
        return new ReferencePatch(title, type, content, sourceUrl);
    }

    private static PatchField<String> absent() {
        return new PatchField<>(false, null);
    }

    private static void assertCode(Runnable action, String code) {
        assertThatThrownBy(action::run)
                .isInstanceOfSatisfying(ApiException.class, error ->
                        assertThat(error.code()).isEqualTo(code));
    }

    private static String databaseUrl() {
        return "postgresql://"
                + POSTGRES.getUsername()
                + ":"
                + POSTGRES.getPassword()
                + "@"
                + POSTGRES.getHost()
                + ":"
                + POSTGRES.getFirstMappedPort()
                + "/"
                + POSTGRES.getDatabaseName();
    }
}
