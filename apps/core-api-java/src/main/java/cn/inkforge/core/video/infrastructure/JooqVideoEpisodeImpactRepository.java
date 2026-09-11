package cn.inkforge.core.video.infrastructure;

import cn.inkforge.core.platform.db.CoreDatabase;
import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.platform.id.CuidV1Generator;
import cn.inkforge.core.platform.time.DatabaseTimestamp;
import cn.inkforge.core.video.application.VideoEpisodeImpactRepository;

import org.jooq.DSLContext;
import org.jooq.Record;

import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;
import tools.jackson.databind.node.ArrayNode;
import tools.jackson.databind.node.ObjectNode;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.Clock;
import java.time.LocalDateTime;
import java.time.OffsetDateTime;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.HexFormat;
import java.util.List;
import java.util.Objects;
import java.util.Set;

/** 影响报告的分页读取和 CAS 决定；旧报告一旦依据漂移就拒绝继续写入。 */
public final class JooqVideoEpisodeImpactRepository implements VideoEpisodeImpactRepository {
    private static final Set<String> STATUSES = Set.of("pending", "resolved");
    private static final Set<String> ACTIONS =
            Set.of("keep_existing", "revise_target", "not_applicable", "defer");

    private final CoreDatabase database;
    private final CuidV1Generator ids;
    private final Clock clock;
    private final ObjectMapper json;

    public JooqVideoEpisodeImpactRepository(
            CoreDatabase database, CuidV1Generator ids, Clock clock, ObjectMapper json) {
        this.database = Objects.requireNonNull(database);
        this.ids = Objects.requireNonNull(ids);
        this.clock = Objects.requireNonNull(clock);
        this.json = Objects.requireNonNull(json);
    }

    @Override
    public ObjectNode list(
            String userId,
            String episodeId,
            String status,
            String beforeReviewId,
            int limit) {
        if (status != null && !STATUSES.contains(status)) {
            throw invalid("VIDEO_IMPACT_STATUS_INVALID", "影响复核状态无效");
        }
        if (limit < 1 || limit > 100) {
            throw invalid("VIDEO_IMPACT_LIMIT_INVALID", "影响复核分页大小须为 1 至 100");
        }
        int checkedLimit = limit;
        return database.transactionResult(
                tx -> {
                    Record episode = ownedEpisode(tx, userId, episodeId, false);
                    LocalDateTime beforeCreatedAt = null;
                    String beforeId = null;
                    if (beforeReviewId != null) {
                        Record cursor = requireReview(tx, episode, episodeId, beforeReviewId, false);
                        beforeCreatedAt = cursor.get("createdAt", LocalDateTime.class);
                        beforeId = cursor.get("id", String.class);
                    }
                    StringBuilder sql =
                            new StringBuilder(
                                    "SELECT * FROM \"VideoImpactReview\" WHERE \"projectId\"=?"
                                            + " AND (\"producerEpisodeId\"=? OR \"targetEpisodeId\"=?)");
                    List<Object> bindings =
                            new ArrayList<>(
                                    List.of(episode.get("projectId"), episodeId, episodeId));
                    if (status != null) {
                        sql.append(" AND status=?");
                        bindings.add(status);
                    }
                    if (beforeCreatedAt != null) {
                        sql.append(" AND (\"createdAt\",id) < (?,?)");
                        bindings.add(beforeCreatedAt);
                        bindings.add(beforeId);
                    }
                    sql.append(" ORDER BY \"createdAt\" DESC,id DESC LIMIT ?");
                    bindings.add(checkedLimit + 1);
                    List<Record> rows = tx.fetch(sql.toString(), bindings.toArray());
                    boolean hasMore = rows.size() > checkedLimit;
                    if (hasMore) {
                        rows = new ArrayList<>(rows.subList(0, checkedLimit));
                    }
                    List<ObjectNode> reviews =
                            rows.stream().map(row -> response(tx, row, false)).toList();
                    return object(
                            "reviews",
                            reviews,
                            "nextBeforeReviewId",
                            hasMore && !rows.isEmpty()
                                    ? rows.get(rows.size() - 1).get("id", String.class)
                                    : null);
                });
    }

