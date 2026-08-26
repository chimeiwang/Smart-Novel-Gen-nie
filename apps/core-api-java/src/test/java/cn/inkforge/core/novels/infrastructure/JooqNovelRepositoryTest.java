package cn.inkforge.core.novels.infrastructure;

import static cn.inkforge.core.db.generated.Tables.CHAPTER;
import static cn.inkforge.core.db.generated.Tables.NOVEL;
import static cn.inkforge.core.db.generated.Tables.OUTLINE;
import static cn.inkforge.core.db.generated.Tables.PLOTPROGRESS;
import static cn.inkforge.core.db.generated.Tables.REVIEWARTIFACT;
import static cn.inkforge.core.db.generated.Tables.REVIEWARTIFACTREVISION;
import static cn.inkforge.core.db.generated.Tables.USER;
import static cn.inkforge.core.db.generated.Tables.WRITINGBIBLE;
import static cn.inkforge.core.db.generated.Tables.WRITINGSTYLE;
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import cn.inkforge.contracts.api.StoryLengthProfile;
import cn.inkforge.core.db.generated.enums.Chapterstatus;
import cn.inkforge.core.db.generated.enums.Reviewartifactkind;
import cn.inkforge.core.db.generated.enums.Reviewartifactstatus;
import cn.inkforge.core.db.generated.enums.Storylengthprofile;
import cn.inkforge.core.db.generated.enums.Stylesourcetype;
import cn.inkforge.core.novels.domain.NovelCreation;
import cn.inkforge.core.platform.db.CoreDatabase;
import cn.inkforge.core.platform.db.PostgresConnectionSettings;
import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.platform.id.CuidV1Generator;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.Clock;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.HexFormat;
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
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;

@Testcontainers
class JooqNovelRepositoryTest {

    private static final LocalDateTime INITIAL =
            LocalDateTime.parse("2026-08-24T10:00:00.000");
    private static final Clock CLOCK = Clock.fixed(
            Instant.parse("2026-08-25T03:00:00.123Z"), ZoneOffset.UTC);
    private static final ObjectMapper JSON = new ObjectMapper();

    @Container
    private static final PostgreSQLContainer POSTGRES =
            new PostgreSQLContainer("pgvector/pgvector:0.8.0-pg14")
                    .withDatabaseName("inkforge_novels_test")
                    .withUsername("inkforge")
                    .withPassword("test-only-password");

