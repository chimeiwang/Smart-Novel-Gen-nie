package cn.inkforge.core.lore.infrastructure;

import static cn.inkforge.core.db.generated.Tables.CHAPTER;
import static cn.inkforge.core.db.generated.Tables.CHARACTEREXPERIENCE;
import static cn.inkforge.core.db.generated.Tables.GLOSSARY;
import static cn.inkforge.core.db.generated.Tables.ITEM;
import static cn.inkforge.core.db.generated.Tables.NOVEL;
import static cn.inkforge.core.db.generated.Tables.USER;
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import cn.inkforge.core.db.generated.enums.Chapterstatus;
import cn.inkforge.core.lore.domain.ContentKind;
import cn.inkforge.core.lore.domain.EntityMutation;
import cn.inkforge.core.lore.domain.ExperienceData;
import cn.inkforge.core.lore.domain.ExperienceMutation;
import cn.inkforge.core.lore.domain.ExperiencePatch;
import cn.inkforge.core.lore.domain.LoreEntityData;
import cn.inkforge.core.lore.domain.LoreEntityKind;
import cn.inkforge.core.lore.domain.LoreEntityPatch;
import cn.inkforge.core.lore.domain.MutationAction;
import cn.inkforge.core.lore.domain.RelationData;
import cn.inkforge.core.lore.domain.RelationPatch;
import cn.inkforge.core.lore.domain.WritingBiblePatch;
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
import java.time.temporal.ChronoUnit;
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
class JooqLoreRepositoryTest {

    private static final LocalDateTime INITIAL =
            LocalDateTime.parse("2026-08-24T10:00:00.000");
    private static final Clock CLOCK = Clock.fixed(
            Instant.parse("2026-08-25T02:00:00.123Z"), ZoneOffset.UTC);

    @Container
    private static final PostgreSQLContainer POSTGRES =
            new PostgreSQLContainer("pgvector/pgvector:0.8.0-pg14")
                    .withDatabaseName("inkforge_lore_test")
                    .withUsername("inkforge")
                    .withPassword("test-only-password");

