package cn.inkforge.core.styles.infrastructure;

import static cn.inkforge.core.db.generated.Tables.NOVEL;
import static cn.inkforge.core.db.generated.Tables.STYLEPORTRAITTASK;
import static cn.inkforge.core.db.generated.Tables.STYLEREFERENCE;
import static cn.inkforge.core.db.generated.Tables.USER;
import static cn.inkforge.core.db.generated.Tables.WRITINGSTYLE;
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import cn.inkforge.core.platform.db.CoreDatabase;
import cn.inkforge.core.platform.db.PostgresConnectionSettings;
import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.platform.id.CuidV1Generator;
import cn.inkforge.core.styles.application.StoredStyleFile;
import cn.inkforge.core.styles.domain.PortraitDispatchRecord;
import cn.inkforge.core.styles.domain.PortraitDispatchStatus;
import cn.inkforge.core.styles.domain.PortraitSection;
import cn.inkforge.core.styles.domain.PortraitSuccessData;
import java.nio.file.Path;
import java.time.Clock;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
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
class JooqStyleRepositoryTest {

    private static final LocalDateTime INITIAL =
            LocalDateTime.parse("2026-08-24T10:00:00.000");
    private static final Clock CLOCK = Clock.fixed(
            Instant.parse("2026-08-25T05:00:00.123Z"), ZoneOffset.UTC);

    @Container
    private static final PostgreSQLContainer POSTGRES =
            new PostgreSQLContainer("pgvector/pgvector:0.8.0-pg14")
                    .withDatabaseName("inkforge_styles_test")
                    .withUsername("inkforge")
                    .withPassword("test-only-password");

    private static CoreDatabase database;
    private static JooqStyleRepository repository;
    private final List<String> users = new ArrayList<>();

    @BeforeAll
    static void restoreSchema() throws Exception {
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
        repository = new JooqStyleRepository(
                database, new CuidV1Generator(CLOCK), CLOCK);
    }

    @AfterEach
    void cleanup() {
        if (!users.isEmpty()) {
            database.dsl().deleteFrom(NOVEL).where(NOVEL.USERID.in(users)).execute();
            database.dsl().deleteFrom(USER).where(USER.ID.in(users)).execute();
        }
    }

    @AfterAll
    static void closeDatabase() {
        if (database != null) database.close();
    }

    @Test
    void 文风与参考资料必须私有稳定聚合并精确返回待清理路径() {
        String owner = user("style-owner-1");
        String stranger = user("style-stranger-1");
        var style = repository.create(owner, "私有文风");
        assertThat(style.sourceType()).isEqualTo("agent");
        assertThat(style.originalCharCount()).isZero();
        assertThat(repository.list(stranger)).isEmpty();
        assertCode(() -> repository.reserveReference(stranger, style.id()), "STYLE_NOT_FOUND");

        String referenceId = repository.reserveReference(owner, style.id());
        StoredStyleFile file = new StoredStyleFile(
                "作品.txt",
                Path.of("/tmp/unused"),
                "/app/uploads/styles/" + style.id() + "/" + referenceId + "_作品.txt",
                3);
        var reference = repository.createReference(owner, style.id(), referenceId, file);
        assertThat(reference.filepath()).isEqualTo(file.databasePath());
        assertThat(repository.list(owner).getFirst().references())
                .extracting(value -> value.id())
                .containsExactly(referenceId);
        assertCode(
                () -> repository.deleteReference(stranger, style.id(), referenceId),
                "STYLE_NOT_FOUND");
        assertThat(repository.deleteReference(owner, style.id(), referenceId))
                .isEqualTo(file.databasePath());

        String secondId = repository.reserveReference(owner, style.id());
        repository.createReference(
                owner,
                style.id(),
                secondId,
                new StoredStyleFile(
                        "二.txt", Path.of("/tmp/unused-2"),
                        "/app/uploads/styles/" + style.id() + "/" + secondId + "_二.txt", 1));
        assertThat(repository.deleteStyle(owner, style.id()))
                .containsExactly("/app/uploads/styles/" + style.id() + "/" + secondId + "_二.txt");
        assertThat(database.dsl().fetchCount(STYLEREFERENCE)).isZero();
        assertThat(database.dsl().fetchCount(STYLEPORTRAITTASK)).isZero();
    }

    @Test
    void 画像任务必须要求ready资料单活动任务并严格幂等流转() {
        String owner = user("style-owner-2");
        var style = repository.create(owner, "画像文风");
        assertCode(
                () -> repository.createPortraitTask(owner, style.id(), null),
                "STYLE_REFERENCE_REQUIRED");
        addReference(owner, style.id(), "portrait-ref-1", "参考.txt", 8);

        var task = repository.createPortraitTask(owner, style.id(), null);
        assertThat(task.status()).isEqualTo("pending");
        assertCode(
                () -> repository.createPortraitTask(owner, style.id(), null),
                "PORTRAIT_TASK_ACTIVE");
        assertThat(repository.portraitSources(style.id(), task.id()))
                .extracting(value -> value.filename())
                .containsExactly("参考.txt");
        assertCode(
                () -> repository.transitionPortraitTask(
                        style.id(), task.id(), "success", fullSuccess(), null, true),
                "PORTRAIT_TASK_STATE_CONFLICT");

        var processing = repository.transitionPortraitTask(
                style.id(), task.id(), "processing", null, null, false);
        var processingReplay = repository.transitionPortraitTask(
                style.id(), task.id(), "processing", null, null, false);
        assertThat(processingReplay.updatedAt()).isEqualTo(processing.updatedAt());
        var success = repository.transitionPortraitTask(
                style.id(), task.id(), "success", fullSuccess(), null, true);
        var successReplay = repository.transitionPortraitTask(
                style.id(), task.id(), "success", fullSuccess(), null, true);
        assertThat(success.status()).isEqualTo("success");
        assertThat(successReplay.updatedAt()).isEqualTo(success.updatedAt());
        assertThat(repository.list(owner).getFirst().portraitMarkdown())
                .contains("创作方法论\n方法", "风格特质\n特质");
        assertCode(
                () -> repository.transitionPortraitTask(
                        style.id(), task.id(), "error", null, null, false),
                "PORTRAIT_TASK_STATE_CONFLICT");

        var sectionTask = repository.createPortraitTask(
                owner, style.id(), PortraitSection.UNIQUE_MARKERS);
        repository.transitionPortraitTask(
                style.id(), sectionTask.id(), "processing", null, null, false);
        assertCode(
                () -> repository.transitionPortraitTask(
                        style.id(),
                        sectionTask.id(),
                        "success",
                        new PortraitSuccessData(Map.of("uniqueMarkers", "新标记")),
                        PortraitSection.STYLE_TRAITS,
                        true),
                "PORTRAIT_TASK_SECTION_MISMATCH");
    }