    private static CoreDatabase database;
    private static JooqNovelRepository repository;
    private final List<String> users = new ArrayList<>();

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
        repository = new JooqNovelRepository(
                database, new CuidV1Generator(CLOCK), CLOCK, JSON);
    }

    @AfterEach
    void cleanup() {
        if (!users.isEmpty()) {
            database.dsl().deleteFrom(USER).where(USER.ID.in(users)).execute();
        }
    }

    @AfterAll
    static void closeDatabase() {
        if (database != null) database.close();
    }

    @Test
    void 中短篇创建必须原子保存七类事实完整来源并按请求标识重放() throws Exception {
        String owner = user("novel-short-owner");
        String requestId = "novel-short-request-0001";
        String source = "  第一行\r\n😀完整起始素材\n最后一行  ";

        var created = repository.create(shortCreation(owner, requestId, "opening", source));
        var replayed = repository.create(shortCreation(owner, requestId, "opening", source));

        assertThat(replayed.getNovelId()).isEqualTo(created.getNovelId());
        assertThat(replayed.getChapterId()).isEqualTo(created.getChapterId());
        String novelId = created.getNovelId();
        var novel = database.dsl().selectFrom(NOVEL)
                .where(NOVEL.ID.eq(novelId))
                .fetchSingle();
        var chapter = database.dsl().selectFrom(CHAPTER)
                .where(CHAPTER.ID.eq(created.getChapterId()))
                .fetchSingle();
        var outline = database.dsl().selectFrom(OUTLINE)
                .where(OUTLINE.NOVELID.eq(novelId))
                .fetchSingle();
        var progress = database.dsl().selectFrom(PLOTPROGRESS)
                .where(PLOTPROGRESS.NOVELID.eq(novelId))
                .fetchSingle();
        var bible = database.dsl().selectFrom(WRITINGBIBLE)
                .where(WRITINGBIBLE.NOVELID.eq(novelId))
                .fetchSingle();
        var artifact = database.dsl().selectFrom(REVIEWARTIFACT)
                .where(REVIEWARTIFACT.NOVELID.eq(novelId))
                .fetchSingle();
        var revision = database.dsl().selectFrom(REVIEWARTIFACTREVISION)
                .where(REVIEWARTIFACTREVISION.ARTIFACTID.eq(artifact.getId()))
                .fetchSingle();

        assertThat(novel.getName()).isEqualTo("短篇");
        assertThat(chapter.getTitle()).isEqualTo("全文");
        assertThat(chapter.getContent()).isEqualTo(source);
        assertThat(chapter.getStatus()).isEqualTo(Chapterstatus.drafting);
        assertThat(outline.getContent()).isEmpty();
        assertThat(progress.getCurrentstage()).isEqualTo("开篇");
        assertThat(bible.getStorylengthprofile()).isEqualTo(Storylengthprofile.short_medium);
        assertThat(bible.getTargettotalwordcount()).isEqualTo(12_000);
        assertThat(artifact.getKind()).isEqualTo(Reviewartifactkind.freeform_markdown);
        assertThat(artifact.getStatus()).isEqualTo(Reviewartifactstatus.applied);
        assertThat(artifact.getArtifactkey()).isEqualTo("short-medium:source:" + novelId);
        assertThat(artifact.getSummary()).isEqualTo("创建请求摘要：" + sha256(requestId));
        assertThat(artifact.getRevision()).isEqualTo(1);
        assertThat(artifact.getAppliedat()).isEqualTo(LocalDateTime.parse("2026-08-25T03:00:00.123"));
        assertThat(revision.getRevision()).isEqualTo(1);
        assertThat(revision.getSummary()).isEqualTo(artifact.getSummary());
        assertThat(revision.getPayloadjson()).isEqualTo(artifact.getPayloadjson());

        JsonNode payload = JSON.readTree(artifact.getPayloadjson());
        assertThat(payload.get("kind").asText()).isEqualTo("freeform_markdown");
        assertThat(payload.get("profile").asText()).isEqualTo("short_medium");
        assertThat(payload.get("clientRequestId").asText()).isEqualTo(requestId);
        assertThat(payload.get("sourceKind").asText()).isEqualTo("opening");
        assertThat(payload.get("sourceText").asText()).isEqualTo(source);
        assertThat(payload.get("contentHash").asText()).isEqualTo(sha256(source));

        assertThat(database.dsl().fetchCount(
                        NOVEL, NOVEL.USERID.eq(owner)))
                .isEqualTo(1);
        assertThat(database.dsl().fetchCount(
                        CHAPTER, CHAPTER.NOVELID.eq(novelId)))
                .isEqualTo(1);
        assertThat(database.dsl().fetchCount(
                        OUTLINE, OUTLINE.NOVELID.eq(novelId)))
                .isEqualTo(1);
        assertThat(database.dsl().fetchCount(
                        PLOTPROGRESS, PLOTPROGRESS.NOVELID.eq(novelId)))
                .isEqualTo(1);
        assertThat(database.dsl().fetchCount(
                        WRITINGBIBLE, WRITINGBIBLE.NOVELID.eq(novelId)))
                .isEqualTo(1);
        assertThat(database.dsl().fetchCount(
                        REVIEWARTIFACT, REVIEWARTIFACT.NOVELID.eq(novelId)))
                .isEqualTo(1);
        assertThat(database.dsl().fetchCount(
                        REVIEWARTIFACTREVISION,
                        REVIEWARTIFACTREVISION.ARTIFACTID.eq(artifact.getId())))
                .isEqualTo(1);
    }

    @Test
    void 来源放置与长篇默认事实必须保持且创建中途失败完整回滚() {
        String owner = user("novel-profile-owner");
        var outlineSource = repository.create(shortCreation(
                owner,
                "novel-outline-request-0001",
                "outline",
                "  完整大纲\n不可清洗  "));
        assertThat(database.dsl().select(CHAPTER.CONTENT)
                        .from(CHAPTER)
                        .where(CHAPTER.ID.eq(outlineSource.getChapterId()))
                        .fetchSingle(CHAPTER.CONTENT))
                .isEmpty();
        assertThat(database.dsl().select(OUTLINE.CONTENT)
                        .from(OUTLINE)
                        .where(OUTLINE.NOVELID.eq(outlineSource.getNovelId()))
                        .fetchSingle(OUTLINE.CONTENT))
                .isEqualTo("  完整大纲\n不可清洗  ");

        var longNovel = repository.create(longCreation(owner));
        assertThat(database.dsl().select(CHAPTER.TITLE)
                        .from(CHAPTER)
                        .where(CHAPTER.ID.eq(longNovel.getChapterId()))
                        .fetchSingle(CHAPTER.TITLE))
                .isEqualTo("第一章");
        assertThat(database.dsl().select(WRITINGBIBLE.TARGETTOTALWORDCOUNT)
                        .from(WRITINGBIBLE)
                        .where(WRITINGBIBLE.NOVELID.eq(longNovel.getNovelId()))
                        .fetchSingle(WRITINGBIBLE.TARGETTOTALWORDCOUNT))
                .isEqualTo(1_000_000);
        assertThat(database.dsl().fetchCount(
                        REVIEWARTIFACT,
                        REVIEWARTIFACT.NOVELID.eq(longNovel.getNovelId())))
                .isZero();

        int before = database.dsl().fetchCount(NOVEL, NOVEL.USERID.eq(owner));
        NovelCreation invalid = new NovelCreation(
                owner,
                null,
                "应回滚",
                null,
                null,
                "short_medium",
                10_000,
                null,
                null,
                null,
                null,
                "全文",
                1,
                "正文",
                "",
                "opening",
                "来源",
                "开篇",
                null);
        assertThatThrownBy(() -> repository.create(invalid))
                .isInstanceOf(IllegalStateException.class)
                .hasMessage("中短篇来源素材缺少创建请求标识");
        assertThat(database.dsl().fetchCount(NOVEL, NOVEL.USERID.eq(owner)))
                .isEqualTo(before);
    }

    @Test
    void 小说读取与摘要更新必须保持归属CAS优先及幂等时间戳() {
        String owner = user("novel-summary-owner");
        String stranger = user("novel-summary-stranger");
        String novelId = novel(
                "novel-summary-1",
                owner,
                "旧摘要",
                Storylengthprofile.long_serial,
                500_000,
                INITIAL,
                null);

        var loaded = repository.get(novelId, owner);
        assertThat(loaded.getSummary()).isEqualTo("旧摘要");
        assertThat(loaded.getStoryLengthProfile()).isEqualTo(StoryLengthProfile.LONG_SERIAL);
        assertThat(loaded.getTargetTotalWordCount()).isEqualTo(500_000);
        assertCode(() -> repository.get(novelId, stranger), 403, "NOVEL_FORBIDDEN");
        assertCode(() -> repository.get("missing", owner), 404, "NOVEL_NOT_FOUND");

        var updated = repository.updateSummary(
                novelId,
                owner,
                "新摘要",
                INITIAL.atOffset(ZoneOffset.UTC));
        assertThat(updated.getUpdatedAt())
                .isEqualTo(OffsetDateTime.parse("2026-08-25T03:00:00.123Z"));
        assertThat(updated.getSummary()).isEqualTo("新摘要");
        assertCode(
                () -> repository.updateSummary(
                        novelId,
                        owner,
                        "新摘要",
                        INITIAL.atOffset(ZoneOffset.UTC)),
                409,
                "NOVEL_VERSION_CONFLICT");
        var replayed = repository.updateSummary(
                novelId, owner, "新摘要", updated.getUpdatedAt());
        assertThat(replayed.getUpdatedAt()).isEqualTo(updated.getUpdatedAt());
        assertCode(
                () -> repository.updateSummary(
                        novelId, stranger, "越权", updated.getUpdatedAt()),
                403,
                "NOVEL_FORBIDDEN");
    }

    @Test
    void Dashboard与列表必须稳定排序按篇幅过滤并隐藏外来文风() {
        String owner = user("novel-list-owner");
        String stranger = user("novel-list-stranger");
        style("style-owned", owner, "自己的文风");
        style("style-foreign", stranger, "外来文风");
        LocalDateTime newer = INITIAL.plusHours(1);
        novel(
                "novel-b",
                owner,
                "B",
                Storylengthprofile.long_serial,
                300_000,
                newer,
                "style-foreign");
        novel(
                "novel-a",
                owner,
                "A",
                Storylengthprofile.short_medium,
                20_000,
                newer,
                "style-owned");
        novel(
                "novel-old",
                owner,
                "旧",
                Storylengthprofile.long_serial,
                600_000,
                INITIAL,
                null);
        chapter("chapter-a-2", "novel-a", 2);
        chapter("chapter-a-1", "novel-a", 1);

        var dashboard = repository.dashboard(owner);
        assertThat(dashboard.getNovels())
                .extracting(value -> value.getId())
                .containsExactly("novel-a", "novel-b", "novel-old");
        assertThat(dashboard.getNovels().getFirst().getChapters())
                .extracting(value -> value.getId())
                .containsExactly("chapter-a-1", "chapter-a-2");
        assertThat(dashboard.getNovels().getFirst().getAppliedStyle().getId())
                .isEqualTo("style-owned");
        assertThat(dashboard.getNovels().get(1).getAppliedStyle()).isNull();

        var shortNovels = repository.list(owner, StoryLengthProfile.SHORT_MEDIUM);
        assertThat(shortNovels).extracting(value -> value.getId())
                .containsExactly("novel-a");
        assertThat(repository.list(owner, null))
                .extracting(value -> value.getId())
                .containsExactly("novel-a", "novel-b", "novel-old");
    }

    private NovelCreation shortCreation(
            String userId, String requestId, String sourceKind, String sourceText) {
        return new NovelCreation(
                userId,
                requestId,
                "短篇",
                "完整摘要",
                "第一章目标：完成故事",
                "short_medium",
                12_000,
                "悬疑",
                "身份反转",
                "兑现真相",
                "主角起点：失忆\n第一章目标：完成故事",
                "全文",
                1,
                "opening".equals(sourceKind) ? sourceText : "",
                "outline".equals(sourceKind) ? sourceText : "",
                sourceKind,
                sourceText,
                "开篇",
                "完成故事");
    }

    private NovelCreation longCreation(String userId) {
        return new NovelCreation(
                userId,
                null,
                "长篇",
                null,
                null,
                "long_serial",
                1_000_000,
                null,
                null,
                null,
                null,
                "第一章",
                1,
                "",
                "",
                null,
                null,
                "开篇",
                null);
    }

    private String user(String id) {
        users.add(id);
        database.dsl().insertInto(USER)
                .set(USER.ID, id)
                .set(USER.USERNAME, id)
                .set(USER.PASSWORDHASH, "test-hash")
                .set(USER.CREDITBALANCEMICROS, 0L)
                .set(USER.CREATEDAT, INITIAL)
                .set(USER.UPDATEDAT, INITIAL)
                .execute();
        return id;
    }

    private String novel(
            String id,
            String userId,
            String summary,
            Storylengthprofile profile,
            int targetWords,
            LocalDateTime updatedAt,
            String styleId) {
        database.dsl().insertInto(NOVEL)
                .set(NOVEL.ID, id)
                .set(NOVEL.NAME, id)
                .set(NOVEL.SUMMARY, summary)
                .set(NOVEL.APPLIEDSTYLEID, styleId)
                .set(NOVEL.USERID, userId)
                .set(NOVEL.CREATEDAT, INITIAL)
                .set(NOVEL.UPDATEDAT, updatedAt)
                .execute();
        database.dsl().insertInto(WRITINGBIBLE)
                .set(WRITINGBIBLE.ID, id + "-bible")
                .set(WRITINGBIBLE.NOVELID, id)
                .set(WRITINGBIBLE.STORYLENGTHPROFILE, profile)
                .set(WRITINGBIBLE.TARGETTOTALWORDCOUNT, targetWords)
                .set(WRITINGBIBLE.CREATEDAT, INITIAL)
                .set(WRITINGBIBLE.UPDATEDAT, INITIAL)
                .execute();
        return id;
    }

    private void chapter(String id, String novelId, int order) {
        database.dsl().insertInto(CHAPTER)
                .set(CHAPTER.ID, id)
                .set(CHAPTER.NOVELID, novelId)
                .set(CHAPTER.TITLE, id)
                .set(CHAPTER.CONTENT, "")
                .set(CHAPTER.ORDER, order)
                .set(CHAPTER.STATUS, Chapterstatus.drafting)
                .set(CHAPTER.CREATEDAT, INITIAL)
                .set(CHAPTER.UPDATEDAT, INITIAL)
                .execute();
    }

    private void style(String id, String userId, String name) {
        database.dsl().insertInto(WRITINGSTYLE)
                .set(WRITINGSTYLE.ID, id)
                .set(WRITINGSTYLE.NAME, name)
                .set(WRITINGSTYLE.SOURCETYPE, Stylesourcetype.manual)
                .set(WRITINGSTYLE.ORIGINALCHARCOUNT, 0)
                .set(WRITINGSTYLE.USEDCHARCOUNT, 0)
                .set(WRITINGSTYLE.TRUNCATED, false)
                .set(WRITINGSTYLE.USERID, userId)
                .set(WRITINGSTYLE.CREATEDAT, INITIAL)
                .set(WRITINGSTYLE.UPDATEDAT, INITIAL)
                .execute();
    }

    private static void assertCode(Runnable action, int status, String code) {
        assertThatThrownBy(action::run)
                .isInstanceOfSatisfying(ApiException.class, error -> {
                    assertThat(error.statusCode()).isEqualTo(status);
                    assertThat(error.code()).isEqualTo(code);
                });
    }

    private static String sha256(String value) {
        try {
            return HexFormat.of().formatHex(
                    MessageDigest.getInstance("SHA-256")
                            .digest(value.getBytes(StandardCharsets.UTF_8)));
        } catch (java.security.NoSuchAlgorithmException error) {
            throw new IllegalStateException(error);
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
