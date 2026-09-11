package cn.inkforge.core.video.infrastructure;

import cn.inkforge.core.platform.db.CoreDatabase;
import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.platform.id.CuidV1Generator;
import cn.inkforge.core.platform.time.DatabaseTimestamp;
import cn.inkforge.core.video.application.VideoEpisodeRepository;
import cn.inkforge.core.workflows.application.WorkflowVideoEpisodeScriptCompletion;

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
import java.util.HashMap;
import java.util.HashSet;
import java.util.HexFormat;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

/** 独立集的来源、工作稿和正式版本；命令回执与业务事实在同一事务提交。 */
public final class JooqVideoEpisodeRepository
        implements VideoEpisodeRepository, WorkflowVideoEpisodeScriptCompletion {
    private final CoreDatabase database;
    private final CuidV1Generator ids;
    private final Clock clock;
    private final ObjectMapper json;

    public JooqVideoEpisodeRepository(
            CoreDatabase database, CuidV1Generator ids, Clock clock, ObjectMapper json) {
        this.database = Objects.requireNonNull(database);
        this.ids = Objects.requireNonNull(ids);
        this.clock = Objects.requireNonNull(clock);
        this.json = Objects.requireNonNull(json);
    }

    @Override
    public ObjectNode list(String user, String projectId) {
        return database.transactionResult(
                tx -> {
                    var project = VideoDatabaseAccess.ownedProject(tx, user, projectId, false);
                    return list(tx, projectId, project.getRevision());
                });
    }

    @Override
    public ObjectNode get(String user, String episodeId) {
        return database.transactionResult(
                tx ->
                        VideoEpisodeAggregateRead.read(
                                owned(tx, user, episodeId, false),
                                episode -> aggregate(tx, episode),
                                () -> owned(tx, user, episodeId, false),
                                episode -> episode.get("revision", Integer.class)));
    }

    private ObjectNode aggregate(DSLContext tx, Record episode) {
        String episodeId = episode.get("id", String.class);
        return object(
                "episode",
                episode(episode),
                "sourceSets",
                sources(tx, episodeId),
                "scriptDraft",
                draft(tx, episodeId, Map.of()),
                "scriptVersions",
                versions(tx, episodeId),
                "currentScriptVersion",
                nullableVersion(
                        tx, episodeId, episode.get("currentScriptVersionId", String.class)),
                "candidateArtifacts",
                candidates(tx, episodeId),
                "dependencies",
                dependencies(tx, episode),
                "latestScriptRun",
                latestRun(tx, episodeId));
    }

    @Override
    public ObjectNode create(String user, String projectId, JsonNode request) {
        return write(
                user,
                projectId,
                null,
                "episode.create",
                request,
                (tx, old) -> {
                    var project = VideoDatabaseAccess.ownedProject(tx, user, projectId, true);
                    VideoDatabaseAccess.requireLongSerial(tx, project.getNovelid(), true);
                    String id = ids.next();
                    LocalDateTime now = now();
                    int ordinal =
                            tx.fetchOne(
                                            "SELECT COALESCE(MAX(ordinal),0)+1 n FROM"
                                                + " \"VideoEpisode\" WHERE \"projectId\"=?",
                                            projectId)
                                    .get("n", Integer.class);
                    tx.execute(
                            "INSERT INTO \"VideoEpisode\""
                                + " (id,\"projectId\",\"novelId\",title,ordinal,\"creativeIntent\",\"targetDurationSeconds\",\"updatedAt\",\"createdAt\")"
                                + " VALUES (?,?,?,?,?,?,?,?,?)",
                            id,
                            projectId,
                            project.getNovelid(),
                            requiredText(request, "title"),
                            ordinal,
                            request.path("creativeIntent").asText(""),
                            nullableInt(request, "targetDurationSeconds"),
                            now,
                            now);
                    JsonNode document = emptyDocument(request);
                    tx.execute(
                            "INSERT INTO \"VideoEpisodeScriptDraft\""
                                + " (\"episodeId\",\"documentJson\",\"contentHash\",\"updatedAt\")"
                                + " VALUES (?,?,?,?)",
                            id,
                            document.toString(),
                            hash(document),
                            now);
                    JsonNode storyboard =
                            object(
                                    "schemaVersion",
                                    "video-episode-storyboard/1.0",
                                    "shots",
                                    List.of());
                    tx.execute(
                            "INSERT INTO \"VideoStoryboardDraft\""
                                    + " (\"episodeId\",\"scriptVersionId\",\"documentJson\",\"contentHash\",\"updatedAt\")"
                                    + " VALUES (?,?,?,?,?)",
                            id,
                            null,
                            storyboard.toString(),
                            hash(storyboard),
                            now);
                    bumpProject(tx, projectId);
                    return episode(requireEpisode(tx, id, false));
                });
    }

    @Override
    public ObjectNode update(String user, String episodeId, JsonNode request) {
        return write(
                user,
                null,
                episodeId,
                "episode.update",
                request,
                (tx, ep) -> {
                    revision(
                            ep,
                            request.path("expectedRevision").asInt(),
                            "VIDEO_EPISODE_REVISION_CONFLICT");
                    String title =
                            request.hasNonNull("title")
                                    ? requiredText(request, "title")
                                    : ep.get("title", String.class);
                    String intent =
                            request.hasNonNull("creativeIntent")
                                    ? request.path("creativeIntent").asText()
                                    : ep.get("creativeIntent", String.class);
                    Integer duration =
                            request.has("targetDurationSeconds")
                                    ? nullableInt(request, "targetDurationSeconds")
                                    : ep.get("targetDurationSeconds", Integer.class);
                    tx.execute(
                            "UPDATE \"VideoEpisode\" SET"
                                + " title=?,\"creativeIntent\"=?,\"targetDurationSeconds\"=?,revision=revision+1,\"updatedAt\"=?"
                                + " WHERE id=?",
                            title,
                            intent,
                            duration,
                            now(),
                            episodeId);
                    return episode(requireEpisode(tx, episodeId, false));
                });
    }

    @Override
    public ObjectNode reorder(String user, String projectId, JsonNode request) {
        return write(
                user,
                projectId,
                null,
                "episode.reorder",
                request,
                (tx, ignored) -> {
                    var project = VideoDatabaseAccess.ownedProject(tx, user, projectId, true);
                    if (project.getRevision() != request.path("expectedProjectRevision").asInt())
                        throw conflict("VIDEO_PROJECT_REVISION_CONFLICT", "分集列表已经变化");
                    List<String> requested = new ArrayList<>();
                    request.path("episodeIds").forEach(n -> requested.add(n.asText()));
                    Set<String> actual =
                            new HashSet<>(
                                    tx.fetch(
                                                    "SELECT id FROM \"VideoEpisode\" WHERE"
                                                        + " \"projectId\"=? AND \"archivedAt\" IS"
                                                        + " NULL",
                                                    projectId)
                                            .getValues("id", String.class));
                    if (!actual.equals(new HashSet<>(requested))
                            || actual.size() != requested.size())
                        throw invalid("VIDEO_EPISODE_ORDER_INVALID", "排序必须包含本项目所有活动分集且不得重复");
                    for (int i = 0; i < requested.size(); i++)
                        tx.execute(
                                "UPDATE \"VideoEpisode\" SET"
                                    + " ordinal=?,revision=revision+1,\"updatedAt\"=? WHERE id=?",
                                i + 1,
                                now(),
                                requested.get(i));
                    bumpProject(tx, projectId);
                    return list(tx, projectId, project.getRevision() + 1);
                });
    }

    @Override
    public ObjectNode createSourceSet(String user, String episodeId, JsonNode request) {
        return write(
                user,
                null,
                episodeId,
                "episode.source.create",
                request,
                (tx, ep) -> {
                    revision(
                            ep,
                            request.path("expectedRevision").asInt(),
                            "VIDEO_EPISODE_REVISION_CONFLICT");
                    String based = text(request, "basedOnVersionId");
                    if (based != null) sourceSet(tx, episodeId, based);
                    List<ObjectNode> snapshots = new ArrayList<>();
                    Set<String> seen = new HashSet<>();
                    // 按章节 ID 排序取锁，避免两集以不同来源顺序冻结同一批章节时产生死锁。
                    List<JsonNode> selections = new ArrayList<>();
                    request.path("sources").forEach(selections::add);
                    if (selections.isEmpty() || selections.size() > 40)
                        throw invalid("VIDEO_SOURCE_SELECTION_INVALID", "请选择 1 至 40 个章节来源");
                    Map<String, Record> chapters = new HashMap<>();
                    selections.stream()
                            .map(n -> requiredText(n, "chapterId"))
                            .sorted()
                            .forEach(
                                    id -> {
                                        if (!seen.add(id))
                                            throw invalid(
                                                    "VIDEO_SOURCE_SELECTION_INVALID", "同一章节的范围应合并");
                                        Record row =
                                                tx.fetchOne(
                                                        "SELECT id,title,content,\"updatedAt\" FROM"
                                                            + " \"Chapter\" WHERE id=? AND"
                                                            + " \"novelId\"=? FOR SHARE",
                                                        id,
                                                        ep.get("novelId"));
                                        if (row == null)
                                            throw missing(
                                                    "VIDEO_EPISODE_CHAPTER_NOT_FOUND",
                                                    "章节不存在或不属于当前小说");
                                        chapters.put(id, row);
                                    });
                    for (JsonNode selection : selections) {
                        Record chapter = chapters.get(selection.path("chapterId").asText());
                        String source = chapter.get("content", String.class);
                        if (source == null || source.isBlank())
                            throw invalid("VIDEO_SOURCE_EMPTY", "章节正文为空");
                        if (source.codePointCount(0, source.length()) > 120000)
                            throw invalid("VIDEO_SOURCE_TOO_LONG", "单章来源超过 120000 个 Unicode 码点");
                        if (!DatabaseTimestamp.sameInstant(
                                        chapter.get("updatedAt", LocalDateTime.class),
                                        OffsetDateTime.parse(
                                                selection.path("expectedUpdatedAt").asText()))
                                || !sha(source).equals(selection.path("sourceHash").asText()))
                            throw conflict("VIDEO_SOURCE_CHANGED", "章节已变化，请重新读取后选择来源");
                        validateRanges(selection.path("ranges"), source);
                        snapshots.add(
                                object(
                                        "id",
                                        ids.next(),
                                        "chapterId",
                                        chapter.get("id"),
                                        "chapterTitle",
                                        chapter.get("title"),
                                        "chapterUpdatedAt",
                                        apiTime(chapter, "updatedAt"),
                                        "sourceText",
                                        source,
                                        "sourceHash",
                                        sha(source),
                                        "ranges",
                                        selection.path("ranges")));
                    }
                    String id = ids.next();
                    int no = nextVersion(tx, "VideoEpisodeSourceSetVersion", episodeId);
                    tx.execute(
                            "INSERT INTO \"VideoEpisodeSourceSetVersion\""
                                + " (id,\"episodeId\",\"versionNo\",\"basedOnVersionId\",\"contentHash\",\"createdByUserId\",\"createdAt\")"
                                + " VALUES (?,?,?,?,?,?,?)",
                            id,
                            episodeId,
                            no,
                            based,
                            hash(json.valueToTree(snapshots)),
                            user,
                            now());
                    for (int i = 0; i < snapshots.size(); i++) {
                        JsonNode s = snapshots.get(i);
                        tx.execute(
                                "INSERT INTO \"VideoEpisodeSourceSnapshot\""
                                    + " (id,\"sourceSetVersionId\",ordinal,\"chapterId\",\"chapterTitle\",\"chapterUpdatedAt\",\"sourceText\",\"sourceHash\",\"rangesJson\")"
                                    + " VALUES (?,?,?,?,?,?,?,?,?)",
                                text(s, "id"),
                                id,
                                i + 1,
                                text(s, "chapterId"),
                                text(s, "chapterTitle"),
                                DatabaseTimestamp.database(
                                        OffsetDateTime.parse(text(s, "chapterUpdatedAt"))),
                                text(s, "sourceText"),
                                text(s, "sourceHash"),
                                s.path("ranges").toString());
                    }
                    tx.execute(
                            "UPDATE \"VideoEpisode\" SET"
                                + " \"currentSourceSetVersionId\"=?,revision=revision+1,\"updatedAt\"=?"
                                + " WHERE id=?",
                            id,
                            now(),
                            episodeId);
                    Record initial = requireDraft(tx, episodeId);
                    JsonNode initialDoc = parse(initial, "documentJson");
                    // 只有从未编辑过的系统空稿随首次取材绑定；已有工作稿的来源切换必须单独 CAS。
                    if (initial.get("revision", Integer.class) == 1
                            && initial.get("sourceSetVersionId") == null
                            && initial.get("basedOnScriptVersionId") == null
                            && initialDoc.path("scenes").isEmpty()
                            && initialDoc.path("endingStates").isEmpty()
                            && initialDoc.path("dependencies").isEmpty())
                        tx.execute(
                                "UPDATE \"VideoEpisodeScriptDraft\" SET"
                                    + " \"sourceSetVersionId\"=?,revision=revision+1,\"updatedAt\"=?"
                                    + " WHERE \"episodeId\"=?",
                                id,
                                now(),
                                episodeId);
                    return sourceSet(tx, episodeId, id);
                });
    }

    @Override
    public ObjectNode listSourceSets(String user, String episodeId) {
        return read(user, episodeId, (tx, ep) -> object("sourceSets", sources(tx, episodeId)));
    }

    @Override
    public ObjectNode getSourceSet(String user, String episodeId, String versionId) {
        return read(user, episodeId, (tx, ep) -> sourceSet(tx, episodeId, versionId));
    }

    @Override
    public ObjectNode getDraft(String user, String episodeId) {
        return read(user, episodeId, (tx, ep) -> draft(tx, episodeId, Map.of()));
    }

    @Override
    public ObjectNode saveDraft(String user, String episodeId, JsonNode request) {
        return write(
                user,
                null,
                episodeId,
                "episode.script.save",
                request,
                (tx, ep) -> {
                    Record draft = requireDraft(tx, episodeId);
                    revision(
                            draft,
                            request.path("expectedRevision").asInt(),
                            "VIDEO_SCRIPT_DRAFT_REVISION_CONFLICT");
                    String source = text(request, "sourceSetVersionId"),
                            base = text(request, "baseScriptVersionId");
                    if (source != null) sourceSet(tx, episodeId, source);
                    if (base != null) version(tx, episodeId, base);
                    Map<String, String> mapping = new LinkedHashMap<>();
                    JsonNode document =
                            normalize(
                                    tx,
                                    ep,
                                    source,
                                    request.path("document"),
                                    parse(draft, "documentJson"),
                                    mapping);
                    tx.execute(
                            "UPDATE \"VideoEpisodeScriptDraft\" SET"
                                + " \"sourceSetVersionId\"=?,\"basedOnScriptVersionId\"=?,\"documentJson\"=?,\"contentHash\"=?,revision=revision+1,\"updatedAt\"=?"
                                + " WHERE \"episodeId\"=?",
                            source,
                            base,
                            document.toString(),
                            hash(document),
                            now(),
                            episodeId);
                    return draft(tx, episodeId, mapping);
                });
    }

    @Override
    public ObjectNode prepareConfirmation(String user, String episodeId, JsonNode request) {
        return write(
                user,
                null,
                episodeId,
                "episode.script.prepare",
                request,
                (tx, ep) -> {
                    Record draft = requireDraft(tx, episodeId);
                    revision(
                            ep,
                            request.path("expectedEpisodeRevision").asInt(),
                            "VIDEO_EPISODE_REVISION_CONFLICT");
                    revision(
                            draft,
                            request.path("expectedDraftRevision").asInt(),
                            "VIDEO_SCRIPT_DRAFT_REVISION_CONFLICT");
                    JsonNode doc = parse(draft, "documentJson");
                    requireConfirmable(doc);
                    normalize(
                            tx,
                            ep,
                            draft.get("sourceSetVersionId", String.class),
                            doc,
                            doc,
                            new LinkedHashMap<>());
                    ObjectNode payload =
                            object(
                                    "applyTarget",
                                    "video_episode_script_confirmation",
                                    "episodeId",
                                    episodeId,
                                    "episodeRevision",
                                    ep.get("revision"),
                                    "draftRevision",
                                    draft.get("revision"),
                                    "sourceSetVersionId",
                                    draft.get("sourceSetVersionId"),
                                    "baseScriptVersionId",
                                    draft.get("basedOnScriptVersionId"),
                                    "document",
                                    doc);
                    payload.put("confirmationHash", hash(payload));
                    String artifactId = insertArtifact(tx, ep, null, "作者确认剧本", payload);
                    return confirmation(tx, episodeId, artifactId);
                });
    }

    @Override
    public ObjectNode getConfirmation(String user, String episodeId, String artifactId) {
        return read(user, episodeId, (tx, ep) -> confirmation(tx, episodeId, artifactId));
    }

    @Override
    public ObjectNode approveConfirmation(
            String user, String episodeId, String artifactId, JsonNode request) {
        ObjectNode command = (ObjectNode) request.deepCopy();
        command.put("artifactId", artifactId);
        return write(
                user,
                null,
                episodeId,
                "episode.script.approve",
                command,
                (tx, ep) -> {
                    Record artifact = artifact(tx, episodeId, artifactId);
                    ObjectNode p = parse(artifact, "payloadJson");
                    Record draft = requireDraft(tx, episodeId);
                    requireTarget(p, "video_episode_script_confirmation");
                    revision(
                            artifact,
                            request.path("expectedArtifactRevision").asInt(),
                            "VIDEO_ARTIFACT_REVISION_CONFLICT");
                    revision(
                            ep,
                            request.path("expectedEpisodeRevision").asInt(),
                            "VIDEO_EPISODE_REVISION_CONFLICT");
                    revision(
                            draft,
                            request.path("expectedDraftRevision").asInt(),
                            "VIDEO_SCRIPT_DRAFT_REVISION_CONFLICT");
                    if (!"awaiting_user".equals(artifact.get("status", String.class))
                            || p.path("episodeRevision").asInt()
                                    != ep.get("revision", Integer.class)
                            || p.path("draftRevision").asInt()
                                    != draft.get("revision", Integer.class)
                            || !p.path("confirmationHash")
                                    .asText()
                                    .equals(request.path("confirmationHash").asText())
                            || !p.path("document").equals(parse(draft, "documentJson")))
                        throw conflict(
                                "VIDEO_SCRIPT_CONFIRMATION_CHANGED", "待确认内容或工作稿已经变化，请重新准备确认");
                    JsonNode doc = p.path("document");
                    requireConfirmable(doc);
                    normalize(
                            tx, ep, text(p, "sourceSetVersionId"), doc, doc, new LinkedHashMap<>());
                    String id = ids.next(), before = ep.get("currentScriptVersionId", String.class);
                    int no = nextVersion(tx, "VideoEpisodeScriptVersion", episodeId);
                    tx.execute(
                            "INSERT INTO \"VideoEpisodeScriptVersion\""
                                + " (id,\"episodeId\",\"projectId\",\"versionNo\",\"basedOnVersionId\",\"sourceSetVersionId\",\"documentJson\",\"contentHash\",\"reviewArtifactId\",\"approvedByUserId\",\"createdAt\")"
                                + " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                            id,
                            episodeId,
                            ep.get("projectId"),
                            no,
                            text(p, "baseScriptVersionId"),
                            text(p, "sourceSetVersionId"),
                            doc.toString(),
                            hash(doc),
                            artifactId,
                            user,
                            now());
                    freezeDependencies(tx, ep, id, doc);
                    tx.execute(
                            "UPDATE \"VideoEpisode\" SET"
                                + " \"currentScriptVersionId\"=?,revision=revision+1,\"updatedAt\"=?"
                                + " WHERE id=?",
                            id,
                            now(),
                            episodeId);
                    tx.execute(
                            "UPDATE \"VideoEpisodeScriptDraft\" SET"
                                + " \"basedOnScriptVersionId\"=?,revision=revision+1,\"updatedAt\"=?"
                                + " WHERE \"episodeId\"=?",
                            id,
                            now(),
                            episodeId);
                    applyArtifact(tx, artifactId);
                    if (before != null) createImpacts(tx, ep, before, id);
                    return version(tx, episodeId, id);
                });
    }

    @Override
    public ObjectNode listVersions(String user, String episodeId) {
        return read(user, episodeId, (tx, ep) -> object("versions", versions(tx, episodeId)));
    }

    @Override
    public ObjectNode getVersion(String user, String episodeId, String versionId) {
        return read(user, episodeId, (tx, ep) -> version(tx, episodeId, versionId));
    }

    @Override
    public ObjectNode getCommand(String user, String episodeId, String clientRequestId) {
        return read(
                user,
                episodeId,
                (tx, ep) -> {
                    Record row =
                            tx.fetchOne(
                                    "SELECT * FROM \"VideoEpisodeCommand\" WHERE \"actorUserId\"=?"
                                        + " AND \"clientRequestId\"=? AND \"episodeId\"=?",
                                    user,
                                    clientRequestId,
                                    episodeId);
                    if (row == null) throw missing("VIDEO_EPISODE_COMMAND_NOT_FOUND", "命令回执不存在");
                    return commandResponse(row);
                });
    }

    @Override
    public ObjectNode getProjectCommand(String user, String projectId, String clientRequestId) {
        return database.transactionResult(
                tx -> {
                    VideoDatabaseAccess.ownedProject(tx, user, projectId, false);
                    Record row =
                            tx.fetchOne(
                                    "SELECT * FROM \"VideoEpisodeCommand\" WHERE \"actorUserId\"=?"
                                        + " AND \"clientRequestId\"=? AND \"projectId\"=?",
                                    user,
                                    clientRequestId,
                                    projectId);
                    if (row == null) throw missing("VIDEO_EPISODE_COMMAND_NOT_FOUND", "命令回执不存在");
                    return commandResponse(row);
                });
    }

    private ObjectNode commandResponse(Record row) {
        JsonNode result = parse(row, "resultJson");
        String type = resultType(row.get("operation", String.class));
        if (result.hasNonNull("runId") && !"storyboard_run".equals(type)) {
            type = "script_run";
        }
        return object(
                "clientRequestId",
                row.get("clientRequestId"),
                "episodeId",
                row.get("episodeId"),
                "operation",
                row.get("operation"),
                "resultType",
                type,
                "resultId",
                result.path("runId").asText(result.path("id")
                        .asText(
                                result.path("artifactId")
                                        .asText(
                                                "episode_list".equals(type)
                                                        ? row.get("projectId", String.class)
                                                        : row.get("episodeId", String.class)))),
                "resultRevision",
                result.has("revision") ? result.path("revision").asInt() : null,
                "createdAt",
                apiTime(row, "createdAt"));
    }

    /** 仅对存在完整 V2 结构的环境读取运行观察；关闭结构门禁时仍可读取手工剧本。 */
    private ObjectNode latestRun(DSLContext tx, String episodeId) {
        if (!tx.fetchExists(
                org.jooq
                        .impl
                        .DSL
                        .selectOne()
                        .from("information_schema.columns")
                        .where(
                                "table_schema='public' AND table_name='WorkflowRun' AND"
                                    + " column_name='targetId'")))
            return null;
        Record r =
                tx.fetchOne(
                        "SELECT"
                            + " r.id,r.status,r.\"errorCode\",r.\"errorMessage\",r.\"createdAt\",r.\"updatedAt\",(SELECT"
                            + " a.id FROM \"ReviewArtifact\" a WHERE a.\"workflowRunId\"=r.id AND"
                            + " a.\"videoEpisodeId\"=? LIMIT 1) artifact FROM \"WorkflowRun\" r"
                            + " WHERE r.\"engineVersion\"=2 AND r.workflow='video' AND"
                            + " r.\"targetId\"=? AND r.operation IN"
                            + " ('episode_script_generate','episode_script_revise') ORDER BY"
                            + " r.\"createdAt\" DESC,r.id DESC LIMIT 1",
                        episodeId,
                        episodeId);
        return r == null
                ? null
                : object(
                        "runId",
                        r.get("id"),
                        "episodeId",
                        episodeId,
                        "status",
                        r.get("status", String.class),
                        "artifactId",
                        r.get("artifact"),
                        "errorCode",
                        r.get("errorCode"),
                        "errorMessage",
                        r.get("errorMessage"),
                        "createdAt",
                        apiTime(r, "createdAt"),
                        "updatedAt",
                        apiTime(r, "updatedAt"));
    }

    @Override
    public ObjectNode adoptCandidate(
            String user, String episodeId, String artifactId, JsonNode request) {
        ObjectNode command = (ObjectNode) request.deepCopy();
        command.put("artifactId", artifactId);
        return write(
                user,
                null,
                episodeId,
                "episode.script.adopt",
                command,
                (tx, ep) -> {
                    Record a = artifact(tx, episodeId, artifactId), d = requireDraft(tx, episodeId);
                    ObjectNode p = parse(a, "payloadJson");
                    requireTarget(p, "video_episode_script_draft");
                    revision(
                            a,
                            request.path("expectedArtifactRevision").asInt(),
                            "VIDEO_ARTIFACT_REVISION_CONFLICT");
                    revision(
                            d,
                            request.path("expectedDraftRevision").asInt(),
                            "VIDEO_SCRIPT_DRAFT_REVISION_CONFLICT");
                    if (!"awaiting_user".equals(a.get("status", String.class))
                            || p.path("expectedDraftRevision").asInt()
                                    != d.get("revision", Integer.class))
                        throw conflict("VIDEO_SCRIPT_CANDIDATE_STALE", "候选基于的草稿已变化");
                    Map<String, String> mapping = new LinkedHashMap<>();
                    JsonNode doc =
                            normalize(
                                    tx,
                                    ep,
                                    text(p, "sourceSetVersionId"),
                                    p.path("document"),
                                    parse(d, "documentJson"),
                                    mapping);
                    tx.execute(
                            "UPDATE \"VideoEpisodeScriptDraft\" SET"
                                + " \"sourceSetVersionId\"=?,\"basedOnScriptVersionId\"=?,\"documentJson\"=?,\"contentHash\"=?,revision=revision+1,\"updatedAt\"=?"
                                + " WHERE \"episodeId\"=?",
                            text(p, "sourceSetVersionId"),
                            text(p, "baseScriptVersionId"),
                            doc.toString(),
                            hash(doc),
                            now(),
                            episodeId);
                    applyArtifact(tx, artifactId);
                    ObjectNode response = draft(tx, episodeId, mapping);
                    response.put("adoptedArtifactId", artifactId);
                    return response;
                });
    }

    @Override
    public boolean targetExists(DSLContext tx, String runId) {
        return tx.fetchOne(
                        "SELECT e.id FROM \"WorkflowRun\" r JOIN \"VideoEpisode\" e ON"
                            + " e.id=r.\"targetId\" AND e.\"novelId\"=r.\"novelId\" JOIN \"Novel\""
                            + " n ON n.id=e.\"novelId\" AND n.\"userId\"=r.\"userId\" WHERE r.id=?"
                            + " AND r.\"engineVersion\"=2 AND r.workflow='video' AND r.operation IN"
                            + " ('episode_script_generate','episode_script_revise') AND"
                            + " e.\"archivedAt\" IS NULL",
                        runId)
                != null;
    }

    @Override
    public String completeCandidate(
            DSLContext tx, String runId, Map<String, Object> document, Map<String, Object> review) {
        if (!targetExists(tx, runId)) throw missing("VIDEO_EPISODE_NOT_FOUND", "候选目标集已不存在");
        Record run =
                tx.fetchOne(
                        "SELECT r.\"targetId\",r.\"userId\",i.\"contentJson\" FROM \"WorkflowRun\""
                            + " r JOIN \"WorkflowEvidenceItem\" i ON"
                            + " i.\"bundleId\"=r.\"currentEvidenceBundleId\" WHERE r.id=? AND"
                            + " i.\"resourceType\"='video_episode_script_context' AND"
                            + " i.\"resourceId\"=r.\"targetId\"",
                        runId);
        if (run == null) throw invalid("VIDEO_SCRIPT_EVIDENCE_MISSING", "剧本候选缺少冻结输入证据");
        Record ep =
                owned(tx, run.get("userId", String.class), run.get("targetId", String.class), true);
        Record old =
                tx.fetchOne(
                        "SELECT id FROM \"ReviewArtifact\" WHERE \"workflowRunId\"=? AND"
                            + " \"videoEpisodeId\"=?",
                        runId,
                        ep.get("id"));
        if (old != null) return old.get("id", String.class);
        ObjectNode context = parse(run, "contentJson");
        ObjectNode payload =
                object(
                        "applyTarget",
                        "video_episode_script_draft",
                        "episodeId",
                        ep.get("id"),
                        "expectedDraftRevision",
                        context.path("draftRevision"),
                        "sourceSetVersionId",
                        context.path("sourceSetVersionId"),
                        "baseScriptVersionId",
                        context.path("baseScriptVersionId"),
                        "document",
                        document,
                        "review",
                        review,
                        "reviewFindings",
                        review.getOrDefault("findings", List.of()));
        return insertArtifact(tx, ep, runId, "剧本候选", payload);
    }

    private ObjectNode write(
            String user,
            String projectId,
            String episodeId,
            String operation,
            JsonNode request,
            Work work) {
        String client = requiredText(request, "clientRequestId");
        String requestHash =
                hash(
                        object(
                                "operation",
                                operation,
                                "projectId",
                                projectId,
                                "episodeId",
                                episodeId,
                                "request",
                                request));
        return database.transactionResult(
                tx -> {
                    // 同一用户的命令键先串行，再统一 Novel→Project→Episode 锁序，避免跨集命令冲突写入。
                    tx.fetchOne(
                            "SELECT pg_advisory_xact_lock(hashtextextended(?,0))",
                            "video-episode-command:" + user + ":" + client);
                    Record ep = episodeId == null ? null : owned(tx, user, episodeId, true);
                    String actualProject =
                            ep == null ? projectId : ep.get("projectId", String.class);
                    var project = VideoDatabaseAccess.ownedProject(tx, user, actualProject, true);
                    Record previous =
                            tx.fetchOne(
                                    "SELECT * FROM \"VideoEpisodeCommand\" WHERE \"actorUserId\"=?"
                                        + " AND \"clientRequestId\"=?",
                                    user,
                                    client);
                    if (previous != null) {
                        if (!requestHash.equals(previous.get("requestHash")))
                            throw conflict(
                                    "VIDEO_EPISODE_CLIENT_REQUEST_REUSED",
                                    "clientRequestId 已用于不同请求");
                        return parse(previous, "resultJson");
                    }
                    ObjectNode result = work.run(tx, ep);
                    String target = episodeId;
                    if (target == null && "episode.create".equals(operation))
                        target = result.path("id").asText();
                    tx.execute(
                            "INSERT INTO \"VideoEpisodeCommand\""
                                + " (id,\"actorUserId\",\"clientRequestId\",\"projectId\",\"novelId\",\"episodeId\",operation,\"requestHash\",\"resultJson\",\"createdAt\")"
                                + " VALUES (?,?,?,?,?,?,?,?,?,?)",
                            ids.next(),
                            user,
                            client,
                            actualProject,
                            project.getNovelid(),
                            target,
                            operation,
                            requestHash,
                            result.toString(),
                            now());
                    return result;
                });
    }

    private ObjectNode read(String user, String episodeId, Work work) {
        return database.transactionResult(tx -> work.run(tx, owned(tx, user, episodeId, false)));
    }

    private Record owned(DSLContext tx, String user, String id, boolean lock) {
        Record row =
                tx.fetchOne(
                        "SELECT \"projectId\" FROM \"VideoEpisode\" WHERE id=? AND \"archivedAt\""
                            + " IS NULL",
                        id);
        if (row == null) throw missing("VIDEO_EPISODE_NOT_FOUND", "分集不存在");
        VideoDatabaseAccess.ownedProject(tx, user, row.get("projectId", String.class), lock);
        return requireEpisode(tx, id, lock);
    }

    private Record requireEpisode(DSLContext tx, String id, boolean lock) {
        Record row =
                tx.fetchOne(
                        "SELECT * FROM \"VideoEpisode\" WHERE id=? AND \"archivedAt\" IS NULL"
                                + (lock ? " FOR UPDATE" : ""),
                        id);
        if (row == null) throw missing("VIDEO_EPISODE_NOT_FOUND", "分集不存在");
        return row;
    }

    private Record requireDraft(DSLContext tx, String id) {
        Record row =
                tx.fetchOne("SELECT * FROM \"VideoEpisodeScriptDraft\" WHERE \"episodeId\"=?", id);
        if (row == null) throw conflict("VIDEO_SCRIPT_DRAFT_MISSING", "分集缺少工作稿");
        return row;
    }

    private ObjectNode list(DSLContext tx, String project, int revision) {
        return object(
                "projectId",
                project,
                "projectRevision",
                revision,
                "episodes",
                tx
                        .fetch(
                                "SELECT * FROM \"VideoEpisode\" WHERE \"projectId\"=? AND"
                                    + " \"archivedAt\" IS NULL ORDER BY ordinal,id",
                                project)
                        .stream()
                        .map(this::episode)
                        .toList());
    }

    private ObjectNode episode(Record r) {
        return object(
                "id",
                r.get("id"),
                "projectId",
                r.get("projectId"),
                "novelId",
                r.get("novelId"),
                "title",
                r.get("title"),
                "creativeIntent",
                r.get("creativeIntent"),
                "targetDurationSeconds",
                r.get("targetDurationSeconds"),
                "order",
                r.get("ordinal"),
                "revision",
                r.get("revision"),
                "currentSourceSetVersionId",
                r.get("currentSourceSetVersionId"),
                "currentScriptVersionId",
                r.get("currentScriptVersionId"),
                "currentStoryboardVersionId",
                r.get("currentStoryboardVersionId"),
                "currentProductionBaselineId",
                r.get("currentProductionBaselineId"),
                "productionRevision",
                r.get("productionRevision"),
                "latestDeliveryVersionId",
                r.get("latestDeliveryVersionId"),
                "deliveryRevision",
                r.get("deliveryRevision"),
                "createdAt",
                apiTime(r, "createdAt"),
                "updatedAt",
                apiTime(r, "updatedAt"));
    }

    private ObjectNode draft(DSLContext tx, String id, Map<String, String> mapping) {
        Record r = requireDraft(tx, id);
        Record adopted =
                tx.fetchOne(
                        "SELECT id FROM \"ReviewArtifact\" WHERE \"videoEpisodeId\"=? AND"
                            + " status='applied' AND"
                            + " \"payloadJson\"::jsonb->>'applyTarget'='video_episode_script_draft'"
                            + " ORDER BY \"appliedAt\" DESC,id DESC LIMIT 1",
                        id);
        return object(
                "episodeId",
                id,
                "revision",
                r.get("revision"),
                "sourceSetVersionId",
                r.get("sourceSetVersionId"),
                "baseScriptVersionId",
                r.get("basedOnScriptVersionId"),
                "document",
                parse(r, "documentJson"),
                "adoptedArtifactId",
                adopted == null ? null : adopted.get("id"),
                "nodeIdMappings",
                mapping,
                "updatedAt",
                apiTime(r, "updatedAt"));
    }

    private List<ObjectNode> sources(DSLContext tx, String episode) {
        return tx
                .fetch(
                        "SELECT id FROM \"VideoEpisodeSourceSetVersion\" WHERE \"episodeId\"=?"
                            + " ORDER BY \"versionNo\" DESC",
                        episode)
                .stream()
                .map(r -> sourceSet(tx, episode, r.get("id", String.class)))
                .toList();
    }

    private ObjectNode sourceSet(DSLContext tx, String episode, String id) {
        Record r =
                tx.fetchOne(
                        "SELECT * FROM \"VideoEpisodeSourceSetVersion\" WHERE id=? AND"
                            + " \"episodeId\"=?",
                        id,
                        episode);
        if (r == null) throw missing("VIDEO_SOURCE_SET_NOT_FOUND", "来源集合不存在或不属于本集");
        List<ObjectNode> items =
                tx
                        .fetch(
                                "SELECT * FROM \"VideoEpisodeSourceSnapshot\" WHERE"
                                    + " \"sourceSetVersionId\"=? ORDER BY ordinal",
                                id)
                        .stream()
                        .map(
                                s -> {
                                    Record current =
                                            tx.fetchOne(
                                                    "SELECT c.content,c.\"updatedAt\" FROM"
                                                        + " \"Chapter\" c JOIN \"VideoEpisode\" e"
                                                        + " ON e.\"novelId\"=c.\"novelId\" WHERE"
                                                        + " c.id=? AND e.id=?",
                                                    s.get("chapterId"),
                                                    episode);
                                    String currentHash =
                                            current == null
                                                    ? null
                                                    : sha(
                                                            current.get("content", String.class)
                                                                            == null
                                                                    ? ""
                                                                    : current.get(
                                                                            "content",
                                                                            String.class));
                                    return object(
                                            "id",
                                            s.get("id"),
                                            "chapterId",
                                            s.get("chapterId"),
                                            "chapterTitle",
                                            s.get("chapterTitle"),
                                            "chapterUpdatedAt",
                                            apiTime(s, "chapterUpdatedAt"),
                                            "sourceText",
                                            s.get("sourceText"),
                                            "sourceHash",
                                            s.get("sourceHash"),
                                            "ranges",
                                            json.readTree(s.get("rangesJson", String.class)),
                                            "sourceStatus",
                                            current == null
                                                    ? "missing"
                                                    : s.get("sourceHash").equals(currentHash)
                                                            ? "current"
                                                            : "updated",
                                            "currentChapterUpdatedAt",
                                            current == null ? null : apiTime(current, "updatedAt"),
                                            "currentChapterContentHash",
                                            currentHash);
                                })
                        .toList();
        return object(
                "id",
                id,
                "episodeId",
                episode,
                "versionNo",
                r.get("versionNo"),
                "basedOnVersionId",
                r.get("basedOnVersionId"),
                "contentHash",
                r.get("contentHash"),
                "sources",
                items,
                "createdAt",
                apiTime(r, "createdAt"));
    }

    private List<ObjectNode> versions(DSLContext tx, String episode) {
        return tx
                .fetch(
                        "SELECT id FROM \"VideoEpisodeScriptVersion\" WHERE \"episodeId\"=? ORDER"
                            + " BY \"versionNo\" DESC",
                        episode)
                .stream()
                .map(r -> version(tx, episode, r.get("id", String.class)))
                .toList();
    }

    private ObjectNode nullableVersion(DSLContext tx, String episode, String id) {
        return id == null ? null : version(tx, episode, id);
    }

    private ObjectNode version(DSLContext tx, String episode, String id) {
        Record r =
                tx.fetchOne(
                        "SELECT * FROM \"VideoEpisodeScriptVersion\" WHERE id=? AND"
                            + " \"episodeId\"=?",
                        id,
                        episode);
        if (r == null) throw missing("VIDEO_SCRIPT_VERSION_NOT_FOUND", "正式剧本版本不存在或不属于本集");
        return object(
                "id",
                id,
                "episodeId",
                episode,
                "versionNo",
                r.get("versionNo"),
                "basedOnVersionId",
                r.get("basedOnVersionId"),
                "sourceSetVersionId",
                r.get("sourceSetVersionId"),
                "document",
                parse(r, "documentJson"),
                "contentHash",
                r.get("contentHash"),
                "confirmationArtifactId",
                r.get("reviewArtifactId"),
                "createdAt",
                apiTime(r, "createdAt"));
    }

    private Record artifact(DSLContext tx, String episode, String id) {
        Record r =
                tx.fetchOne(
                        "SELECT * FROM \"ReviewArtifact\" WHERE id=? AND \"videoEpisodeId\"=?",
                        id,
                        episode);
        if (r == null) throw missing("VIDEO_SCRIPT_ARTIFACT_NOT_FOUND", "剧本审核记录不存在");
        return r;
    }

    private ObjectNode confirmation(DSLContext tx, String episode, String id) {
        Record r = artifact(tx, episode, id);
        ObjectNode p = parse(r, "payloadJson");
        requireTarget(p, "video_episode_script_confirmation");
        return object(
                "artifactId",
                id,
                "artifactRevision",
                r.get("revision"),
                "episodeId",
                episode,
                "episodeRevision",
                p.path("episodeRevision"),
                "draftRevision",
                p.path("draftRevision"),
                "sourceSetVersionId",
                p.path("sourceSetVersionId"),
                "document",
                p.path("document"),
                "confirmationHash",
                p.path("confirmationHash"),
                "createdAt",
                apiTime(r, "createdAt"));
    }

    private List<ObjectNode> candidates(DSLContext tx, String episode) {
        return tx
                .fetch(
                        "SELECT * FROM \"ReviewArtifact\" WHERE \"videoEpisodeId\"=? AND"
                            + " \"workflowRunId\" IS NOT NULL ORDER BY \"createdAt\" DESC",
                        episode)
                .stream()
                .filter(
                        r ->
                                "video_episode_script_draft"
                                        .equals(
                                                parse(r, "payloadJson")
                                                        .path("applyTarget")
                                                        .asText()))
                .map(this::candidate)
                .toList();
    }

    private ObjectNode candidate(Record r) {
        ObjectNode p = parse(r, "payloadJson");
        return object(
                "artifactId",
                r.get("id"),
                "workflowRunId",
                r.get("workflowRunId"),
                "episodeId",
                r.get("videoEpisodeId"),
                "revision",
                r.get("revision"),
                "status",
                r.get("status", String.class),
                "title",
                r.get("title"),
                "summary",
                r.get("summary"),
                "expectedDraftRevision",
                p.path("expectedDraftRevision"),
                "sourceSetVersionId",
                p.path("sourceSetVersionId"),
                "baseScriptVersionId",
                p.path("baseScriptVersionId"),
                "document",
                p.path("document"),
                "review",
                p.hasNonNull("review") ? p.path("review") : null,
                "reviewFindings",
                p.has("reviewFindings") ? p.path("reviewFindings") : json.createArrayNode(),
                "createdAt",
                apiTime(r, "createdAt"));
    }

    private String insertArtifact(
            DSLContext tx, Record ep, String run, String title, JsonNode payload) {
        String id = ids.next();
        tx.execute(
                "INSERT INTO \"ReviewArtifact\""
                    + " (id,\"novelId\",\"videoEpisodeId\",\"workflowRunId\",\"artifactKey\",kind,status,title,\"payloadJson\",revision,\"createdAt\",\"updatedAt\")"
                    + " VALUES (?,?,?,?,?,'video_episode_script','awaiting_user',?,?,1,?,?)",
                id,
                ep.get("novelId"),
                ep.get("id"),
                run,
                "video-episode:" + ep.get("id"),
                title,
                payload.toString(),
                now(),
                now());
        tx.execute(
                "INSERT INTO \"ReviewArtifactRevision\""
                    + " (id,\"artifactId\",revision,\"payloadJson\",\"createdAt\") VALUES"
                    + " (?,?,1,?,?)",
                ids.next(),
                id,
                payload.toString(),
                now());
        return id;
    }

    private void applyArtifact(DSLContext tx, String id) {
        tx.execute(
                "UPDATE \"ReviewArtifact\" SET status='applied',\"appliedAt\"=?,\"updatedAt\"=?"
                    + " WHERE id=?",
                now(),
                now(),
                id);
    }

    private JsonNode normalize(
            DSLContext tx,
            Record ep,
            String sourceSet,
            JsonNode input,
            JsonNode existing,
            Map<String, String> mapping) {
        if (!input.isObject()
                || !"video-episode-script/1.0".equals(input.path("schemaVersion").asText()))
            throw invalid("VIDEO_SCRIPT_DOCUMENT_INVALID", "剧本文档版本无效");
        ObjectNode doc = (ObjectNode) input.deepCopy();
        Map<String, String> permitted = new HashMap<>();
        collectNodes(existing, permitted);
        Set<String> used = new HashSet<>();
        for (JsonNode scene : doc.path("scenes")) {
            assignId(scene, "scene", permitted, used, mapping);
            for (JsonNode character : scene.path("characterIds"))
                requireEntity(tx, ep, character.asText(), true);
            for (JsonNode line : scene.path("lines")) {
                assignId(line, "line", permitted, used, mapping);
                String speaker = text(line, "speakerId");
                if (speaker != null) requireEntity(tx, ep, speaker, true);
                if ("dialogue".equals(line.path("kind").asText()) && speaker == null)
                    throw invalid("VIDEO_SCRIPT_SPEAKER_REQUIRED", "对白须绑定角色");
                if ("action".equals(line.path("kind").asText()) && speaker != null)
                    throw invalid("VIDEO_SCRIPT_SPEAKER_INVALID", "行动节点不能绑定说话人");
                for (JsonNode ref : line.path("sourceRefs")) validateSourceRef(tx, sourceSet, ref);
            }
        }
        Set<String> states = new HashSet<>();
        for (JsonNode state : doc.path("endingStates")) {
            if (!states.add(requiredText(state, "key")))
                throw invalid("VIDEO_SCRIPT_STATE_DUPLICATE", "结尾状态 key 不能重复");
            for (JsonNode entity : state.path("entityIds"))
                requireEntity(tx, ep, entity.asText(), false);
        }
        for (JsonNode dependency : doc.path("dependencies")) {
            ObjectNode d = (ObjectNode) dependency;
            String sceneId = resolve(mapping, requiredText(d, "consumerSceneId")),
                    lineId = resolve(mapping, text(d, "consumerLineId"));
            d.put("consumerSceneId", sceneId);
            if (lineId != null) d.put("consumerLineId", lineId);
            JsonNode consumer = null;
            for (JsonNode scene : doc.path("scenes"))
                if (sceneId.equals(text(scene, "id"))) consumer = scene;
            if (consumer == null) throw invalid("VIDEO_DEPENDENCY_TARGET_INVALID", "承接必须属于当前剧本场次");
            if (lineId != null) {
                boolean found = false;
                for (JsonNode line : consumer.path("lines"))
                    if (lineId.equals(text(line, "id"))) found = true;
                if (!found) throw invalid("VIDEO_DEPENDENCY_TARGET_INVALID", "承接台词不属于指定场次");
            }
            producerState(tx, ep, d);
        }
        return doc;
    }

    private void assignId(
            JsonNode node,
            String kind,
            Map<String, String> permitted,
            Set<String> used,
            Map<String, String> mapping) {
        String id = text(node, "id"), temporary = text(node, "tempKey");
        if ((id == null) == (temporary == null))
            throw invalid("VIDEO_SCRIPT_NODE_ID_INVALID", "节点必须提供已有 id 或新建 tempKey");
        String original = id == null ? temporary : id;
        if (!used.add(original)) throw invalid("VIDEO_SCRIPT_NODE_ID_DUPLICATE", "节点身份不能重复");
        if (id == null) {
            id = ids.next();
            mapping.put(temporary, id);
        } else if (!kind.equals(permitted.get(id)))
            throw invalid("VIDEO_SCRIPT_NODE_ID_INVALID", "不能伪造其他场次、剧本或已删除节点的身份");
        ((ObjectNode) node).put("id", id);
        ((ObjectNode) node).putNull("tempKey");
    }

    private void collectNodes(JsonNode doc, Map<String, String> result) {
        for (JsonNode scene : doc.path("scenes")) {
            if (text(scene, "id") != null) result.put(text(scene, "id"), "scene");
            for (JsonNode line : scene.path("lines"))
                if (text(line, "id") != null) result.put(text(line, "id"), "line");
        }
    }

    private void requireEntity(DSLContext tx, Record ep, String id, boolean characterOnly) {
        Record row =
                characterOnly
                        ? tx.fetchOne(
                                "SELECT id FROM \"Character\" WHERE id=? AND \"novelId\"=?",
                                id,
                                ep.get("novelId"))
                        : tx.fetchOne(
                                "SELECT id FROM \"Character\" WHERE id=? AND \"novelId\"=? UNION"
                                    + " ALL SELECT id FROM \"Location\" WHERE id=? AND"
                                    + " \"novelId\"=? UNION ALL SELECT id FROM \"Item\" WHERE id=?"
                                    + " AND \"novelId\"=?",
                                id,
                                ep.get("novelId"),
                                id,
                                ep.get("novelId"),
                                id,
                                ep.get("novelId"));
        if (row == null) throw invalid("VIDEO_SCRIPT_ENTITY_INVALID", "剧本角色或状态实体不属于当前小说");
    }

    private void validateSourceRef(DSLContext tx, String sourceSet, JsonNode ref) {
        Record snapshot =
                tx.fetchOne(
                        "SELECT \"sourceText\",\"rangesJson\" FROM \"VideoEpisodeSourceSnapshot\""
                            + " WHERE id=? AND \"sourceSetVersionId\"=?",
                        text(ref, "sourceSnapshotId"),
                        sourceSet);
        if (snapshot == null) throw invalid("VIDEO_SCRIPT_SOURCE_INVALID", "来源锚点不属于当前来源集合");
        int start = ref.path("start").asInt(-1), end = ref.path("end").asInt(-1);
        boolean contained = false;
        for (JsonNode range : json.readTree(snapshot.get("rangesJson", String.class)))
            if (start >= range.path("start").asInt()
                    && end <= range.path("end").asInt()
                    && end > start) contained = true;
        if (!contained) throw invalid("VIDEO_SCRIPT_SOURCE_RANGE_INVALID", "剧本来源锚点超出作者选定范围");
    }

    private JsonNode producerState(DSLContext tx, Record consumer, JsonNode dependency) {
        if (consumer.get("id").equals(text(dependency, "producerEpisodeId")))
            throw invalid("VIDEO_DEPENDENCY_SELF_REFERENCE", "跨集承接不能引用本集自身");
        Record producer =
                tx.fetchOne(
                        "SELECT \"documentJson\" FROM \"VideoEpisodeScriptVersion\" WHERE id=? AND"
                            + " \"episodeId\"=? AND \"projectId\"=?",
                        text(dependency, "producerScriptVersionId"),
                        text(dependency, "producerEpisodeId"),
                        consumer.get("projectId"));
        if (producer == null) throw invalid("VIDEO_DEPENDENCY_SOURCE_INVALID", "承接必须引用同项目已确认的剧本版本");
        for (JsonNode state : parse(producer, "documentJson").path("endingStates"))
            if (state.path("key").asText().equals(text(dependency, "producerStateKey")))
                return state;
        throw invalid("VIDEO_DEPENDENCY_STATE_MISSING", "来源版本没有指定结尾状态");
    }

    private void freezeDependencies(DSLContext tx, Record ep, String version, JsonNode doc) {
        for (JsonNode d : doc.path("dependencies"))
            tx.execute(
                    "INSERT INTO \"VideoEpisodeDependency\""
                        + " (id,\"projectId\",\"consumerEpisodeId\",\"consumerScriptVersionId\",\"consumerSceneId\",\"consumerLineId\",\"producerEpisodeId\",\"producerScriptVersionId\",\"producerStateKey\",\"narrativeTime\",description,\"sourceHash\")"
                        + " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                    ids.next(),
                    ep.get("projectId"),
                    ep.get("id"),
                    version,
                    text(d, "consumerSceneId"),
                    text(d, "consumerLineId"),
                    text(d, "producerEpisodeId"),
                    text(d, "producerScriptVersionId"),
                    text(d, "producerStateKey"),
                    requiredText(d, "narrativeTime"),
                    requiredText(d, "description"),
                    hash(producerState(tx, ep, d)));
    }

    private List<ObjectNode> dependencies(DSLContext tx, Record ep) {
        return tx
                .fetch(
                        "SELECT * FROM \"VideoEpisodeDependency\" WHERE"
                            + " \"consumerScriptVersionId\"=? ORDER BY id",
                        ep.get("currentScriptVersionId"))
                .stream()
                .map(
                        r ->
                                object(
                                        "id",
                                        r.get("id"),
                                        "consumerEpisodeId",
                                        r.get("consumerEpisodeId"),
                                        "consumerScriptVersionId",
                                        r.get("consumerScriptVersionId"),
                                        "producerEpisodeId",
                                        r.get("producerEpisodeId"),
                                        "producerScriptVersionId",
                                        r.get("producerScriptVersionId"),
                                        "producerStateKey",
                                        r.get("producerStateKey"),
                                        "consumerSceneId",
                                        r.get("consumerSceneId"),
                                        "consumerLineId",
                                        r.get("consumerLineId"),
                                        "narrativeTime",
                                        r.get("narrativeTime"),
                                        "description",
                                        r.get("description"),
                                        "producerStateHash",
                                        r.get("sourceHash")))
                .toList();
    }

    private void createImpacts(DSLContext tx, Record ep, String before, String after) {
        Record beforeVersion =
                tx.fetchOne(
                        "SELECT \"documentJson\" FROM \"VideoEpisodeScriptVersion\" WHERE id=?"
                                + " AND \"episodeId\"=?",
                        before,
                        ep.get("id"));
        Record afterVersion =
                tx.fetchOne(
                        "SELECT \"documentJson\" FROM \"VideoEpisodeScriptVersion\" WHERE id=?"
                                + " AND \"episodeId\"=?",
                        after,
                        ep.get("id"));
        if (beforeVersion == null || afterVersion == null) {
            throw invalid("VIDEO_IMPACT_SOURCE_MISSING", "影响复核缺少确切的前后剧本版本");
        }
        Map<String, JsonNode> beforeStates = endingStates(parse(beforeVersion, "documentJson"));
        Map<String, JsonNode> afterStates = endingStates(parse(afterVersion, "documentJson"));
        Map<String, List<Record>> byTarget = new LinkedHashMap<>();
        for (Record dependency :
                tx.fetch(
                        "SELECT d.*,e.\"productionRevision\",e.\"currentProductionBaselineId\""
                                + " FROM \"VideoEpisodeDependency\" d JOIN \"VideoEpisode\" e ON"
                                + " e.id=d.\"consumerEpisodeId\" AND"
                                + " e.\"currentScriptVersionId\"=d.\"consumerScriptVersionId\""
                                + " WHERE d.\"producerScriptVersionId\"=? ORDER BY"
                                + " d.\"consumerEpisodeId\",d.id",
                        before)) {
            String stateKey = dependency.get("producerStateKey", String.class);
            JsonNode afterState = afterStates.get(stateKey);
            String afterHash = afterState == null ? null : hash(afterState);
            if (Objects.equals(dependency.get("sourceHash", String.class), afterHash)) {
                continue;
            }
            String targetKey =
                    dependency.get("consumerEpisodeId", String.class)
                            + "\u0000"
                            + dependency.get("consumerScriptVersionId", String.class);
            byTarget.computeIfAbsent(targetKey, ignored -> new ArrayList<>()).add(dependency);
        }
        for (List<Record> dependencies : byTarget.values()) {
            Record target = dependencies.get(0);
            ArrayNode items = json.createArrayNode();
            for (Record dependency : dependencies) {
                String stateKey = dependency.get("producerStateKey", String.class);
                JsonNode beforeState = beforeStates.get(stateKey);
                JsonNode afterState = afterStates.get(stateKey);
                if (beforeState == null) {
                    throw invalid(
                            "VIDEO_IMPACT_SOURCE_MISSING", "承接依据在前一正式剧本中已不存在");
                }
                ObjectNode item =
                        object(
                                "itemId",
                                dependency.get("id"),
                                "dependencyId",
                                dependency.get("id"),
                                "kind",
                                "direct_dependency_changed",
                                "changeType",
                                afterState == null ? "removed" : "changed",
                                "producerStateKey",
                                stateKey,
                                "beforeState",
                                beforeState,
                                "afterState",
                                afterState,
                                "consumerSceneId",
                                dependency.get("consumerSceneId"),
                                "consumerLineId",
                                dependency.get("consumerLineId"),
                                "narrativeTime",
                                dependency.get("narrativeTime"),
                                "description",
                                dependency.get("description"),
                                "beforeStateHash",
                                dependency.get("sourceHash"),
                                "afterStateHash",
                                afterState == null ? null : hash(afterState));
                item.put("itemHash", hash(item));
                items.add(item);
            }
            ObjectNode report =
                    object(
                            "schemaVersion",
                            "video-impact-review/1.0",
                            "kind",
                            "explicit_dependency_changed",
                            "requiresAuthorReview",
                            true,
                            "producerEpisodeId",
                            ep.get("id"),
                            "beforeScriptVersionId",
                            before,
                            "afterScriptVersionId",
                            after,
                            "targetEpisodeId",
                            target.get("consumerEpisodeId"),
                            "targetScriptVersionId",
                            target.get("consumerScriptVersionId"),
                            "producerProductionRevision",
                            ep.get("productionRevision"),
                            "targetProductionRevision",
                            target.get("productionRevision"),
                            "producerBaselineId",
                            ep.get("currentProductionBaselineId"),
                            "targetBaselineId",
                            target.get("currentProductionBaselineId"),
                            "items",
                            items);
            tx.execute(
                    "INSERT INTO \"VideoImpactReview\""
                        + " (id,\"projectId\",\"producerEpisodeId\",\"beforeScriptVersionId\",\"afterScriptVersionId\",\"targetEpisodeId\",\"targetScriptVersionId\",\"producerProductionRevision\",\"targetProductionRevision\",\"producerBaselineId\",\"targetBaselineId\",\"reportJson\",\"createdAt\",\"updatedAt\")"
                        + " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    ids.next(),
                    ep.get("projectId"),
                    ep.get("id"),
                    before,
                    after,
                    target.get("consumerEpisodeId"),
                    target.get("consumerScriptVersionId"),
                    ep.get("productionRevision"),
                    target.get("productionRevision"),
                    ep.get("currentProductionBaselineId"),
                    target.get("currentProductionBaselineId"),
                    report.toString(),
                    now(),
                    now());
        }
    }

    private Map<String, JsonNode> endingStates(JsonNode document) {
        Map<String, JsonNode> states = new LinkedHashMap<>();
        for (JsonNode state : document.path("endingStates")) {
            states.put(state.path("key").asText(), state);
        }
        return states;
    }

    private void validateRanges(JsonNode ranges, String source) {
        int length = source.codePointCount(0, source.length());
        if (!ranges.isArray() || ranges.isEmpty() || ranges.size() > 100)
            throw invalid("VIDEO_SOURCE_RANGE_INVALID", "来源选区应为 1 至 100 个范围");
        List<JsonNode> ordered = new ArrayList<>();
        for (JsonNode range : ranges) {
            int start = range.path("start").asInt(-1), end = range.path("end").asInt();
            if (start < 0 || end <= start || end > length)
                throw invalid("VIDEO_SOURCE_RANGE_INVALID", "来源范围超出完整章节 Unicode 码点");
            ordered.add(range);
        }
        ordered.sort(
                java.util.Comparator.comparingInt((JsonNode r) -> r.path("start").asInt())
                        .thenComparingInt(r -> r.path("end").asInt()));
        int previousEnd = -1;
        for (JsonNode range : ordered) {
            if (range.path("start").asInt() < previousEnd)
                throw invalid("VIDEO_SOURCE_RANGE_OVERLAP", "来源选区重叠，请明确调整范围；不会自动合并");
            previousEnd = range.path("end").asInt();
        }
    }

    private void requireConfirmable(JsonNode doc) {
        if (doc.path("scenes").isEmpty()) throw invalid("VIDEO_SCRIPT_EMPTY", "空工作稿不能确认为正式剧本");
        for (JsonNode scene : doc.path("scenes"))
            if (scene.path("title").asText().isBlank() || scene.path("lines").isEmpty())
                throw invalid("VIDEO_SCRIPT_EMPTY_SCENE", "正式剧本场次须有标题和内容");
    }

    private void requireTarget(JsonNode payload, String target) {
        if (!target.equals(payload.path("applyTarget").asText()))
            throw invalid("VIDEO_SCRIPT_ARTIFACT_TARGET_INVALID", "审核记录不属于此操作");
    }

    private void revision(Record row, int expected, String code) {
        if (row.get("revision", Integer.class) != expected)
            throw conflict(code, "版本已变化，请保留输入并重新读取");
    }

    private int nextVersion(DSLContext tx, String table, String episode) {
        return tx.fetchOne(
                        "SELECT COALESCE(MAX(\"versionNo\"),0)+1 n FROM \""
                                + table
                                + "\" WHERE \"episodeId\"=?",
                        episode)
                .get("n", Integer.class);
    }

    private void bumpProject(DSLContext tx, String id) {
        tx.execute(
                "UPDATE \"VideoProject\" SET revision=revision+1,\"updatedAt\"=? WHERE id=?",
                now(),
                id);
    }

    private ObjectNode emptyDocument(JsonNode request) {
        return object(
                "schemaVersion",
                "video-episode-script/1.0",
                "overview",
                object(
                        "summary",
                        "",
                        "creativeIntent",
                        request.path("creativeIntent").asText(""),
                        "targetDurationSeconds",
                        nullableInt(request, "targetDurationSeconds")),
                "scenes",
                List.of(),
                "endingStates",
                List.of(),
                "dependencies",
                List.of());
    }

    private ObjectNode parse(Record row, String column) {
        return (ObjectNode) json.readTree(row.get(column, String.class));
    }

    private ObjectNode object(Object... values) {
        ObjectNode result = json.createObjectNode();
        for (int i = 0; i < values.length; i += 2) {
            Object value = values[i + 1];
            result.set(
                    (String) values[i],
                    json.valueToTree(
                            value instanceof OffsetDateTime time ? time.toString() : value));
        }
        return result;
    }

    private LocalDateTime now() {
        return DatabaseTimestamp.now(clock);
    }

    private static OffsetDateTime apiTime(Record row, String column) {
        return DatabaseTimestamp.api(row.get(column, LocalDateTime.class));
    }

    private static String resolve(Map<String, String> map, String value) {
        return value == null ? null : map.getOrDefault(value, value);
    }

    private static String text(JsonNode node, String key) {
        return node.hasNonNull(key) ? node.path(key).asText() : null;
    }

    private static Integer nullableInt(JsonNode node, String key) {
        return node.hasNonNull(key) ? node.path(key).asInt() : null;
    }

    private static String requiredText(JsonNode node, String key) {
        String result = text(node, key);
        if (result == null || result.isBlank())
            throw invalid("VIDEO_EPISODE_INPUT_INVALID", key + " 不能为空");
        return result.strip();
    }

    private static String resultType(String operation) {
        if (operation.contains("production-baseline")) return "production_baseline";
        if (operation.contains("take-adoption")) return "take_adoption";
        if (operation.contains("storyboard")) {
            if (operation.endsWith("prepare")) return "storyboard_confirmation";
            if (operation.endsWith("approve")) return "storyboard_version";
            if (operation.endsWith("run")) return "storyboard_run";
            return "storyboard_draft";
        }
        return operation.endsWith("reorder")
                ? "episode_list"
                : operation.endsWith("prepare")
                        ? "script_confirmation"
                        : operation.endsWith("approve")
                                ? "script_version"
                                : operation.endsWith("save") || operation.endsWith("adopt")
                                        ? "script_draft"
                                        : operation.contains("source") ? "source_set" : "episode";
    }

    private String hash(JsonNode node) {
        return sha(canonical(node));
    }

    private String canonical(JsonNode node) {
        if (node.isObject()) {
            var sorted = new java.util.TreeMap<String, JsonNode>();
            node.properties().forEach(e -> sorted.put(e.getKey(), e.getValue()));
            return "{"
                    + sorted.entrySet().stream()
                            .map(
                                    e ->
                                            json.writeValueAsString(e.getKey())
                                                    + ":"
                                                    + canonical(e.getValue()))
                            .collect(java.util.stream.Collectors.joining(","))
                    + "}";
        }
        if (node.isArray()) {
            List<String> children = new ArrayList<>();
            node.forEach(n -> children.add(canonical(n)));
            return "[" + String.join(",", children) + "]";
        }
        return node.toString();
    }

    private static String sha(String value) {
        try {
            return HexFormat.of()
                    .formatHex(
                            MessageDigest.getInstance("SHA-256")
                                    .digest(value.getBytes(StandardCharsets.UTF_8)));
        } catch (java.security.NoSuchAlgorithmException e) {
            throw new IllegalStateException(e);
        }
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

    @FunctionalInterface
    private interface Work {
        ObjectNode run(DSLContext tx, Record episode);
    }
}