    @Test
    void 应用文风必须先CAS再校验目标并支持应用清除和同值幂等() {
        String owner = user("style-owner-3");
        String stranger = user("style-stranger-3");
        var oldStyle = repository.create(owner, "旧文风");
        var newStyle = repository.create(owner, "新文风");
        var foreign = repository.create(stranger, "外来文风");
        completeStyle(oldStyle.id());
        completeStyle(newStyle.id());
        completeStyle(foreign.id());
        String novel = novel("style-novel-3", owner, oldStyle.id());

        assertCode(
                () -> repository.applyStyle(novel, owner, foreign.id(), null),
                "APPLIED_STYLE_VERSION_CONFLICT");
        assertThat(repository.applyStyle(novel, owner, oldStyle.id(), oldStyle.id()).effective())
                .isFalse();
        assertThat(repository.applyStyle(novel, owner, newStyle.id(), oldStyle.id()).effective())
                .isTrue();
        assertCode(
                () -> repository.applyStyle(novel, owner, foreign.id(), newStyle.id()),
                "STYLE_NOT_FOUND");
        assertThat(repository.applyStyle(novel, owner, null, newStyle.id()).effective())
                .isTrue();
        assertThat(repository.applyStyle(novel, owner, null, null).effective()).isFalse();
        assertCode(
                () -> repository.applyStyle("missing", owner, null, null),
                "NOVEL_NOT_FOUND");
    }

    @Test
    void 后台领取必须包含pending和陈旧processing且终态只覆盖活动任务() {
        String owner = user("style-owner-4");
        var style = repository.create(owner, "后台文风");
        addReference(owner, style.id(), "dispatch-ref", "参考.txt", 2);
        var task = repository.createPortraitTask(
                owner, style.id(), PortraitSection.STYLE_TRAITS);
        OffsetDateTime staleBefore = OffsetDateTime.parse("2026-08-25T05:10:00Z");

        assertThat(repository.listReconcilable(20, staleBefore))
                .extracting(PortraitDispatchRecord::taskId)
                .containsExactly(task.id());
        repository.markDispatchTerminal(style.id(), task.id(), PortraitDispatchStatus.QUEUED);
        assertThat(repository.getPortraitTask(owner, task.id()).status()).isEqualTo("pending");
        repository.markDispatchTerminal(style.id(), task.id(), PortraitDispatchStatus.FAILED);
        assertThat(repository.getPortraitTask(owner, task.id()).status()).isEqualTo("error");
        assertThat(repository.getPortraitTask(owner, task.id()).errorMessage())
                .isEqualTo("智能体画像任务已终止：failed");
    }

    private static PortraitSuccessData fullSuccess() {
        LinkedHashMap<String, Object> fields = new LinkedHashMap<>();
        fields.put("creativeMethodology", "方法");
        fields.put("uniqueMarkers", "标记");
        fields.put("generationStyle", "生成");
        fields.put("expressionFeatures", "表达");
        fields.put("styleTraits", "特质");
        fields.put(
                "portraitMarkdown",
                "创作方法论\n方法\n\n独特标记\n标记\n\n生成风格\n生成\n\n"
                        + "表达特征\n表达\n\n风格特质\n特质");
        fields.put("originalCharCount", 10);
        fields.put("usedCharCount", 10);
        fields.put("truncated", false);
        fields.put("errorMessage", null);
        return new PortraitSuccessData(fields);
    }

    private static void completeStyle(String styleId) {
        database.dsl().update(WRITINGSTYLE)
                .set(WRITINGSTYLE.PORTRAITMARKDOWN, "完整画像")
                .where(WRITINGSTYLE.ID.eq(styleId))
                .execute();
    }

    private static void addReference(
            String owner, String styleId, String id, String filename, int charCount) {
        repository.createReference(
                owner,
                styleId,
                id,
                new StoredStyleFile(
                        filename,
                        Path.of("/tmp/unused-" + id),
                        "/app/uploads/styles/" + styleId + "/" + id + "_" + filename,
                        charCount));
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

    private static String novel(String id, String owner, String styleId) {
        database.dsl().insertInto(NOVEL)
                .set(NOVEL.ID, id)
                .set(NOVEL.NAME, id)
                .set(NOVEL.USERID, owner)
                .set(NOVEL.APPLIEDSTYLEID, styleId)
                .set(NOVEL.CREATEDAT, INITIAL)
                .set(NOVEL.UPDATEDAT, INITIAL)
                .execute();
        return id;
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
