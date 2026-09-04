package cn.inkforge.core.reviews.infrastructure;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import cn.inkforge.core.platform.db.CoreDatabase;
import cn.inkforge.core.platform.db.PostgresConnectionSettings;
import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.reviews.application.ChapterPlanEvidenceReader;
import cn.inkforge.core.workflows.protocol.ExecutionCanonicalJson;
import java.time.LocalDateTime;
import java.util.Map;
import java.util.UUID;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.postgresql.PostgreSQLContainer;
import org.testcontainers.utility.MountableFile;
import tools.jackson.databind.json.JsonMapper;

@Testcontainers
class JooqChapterPlanEvidenceReaderTest {

    private static final LocalDateTime NOW = LocalDateTime.parse("2026-09-04T12:00:00");
    private static final JsonMapper JSON = JsonMapper.builder().build();
    @Container
    private static final PostgreSQLContainer POSTGRES = new PostgreSQLContainer("pgvector/pgvector:0.8.0-pg14")
            .withDatabaseName("chapter_plan_evidence")
            .withUsername("inkforge").withPassword("test-only-password");
    private static CoreDatabase database;
    private static ChapterPlanEvidenceReader reader;

    @BeforeAll
    static void schema() throws Exception {
        POSTGRES.copyFileToContainer(MountableFile.forClasspathResource("db/novelwriterdev-schema.sql"), "/tmp/schema.sql");
        var result = POSTGRES.execInContainer("psql", "-v", "ON_ERROR_STOP=1", "-U", POSTGRES.getUsername(),
                "-d", POSTGRES.getDatabaseName(), "-f", "/tmp/schema.sql");
        assertThat(result.getExitCode()).as(result.getStderr()).isZero();
        database = CoreDatabase.connect(PostgresConnectionSettings.parse("postgresql://" + POSTGRES.getUsername()
                + ":" + POSTGRES.getPassword() + "@" + POSTGRES.getHost() + ":" + POSTGRES.getMappedPort(5432)
                + "/" + POSTGRES.getDatabaseName()));
        reader = new JooqChapterPlanEvidenceReader(JSON);
    }

    @AfterAll
    static void close() { if (database != null) database.close(); }

    @Test
    void 最小投影保留完整目标大纲路径剧情相关设定伏笔而不读取整部正文() {
        String novel = fixture();
        String chapter = novel + "-chapter";
        database.dsl().execute("""
                INSERT INTO public."ChapterWritingGoal" (id,"novelId","chapterId","narrativeGoal", "requiredCharacters", "requiredForeshadowing", "updatedAt")
                VALUES (?, ?, ?, '让林澈发现旧钥匙，限期三日', '林澈', '旧钥匙', ?)
                """, novel + "-goal", novel, chapter, NOW);
        node(novel, "stage", "stage", null, null, null, "主阶段完整正文：三日之内");
        node(novel, "unit", "plot_unit", "stage", null, null, "剧情单元完整正文：林澈进入旧城");
        node(novel, "group", "chapter_group", "unit", 1, 3, "当前章节组完整正文：旧钥匙打开西门");
        node(novel, "unrelated-group", "chapter_group", null, 8, 9, "不相关章节组正文");
        database.dsl().execute("""
                INSERT INTO public."PlotProgress" (id,"novelId","currentStage","currentGoal","updatedAt")
                VALUES (?, ?, '第二天清晨', '找出西门入口', ?)
                """, novel + "-plot", novel, NOW);
        database.dsl().execute("""
                INSERT INTO public."Character" (id,"novelId",name,identity,"updatedAt")
                VALUES (?, ?, '林澈', '受伤的信使：伤势不可忽略', ?), (?, ?, '远方路人', '不相关人物完整设定', ?)
                """, novel + "-character", novel, NOW, novel + "-unrelated-character", novel, NOW);
        database.dsl().execute("""
                INSERT INTO public."Foreshadowing" (id,"novelId",name,"plantedContent","updatedAt")
                VALUES (?, ?, '旧钥匙', '钥匙有三道刻痕', ?), (?, ?, '遥远谜题', '不相关伏笔', ?)
                """, novel + "-foreshadowing", novel, NOW, novel + "-unrelated-foreshadowing", novel, NOW);

        var snapshot = capture(novel);
        var context = JSON.valueToTree(snapshot.context());
        assertThat(context.at("/chapterGoal/narrativeGoal").textValue()).contains("限期三日");
        assertThat(context.at("/outline/content").textValue()).isEqualTo("完整总纲😀不可截断尾部");
        assertThat(context.path("outlinePath").findValues("content"))
                .extracting(tools.jackson.databind.JsonNode::textValue)
                .containsExactly("主阶段完整正文：三日之内", "剧情单元完整正文：林澈进入旧城", "当前章节组完整正文：旧钥匙打开西门");
        assertThat(context.at("/plotProgress/currentStage").textValue()).isEqualTo("第二天清晨");
        assertThat(context.at("/relatedLore/characters")).hasSize(1);
        assertThat(context.path("foreshadowing")).hasSize(1);
        assertThat(context.toString()).contains("伤势不可忽略", "钥匙有三道刻痕")
                .doesNotContain("不相关人物", "不相关伏笔", "不相关章节组正文", "正文不应进入章节规划提示", "workspace");
        assertThat(snapshot.chapterUpdatedAt().toString()).isEqualTo("2026-09-04T12:00Z");
        assertThat(ExecutionCanonicalJson.sha256(capture(novel).context()))
                .isEqualTo(ExecutionCanonicalJson.sha256(snapshot.context()));
        assertThatThrownBy(() -> snapshot.context().put("novelId", "其他作品"))
                .isInstanceOf(UnsupportedOperationException.class);
    }

