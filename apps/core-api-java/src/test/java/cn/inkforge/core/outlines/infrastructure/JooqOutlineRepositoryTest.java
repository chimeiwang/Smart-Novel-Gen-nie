package cn.inkforge.core.outlines.infrastructure;

import static cn.inkforge.core.db.generated.Tables.CHAPTER;
import static cn.inkforge.core.db.generated.Tables.FORESHADOWING;
import static cn.inkforge.core.db.generated.Tables.NOVEL;
import static cn.inkforge.core.db.generated.Tables.OUTLINE;
import static cn.inkforge.core.db.generated.Tables.OUTLINENODE;
import static cn.inkforge.core.db.generated.Tables.USER;
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import cn.inkforge.core.db.generated.enums.Chapterstatus;
import cn.inkforge.core.outlines.domain.ForeshadowingData;
import cn.inkforge.core.outlines.domain.ForeshadowingPatch;
import cn.inkforge.core.outlines.domain.OutlineNodeData;
import cn.inkforge.core.outlines.domain.OutlineNodePatch;
import cn.inkforge.core.outlines.domain.PlotProgressData;
import cn.inkforge.core.platform.db.CoreDatabase;
import cn.inkforge.core.platform.db.PostgresConnectionSettings;
import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.platform.id.CommandResourceId;
import cn.inkforge.core.platform.id.CuidV1Generator;
import cn.inkforge.core.platform.patch.PatchField;
import java.time.Clock;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.OffsetDateTime;
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
class JooqOutlineRepositoryTest {

    private static final LocalDateTime INITIAL =
            LocalDateTime.parse("2026-08-24T10:00:00.000");
    private static final Clock CLOCK = Clock.fixed(
            Instant.parse("2026-08-25T01:00:00.123Z"), ZoneOffset.UTC);

    @Container
    private static final PostgreSQLContainer POSTGRES =
            new PostgreSQLContainer("pgvector/pgvector:0.8.0-pg14")
                    .withDatabaseName("inkforge_outlines_test")
                    .withUsername("inkforge")
                    .withPassword("test-only-password");

    private static CoreDatabase database;
    private static JooqOutlineRepository repository;
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
        repository = new JooqOutlineRepository(
                database, new CuidV1Generator(CLOCK), CLOCK);
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
    void 大纲与剧情进度必须先CAS再判断幂等并保留完整文本() {
        String owner = user("outline-owner-1");
        String stranger = user("outline-stranger-1");
        String novel = novel("outline-novel-1", owner, "旧大纲");
        OffsetDateTime expected = INITIAL.atOffset(ZoneOffset.UTC);
        String fullContent = "  第一幕\n\n第二幕  ".repeat(20_000);

        var saved = repository.saveOutline(novel, owner, fullContent, expected);
        assertThat(saved.getContent()).isEqualTo(fullContent);
        assertThat(saved.getContentHash()).hasSize(64);
        assertCode(
                () -> repository.saveOutline(novel, owner, "陈旧覆盖", expected),
                "OUTLINE_VERSION_CONFLICT");
        assertThat(repository.saveOutline(novel, owner, fullContent, saved.getUpdatedAt()))
                .isEqualTo(saved);

        PlotProgressData first =
                new PlotProgressData("第一幕", "找到线索", null, "进入遗迹");
        var plot = repository.savePlot(novel, owner, first, null);
        assertThat(plot.getCurrentStage()).isEqualTo("第一幕");
        assertCode(
                () -> repository.savePlot(novel, owner, first, null),
                "PLOT_PROGRESS_VERSION_CONFLICT");
        assertThat(repository.savePlot(novel, owner, first, plot.getUpdatedAt()))
                .isEqualTo(plot);
        assertCode(
                () -> repository.listNodes(novel, stranger), "NOVEL_FORBIDDEN");
    }