    private static CoreDatabase database;
    private static JooqLoreRepository repository;
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
        repository = new JooqLoreRepository(
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
    void 五类实体保持确定性创建历史敏感重放CAS引用隔离和地点环门禁() {
        String owner = user("lore-owner-1");
        String novel = novel("lore-novel-1", owner);
        String otherNovel = novel("lore-other-1", owner);

        for (LoreEntityKind kind : LoreEntityKind.values()) {
            LoreEntityData initial = entityData(kind, "初始");
            String requestId = "lore-entity-request-" + kind.value();
            var created = repository.createEntity(
                    novel, owner, kind, requestId, initial);
            assertThat(created.entity().id()).isEqualTo(CommandResourceId.derive(
                    kind.value(), owner, novel, requestId));
            assertThat(created.effective()).isTrue();
            assertThat(repository.createEntity(novel, owner, kind, requestId, initial)
                            .effective())
                    .isFalse();
            assertCode(
                    () -> repository.createEntity(
                            novel, owner, kind, requestId, entityData(kind, "冲突")),
                    "RESOURCE_CREATE_CONFLICT");

            String changedField = kind == LoreEntityKind.GLOSSARY ? "term" : "name";
            var changed = repository.updateEntity(
                    novel,
                    owner,
                    kind,
                    created.entity().id(),
                    new LoreEntityPatch(Map.of(changedField, "变化")),
                    created.entity().updatedAt());
            assertThat(changed.updatedAt()).isAfter(created.entity().updatedAt());
            assertCode(
                    () -> repository.updateEntity(
                            novel,
                            owner,
                            kind,
                            created.entity().id(),
                            new LoreEntityPatch(Map.of(changedField, "陈旧")),
                            created.entity().updatedAt()),
                    "LORE_ENTITY_VERSION_CONFLICT");
            assertCode(
                    () -> repository.createEntity(novel, owner, kind, requestId, initial),
                    "RESOURCE_CREATE_CONFLICT");
            repository.deleteEntity(
                    novel, owner, kind, created.entity().id(), changed.updatedAt());
        }

        var foreignFaction = repository.createEntity(
                otherNovel,
                owner,
                LoreEntityKind.FACTIONS,
                "foreign-faction-request",
                new LoreEntityData(Map.of("name", "异界势力")));
        assertCode(
                () -> repository.createEntity(
                        novel,
                        owner,
                        LoreEntityKind.CHARACTERS,
                        "cross-character-request",
                        new LoreEntityData(Map.of(
                                "name", "越界角色",
                                "currentStatus", "active",
                                "factionId", foreignFaction.entity().id()))),
                "RELATED_RESOURCE_CROSS_NOVEL");

        var parent = repository.createEntity(
                novel, owner, LoreEntityKind.LOCATIONS, "location-parent-request",
                new LoreEntityData(Map.of("name", "父地点")));
        var child = repository.createEntity(
                novel, owner, LoreEntityKind.LOCATIONS, "location-child-request",
                new LoreEntityData(Map.of(
                        "name", "子地点", "parentId", parent.entity().id())));
        assertCode(
                () -> repository.updateEntity(
                        novel,
                        owner,
                        LoreEntityKind.LOCATIONS,
                        parent.entity().id(),
                        new LoreEntityPatch(Map.of("parentId", child.entity().id())),
                        parent.entity().updatedAt()),
                "LOCATION_CYCLE");
    }

    @Test
    void 经历和关系保持顺序分配确定性重放CAS跨小说边界与精确删除() {
        String owner = user("lore-owner-2");
        String novel = novel("lore-novel-2", owner);
        String otherNovel = novel("lore-other-2", owner);
        chapter("lore-chapter-1", novel);
        chapter("lore-chapter-other", otherNovel);
        var first = character(novel, owner, "甲", "character-a-request");
        var second = character(novel, owner, "乙", "character-b-request");
        var foreign = character(otherNovel, owner, "异界", "character-other-request");

        var experience = repository.createExperience(
                novel,
                owner,
                first.entity().id(),
                "experience-request-0001",
                new ExperienceData("lore-chapter-1", "完整经历", null));
        assertThat(experience.experience().order()).isZero();
        assertThat(repository.createExperience(
                        novel,
                        owner,
                        first.entity().id(),
                        "experience-request-0001",
                        new ExperienceData("lore-chapter-1", "完整经历", null))
                        .effective())
                .isFalse();
        assertCode(
                () -> repository.createExperience(
                        novel,
                        owner,
                        foreign.entity().id(),
                        "experience-cross-0001",
                        new ExperienceData(null, "越界", null)),
                "RELATED_RESOURCE_CROSS_NOVEL");
        var updatedExperience = repository.updateExperience(
                novel,
                owner,
                experience.experience().id(),
                new ExperiencePatch(absent(), new PatchField<>(true, "变化"), absent()),
                experience.experience().updatedAt());
        assertCode(
                () -> repository.updateExperience(
                        novel,
                        owner,
                        experience.experience().id(),
                        new ExperiencePatch(absent(), new PatchField<>(true, "陈旧"), absent()),
                        experience.experience().updatedAt()),
                "LORE_EXPERIENCE_VERSION_CONFLICT");

        RelationData relationData = new RelationData(
                first.entity().id(), second.entity().id(), "friend", 20,
                "旧识", null, null);
        var relation = repository.createRelation(
                novel, owner, "relation-request-00001", relationData);
        assertThat(repository.createRelation(
                        novel, owner, "relation-request-00001", relationData)
                        .effective())
                .isFalse();
        var relationChanged = repository.updateRelation(
                novel,
                owner,
                relation.relation().id(),
                new RelationPatch(
                        absent(), absent(), new PatchField<>(true, "反目"), absent(), absent()),
                relation.relation().updatedAt());
        repository.deleteRelation(
                novel, owner, relation.relation().id(), relationChanged.updatedAt());
        repository.deleteExperience(
                novel, owner, experience.experience().id(), updatedExperience.updatedAt());
        assertThat(repository.listRelations(novel, owner)).isEmpty();
        assertThat(repository.listExperiences(novel, owner, first.entity().id())).isEmpty();
    }

    @Test
    void 单例内容先校验版本再幂等并逐字保存且故事进展使用小说版本() {
        String owner = user("lore-owner-3");
        String novel = novel("lore-novel-3", owner);

        String fullText = "  第一行\r\n\r\n最后一行  ".repeat(10_000);
        var created = repository.saveContent(
                novel, owner, ContentKind.WORLD_SETTING, fullText, null);
        assertThat(created.content()).isEqualTo(fullText);
        assertThat(created.createdAt()).isEqualTo(created.updatedAt());
        assertCode(
                () -> repository.saveContent(
                        novel, owner, ContentKind.WORLD_SETTING, fullText, null),
                "LORE_CONTENT_VERSION_CONFLICT");
        assertThat(repository.saveContent(
                        novel,
                        owner,
                        ContentKind.WORLD_SETTING,
                        fullText,
                        created.updatedAt()))
                .isEqualTo(created);

        OffsetDateTime novelVersion = INITIAL.atOffset(ZoneOffset.UTC);
        var progress = repository.saveStoryProgress(
                novel, owner, "推进到第一章", novelVersion);
        assertThat(progress.updatedAt()).isAfter(novelVersion);
        assertCode(
                () -> repository.saveStoryProgress(
                        novel, owner, "陈旧覆盖", novelVersion),
                "LORE_CONTENT_VERSION_CONFLICT");

        Map<String, Object> bibleFields = new LinkedHashMap<>();
        bibleFields.put("genre", "仙侠");
        bibleFields.put("notes", null);
        var bible = repository.saveWritingBible(
                novel, owner, new WritingBiblePatch(bibleFields), null);
        assertThat(bible.storyLengthProfile()).isEqualTo("long_serial");
        assertThat(bible.genre()).isEqualTo("仙侠");
        assertThat(bible.notes()).isNull();
    }

    @Test
    void 设定实体批量命令共享一个事务并在后续CAS失败时完整回滚() {
        String owner = user("lore-owner-batch-1");
        String novel = novel("lore-novel-batch-1", owner);
        var target = repository.createEntity(
                novel,
                owner,
                LoreEntityKind.ITEMS,
                "batch-target-item-request",
                new LoreEntityData(Map.of("name", "旧物品")));
        String createRequestId = "batch-glossary-request";
        String createdId = CommandResourceId.derive(
                "glossary", owner, novel, createRequestId);

        assertCode(
                () -> repository.applyEntityMutations(
                        novel,
                        owner,
                        List.of(
                                new EntityMutation(
                                        MutationAction.CREATE,
                                        LoreEntityKind.GLOSSARY,
                                        Map.of("term", "批量术语", "definition", "不会落库"),
                                        null,
                                        createRequestId,
                                        null,
                                        null,
                                        null,
                                        "glossary"),
                                new EntityMutation(
                                        MutationAction.UPDATE,
                                        LoreEntityKind.ITEMS,
                                        Map.of("name", "陈旧覆盖"),
                                        target.entity().id(),
                                        null,
                                        target.entity().updatedAt().minus(1, ChronoUnit.SECONDS),
                                        null,
                                        null,
                                        "items"))),
                "LORE_ENTITY_VERSION_CONFLICT");

        assertThat(database.dsl().fetchExists(
                        GLOSSARY, GLOSSARY.ID.eq(createdId)))
                .isFalse();
        assertThat(database.dsl().select(ITEM.NAME)
                        .from(ITEM)
                        .where(ITEM.ID.eq(target.entity().id()))
                        .fetchSingle(ITEM.NAME))
                .isEqualTo("旧物品");
    }

    @Test
    void 经历批量命令原子回滚且命名重放先检查既有绑定() {
        String owner = user("lore-owner-batch-2");
        String novel = novel("lore-novel-batch-2", owner);
        var character = character(
                novel, owner, "甲", "batch-character-request");
        var target = repository.createExperience(
                novel,
                owner,
                character.entity().id(),
                "batch-target-experience",
                new ExperienceData(null, "旧经历", null));
        String requestId = "batch-new-experience";
        String createdId = CommandResourceId.derive(
                "experiences", owner, novel, requestId);

        assertCode(
                () -> repository.applyExperienceMutations(
                        novel,
                        owner,
                        List.of(
                                new ExperienceMutation(
                                        MutationAction.CREATE,
                                        Map.of("content", "不会落库"),
                                        null,
                                        character.entity().id(),
                                        null,
                                        requestId,
                                        null),
                                new ExperienceMutation(
                                        MutationAction.UPDATE,
                                        Map.of("content", "陈旧覆盖"),
                                        target.experience().id(),
                                        null,
                                        null,
                                        null,
                                        target.experience().updatedAt()
                                                .minus(1, ChronoUnit.SECONDS)))),
                "LORE_EXPERIENCE_VERSION_CONFLICT");
        assertThat(database.dsl().fetchExists(
                        CHARACTEREXPERIENCE,
                        CHARACTEREXPERIENCE.ID.eq(createdId)))
                .isFalse();

        var original = repository.createExperience(
                novel,
                owner,
                character.entity().id(),
                "named-experience-request",
                new ExperienceData(null, "绑定经历", 2));
        var replay = repository.applyExperienceMutations(
                novel,
                owner,
                List.of(new ExperienceMutation(
                        MutationAction.CREATE,
                        Map.of("content", "绑定经历", "order", 2),
                        null,
                        null,
                        "甲",
                        "named-experience-request",
                        null)));
        assertThat(replay.getFirst().effective()).isFalse();
        assertThat(replay.getFirst().experience()).isEqualTo(original.experience());

        assertCode(
                () -> repository.applyExperienceMutations(
                        novel,
                        owner,
                        List.of(new ExperienceMutation(
                                MutationAction.CREATE,
                                Map.of("content", "更换内容", "order", 2),
                                null,
                                null,
                                "不存在的角色",
                                "named-experience-request",
                                null))),
                "RESOURCE_CREATE_CONFLICT");
    }

    private static LoreEntityData entityData(LoreEntityKind kind, String value) {
        return switch (kind) {
            case CHARACTERS -> new LoreEntityData(Map.of(
                    "name", value + "角色", "currentStatus", "active"));
            case ITEMS -> new LoreEntityData(Map.of("name", value + "物品"));
            case LOCATIONS -> new LoreEntityData(Map.of("name", value + "地点"));
            case FACTIONS -> new LoreEntityData(Map.of("name", value + "势力"));
            case GLOSSARY -> new LoreEntityData(Map.of(
                    "term", value + "术语", "definition", "释义"));
        };
    }

    private cn.inkforge.core.lore.domain.LoreEntityMutationResult character(
            String novelId, String userId, String name, String requestId) {
        return repository.createEntity(
                novelId,
                userId,
                LoreEntityKind.CHARACTERS,
                requestId,
                new LoreEntityData(Map.of("name", name, "currentStatus", "active")));
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

    private String novel(String id, String owner) {
        database.dsl().insertInto(NOVEL)
                .set(NOVEL.ID, id)
                .set(NOVEL.NAME, id)
                .set(NOVEL.USERID, owner)
                .set(NOVEL.CREATEDAT, INITIAL)
                .set(NOVEL.UPDATEDAT, INITIAL)
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
                + POSTGRES.getUsername() + ":" + POSTGRES.getPassword()
                + "@127.0.0.1:" + POSTGRES.getMappedPort(5432)
                + "/" + POSTGRES.getDatabaseName();
    }
}
