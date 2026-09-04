package cn.inkforge.core.reviews.infrastructure;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import cn.inkforge.core.chapters.domain.TextLength;
import cn.inkforge.core.platform.db.CoreDatabase;
import cn.inkforge.core.platform.db.PostgresConnectionSettings;
import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.reviews.application.ChapterWritingEvidenceReader;
import cn.inkforge.core.workflows.protocol.ExecutionCanonicalJson;
import java.time.LocalDateTime;
import java.util.UUID;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.postgresql.PostgreSQLContainer;
import org.testcontainers.utility.MountableFile;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.json.JsonMapper;

@Testcontainers
class JooqChapterWritingEvidenceReaderTest {
    private static final LocalDateTime NOW = LocalDateTime.parse("2026-09-04T12:00:00");
    private static final JsonMapper JSON = JsonMapper.builder().build();
    @Container
    private static final PostgreSQLContainer POSTGRES = new PostgreSQLContainer("pgvector/pgvector:0.8.0-pg14")
            .withDatabaseName("chapter_writing_evidence")
            .withUsername("inkforge").withPassword("test-only-password");
    private static CoreDatabase database;
    private static ChapterWritingEvidenceReader reader;

    @BeforeAll
    static void schema() throws Exception {
        POSTGRES.copyFileToContainer(MountableFile.forClasspathResource("db/novelwriterdev-schema.sql"), "/tmp/schema.sql");
        var result = POSTGRES.execInContainer("psql", "-v", "ON_ERROR_STOP=1", "-U", POSTGRES.getUsername(),
                "-d", POSTGRES.getDatabaseName(), "-f", "/tmp/schema.sql");
        assertThat(result.getExitCode()).as(result.getStderr()).isZero();
        database = CoreDatabase.connect(PostgresConnectionSettings.parse("postgresql://" + POSTGRES.getUsername()
                + ":" + POSTGRES.getPassword() + "@" + POSTGRES.getHost() + ":" + POSTGRES.getMappedPort(5432)
                + "/" + POSTGRES.getDatabaseName()));
        reader = new JooqChapterWritingEvidenceReader(JSON);
    }

    @AfterAll
    static void close() { if (database != null) database.close(); }

    @Test
    void 冻结完整目标章和已选文风且相邻章仅按稳定顺序投影摘要() {
        String novel = fixture();
        String body = "林澈😀\u0085\uFEFF\u001c" + "完整正文".repeat(6000) + "尾部不可截断";
        database.dsl().execute("UPDATE public.\"Chapter\" SET content = ? WHERE id = ?", body, novel + "-c2");
        chapter(novel, "c0", 1, "较远章节不进入");
        chapter(novel, "c1", 10, "甲😀\u0085\uFEFF\u001c");
        chapter(novel, "c3", 10, "下一章正文不进入");
        chapter(novel, "c4", 20, "更远下一章不进入");
        style(novel, "style", "文风画像".repeat(6000) + "完整画像尾部");
        database.dsl().execute("UPDATE public.\"Novel\" SET \"appliedStyleId\" = ? WHERE id = ?", novel + "-style", novel);
        database.dsl().execute("""
                INSERT INTO public."StyleReference" (id,"styleId",filename,filepath)
                VALUES (?, ?, '上传原文不进入', '/private/上传路径不进入')
                """, novel + "-reference", novel + "-style");
        database.dsl().execute("""
                INSERT INTO public."Character" (id,"novelId",name,identity,"updatedAt")
                VALUES (?, ?, '林澈', '正文提及人物完整设定', ?), (?, ?, '远方人物', '无关人物不进入', ?)
                """, novel + "-character", novel, NOW, novel + "-unrelated", novel, NOW);
        var snapshot = capture(novel);
        JsonNode context = JSON.valueToTree(snapshot.context());
        assertThat(context.at("/currentChapter/content").textValue()).isEqualTo(body);
        assertThat(context.at("/currentChapter/wordCount").intValue()).isEqualTo(TextLength.count(body));
        assertThat(context.at("/adjacentChapters/previous/id").textValue()).isEqualTo(novel + "-c1");
        assertThat(context.at("/adjacentChapters/previous/wordCount").intValue()).isEqualTo(3);
        assertThat(context.at("/adjacentChapters/next/id").textValue()).isEqualTo(novel + "-c3");
        assertThat(context.at("/appliedStyle/available").booleanValue()).isTrue();
        assertThat(context.at("/appliedStyle/profile/portraitMarkdown").textValue()).endsWith("完整画像尾部");
        assertThat(context.at("/novelContext/summary").textValue()).isEqualTo("完整作品简介");
        assertThat(context.at("/novelContext/storyProgress").textValue()).isEqualTo("完整故事进展");
        assertThat(context.at("/writingBible/taboo").textValue()).isEqualTo("作者禁止事项");
        assertThat(context.at("/relatedLore/characters")).hasSize(1);
        assertThat(context.toString()).contains("正文提及人物完整设定")
                .doesNotContain("下一章正文不进入", "较远章节不进入", "更远下一章不进入", "上传路径不进入", "无关人物不进入", "styleMode");
        assertThat(snapshot.chapterUpdatedAt().toString()).isEqualTo("2026-09-04T12:00Z");
        for (JsonNode binding : context.path("sourceBindings")) {
            if (binding.path("exists").booleanValue()) {
                assertThat(binding.path("updatedAt").isTextual()).isTrue();
                assertThat(binding.path("contentSha256").textValue()).matches("[0-9a-f]{64}");
            }
        }
        assertThat(hash(novel)).isEqualTo(ExecutionCanonicalJson.sha256(snapshot.context()));
        assertThatThrownBy(() -> snapshot.context().put("currentChapter", null)).isInstanceOf(UnsupportedOperationException.class);
    }

