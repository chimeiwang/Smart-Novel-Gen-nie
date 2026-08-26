package cn.inkforge.core.writing.infrastructure;

import static cn.inkforge.core.db.generated.Tables.CHAPTER;
import static cn.inkforge.core.db.generated.Tables.NOVEL;
import static cn.inkforge.core.db.generated.Tables.WRITINGMESSAGE;
import static cn.inkforge.core.db.generated.Tables.WRITINGSESSION;
import static cn.inkforge.core.db.generated.Tables.WRITINGTASK;
import static org.jooq.impl.DSL.count;
import static org.jooq.impl.DSL.rowNumber;

import cn.inkforge.contracts.api.CreateMessageRequest;
import cn.inkforge.contracts.api.CreateWritingSessionRequest;
import cn.inkforge.contracts.api.LastMessageResponse;
import cn.inkforge.contracts.api.MessageResponse;
import cn.inkforge.contracts.api.UpdateWritingSessionRequest;
import cn.inkforge.contracts.api.WritingSessionDetail;
import cn.inkforge.contracts.api.WritingSessionListItem;
import cn.inkforge.contracts.api.WritingSessionResponse;
import cn.inkforge.core.db.generated.tables.records.WritingmessageRecord;
import cn.inkforge.core.db.generated.tables.records.WritingsessionRecord;
import cn.inkforge.core.db.generated.tables.records.WritingtaskRecord;
import cn.inkforge.core.platform.db.CoreDatabase;
import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.platform.id.CuidV1Generator;
import cn.inkforge.core.platform.time.DatabaseTimestamp;
import cn.inkforge.core.writing.application.WritingSessionRepository;
import cn.inkforge.core.writing.domain.WritingRecovery;
import java.time.Clock;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import org.jooq.DSLContext;
import org.jooq.Field;
import org.jooq.Record;
import org.jooq.Table;
import org.openapitools.jackson.nullable.JsonNullable;
import tools.jackson.core.type.TypeReference;
import tools.jackson.databind.ObjectMapper;

/** 写作会话与消息的 PostgreSQL 实现；列表聚合始终使用固定数量查询。 */
final class JooqWritingSessionRepository implements WritingSessionRepository {

    private final CoreDatabase database;
    private final CuidV1Generator ids;
    private final Clock clock;
    private final ObjectMapper json;

    JooqWritingSessionRepository(
            CoreDatabase database,
            CuidV1Generator ids,
            Clock clock,
            ObjectMapper json) {
        this.database = Objects.requireNonNull(database);
        this.ids = Objects.requireNonNull(ids);
        this.clock = Objects.requireNonNull(clock);
        this.json = Objects.requireNonNull(json);
    }

    @Override
    public WritingSessionResponse create(
            String userId, CreateWritingSessionRequest request) {
        return database.transactionResult(transaction -> {
            requireChapter(
                    transaction, userId, request.getNovelId(), request.getChapterId());
            LocalDateTime now = DatabaseTimestamp.now(clock);
            WritingsessionRecord session = transaction.newRecord(WRITINGSESSION);
            session.setId(ids.next());
            session.setNovelid(request.getNovelId());
            session.setChapterid(request.getChapterId());
            session.setTitle(nullable(request.getTitle()));
            session.setPhase("idle");
            session.setCreatedat(now);
            session.setUpdatedat(now);
            session.insert();
            return response(session);
        });
    }

    @Override
    public List<WritingSessionListItem> list(
            String userId, String novelId, String chapterId) {
        DSLContext context = database.dsl();
        requireNovel(context, userId, novelId);
        var query = context.selectFrom(WRITINGSESSION)
                .where(WRITINGSESSION.NOVELID.eq(novelId));
        List<WritingsessionRecord> sessions = (chapterId == null
                        ? query
                        : query.and(WRITINGSESSION.CHAPTERID.eq(chapterId)))
                .orderBy(WRITINGSESSION.UPDATEDAT.desc(), WRITINGSESSION.ID.asc())
                .fetch();
        if (sessions.isEmpty()) return List.of();
        List<String> sessionIds = sessions.stream().map(WritingsessionRecord::getId).toList();
        Map<String, Integer> counts = new LinkedHashMap<>();
        context.select(WRITINGMESSAGE.SESSIONID, count())
                .from(WRITINGMESSAGE)
                .where(WRITINGMESSAGE.SESSIONID.in(sessionIds))
                .groupBy(WRITINGMESSAGE.SESSIONID)
                .fetch()
                .forEach(row -> counts.put(
                        row.value1(), Math.toIntExact(row.value2())));
        Map<String, LastMessageResponse> last = lastMessages(context, sessionIds);
        return sessions.stream()
                .map(session -> listItem(
                        session,
                        counts.getOrDefault(session.getId(), 0),
                        last.get(session.getId())))
                .toList();
    }