    @Override
    public ObjectNode get(String userId, String episodeId, String reviewId) {
        return database.transactionResult(
                tx -> {
                    Record episode = ownedEpisode(tx, userId, episodeId, false);
                    return response(
                            tx, requireReview(tx, episode, episodeId, reviewId, false), true);
                });
    }

    @Override
    public ObjectNode decide(
            String userId, String episodeId, String reviewId, JsonNode request) {
        String clientRequestId = requiredText(request, "clientRequestId");
        String requestHash =
                hash(
                        object(
                                "operation",
                                "episode.impact-review.decide",
                                "episodeId",
                                episodeId,
                                "reviewId",
                                reviewId,
                                "request",
                                request));
        return database.transactionResult(
                tx -> {
                    tx.fetchOne(
                            "SELECT pg_advisory_xact_lock(hashtextextended(?,0))",
                            "video-episode-command:" + userId + ":" + clientRequestId);
                    Record episode = ownedEpisode(tx, userId, episodeId, true);
                    Record previous =
                            tx.fetchOne(
                                    "SELECT * FROM \"VideoEpisodeCommand\" WHERE"
                                            + " \"actorUserId\"=? AND \"clientRequestId\"=?",
                                    userId,
                                    clientRequestId);
                    if (previous != null) {
                        if (!requestHash.equals(previous.get("requestHash", String.class))) {
                            throw conflict(
                                    "VIDEO_EPISODE_CLIENT_REQUEST_REUSED",
                                    "clientRequestId 已用于不同请求");
                        }
                        return parse(previous, "resultJson");
                    }
                    Record review = requireReview(tx, episode, episodeId, reviewId, true);
                    int expectedRevision = request.path("expectedRevision").asInt(-1);
                    if (review.get("revision", Integer.class) != expectedRevision) {
                        throw conflict("VIDEO_IMPACT_REVISION_CONFLICT", "影响决定已变化，请重新读取");
                    }
                    List<String> staleReasons = staleReasons(tx, review);
                    if (!staleReasons.isEmpty()) {
                        throw conflict(
                                "VIDEO_IMPACT_REVIEW_STALE",
                                "影响报告所依据的剧本或制作基线已经变化，请基于新依据复核");
                    }
                    ArrayNode decisions = validateDecisions(review, request.path("decisions"));
                    Set<String> completed = new HashSet<>();
                    for (JsonNode decision : decisions) {
                        if (!"defer".equals(decision.path("action").asText())) {
                            completed.add(decision.path("itemId").asText());
                        }
                    }
                    int itemCount = parse(review, "reportJson").path("items").size();
                    String nextStatus = completed.size() == itemCount ? "resolved" : "pending";
                    tx.execute(
                            "UPDATE \"VideoImpactReview\" SET \"decisionsJson\"=?,status=?,"
                                    + " revision=revision+1,\"updatedAt\"=? WHERE id=?",
                            decisions.toString(),
                            nextStatus,
                            now(),
                            reviewId);
                    ObjectNode result =
                            response(
                                    tx,
                                    requireReview(tx, episode, episodeId, reviewId, false),
                                    true);
                    tx.execute(
                            "INSERT INTO \"VideoEpisodeCommand\""
                                    + " (id,\"actorUserId\",\"clientRequestId\",\"projectId\",\"novelId\",\"episodeId\",operation,\"requestHash\",\"resultJson\",\"createdAt\")"
                                    + " VALUES (?,?,?,?,?,?,?,?,?,?)",
                            ids.next(),
                            userId,
                            clientRequestId,
                            episode.get("projectId"),
                            episode.get("novelId"),
                            review.get("targetEpisodeId"),
                            "episode.impact-review.decide",
                            requestHash,
                            result.toString(),
                            now());
                    return result;
                });
    }

