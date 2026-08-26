package cn.inkforge.core.lore.infrastructure;

import static cn.inkforge.core.db.generated.Tables.STORYBACKGROUND;
import static cn.inkforge.core.db.generated.Tables.WORLDSETTING;
import static cn.inkforge.core.db.generated.Tables.WRITINGBIBLE;

import cn.inkforge.core.db.generated.enums.Storylengthprofile;
import cn.inkforge.core.db.generated.tables.records.NovelRecord;
import cn.inkforge.core.db.generated.tables.records.StorybackgroundRecord;
import cn.inkforge.core.db.generated.tables.records.WorldsettingRecord;
import cn.inkforge.core.db.generated.tables.records.WritingbibleRecord;
import cn.inkforge.core.lore.domain.ContentKind;
import cn.inkforge.core.lore.domain.ContentSnapshot;
import cn.inkforge.core.lore.domain.WritingBiblePatch;
import cn.inkforge.core.lore.domain.WritingBibleSnapshot;
import cn.inkforge.core.platform.db.CoreDatabase;
import cn.inkforge.core.platform.id.CuidV1Generator;
import cn.inkforge.core.platform.time.DatabaseTimestamp;
import java.time.Clock;
import java.time.LocalDateTime;
import java.time.OffsetDateTime;
import java.util.Map;
import java.util.Objects;
import org.jooq.DSLContext;
import org.jooq.impl.DSL;

/** 故事背景、世界设定、作品圣经和故事进展的单例事务仓储。 */
final class JooqLoreContentStore {

    private final CoreDatabase database;
    private final CuidV1Generator ids;
    private final Clock clock;

    JooqLoreContentStore(
            CoreDatabase database, CuidV1Generator ids, Clock clock) {
        this.database = database;
        this.ids = ids;
        this.clock = clock;
    }

    ContentSnapshot saveContent(
            String novelId,
            String userId,
            ContentKind kind,
            String content,
            OffsetDateTime expectedUpdatedAt) {
        return database.dsl().transactionResult(configuration -> {
            DSLContext transaction = DSL.using(configuration);
            LoreTransactionGuard.requireOwner(transaction, novelId, userId);
            LoreTransactionGuard.lockNovel(transaction, novelId, userId);
            return switch (kind) {
                case STORY_BACKGROUND -> saveStoryBackground(
                        transaction, novelId, content, expectedUpdatedAt);
                case WORLD_SETTING -> saveWorldSetting(
                        transaction, novelId, content, expectedUpdatedAt);
            };
        });
    }

    ContentSnapshot saveStoryProgress(
            String novelId,
            String userId,
            String content,
            OffsetDateTime expectedUpdatedAt) {
        return database.dsl().transactionResult(configuration -> {
            DSLContext transaction = DSL.using(configuration);
            LoreTransactionGuard.requireOwner(transaction, novelId, userId);
            NovelRecord novel = LoreTransactionGuard.lockNovel(
                    transaction, novelId, userId);
            LoreTransactionGuard.requireVersion(
                    novel.getUpdatedat(), expectedUpdatedAt,
                    "LORE_CONTENT_VERSION_CONFLICT");
            if (!Objects.equals(novel.getStoryprogress(), content)) {
                novel.setStoryprogress(content);
                novel.setUpdatedat(DatabaseTimestamp.next(clock, novel.getUpdatedat()));
                novel.store();
            }
            return new ContentSnapshot(
                    novel.getId(),
                    novel.getStoryprogress(),
                    DatabaseTimestamp.api(novel.getCreatedat()),
                    DatabaseTimestamp.api(novel.getUpdatedat()));
        });
    }

    WritingBibleSnapshot saveWritingBible(
            String novelId,
            String userId,
            WritingBiblePatch patch,
            OffsetDateTime expectedUpdatedAt) {
        return database.dsl().transactionResult(configuration -> {
            DSLContext transaction = DSL.using(configuration);
            LoreTransactionGuard.requireOwner(transaction, novelId, userId);
            LoreTransactionGuard.lockNovel(transaction, novelId, userId);
            WritingbibleRecord current = transaction.selectFrom(WRITINGBIBLE)
                    .where(WRITINGBIBLE.NOVELID.eq(novelId))
                    .forUpdate()
                    .fetchOne();
            LoreTransactionGuard.requireVersion(
                    current == null ? null : current.getUpdatedat(),
                    expectedUpdatedAt,
                    "LORE_CONTENT_VERSION_CONFLICT");
            if (current == null) {
                LocalDateTime now = DatabaseTimestamp.now(clock);
                current = transaction.insertInto(WRITINGBIBLE)
                        .set(WRITINGBIBLE.ID, ids.next())
                        .set(WRITINGBIBLE.NOVELID, novelId)
                        .set(WRITINGBIBLE.STORYLENGTHPROFILE,
                                Storylengthprofile.long_serial)
                        .set(WRITINGBIBLE.CREATEDAT, now)
                        .set(WRITINGBIBLE.UPDATEDAT, now)
                        .returning()
                        .fetchSingle();
                apply(current, patch.fields());
                current.store();
            } else if (changed(current, patch.fields())) {
                apply(current, patch.fields());
                current.setUpdatedat(DatabaseTimestamp.next(clock, current.getUpdatedat()));
                current.store();
            }
            return writingBible(current);
        });
    }