    @Test
    void 缺失来源显式绑定父域且后来出现或原值变化均改变完整证据哈希() {
        String novel = fixture();
        var original = JSON.valueToTree(capture(novel).context());
        assertThat(original.path("chapterGoal").isNull()).isTrue();
        assertThat(original.path("approvedBeatPlan").isNull()).isTrue();
        assertThat(original.path("sourceBindings").findValues("exists"))
                .anySatisfy(value -> assertThat(value.booleanValue()).isFalse());
        assertThat(original.path("sourceBindings").findValues("absenceSentinel"))
                .anySatisfy(value -> assertThat(value.path("resourceId").asText("")).isEqualTo(novel + "-chapter"));
        String before = ExecutionCanonicalJson.sha256(capture(novel).context());
        database.dsl().execute("""
                INSERT INTO public."ChapterWritingGoal" (id,"novelId","chapterId","narrativeGoal","updatedAt")
                VALUES (?, ?, ?, '新出现的章节目标', ?)
                """, novel + "-goal", novel, novel + "-chapter", NOW);
        String added = ExecutionCanonicalJson.sha256(capture(novel).context());
        assertThat(added).isNotEqualTo(before);
        database.dsl().execute("UPDATE public.\"ChapterWritingGoal\" SET \"narrativeGoal\" = '同一时间戳的目标变化' WHERE id = ?", novel + "-goal");
        assertThat(ExecutionCanonicalJson.sha256(capture(novel).context())).isNotEqualTo(added);
    }

    @Test
    void 大纲父级跨作品循环或章节映射不唯一均拒绝而不丢弃来源() {
        String novel = fixture();
        node(novel, "group", "chapter_group", null, 1, 2, "当前组");
        database.dsl().execute("UPDATE public.\"OutlineNode\" SET \"parentId\" = id WHERE id = ?", novel + "-group");
        assertThatThrownBy(() -> capture(novel)).isInstanceOfSatisfying(ApiException.class,
                error -> assertThat(error.code()).isEqualTo("OUTLINE_PARENT_CYCLE"));
        database.dsl().execute("UPDATE public.\"OutlineNode\" SET \"parentId\" = NULL WHERE id = ?", novel + "-group");
        node(novel, "other", "chapter_group", null, 1, 1, "重叠组");
        assertThatThrownBy(() -> capture(novel)).isInstanceOfSatisfying(ApiException.class,
                error -> assertThat(error.code()).isEqualTo("CHAPTER_GROUP_MAPPING_CONFLICT"));
        database.dsl().execute("DELETE FROM public.\"OutlineNode\" WHERE id = ?", novel + "-other");
        String foreignNovel = fixture();
        node(foreignNovel, "foreign-stage", "stage", null, null, null, "其他作品私有大纲");
        database.dsl().execute("UPDATE public.\"OutlineNode\" SET \"parentId\" = ? WHERE id = ?",
                foreignNovel + "-foreign-stage", novel + "-group");
        assertThatThrownBy(() -> capture(novel)).isInstanceOfSatisfying(ApiException.class,
                error -> assertThat(error.code()).isEqualTo("OUTLINE_PARENT_MISSING"));
    }