    private ArrayNode validateDecisions(Record review, JsonNode node) {
        if (!node.isArray() || node.isEmpty() || node.size() > 500) {
            throw invalid("VIDEO_IMPACT_DECISIONS_INVALID", "影响决定应包含 1 至 500 项");
        }
        Set<String> allowed = new HashSet<>();
        for (JsonNode item : parse(review, "reportJson").path("items")) {
            allowed.add(requiredText(item, "itemId"));
        }
        Set<String> seen = new HashSet<>();
        ArrayNode normalized = json.createArrayNode();
        for (JsonNode decision : node) {
            String itemId = requiredText(decision, "itemId");
            String action = requiredText(decision, "action");
            String note = decision.path("note").asText("");
            if (!allowed.contains(itemId) || !seen.add(itemId) || !ACTIONS.contains(action)) {
                throw invalid(
                        "VIDEO_IMPACT_DECISIONS_INVALID",
                        "影响决定必须唯一对应当前报告中的项目并使用有效动作");
            }
            if (note.length() > 4_000) {
                throw invalid("VIDEO_IMPACT_DECISIONS_INVALID", "影响决定说明不能超过 4000 字符");
            }
            if (!"defer".equals(action) && note.isBlank()) {
                throw invalid(
                        "VIDEO_IMPACT_DECISIONS_INVALID",
                        "完成影响项必须记录作者判断依据或修改安排");
            }
            normalized.add(object("itemId", itemId, "action", action, "note", note));
        }
        return normalized;
    }

    private Record ownedEpisode(DSLContext tx, String userId, String episodeId, boolean lock) {
        Record row =
                tx.fetchOne(
                        "SELECT * FROM \"VideoEpisode\" WHERE id=? AND \"archivedAt\" IS NULL",
                        episodeId);
        if (row == null) {
            throw missing("VIDEO_EPISODE_NOT_FOUND", "分集不存在");
        }
        VideoDatabaseAccess.ownedProject(
                tx, userId, row.get("projectId", String.class), lock);
        if (lock) {
            row =
                    tx.fetchOne(
                            "SELECT * FROM \"VideoEpisode\" WHERE id=? AND \"archivedAt\" IS NULL"
                                    + " FOR UPDATE",
                            episodeId);
        }
        return row;
    }

    private Record requireReview(
            DSLContext tx, Record episode, String episodeId, String reviewId, boolean lock) {
        Record row =
                tx.fetchOne(
                        "SELECT * FROM \"VideoImpactReview\" WHERE id=? AND \"projectId\"=?"
                                + " AND (\"producerEpisodeId\"=? OR \"targetEpisodeId\"=?)"
                                + (lock ? " FOR UPDATE" : ""),
                        reviewId,
                        episode.get("projectId"),
                        episodeId,
                        episodeId);
        if (row == null) {
            throw missing("VIDEO_IMPACT_REVIEW_NOT_FOUND", "影响报告不存在或不属于本集");
        }
        return row;
    }

    private ObjectNode response(DSLContext tx, Record row, boolean full) {
        ObjectNode report = parse(row, "reportJson");
        JsonNode decisions = json.readTree(row.get("decisionsJson", String.class));
        List<String> staleReasons = staleReasons(tx, row);
        ObjectNode result =
                object(
                        "id",
                        row.get("id"),
                        "projectId",
                        row.get("projectId"),
                        "producerEpisodeId",
                        row.get("producerEpisodeId"),
                        "beforeScriptVersionId",
                        row.get("beforeScriptVersionId"),
                        "afterScriptVersionId",
                        row.get("afterScriptVersionId"),
                        "targetEpisodeId",
                        row.get("targetEpisodeId"),
                        "targetScriptVersionId",
                        row.get("targetScriptVersionId"),
                        "producerProductionRevision",
                        row.get("producerProductionRevision"),
                        "targetProductionRevision",
                        row.get("targetProductionRevision"),
                        "producerBaselineId",
                        row.get("producerBaselineId"),
                        "targetBaselineId",
                        row.get("targetBaselineId"),
                        "revision",
                        row.get("revision"),
                        "status",
                        row.get("status"),
                        "itemCount",
                        report.path("items").size(),
                        "decisionCount",
                        decisions.size(),
                        "isStale",
                        !staleReasons.isEmpty(),
                        "staleReasons",
                        staleReasons,
                        "createdAt",
                        apiTime(row, "createdAt"),
                        "updatedAt",
                        apiTime(row, "updatedAt"));
        if (full) {
            result.set("report", report);
            result.set("decisions", decisions);
        }
        return result;
    }