    private ContentSnapshot saveStoryBackground(
            DSLContext transaction,
            String novelId,
            String content,
            OffsetDateTime expectedUpdatedAt) {
        StorybackgroundRecord current = transaction.selectFrom(STORYBACKGROUND)
                .where(STORYBACKGROUND.NOVELID.eq(novelId))
                .forUpdate()
                .fetchOne();
        LoreTransactionGuard.requireVersion(
                current == null ? null : current.getUpdatedat(),
                expectedUpdatedAt,
                "LORE_CONTENT_VERSION_CONFLICT");
        if (current == null) {
            LocalDateTime now = DatabaseTimestamp.now(clock);
            current = transaction.insertInto(STORYBACKGROUND)
                    .set(STORYBACKGROUND.ID, ids.next())
                    .set(STORYBACKGROUND.NOVELID, novelId)
                    .set(STORYBACKGROUND.CONTENT, content)
                    .set(STORYBACKGROUND.CREATEDAT, now)
                    .set(STORYBACKGROUND.UPDATEDAT, now)
                    .returning()
                    .fetchSingle();
        } else if (!current.getContent().equals(content)) {
            current.setContent(content);
            current.setUpdatedat(DatabaseTimestamp.next(clock, current.getUpdatedat()));
            current.store();
        }
        return content(
                current.getId(), current.getContent(),
                current.getCreatedat(), current.getUpdatedat());
    }

    private ContentSnapshot saveWorldSetting(
            DSLContext transaction,
            String novelId,
            String content,
            OffsetDateTime expectedUpdatedAt) {
        WorldsettingRecord current = transaction.selectFrom(WORLDSETTING)
                .where(WORLDSETTING.NOVELID.eq(novelId))
                .forUpdate()
                .fetchOne();
        LoreTransactionGuard.requireVersion(
                current == null ? null : current.getUpdatedat(),
                expectedUpdatedAt,
                "LORE_CONTENT_VERSION_CONFLICT");
        if (current == null) {
            LocalDateTime now = DatabaseTimestamp.now(clock);
            current = transaction.insertInto(WORLDSETTING)
                    .set(WORLDSETTING.ID, ids.next())
                    .set(WORLDSETTING.NOVELID, novelId)
                    .set(WORLDSETTING.CONTENT, content)
                    .set(WORLDSETTING.CREATEDAT, now)
                    .set(WORLDSETTING.UPDATEDAT, now)
                    .returning()
                    .fetchSingle();
        } else if (!current.getContent().equals(content)) {
            current.setContent(content);
            current.setUpdatedat(DatabaseTimestamp.next(clock, current.getUpdatedat()));
            current.store();
        }
        return content(
                current.getId(), current.getContent(),
                current.getCreatedat(), current.getUpdatedat());
    }

    private static ContentSnapshot content(
            String id,
            String value,
            LocalDateTime createdAt,
            LocalDateTime updatedAt) {
        return new ContentSnapshot(
                id,
                value,
                DatabaseTimestamp.api(createdAt),
                DatabaseTimestamp.api(updatedAt));
    }

    private static boolean changed(
            WritingbibleRecord current, Map<String, Object> fields) {
        return fields.entrySet().stream().anyMatch(entry ->
                !Objects.equals(field(current, entry.getKey()), entry.getValue()));
    }

    private static Object field(WritingbibleRecord current, String name) {
        return switch (name) {
            case "storyLengthProfile" -> current.getStorylengthprofile().getLiteral();
            case "targetTotalWordCount" -> current.getTargettotalwordcount();
            case "genre" -> current.getGenre();
            case "targetReaders" -> current.getTargetreaders();
            case "coreSellingPoint" -> current.getCoresellingpoint();
            case "readerPromise" -> current.getReaderpromise();
            case "appealModel" -> current.getAppealmodel();
            case "taboo" -> current.getTaboo();
            case "comparableTitles" -> current.getComparabletitles();
            case "notes" -> current.getNotes();
            default -> throw new IllegalArgumentException("未知作品圣经字段：" + name);
        };
    }

    private static void apply(
            WritingbibleRecord current, Map<String, Object> fields) {
        for (Map.Entry<String, Object> entry : fields.entrySet()) {
            switch (entry.getKey()) {
                case "storyLengthProfile" -> current.setStorylengthprofile(
                        Storylengthprofile.lookupLiteral((String) entry.getValue()));
                case "targetTotalWordCount" -> current.setTargettotalwordcount(
                        (Integer) entry.getValue());
                case "genre" -> current.setGenre((String) entry.getValue());
                case "targetReaders" -> current.setTargetreaders((String) entry.getValue());
                case "coreSellingPoint" -> current.setCoresellingpoint(
                        (String) entry.getValue());
                case "readerPromise" -> current.setReaderpromise(
                        (String) entry.getValue());
                case "appealModel" -> current.setAppealmodel((String) entry.getValue());
                case "taboo" -> current.setTaboo((String) entry.getValue());
                case "comparableTitles" -> current.setComparabletitles(
                        (String) entry.getValue());
                case "notes" -> current.setNotes((String) entry.getValue());
                default -> throw new IllegalArgumentException(
                        "未知作品圣经字段：" + entry.getKey());
            }
        }
    }

    private static WritingBibleSnapshot writingBible(WritingbibleRecord value) {
        return new WritingBibleSnapshot(
                value.getId(),
                value.getStorylengthprofile().getLiteral(),
                value.getTargettotalwordcount(),
                value.getGenre(),
                value.getTargetreaders(),
                value.getCoresellingpoint(),
                value.getReaderpromise(),
                value.getAppealmodel(),
                value.getTaboo(),
                value.getComparabletitles(),
                value.getNotes(),
                DatabaseTimestamp.api(value.getCreatedat()),
                DatabaseTimestamp.api(value.getUpdatedat()));
    }
}
