package cn.inkforge.core.video.infrastructure;

import static cn.inkforge.core.db.generated.Tables.NOVEL;
import static cn.inkforge.core.db.generated.Tables.USER;
import static cn.inkforge.core.db.generated.Tables.VIDEOASSET;
import static cn.inkforge.core.db.generated.Tables.VIDEOPROJECT;
import static cn.inkforge.core.db.generated.Tables.WRITINGBIBLE;
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import cn.inkforge.core.db.generated.enums.Storylengthprofile;
import cn.inkforge.core.platform.db.CoreDatabase;
import cn.inkforge.core.platform.db.PostgresConnectionSettings;
import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.platform.id.CuidV1Generator;
import cn.inkforge.core.video.application.StoredVideoAsset;
import cn.inkforge.core.video.application.VideoAssetCreation;
import cn.inkforge.core.video.application.VideoProjectCreation;
import java.nio.file.Path;
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
class JooqVideoProjectRepositoryTest {

    private static final LocalDateTime INITIAL =
            LocalDateTime.parse("2026-08-24T10:00:00.000");
    private static final Clock CLOCK = Clock.fixed(
            Instant.parse("2026-08-25T05:00:00.123Z"), ZoneOffset.UTC);

    @Container
    private static final PostgreSQLContainer POSTGRES =
            new PostgreSQLContainer("pgvector/pgvector:0.8.0-pg14")
                    .withDatabaseName("inkforge_video_project_test")
                    .withUsername("inkforge")
                    .withPassword("test-only-password");