    private List<String> staleReasons(DSLContext tx, Record review) {
        Record producer =
                tx.fetchOne(
                        "SELECT \"currentScriptVersionId\",\"currentProductionBaselineId\","
                                + " \"productionRevision\" FROM \"VideoEpisode\" WHERE id=?",
                        review.get("producerEpisodeId"));
        Record target =
                tx.fetchOne(
                        "SELECT \"currentScriptVersionId\",\"currentProductionBaselineId\","
                                + " \"productionRevision\" FROM \"VideoEpisode\" WHERE id=?",
                        review.get("targetEpisodeId"));
        List<String> reasons = new ArrayList<>();
        if (producer == null
                || !Objects.equals(
                        producer.get("currentScriptVersionId"),
                        review.get("afterScriptVersionId"))) {
            reasons.add("producer_script_changed");
        }
        if (target == null
                || !Objects.equals(
                        target.get("currentScriptVersionId"),
                        review.get("targetScriptVersionId"))) {
            reasons.add("target_script_changed");
        }
        if (producer != null
                && (!Objects.equals(
                                producer.get("productionRevision"),
                                review.get("producerProductionRevision"))
                        || !Objects.equals(
                                producer.get("currentProductionBaselineId"),
                                review.get("producerBaselineId")))) {
            reasons.add("producer_production_changed");
        }
        if (target != null
                && (!Objects.equals(
                                target.get("productionRevision"),
                                review.get("targetProductionRevision"))
                        || !Objects.equals(
                                target.get("currentProductionBaselineId"),
                                review.get("targetBaselineId")))) {
            reasons.add("target_production_changed");
        }
        return List.copyOf(reasons);
    }

    private ObjectNode parse(Record row, String column) {
        return (ObjectNode) json.readTree(row.get(column, String.class));
    }

    private ObjectNode object(Object... values) {
        ObjectNode result = json.createObjectNode();
        for (int index = 0; index < values.length; index += 2) {
            Object value = values[index + 1];
            result.set(
                    (String) values[index],
                    json.valueToTree(
                            value instanceof OffsetDateTime time ? time.toString() : value));
        }
        return result;
    }

    private String hash(JsonNode node) {
        try {
            return HexFormat.of()
                    .formatHex(
                            MessageDigest.getInstance("SHA-256")
                                    .digest(node.toString().getBytes(StandardCharsets.UTF_8)));
        } catch (Exception exception) {
            throw new IllegalStateException(exception);
        }
    }

    private LocalDateTime now() {
        return DatabaseTimestamp.now(clock);
    }

    private static OffsetDateTime apiTime(Record row, String column) {
        return DatabaseTimestamp.api(row.get(column, LocalDateTime.class));
    }

    private static String requiredText(JsonNode node, String key) {
        String value = node.path(key).asText("").trim();
        if (value.isEmpty()) {
            throw invalid("VIDEO_IMPACT_DECISIONS_INVALID", key + " 不能为空");
        }
        return value;
    }

    private static ApiException invalid(String code, String message) {
        return new ApiException(422, code, message);
    }

    private static ApiException conflict(String code, String message) {
        return new ApiException(409, code, message);
    }

    private static ApiException missing(String code, String message) {
        return new ApiException(404, code, message);
    }
}