    @Test
    void 空正文是存在来源且未选择未生成画像和缺相邻章节各自显式表达() {
        String novel = fixture();
        JsonNode empty = JSON.valueToTree(capture(novel).context());
        assertThat(empty.at("/currentChapter/content").textValue()).isEmpty();
        assertThat(binding(empty, "chapter_content").path("exists").booleanValue()).isTrue();
        assertThat(empty.at("/adjacentChapters/previous").isNull()).isTrue();
        assertThat(empty.at("/adjacentChapters/next").isNull()).isTrue();
        assertThat(binding(empty, "previous_chapter").path("exists").booleanValue()).isFalse();
        assertThat(binding(empty, "next_chapter").at("/absenceSentinel/resourceId").textValue()).isEqualTo(novel + "-c2");
        assertThat(empty.at("/appliedStyle/selectedStyleId").isNull()).isTrue();
        assertThat(empty.at("/appliedStyle/available").booleanValue()).isFalse();
        style(novel, "unready", null);
        database.dsl().execute("UPDATE public.\"Novel\" SET \"appliedStyleId\" = ? WHERE id = ?", novel + "-unready", novel);
        JsonNode unready = JSON.valueToTree(capture(novel).context());
        assertThat(unready.at("/appliedStyle/selectedStyleId").textValue()).isEqualTo(novel + "-unready");
        assertThat(unready.at("/appliedStyle/available").booleanValue()).isFalse();
        assertThat(unready.at("/appliedStyle/profile/portraitMarkdown").isNull()).isTrue();
        assertThat(binding(unready, "writing_style").path("exists").booleanValue()).isTrue();
        assertThat(unready).isNotEqualTo(empty);
    }

    @Test
    void 同时间戳正文文风变化和相邻新增重排删除均改变来源哈希() {
        String novel = fixture();
        String before = hash(novel);
        database.dsl().execute("UPDATE public.\"Chapter\" SET content = '同时间戳新正文' WHERE id = ?", novel + "-c2");
        String changed = hash(novel);
        assertThat(changed).isNotEqualTo(before);
        chapter(novel, "c1", 9, "前章正文");
        assertThat(hash(novel)).isNotEqualTo(changed);
        changed = hash(novel);
        database.dsl().execute("UPDATE public.\"Chapter\" SET \"order\" = 11 WHERE id = ?", novel + "-c1");
        assertThat(hash(novel)).isNotEqualTo(changed);
        changed = hash(novel);
        database.dsl().execute("DELETE FROM public.\"Chapter\" WHERE id = ?", novel + "-c1");
        assertThat(hash(novel)).isNotEqualTo(changed);
        style(novel, "first", "初始画像");
        style(novel, "second", "第二画像");
        database.dsl().execute("UPDATE public.\"Novel\" SET \"appliedStyleId\" = ? WHERE id = ?", novel + "-first", novel);
        changed = hash(novel);
        database.dsl().execute("UPDATE public.\"WritingStyle\" SET \"portraitMarkdown\" = '同时间戳画像变化' WHERE id = ?", novel + "-first");
        assertThat(hash(novel)).isNotEqualTo(changed);
        changed = hash(novel);
        database.dsl().execute("UPDATE public.\"Novel\" SET \"appliedStyleId\" = ? WHERE id = ?", novel + "-second", novel);
        assertThat(hash(novel)).isNotEqualTo(changed);
    }