    @Test
    void 已批准计划包含全部有序节拍而多个批准计划明确冲突() {
        String novel = fixture();
        plan(novel, "first");
        database.dsl().execute("""
                INSERT INTO public."SceneBeat" (id,"beatPlanId","order",goal,"characters","acceptanceCriteria")
                VALUES (?, ?, 2, '第二拍完整内容', '林澈', '完成第二拍'), (?, ?, 1, '第一拍完整内容', '林澈', '完成第一拍')
                """, novel + "-beat2", novel + "-first", novel + "-beat1", novel + "-first");
        var context = JSON.valueToTree(capture(novel).context());
        assertThat(context.at("/approvedBeatPlan/sceneBeats").findValues("goal"))
                .extracting(tools.jackson.databind.JsonNode::textValue).containsExactly("第一拍完整内容", "第二拍完整内容");
        String before = ExecutionCanonicalJson.sha256(capture(novel).context());
        database.dsl().execute("UPDATE public.\"SceneBeat\" SET goal = '第一拍已被修改' WHERE id = ?", novel + "-beat1");
        assertThat(ExecutionCanonicalJson.sha256(capture(novel).context())).isNotEqualTo(before);
        plan(novel, "second");
        assertThatThrownBy(() -> capture(novel)).isInstanceOfSatisfying(ApiException.class,
                error -> assertThat(error.code()).isEqualTo("BEAT_PLAN_SOURCE_AMBIGUOUS"));
    }

    private static ChapterPlanEvidenceReader.Snapshot capture(String novel) {
        return database.transactionResult(tx -> reader.capture(tx, novel, novel + "-chapter", "请规划当前章节"));
    }

    private static String fixture() {
        String id = "plan-" + UUID.randomUUID();
        database.dsl().execute("INSERT INTO public.\"User\" (id,username,\"passwordHash\",\"updatedAt\") VALUES (?, ?, 'test', ?)", id, id, NOW);
        database.dsl().execute("INSERT INTO public.\"Novel\" (id,name,\"userId\",\"updatedAt\") VALUES (?, '章节规划作品', ?, ?)", id, id, NOW);
        database.dsl().execute("INSERT INTO public.\"WritingBible\" (id,\"novelId\",\"storyLengthProfile\",\"updatedAt\") VALUES (?, ?, 'long_serial', ?)", id + "-bible", id, NOW);
        database.dsl().execute("INSERT INTO public.\"Chapter\" (id,\"novelId\",title,content,\"order\",\"updatedAt\") VALUES (?, ?, '当前章', '正文不应进入章节规划提示', 1, ?)", id + "-chapter", id, NOW);
        database.dsl().execute("INSERT INTO public.\"Outline\" (id,\"novelId\",content,\"updatedAt\") VALUES (?, ?, '完整总纲😀不可截断尾部', ?)", id + "-outline", id, NOW);
        return id;
    }

    private static void node(String novel, String suffix, String kind, String parent, Integer start, Integer end, String content) {
        database.dsl().execute("""
                INSERT INTO public."OutlineNode" (id,"novelId",kind,title,"parentId","order","chapterStartOrder","chapterEndOrder",content,"updatedAt")
                VALUES (?, ?, ?::"OutlineNodeKind", ?, ?, 1, ?, ?, ?, ?)
                """, novel + "-" + suffix, novel, kind, suffix, parent == null ? null : novel + "-" + parent, start, end, content, NOW);
    }

    private static void plan(String novel, String suffix) {
        database.dsl().execute("""
                INSERT INTO public."ChapterBeatPlan" (id,"chapterId",status,"chapterGoal","updatedAt")
                VALUES (?, ?, 'approved', '原批准计划', ?)
                """, novel + "-" + suffix, novel + "-chapter", NOW);
    }
}