    @Override
    public WritingSessionDetail get(String userId, String sessionId) {
        DSLContext context = database.dsl();
        WritingsessionRecord session = requireSession(context, userId, sessionId, false);
        List<MessageResponse> messages = context.selectFrom(WRITINGMESSAGE)
                .where(WRITINGMESSAGE.SESSIONID.eq(sessionId))
                .orderBy(WRITINGMESSAGE.CREATEDAT.asc(), WRITINGMESSAGE.ID.asc())
                .fetch()
                .stream()
                .map(this::message)
                .toList();
        List<WritingtaskRecord> tasks = context.selectFrom(WRITINGTASK)
                .where(WRITINGTASK.WRITINGSESSIONID.eq(sessionId))
                .orderBy(WRITINGTASK.UPDATEDAT.desc())
                .fetch();
        WritingRecovery.RecoveryState recovery = WritingRecovery.select(tasks, json);
        return new WritingSessionDetail(
                session.getChapterid(),
                DatabaseTimestamp.api(session.getCreatedat()),
                recovery.currentTask(),
                session.getId(),
                recovery.lastTask(),
                messages,
                session.getNovelid(),
                session.getPhase(),
                session.getTitle(),
                DatabaseTimestamp.api(session.getUpdatedat()));
    }

    @Override
    public WritingSessionResponse update(
            String userId, String sessionId, UpdateWritingSessionRequest request) {
        return database.transactionResult(transaction -> {
            WritingsessionRecord session = requireSession(
                    transaction, userId, sessionId, true);
            String title = nullable(request.getTitle());
            if (title != null) session.setTitle(title);
            UpdateWritingSessionRequest.PhaseEnum phase = nullable(request.getPhase());
            if (phase != null) session.setPhase(phase.getValue());
            session.setUpdatedat(DatabaseTimestamp.next(clock, session.getUpdatedat()));
            session.update();
            return response(session);
        });
    }

    @Override
    public void delete(String userId, String sessionId) {
        database.transactionResult(transaction -> {
            WritingsessionRecord session = requireSession(
                    transaction, userId, sessionId, true);
            session.delete();
            return null;
        });
    }

    @Override
    public MessageResponse addMessage(
            String userId, String sessionId, CreateMessageRequest request) {
        return database.transactionResult(transaction -> {
            WritingsessionRecord session = requireSession(
                    transaction, userId, sessionId, true);
            LocalDateTime now = DatabaseTimestamp.now(clock);
            WritingmessageRecord message = transaction.newRecord(WRITINGMESSAGE);
            message.setId(ids.next());
            message.setSessionid(sessionId);
            message.setRole(request.getRole().getValue());
            message.setAgentid(nullable(request.getAgentId()));
            message.setContent(request.getContent());
            message.setIntent(nullable(request.getIntent()));
            Object metadata = nullable(request.getMetadata());
            message.setMetadata(metadata == null ? null : json.writeValueAsString(metadata));
            message.setParentid(nullable(request.getParentId()));
            message.setCreatedat(now);
            message.insert();
            session.setUpdatedat(DatabaseTimestamp.next(clock, session.getUpdatedat()));
            session.update();
            return message(message);
        });
    }