    @Test
    void 不允许将其他作者文风或其他小说章节作为本次来源() {
        String novel = fixture();
        String foreign = fixture();
        style(foreign, "private", "其他作者私有画像");
        database.dsl().execute("UPDATE public.\"Novel\" SET \"appliedStyleId\" = ? WHERE id = ?", foreign + "-private", novel);
        assertThatThrownBy(() -> capture(novel)).isInstanceOfSatisfying(ApiException.class,
                error -> assertThat(error.code()).isEqualTo("CHAPTER_WRITING_STYLE_SOURCE_MISMATCH"));
        assertThatThrownBy(() -> database.transactionResult(tx -> reader.capture(tx, novel, foreign + "-c2", "请写正文")))
                .isInstanceOfSatisfying(ApiException.class, error -> assertThat(error.code()).isEqualTo("CHAPTER_NOT_FOUND"));
    }

    @Test
    void 写作额外相关性不会改变章节规划默认入口的快照或哈希() {
        String novel = fixture();
        database.dsl().execute("UPDATE public.\"Chapter\" SET content = '林澈进入城门' WHERE id = ?", novel + "-c2");
        database.dsl().execute("INSERT INTO public.\"Character\" (id,\"novelId\",name,\"updatedAt\") VALUES (?, ?, '林澈', ?)", novel + "-character", novel, NOW);
        var plan = new JooqChapterPlanEvidenceReader(JSON);
        var before = database.transactionResult(tx -> plan.capture(tx, novel, novel + "-c2", "请规划"));
        assertThat(JSON.valueToTree(before.context()).at("/relatedLore/characters")).isEmpty();
        assertThat(JSON.valueToTree(capture(novel).context()).at("/relatedLore/characters")).hasSize(1);
        var explicit = database.transactionResult(tx -> plan.capture(tx, novel, novel + "-c2", "请规划", ""));
        assertThat(explicit.context()).isEqualTo(before.context());
        assertThat(ExecutionCanonicalJson.sha256(explicit.context())).isEqualTo(ExecutionCanonicalJson.sha256(before.context()));
    }

    private static JsonNode binding(JsonNode context, String type) {
        for (JsonNode binding : context.path("sourceBindings")) {
            if (type.equals(binding.path("resourceType").textValue())) return binding;
        }
        throw new AssertionError("缺少来源绑定：" + type);
    }

    private static ChapterWritingEvidenceReader.Snapshot capture(String novel) {
        return database.transactionResult(tx -> reader.capture(tx, novel, novel + "-c2", "请写正文"));
    }

    private static String hash(String novel) { return ExecutionCanonicalJson.sha256(capture(novel).context()); }

    private static String fixture() {
        String id = "draft-" + UUID.randomUUID();
        database.dsl().execute("INSERT INTO public.\"User\" (id,username,\"passwordHash\",\"updatedAt\") VALUES (?, ?, 'test', ?)", id, id, NOW);
        database.dsl().execute("INSERT INTO public.\"Novel\" (id,name,summary,\"storyProgress\",\"userId\",\"updatedAt\") VALUES (?, '写章作品', '完整作品简介', '完整故事进展', ?, ?)", id, id, NOW);
        database.dsl().execute("INSERT INTO public.\"WritingBible\" (id,\"novelId\",taboo,\"storyLengthProfile\",\"updatedAt\") VALUES (?, ?, '作者禁止事项', 'long_serial', ?)", id + "-bible", id, NOW);
        chapter(id, "c2", 10, "");
        return id;
    }

    private static void chapter(String novel, String suffix, int order, String content) {
        database.dsl().execute("INSERT INTO public.\"Chapter\" (id,\"novelId\",title,content,\"order\",\"updatedAt\") VALUES (?, ?, '章节标题', ?, ?, ?)", novel + "-" + suffix, novel, content, order, NOW);
    }

    private static void style(String novel, String suffix, String portrait) {
        database.dsl().execute("INSERT INTO public.\"WritingStyle\" (id,\"userId\",name,\"portraitMarkdown\",\"updatedAt\") VALUES (?, ?, '作者文风', ?, ?)", novel + "-" + suffix, novel, portrait, NOW);
    }
}