    private static CoreDatabase database;
    private static JooqVideoProjectRepository repository;
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
        repository = new JooqVideoProjectRepository(
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
    void 创建和读取必须校验小说归属长篇事实及项目软删除() {
        String owner = user("video-owner-1");
        String stranger = user("video-stranger-1");
        String novel = novel("video-novel-1", owner, Storylengthprofile.long_serial);

        var project = repository.createProject(
                owner,
                novel,
                new VideoProjectCreation("第一集", "series", "9:16", "zh-CN"));

        assertThat(project.provider()).isEqualTo("seedance_2_5");
        assertThat(project.status()).isEqualTo("draft");
        assertThat(project.revision()).isOne();
        assertThat(repository.listProjects(owner, novel))
                .extracting(value -> value.id())
                .containsExactly(project.id());
        assertThat(repository.listProjects(stranger, novel)).isEmpty();
        assertCode(
                () -> repository.getProject(stranger, project.id()),
                "VIDEO_PROJECT_NOT_FOUND");

        database.dsl().update(VIDEOPROJECT)
                .set(VIDEOPROJECT.DELETEDAT, INITIAL)
                .where(VIDEOPROJECT.ID.eq(project.id()))
                .execute();
        assertThat(repository.listProjects(owner, novel)).isEmpty();
        assertCode(
                () -> repository.getProject(owner, project.id()),
                "VIDEO_PROJECT_NOT_FOUND");
    }

    @Test
    void 非长篇和非归属小说必须以稳定业务错误拒绝项目创建() {
        String owner = user("video-owner-2");
        String stranger = user("video-stranger-2");
        String shortNovel = novel(
                "video-short-2", owner, Storylengthprofile.short_medium);

        assertCode(
                () -> repository.createProject(
                        owner,
                        shortNovel,
                        new VideoProjectCreation("短篇", "highlight", "16:9", "zh-CN")),
                "VIDEO_LONG_SERIAL_REQUIRED");
        assertCode(
                () -> repository.createProject(
                        stranger,
                        shortNovel,
                        new VideoProjectCreation("越权", "highlight", "16:9", "zh-CN")),
                "NOVEL_NOT_FOUND");
    }

    @Test
    void series项目必须可登记素材并按权利状态原子锁定和解锁() {
        String owner = user("video-owner-3");
        String stranger = user("video-stranger-3");
        String novel = novel("video-novel-3", owner, Storylengthprofile.long_serial);
        var project = repository.createProject(
                owner,
                novel,
                new VideoProjectCreation("连续剧", "series", "16:9", "zh-CN"));

        repository.requireWritableProject(owner, project.id());
        assertCode(
                () -> repository.requireWritableProject(stranger, project.id()),
                "VIDEO_PROJECT_NOT_FOUND");

        StoredVideoAsset stored = new StoredVideoAsset(
                project.id() + "/asset-1.png",
                Path.of("/tmp/unused.png"),
                "image/png",
                123,
                "a".repeat(64));
        var asset = repository.createAsset(
                owner,
                project.id(),
                new VideoAssetCreation(
                        "asset-1",
                        "人物定妆",
                        "image",
                        "identity",
                        "user_upload",
                        null,
                        stored));

        assertThat(asset.rightsStatus()).isEqualTo("unconfirmed");
        assertThat(asset.lockedAt()).isNull();
        assertThat(repository.getProject(owner, project.id()).assets())
                .extracting(value -> value.id())
                .containsExactly("asset-1");
        assertThat(repository.getAssetFile(owner, "asset-1").storageKey())
                .isEqualTo(stored.storageKey());
        assertCode(
                () -> repository.getAssetFile(stranger, "asset-1"),
                "VIDEO_ASSET_NOT_FOUND");

        var confirmed = repository.confirmAsset(owner, "asset-1", "confirmed");
        assertThat(confirmed.rightsStatus()).isEqualTo("confirmed");
        assertThat(confirmed.lockedAt()).isNotNull();
        var restricted = repository.confirmAsset(owner, "asset-1", "restricted");
        assertThat(restricted.rightsStatus()).isEqualTo("restricted");
        assertThat(restricted.lockedAt()).isNull();
        assertThat(database.dsl().fetchCount(VIDEOASSET)).isOne();
    }

    @Test
    void 文件落盘后的二次事务必须重新校验长篇事实防止竞态写入() {
        String owner = user("video-owner-4");
        String novel = novel("video-novel-4", owner, Storylengthprofile.long_serial);
        var project = repository.createProject(
                owner,
                novel,
                new VideoProjectCreation("竞态", "series", "16:9", "zh-CN"));
        repository.requireWritableProject(owner, project.id());
        database.dsl().update(WRITINGBIBLE)
                .set(WRITINGBIBLE.STORYLENGTHPROFILE, Storylengthprofile.short_medium)
                .where(WRITINGBIBLE.NOVELID.eq(novel))
                .execute();

        assertCode(
                () -> repository.createAsset(
                        owner,
                        project.id(),
                        new VideoAssetCreation(
                                "asset-race",
                                "竞态素材",
                                "image",
                                "identity",
                                "user_upload",
                                null,
                                new StoredVideoAsset(
                                        project.id() + "/asset-race.png",
                                        Path.of("/tmp/unused-race.png"),
                                        "image/png",
                                        1,
                                        "b".repeat(64)))),
                "VIDEO_LONG_SERIAL_REQUIRED");
        assertThat(database.dsl().fetchCount(VIDEOASSET)).isZero();
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

    private static String novel(
            String id, String owner, Storylengthprofile profile) {
        database.dsl().insertInto(NOVEL)
                .set(NOVEL.ID, id)
                .set(NOVEL.NAME, id)
                .set(NOVEL.USERID, owner)
                .set(NOVEL.CREATEDAT, INITIAL)
                .set(NOVEL.UPDATEDAT, INITIAL)
                .execute();
        database.dsl().insertInto(WRITINGBIBLE)
                .set(WRITINGBIBLE.ID, id + "-bible")
                .set(WRITINGBIBLE.NOVELID, id)
                .set(WRITINGBIBLE.STORYLENGTHPROFILE, profile)
                .set(WRITINGBIBLE.CREATEDAT, INITIAL)
                .set(WRITINGBIBLE.UPDATEDAT, INITIAL)
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