    private Map<String, LastMessageResponse> lastMessages(
            DSLContext context, List<String> sessionIds) {
        Field<Integer> rank = rowNumber()
                .over(org.jooq.impl.DSL.partitionBy(WRITINGMESSAGE.SESSIONID)
                        .orderBy(
                                WRITINGMESSAGE.CREATEDAT.desc(),
                                WRITINGMESSAGE.ID.desc()))
                .as("messageRank");
        Table<?> ranked = context.select(
                        WRITINGMESSAGE.SESSIONID.as("sessionId"),
                        WRITINGMESSAGE.CONTENT.as("content"),
                        WRITINGMESSAGE.ROLE.as("role"),
                        WRITINGMESSAGE.AGENTID.as("agentId"),
                        rank)
                .from(WRITINGMESSAGE)
                .where(WRITINGMESSAGE.SESSIONID.in(sessionIds))
                .asTable("ranked_messages");
        Field<String> sessionId = ranked.field("sessionId", String.class);
        Field<String> content = ranked.field("content", String.class);
        Field<String> role = ranked.field("role", String.class);
        Field<String> agentId = ranked.field("agentId", String.class);
        Field<Integer> messageRank = ranked.field("messageRank", Integer.class);
        Map<String, LastMessageResponse> result = new LinkedHashMap<>();
        context.select(sessionId, content, role, agentId)
                .from(ranked)
                .where(messageRank.eq(1))
                .fetch()
                .forEach(row -> result.put(
                        row.value1(),
                        new LastMessageResponse(row.value4(), row.value2(), row.value3())));
        return result;
    }

    private static void requireNovel(
            DSLContext context, String userId, String novelId) {
        String found = context.select(NOVEL.ID)
                .from(NOVEL)
                .where(NOVEL.ID.eq(novelId), NOVEL.USERID.eq(userId))
                .fetchOne(NOVEL.ID);
        if (found == null) {
            throw new ApiException(403, "NOVEL_FORBIDDEN", "无权访问该小说");
        }
    }

    private static void requireChapter(
            DSLContext context, String userId, String novelId, String chapterId) {
        String found = context.select(CHAPTER.ID)
                .from(CHAPTER)
                .join(NOVEL)
                .on(NOVEL.ID.eq(CHAPTER.NOVELID))
                .where(
                        CHAPTER.ID.eq(chapterId),
                        CHAPTER.NOVELID.eq(novelId),
                        NOVEL.USERID.eq(userId))
                .fetchOne(CHAPTER.ID);
        if (found == null) {
            throw new ApiException(
                    404,
                    "CHAPTER_NOT_FOUND",
                    "章节不存在或不属于该小说");
        }
    }

    private static WritingsessionRecord requireSession(
            DSLContext context,
            String userId,
            String sessionId,
            boolean lock) {
        var query = context.select(WRITINGSESSION.fields())
                .from(WRITINGSESSION)
                .join(NOVEL)
                .on(NOVEL.ID.eq(WRITINGSESSION.NOVELID))
                .where(
                        WRITINGSESSION.ID.eq(sessionId),
                        NOVEL.USERID.eq(userId));
        Record row = lock ? query.forUpdate().fetchOne() : query.fetchOne();
        if (row == null) {
            throw new ApiException(
                    403,
                    "WRITING_SESSION_FORBIDDEN",
                    "无权访问该写作会话");
        }
        return row.into(WRITINGSESSION);
    }

    private WritingSessionListItem listItem(
            WritingsessionRecord session,
            int messageCount,
            LastMessageResponse lastMessage) {
        return new WritingSessionListItem(
                session.getChapterid(),
                DatabaseTimestamp.api(session.getCreatedat()),
                session.getId(),
                lastMessage,
                messageCount,
                session.getNovelid(),
                session.getPhase(),
                session.getTitle(),
                DatabaseTimestamp.api(session.getUpdatedat()));
    }

    private static WritingSessionResponse response(WritingsessionRecord session) {
        return new WritingSessionResponse(
                session.getChapterid(),
                DatabaseTimestamp.api(session.getCreatedat()),
                session.getId(),
                session.getNovelid(),
                session.getPhase(),
                session.getTitle(),
                DatabaseTimestamp.api(session.getUpdatedat()));
    }

    private MessageResponse message(WritingmessageRecord message) {
        return new MessageResponse(
                message.getAgentid(),
                message.getContent(),
                DatabaseTimestamp.api(message.getCreatedat()),
                message.getId(),
                message.getIntent(),
                parseMetadata(message.getMetadata()),
                message.getParentid(),
                message.getRole(),
                message.getSessionid());
    }

    private Object parseMetadata(String value) {
        if (value == null) return null;
        try {
            return json.readValue(value, new TypeReference<Object>() {});
        } catch (RuntimeException exception) {
            return null;
        }
    }

    private static <T> T nullable(JsonNullable<T> value) {
        return value == null || value.isUndefined() ? null : value.orElse(null);
    }
}