    @Test
    void 节点必须支持幂等创建三层校验跨小说拒绝和删除门禁() {
        String owner = user("outline-owner-2");
        String novel = novel("outline-novel-2", owner, "大纲");
        String otherNovel = novel("outline-novel-other-2", owner, "其他大纲");
        chapter("outline-chapter-other", otherNovel);
        OutlineNodeData stage = node(
                "第一卷", "stage", null, null, 1, 30);

        var created = repository.createNode(
                novel, owner, "outline-node-create-0001", stage);
        String expectedId = CommandResourceId.derive(
                "outline_nodes", owner, novel, "outline-node-create-0001");
        assertThat(created.getId()).isEqualTo(expectedId);
        assertThat(created.getEffective()).isTrue();
        assertThat(repository.createNode(
                        novel, owner, "outline-node-create-0001", stage)
                        .getEffective())
                .isFalse();
        assertCode(
                () -> repository.createNode(
                        novel,
                        owner,
                        "outline-node-create-0001",
                        node("不同内容", "stage", null, null, 1, 30)),
                "RESOURCE_CREATE_CONFLICT");

        var child = repository.createNode(
                novel,
                owner,
                "outline-node-create-0002",
                node("冲突单元", "plot_unit", expectedId, null, 2, 10));
        assertCode(
                () -> repository.createNode(
                        novel,
                        owner,
                        "outline-node-create-0003",
                        new OutlineNodeData(
                                "跨小说章节",
                                null,
                                "stage",
                                "planned",
                                2,
                                null,
                                "outline-chapter-other",
                                null,
                                null,
                                31,
                                40)),
                "OUTLINE_CHAPTER_CROSS_NOVEL");
        assertCode(
                () -> repository.deleteNode(
                        novel, owner, expectedId, created.getUpdatedAt()),
                "OUTLINE_NODE_HAS_CHILDREN");

        OutlineNodePatch titlePatch = patchTitle("第一卷·立足");
        var changed = repository.updateNode(
                novel, owner, expectedId, titlePatch, created.getUpdatedAt());
        assertThat(changed.getEffective()).isTrue();
        assertCode(
                () -> repository.updateNode(
                        novel, owner, expectedId, patchTitle("陈旧"), created.getUpdatedAt()),
                "OUTLINE_NODE_VERSION_CONFLICT");
        repository.deleteNode(novel, owner, child.getId(), child.getUpdatedAt());
        repository.deleteNode(novel, owner, expectedId, changed.getUpdatedAt());
        assertThat(database.dsl().fetchCount(
                        OUTLINENODE, OUTLINENODE.NOVELID.eq(novel)))
                .isZero();
    }

    @Test
    void 伏笔CRUD必须保持三态Patch稳定排序和资源范围() {
        String owner = user("outline-owner-3");
        String novel = novel("outline-novel-3", owner, "大纲");
        ForeshadowingData data = new ForeshadowingData(
                "门上的划痕", "第一章", "  原文\r\n  ", "身份揭晓", null, "active");

        var created = repository.createForeshadowing(novel, owner, data);
        ForeshadowingPatch patch = new ForeshadowingPatch(
                absent(),
                absent(),
                new PatchField<>(true, null),
                absent(),
                new PatchField<>(true, "第十章"),
                absent());
        var updated = repository.updateForeshadowing(
                novel, owner, created.getId(), patch);
        assertThat(updated.getPlantedContent()).isNull();
        assertThat(updated.getPayoffAt()).isEqualTo("第十章");
        assertThat(repository.listForeshadowings(novel, owner))
                .extracting(value -> value.getId())
                .containsExactly(created.getId());
        repository.deleteForeshadowing(novel, owner, created.getId());
        assertThat(database.dsl().fetchCount(
                        FORESHADOWING, FORESHADOWING.NOVELID.eq(novel)))
                .isZero();
        assertCode(
                () -> repository.deleteForeshadowing(novel, owner, created.getId()),
                "FORESHADOWING_NOT_FOUND");
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

    private String novel(String id, String owner, String outlineContent) {
        database.dsl().insertInto(NOVEL)
                .set(NOVEL.ID, id)
                .set(NOVEL.NAME, id)
                .set(NOVEL.USERID, owner)
                .set(NOVEL.CREATEDAT, INITIAL)
                .set(NOVEL.UPDATEDAT, INITIAL)
                .execute();
        database.dsl().insertInto(OUTLINE)
                .set(OUTLINE.ID, id + "-outline")
                .set(OUTLINE.NOVELID, id)
                .set(OUTLINE.CONTENT, outlineContent)
                .set(OUTLINE.CREATEDAT, INITIAL)
                .set(OUTLINE.UPDATEDAT, INITIAL)
                .execute();
        return id;
    }

    private void chapter(String id, String novelId) {
        database.dsl().insertInto(CHAPTER)
                .set(CHAPTER.ID, id)
                .set(CHAPTER.NOVELID, novelId)
                .set(CHAPTER.TITLE, "第一章")
                .set(CHAPTER.CONTENT, "")
                .set(CHAPTER.ORDER, 1)
                .set(CHAPTER.STATUS, Chapterstatus.drafting)
                .set(CHAPTER.CREATEDAT, INITIAL)
                .set(CHAPTER.UPDATEDAT, INITIAL)
                .execute();
    }

    private static OutlineNodeData node(
            String title,
            String kind,
            String parentId,
            String linkedChapterId,
            Integer start,
            Integer end) {
        return new OutlineNodeData(
                title,
                "完整内容",
                kind,
                "planned",
                0,
                parentId,
                linkedChapterId,
                1000,
                null,
                start,
                end);
    }

    private static OutlineNodePatch patchTitle(String title) {
        return new OutlineNodePatch(
                new PatchField<>(true, title),
                absent(),
                absent(),
                absent(),
                absent(),
                absent(),
                absent(),
                absent(),
                absent(),
                absent(),
                absent());
    }

    private static <T> PatchField<T> absent() {
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
                + "@127.0.0.1:"
                + POSTGRES.getMappedPort(5432)
                + "/"
                + POSTGRES.getDatabaseName();
    }
}
