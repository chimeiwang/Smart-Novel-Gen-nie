package cn.inkforge.core.novels.infrastructure;

import static cn.inkforge.core.db.generated.Tables.CHAPTER;
import static cn.inkforge.core.db.generated.Tables.CHAPTERBEATPLAN;
import static cn.inkforge.core.db.generated.Tables.CHAPTERPROGRESS;
import static cn.inkforge.core.db.generated.Tables.CHAPTERQUALITYCHECK;
import static cn.inkforge.core.db.generated.Tables.CHARACTER;
import static cn.inkforge.core.db.generated.Tables.CHARACTEREXPERIENCE;
import static cn.inkforge.core.db.generated.Tables.CHARACTERRELATION;
import static cn.inkforge.core.db.generated.Tables.FACTION;
import static cn.inkforge.core.db.generated.Tables.GLOSSARY;
import static cn.inkforge.core.db.generated.Tables.ITEM;
import static cn.inkforge.core.db.generated.Tables.LOCATION;
import static cn.inkforge.core.db.generated.Tables.NOVEL;
import static cn.inkforge.core.db.generated.Tables.OUTLINE;
import static cn.inkforge.core.db.generated.Tables.OUTLINENODE;
import static cn.inkforge.core.db.generated.Tables.PLOTPROGRESS;
import static cn.inkforge.core.db.generated.Tables.RAGDOCUMENT;
import static cn.inkforge.core.db.generated.Tables.REFERENCEMATERIAL;
import static cn.inkforge.core.db.generated.Tables.SCENEBEAT;
import static cn.inkforge.core.db.generated.Tables.STORYBACKGROUND;
import static cn.inkforge.core.db.generated.Tables.USER;
import static cn.inkforge.core.db.generated.Tables.WORLDSETTING;
import static cn.inkforge.core.db.generated.Tables.WRITINGBIBLE;
import static cn.inkforge.core.db.generated.Tables.WRITINGSTYLE;
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import cn.inkforge.core.db.generated.enums.Beatplanstatus;
import cn.inkforge.core.db.generated.enums.Chapterstatus;
import cn.inkforge.core.db.generated.enums.Characterstatus;
import cn.inkforge.core.db.generated.enums.Outlinenodekind;
import cn.inkforge.core.db.generated.enums.Outlinenodestatus;
import cn.inkforge.core.db.generated.enums.Qualitycheckstatus;
import cn.inkforge.core.db.generated.enums.Qualitychecktype;
import cn.inkforge.core.db.generated.enums.Ragdocumentstatus;
import cn.inkforge.core.db.generated.enums.Ragsourcetype;
import cn.inkforge.core.db.generated.enums.Referencematerialtype;
import cn.inkforge.core.db.generated.enums.Relationtype;
import cn.inkforge.core.db.generated.enums.Storylengthprofile;
import cn.inkforge.core.db.generated.enums.Stylesourcetype;
import cn.inkforge.core.platform.db.CoreDatabase;
import cn.inkforge.core.platform.db.PostgresConnectionSettings;
import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.platform.id.CuidV1Generator;
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
import tools.jackson.databind.ObjectMapper;

@Testcontainers
class JooqWorkspaceReaderTest {

    private static final LocalDateTime INITIAL =
            LocalDateTime.parse("2026-08-24T10:00:00.000");
    private static final Clock CLOCK = Clock.fixed(
            Instant.parse("2026-08-25T04:00:00.123Z"), ZoneOffset.UTC);

    @Container
    private static final PostgreSQLContainer POSTGRES =
            new PostgreSQLContainer("pgvector/pgvector:0.8.0-pg14")
                    .withDatabaseName("inkforge_workspace_test")
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
                database,
                new CuidV1Generator(CLOCK),
                CLOCK,
                new ObjectMapper());
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
    void 工作区归属查询前必须进入只读可重复读事务() {
        String owner = user("workspace-transaction-owner");
        String novel = novel("workspace-transaction-novel", owner, null);

        new WorkspaceReadTransaction(database).read(
                novel,
                owner,
                false,
                (transaction, ignored) -> {
                    assertThat(transaction.fetchValue(
                                    "show transaction_isolation", String.class))
                            .isEqualTo("repeatable read");
                    assertThat(transaction.fetchValue(
                                    "show transaction_read_only", String.class))
                            .isEqualTo("on");
                    return null;
                });
    }

    @Test
    void Bootstrap只加载当前章节详情并按回退规则提供全部轻量摘要() {
        String owner = user("workspace-bootstrap-owner");
        String stranger = user("workspace-bootstrap-stranger");
        String novel = novel("workspace-bootstrap-novel", owner, null);
        chapter("chapter-1", novel, 1, Chapterstatus.completed, "第一章");
        String currentContent = "😀 当前正文\n".repeat(20_000);
        chapter("chapter-2", novel, 2, Chapterstatus.drafting, currentContent);
        chapter("chapter-3", novel, 3, Chapterstatus.review, "第三章");
        progress("progress-2", "chapter-2", "完整章节进展");
        quality("quality-2", "chapter-2");
        beatPlan("plan-1-old", "chapter-1", INITIAL, 300);
        beatPlan("plan-1-new", "chapter-1", INITIAL.plusMinutes(1), 600);
        beat("beat-1", "plan-1-new", 1);
        beat("beat-2", "plan-1-new", 2);

        var bootstrap = repository.workspaceBootstrap(novel, owner, "invalid");

        assertThat(bootstrap.getCurrentChapterId()).isEqualTo("chapter-2");
        assertThat(bootstrap.getCurrentChapter().getContent()).isEqualTo(currentContent);
        assertThat(bootstrap.getCurrentChapter().getProgress().getContent())
                .isEqualTo("完整章节进展");
        assertThat(bootstrap.getCurrentChapter().getQualityChecks()).hasSize(1);
        assertThat(bootstrap.getChapters()).extracting(value -> value.getId())
                .containsExactly("chapter-1", "chapter-2", "chapter-3");
        assertThat(bootstrap.getChapters().getFirst().getApprovedBeatPlan().getSceneCount())
                .isEqualTo(2);
        assertThat(bootstrap.getChapters().getFirst()
                        .getApprovedBeatPlan()
                        .getTotalEstimatedWords())
                .isEqualTo(600);
        assertThat(bootstrap.getChapters().get(1).getWordCount()).isEqualTo(100_000);
        assertThat(repository.workspaceBootstrap(novel, owner, "chapter-1")
                        .getCurrentChapterId())
                .isEqualTo("chapter-1");

        assertCode(
                () -> repository.workspaceBootstrap(novel, stranger, null),
                404,
                "NOVEL_NOT_FOUND");
        assertCode(
                () -> repository.workspaceLore(novel, stranger),
                404,
                "NOVEL_NOT_FOUND");
        assertCode(
                () -> repository.workspacePlanning(novel, stranger),
                404,
                "NOVEL_NOT_FOUND");
        assertCode(
                () -> repository.workspaceResources(novel, stranger),
                404,
                "NOVEL_NOT_FOUND");
        assertCode(
                () -> repository.workspace(novel, stranger, null),
                403,
                "NOVEL_FORBIDDEN");
    }

    @Test
    void 分组与完整工作区必须隔离聚合设定规划资料并完整返回正文() {
        String owner = user("workspace-full-owner");
        String stranger = user("workspace-full-stranger");
        style("style-owned", owner, "作者文风");
        style("style-foreign", stranger, "外来文风");
        String novel = novel("workspace-full-novel", owner, "style-owned");
        String longContent = "  长正文\r\n😀  ".repeat(30_000);
        chapter("full-chapter", novel, 1, Chapterstatus.drafting, longContent);
        lore(novel);
        planning(novel);
        resources(novel);

        var lore = repository.workspaceLore(novel, owner);
        assertThat(lore.getCharacters()).extracting(value -> value.getId())
                .containsExactly("character-a", "character-b");
        assertThat(lore.getCharacters().getFirst().getFaction().getName())
                .isEqualTo("门派");
        assertThat(lore.getCharacters().getFirst().getExperiences().getFirst().getContent())
                .isEqualTo("完整经历");
        assertThat(lore.getCharacters().getFirst().getOutgoingRelations().getFirst()
                        .getTarget()
                        .getName())
                .isEqualTo("乙");
        assertThat(lore.getCharacters().get(1).getIncomingRelations().getFirst()
                        .getCharacter()
                        .getName())
                .isEqualTo("甲");
        assertThat(lore.getItems().getFirst().getOwner().getName()).isEqualTo("甲");

        var planning = repository.workspacePlanning(novel, owner);
        assertThat(planning.getStoryProgress()).isEqualTo("推进到转折");
        assertThat(planning.getStoryBackground().getContent()).isEqualTo("完整背景");
        assertThat(planning.getWorldSetting().getContent()).isEqualTo("完整世界观");
        assertThat(planning.getWritingBible().getGenre()).isEqualTo("仙侠");
        assertThat(planning.getOutline().getContent()).isEqualTo("完整总纲");
        assertThat(planning.getOutlineNodes()).extracting(value -> value.getId())
                .containsExactly("node-a", "node-b");
        assertThat(planning.getPlotProgress().getCurrentConflict()).isEqualTo("正邪冲突");

        var resources = repository.workspaceResources(novel, owner);
        assertThat(resources.getReferences()).extracting(value -> value.getId())
                .containsExactly("reference-a", "reference-b");
        assertThat(resources.getReferences().getFirst().getErrorMessage())
                .isEqualTo("索引生成失败");
        assertThat(resources.getReferences().get(1).getRagStatus().getValue())
                .isEqualTo("disabled");
        assertThat(resources.getReferences().get(1).getContentHash())
                .isNotBlank();
        assertThat(resources.getStyles()).extracting(value -> value.getId())
                .containsExactly("style-owned");
        assertThat(resources.getAppliedStyle().getId()).isEqualTo("style-owned");

        var workspace = repository.workspace(novel, owner, null);
        assertThat(workspace.getChapters().getFirst().getContent()).isEqualTo(longContent);
        assertThat(workspace.getCurrentChapterId()).isEqualTo("full-chapter");
        assertThat(workspace.getNovel().getAppliedStyle().getId()).isEqualTo("style-owned");
        assertThat(workspace.getCharacters()).hasSize(2);
        assertThat(workspace.getOutlineNodes()).hasSize(2);
        assertThat(workspace.getReferences()).hasSize(2);
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

    private String novel(String id, String userId, String appliedStyleId) {
        database.dsl().insertInto(NOVEL)
                .set(NOVEL.ID, id)
                .set(NOVEL.NAME, id)
                .set(NOVEL.SUMMARY, "简介")
                .set(NOVEL.STORYPROGRESS, "推进到转折")
                .set(NOVEL.APPLIEDSTYLEID, appliedStyleId)
                .set(NOVEL.USERID, userId)
                .set(NOVEL.CREATEDAT, INITIAL)
                .set(NOVEL.UPDATEDAT, INITIAL)
                .execute();
        database.dsl().insertInto(OUTLINE)
                .set(OUTLINE.ID, id + "-outline")
                .set(OUTLINE.NOVELID, id)
                .set(OUTLINE.CONTENT, "")
                .set(OUTLINE.CREATEDAT, INITIAL)
                .set(OUTLINE.UPDATEDAT, INITIAL)
                .execute();
        database.dsl().insertInto(PLOTPROGRESS)
                .set(PLOTPROGRESS.ID, id + "-plot")
                .set(PLOTPROGRESS.NOVELID, id)
                .set(PLOTPROGRESS.CURRENTSTAGE, "开篇")
                .set(PLOTPROGRESS.UPDATEDAT, INITIAL)
                .execute();
        database.dsl().insertInto(WRITINGBIBLE)
                .set(WRITINGBIBLE.ID, id + "-bible")
                .set(WRITINGBIBLE.NOVELID, id)
                .set(WRITINGBIBLE.STORYLENGTHPROFILE, Storylengthprofile.long_serial)
                .set(WRITINGBIBLE.TARGETTOTALWORDCOUNT, 1_000_000)
                .set(WRITINGBIBLE.CREATEDAT, INITIAL)
                .set(WRITINGBIBLE.UPDATEDAT, INITIAL)
                .execute();
        return id;
    }

    private void chapter(
            String id,
            String novelId,
            int order,
            Chapterstatus status,
            String content) {
        database.dsl().insertInto(CHAPTER)
                .set(CHAPTER.ID, id)
                .set(CHAPTER.NOVELID, novelId)
                .set(CHAPTER.TITLE, id)
                .set(CHAPTER.CONTENT, content)
                .set(CHAPTER.ORDER, order)
                .set(CHAPTER.STATUS, status)
                .set(CHAPTER.CREATEDAT, INITIAL)
                .set(CHAPTER.UPDATEDAT, INITIAL)
                .execute();
    }

    private void progress(String id, String chapterId, String content) {
        database.dsl().insertInto(CHAPTERPROGRESS)
                .set(CHAPTERPROGRESS.ID, id)
                .set(CHAPTERPROGRESS.CHAPTERID, chapterId)
                .set(CHAPTERPROGRESS.CONTENT, content)
                .set(CHAPTERPROGRESS.CREATEDAT, INITIAL)
                .set(CHAPTERPROGRESS.UPDATEDAT, INITIAL)
                .execute();
    }

    private void quality(String id, String chapterId) {
        database.dsl().insertInto(CHAPTERQUALITYCHECK)
                .set(CHAPTERQUALITYCHECK.ID, id)
                .set(CHAPTERQUALITYCHECK.CHAPTERID, chapterId)
                .set(CHAPTERQUALITYCHECK.TYPE, Qualitychecktype.consistency)
                .set(CHAPTERQUALITYCHECK.STATUS, Qualitycheckstatus.completed)
                .set(CHAPTERQUALITYCHECK.TITLE, "一致性终检")
                .set(CHAPTERQUALITYCHECK.CREATEDAT, INITIAL)
                .set(CHAPTERQUALITYCHECK.UPDATEDAT, INITIAL)
                .execute();
    }

    private void beatPlan(
            String id, String chapterId, LocalDateTime updatedAt, int words) {
        database.dsl().insertInto(CHAPTERBEATPLAN)
                .set(CHAPTERBEATPLAN.ID, id)
                .set(CHAPTERBEATPLAN.CHAPTERID, chapterId)
                .set(CHAPTERBEATPLAN.STATUS, Beatplanstatus.approved)
                .set(CHAPTERBEATPLAN.CHAPTERGOAL, "推进冲突")
                .set(CHAPTERBEATPLAN.TOTALESTIMATEDWORDS, words)
                .set(CHAPTERBEATPLAN.CREATEDAT, INITIAL)
                .set(CHAPTERBEATPLAN.UPDATEDAT, updatedAt)
                .execute();
    }

    private void beat(String id, String planId, int order) {
        database.dsl().insertInto(SCENEBEAT)
                .set(SCENEBEAT.ID, id)
                .set(SCENEBEAT.BEATPLANID, planId)
                .set(SCENEBEAT.ORDER, order)
                .set(SCENEBEAT.GOAL, "场景目标")
                .set(SCENEBEAT.CHARACTERS, "甲")
                .set(SCENEBEAT.ESTIMATEDWORDS, 300)
                .set(SCENEBEAT.ACCEPTANCECRITERIA, "产生变化")
                .execute();
    }

    private void lore(String novelId) {
        database.dsl().insertInto(FACTION)
                .set(FACTION.ID, "faction-a")
                .set(FACTION.NOVELID, novelId)
                .set(FACTION.NAME, "门派")
                .set(FACTION.CREATEDAT, INITIAL)
                .set(FACTION.UPDATEDAT, INITIAL)
                .execute();
        character("character-a", novelId, "甲", "faction-a");
        character("character-b", novelId, "乙", null);
        database.dsl().insertInto(CHARACTEREXPERIENCE)
                .set(CHARACTEREXPERIENCE.ID, "experience-a")
                .set(CHARACTEREXPERIENCE.CHARACTERID, "character-a")
                .set(CHARACTEREXPERIENCE.CHAPTERID, "full-chapter")
                .set(CHARACTEREXPERIENCE.CONTENT, "完整经历")
                .set(CHARACTEREXPERIENCE.ORDER, 1)
                .set(CHARACTEREXPERIENCE.CREATEDAT, INITIAL)
                .set(CHARACTEREXPERIENCE.UPDATEDAT, INITIAL)
                .execute();
        database.dsl().insertInto(CHARACTERRELATION)
                .set(CHARACTERRELATION.ID, "relation-a")
                .set(CHARACTERRELATION.CHARACTERID, "character-a")
                .set(CHARACTERRELATION.TARGETID, "character-b")
                .set(CHARACTERRELATION.RELATIONTYPE, Relationtype.friend)
                .set(CHARACTERRELATION.INTIMACY, 80)
                .set(CHARACTERRELATION.CREATEDAT, INITIAL)
                .set(CHARACTERRELATION.UPDATEDAT, INITIAL)
                .execute();
        database.dsl().insertInto(ITEM)
                .set(ITEM.ID, "item-a")
                .set(ITEM.NOVELID, novelId)
                .set(ITEM.NAME, "信物")
                .set(ITEM.OWNERID, "character-a")
                .set(ITEM.CREATEDAT, INITIAL)
                .set(ITEM.UPDATEDAT, INITIAL)
                .execute();
        database.dsl().insertInto(LOCATION)
                .set(LOCATION.ID, "location-a")
                .set(LOCATION.NOVELID, novelId)
                .set(LOCATION.NAME, "山门")
                .set(LOCATION.CREATEDAT, INITIAL)
                .set(LOCATION.UPDATEDAT, INITIAL)
                .execute();
        database.dsl().insertInto(GLOSSARY)
                .set(GLOSSARY.ID, "glossary-a")
                .set(GLOSSARY.NOVELID, novelId)
                .set(GLOSSARY.TERM, "灵息")
                .set(GLOSSARY.DEFINITION, "修行能量")
                .set(GLOSSARY.CREATEDAT, INITIAL)
                .set(GLOSSARY.UPDATEDAT, INITIAL)
                .execute();
    }

    private void character(String id, String novelId, String name, String factionId) {
        database.dsl().insertInto(CHARACTER)
                .set(CHARACTER.ID, id)
                .set(CHARACTER.NOVELID, novelId)
                .set(CHARACTER.NAME, name)
                .set(CHARACTER.FACTIONID, factionId)
                .set(CHARACTER.CURRENTSTATUS, Characterstatus.active)
                .set(CHARACTER.CREATEDAT, INITIAL)
                .set(CHARACTER.UPDATEDAT, INITIAL)
                .execute();
    }

    private void planning(String novelId) {
        database.dsl().update(OUTLINE)
                .set(OUTLINE.CONTENT, "完整总纲")
                .where(OUTLINE.NOVELID.eq(novelId))
                .execute();
        database.dsl().update(PLOTPROGRESS)
                .set(PLOTPROGRESS.CURRENTCONFLICT, "正邪冲突")
                .where(PLOTPROGRESS.NOVELID.eq(novelId))
                .execute();
        database.dsl().update(WRITINGBIBLE)
                .set(WRITINGBIBLE.GENRE, "仙侠")
                .where(WRITINGBIBLE.NOVELID.eq(novelId))
                .execute();
        content(STORYBACKGROUND.ID, STORYBACKGROUND.NOVELID, STORYBACKGROUND.CONTENT,
                STORYBACKGROUND.CREATEDAT, STORYBACKGROUND.UPDATEDAT,
                "background-a", novelId, "完整背景");
        content(WORLDSETTING.ID, WORLDSETTING.NOVELID, WORLDSETTING.CONTENT,
                WORLDSETTING.CREATEDAT, WORLDSETTING.UPDATEDAT,
                "world-a", novelId, "完整世界观");
        outlineNode("node-b", novelId, 2, "乙节点");
        outlineNode("node-a", novelId, 1, "甲节点");
    }

    private <R extends org.jooq.Record> void content(
            org.jooq.TableField<R, String> id,
            org.jooq.TableField<R, String> novelIdField,
            org.jooq.TableField<R, String> content,
            org.jooq.TableField<R, LocalDateTime> createdAt,
            org.jooq.TableField<R, LocalDateTime> updatedAt,
            String valueId,
            String novelId,
            String value) {
        database.dsl().insertInto(id.getTable())
                .set(id, valueId)
                .set(novelIdField, novelId)
                .set(content, value)
                .set(createdAt, INITIAL)
                .set(updatedAt, INITIAL)
                .execute();
    }

    private void outlineNode(String id, String novelId, int order, String title) {
        database.dsl().insertInto(OUTLINENODE)
                .set(OUTLINENODE.ID, id)
                .set(OUTLINENODE.NOVELID, novelId)
                .set(OUTLINENODE.TITLE, title)
                .set(OUTLINENODE.ORDER, order)
                .set(OUTLINENODE.STATUS, Outlinenodestatus.planned)
                .set(OUTLINENODE.KIND, Outlinenodekind.stage)
                .set(OUTLINENODE.CREATEDAT, INITIAL)
                .set(OUTLINENODE.UPDATEDAT, INITIAL)
                .execute();
    }

    private void resources(String novelId) {
        reference("reference-b", novelId, "无索引", "完整资料乙", INITIAL);
        reference("reference-a", novelId, "失败索引", "完整资料甲", INITIAL.plusMinutes(1));
        database.dsl().insertInto(RAGDOCUMENT)
                .set(RAGDOCUMENT.ID, "rag-a")
                .set(RAGDOCUMENT.NOVELID, novelId)
                .set(RAGDOCUMENT.SOURCETYPE, Ragsourcetype.reference_material)
                .set(RAGDOCUMENT.SOURCEID, "reference-a")
                .set(RAGDOCUMENT.TITLE, "失败索引")
                .set(RAGDOCUMENT.CONTENTHASH, "stored-content-hash")
                .set(RAGDOCUMENT.STATUS, Ragdocumentstatus.failed)
                .set(RAGDOCUMENT.ERRORMESSAGE, "敏感内部错误")
                .set(RAGDOCUMENT.CREATEDAT, INITIAL)
                .set(RAGDOCUMENT.UPDATEDAT, INITIAL)
                .execute();
    }

    private void reference(
            String id,
            String novelId,
            String title,
            String content,
            LocalDateTime updatedAt) {
        database.dsl().insertInto(REFERENCEMATERIAL)
                .set(REFERENCEMATERIAL.ID, id)
                .set(REFERENCEMATERIAL.NOVELID, novelId)
                .set(REFERENCEMATERIAL.TITLE, title)
                .set(REFERENCEMATERIAL.TYPE, Referencematerialtype.note)
                .set(REFERENCEMATERIAL.CONTENT, content)
                .set(REFERENCEMATERIAL.CREATEDAT, INITIAL)
                .set(REFERENCEMATERIAL.UPDATEDAT, updatedAt)
                .execute();
    }

    private void style(String id, String userId, String name) {
        database.dsl().insertInto(WRITINGSTYLE)
                .set(WRITINGSTYLE.ID, id)
                .set(WRITINGSTYLE.NAME, name)
                .set(WRITINGSTYLE.SOURCETYPE, Stylesourcetype.manual)
                .set(WRITINGSTYLE.PORTRAITMARKDOWN, "完整文风画像")
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
