package cn.inkforge.core.styles.infrastructure;

import static cn.inkforge.core.db.generated.Tables.NOVEL;
import static cn.inkforge.core.db.generated.Tables.STYLEPORTRAITTASK;
import static cn.inkforge.core.db.generated.Tables.STYLEREFERENCE;
import static cn.inkforge.core.db.generated.Tables.WRITINGSTYLE;

import cn.inkforge.core.db.generated.enums.Stylesourcetype;
import cn.inkforge.core.db.generated.tables.records.NovelRecord;
import cn.inkforge.core.db.generated.tables.records.StyleportraittaskRecord;
import cn.inkforge.core.db.generated.tables.records.StylereferenceRecord;
import cn.inkforge.core.db.generated.tables.records.WritingstyleRecord;
import cn.inkforge.core.platform.db.CoreDatabase;
import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.platform.id.CuidV1Generator;
import cn.inkforge.core.platform.time.DatabaseTimestamp;
import cn.inkforge.core.styles.application.StoredStyleFile;
import cn.inkforge.core.styles.application.StyleRepository;
import cn.inkforge.core.styles.application.StyleService;
import cn.inkforge.core.styles.domain.ApplyStyleResult;
import cn.inkforge.core.styles.domain.PortraitDispatchRecord;
import cn.inkforge.core.styles.domain.PortraitDispatchStatus;
import cn.inkforge.core.styles.domain.PortraitSection;
import cn.inkforge.core.styles.domain.PortraitSource;
import cn.inkforge.core.styles.domain.PortraitSuccessData;
import cn.inkforge.core.styles.domain.PortraitTaskSnapshot;
import cn.inkforge.core.styles.domain.StyleReferenceSnapshot;
import cn.inkforge.core.styles.domain.StyleSnapshot;
import java.time.Clock;
import java.time.LocalDateTime;
import java.time.OffsetDateTime;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import org.jooq.DSLContext;
import org.jooq.impl.DSL;

/**
 * 基于冻结 PostgreSQL 结构的私有文风与画像任务仓储。
 *
 * <p>参考文件由应用层先写入受控存储，本仓储登记数据库路径并返回待清理路径；画像任务与画像字段在同一事务内
 * 收敛。每个文风同一时刻只允许一个活动画像任务，小说应用文风则对 {@code appliedStyleId} 做 CAS。
 */
final class JooqStyleRepository implements StyleRepository {

    private final CoreDatabase database;
    private final CuidV1Generator ids;
    private final Clock clock;

    JooqStyleRepository(CoreDatabase database, CuidV1Generator ids, Clock clock) {
        this.database = Objects.requireNonNull(database);
        this.ids = Objects.requireNonNull(ids);
        this.clock = Objects.requireNonNull(clock);
    }

    @Override
    public List<StyleSnapshot> list(String userId) {
        DSLContext context = database.dsl();
        List<WritingstyleRecord> styles = context.selectFrom(WRITINGSTYLE)
                .where(WRITINGSTYLE.USERID.eq(userId))
                .orderBy(WRITINGSTYLE.CREATEDAT.desc(), WRITINGSTYLE.ID.asc())
                .fetch();
        if (styles.isEmpty()) return List.of();
        List<String> styleIds = styles.stream().map(WritingstyleRecord::getId).toList();
        Map<String, List<StyleReferenceSnapshot>> references = new LinkedHashMap<>();
        context.selectFrom(STYLEREFERENCE)
                .where(STYLEREFERENCE.STYLEID.in(styleIds))
                .orderBy(
                        STYLEREFERENCE.STYLEID.asc(),
                        STYLEREFERENCE.CREATEDAT.asc(),
                        STYLEREFERENCE.ID.asc())
                .forEach(value -> references
                        .computeIfAbsent(value.getStyleid(), ignored -> new ArrayList<>())
                        .add(reference(value)));
        Map<String, List<PortraitTaskSnapshot>> tasks = new LinkedHashMap<>();
        context.selectFrom(STYLEPORTRAITTASK)
                .where(STYLEPORTRAITTASK.STYLEID.in(styleIds))
                .orderBy(
                        STYLEPORTRAITTASK.STYLEID.asc(),
                        STYLEPORTRAITTASK.CREATEDAT.asc(),
                        STYLEPORTRAITTASK.ID.asc())
                .forEach(value -> tasks
                        .computeIfAbsent(value.getStyleid(), ignored -> new ArrayList<>())
                        .add(task(value)));
        return styles.stream()
                .map(value -> style(
                        value,
                        references.getOrDefault(value.getId(), List.of()),
                        tasks.getOrDefault(value.getId(), List.of())))
                .toList();
    }

    @Override
    public StyleSnapshot create(String userId, String name) {
        LocalDateTime now = DatabaseTimestamp.now(clock);
        WritingstyleRecord value = database.dsl().insertInto(WRITINGSTYLE)
                .set(WRITINGSTYLE.ID, ids.next())
                .set(WRITINGSTYLE.USERID, userId)
                .set(WRITINGSTYLE.NAME, name)
                .set(WRITINGSTYLE.SOURCETYPE, Stylesourcetype.agent)
                .set(WRITINGSTYLE.ORIGINALCHARCOUNT, 0)
                .set(WRITINGSTYLE.USEDCHARCOUNT, 0)
                .set(WRITINGSTYLE.TRUNCATED, false)
                .set(WRITINGSTYLE.CREATEDAT, now)
                .set(WRITINGSTYLE.UPDATEDAT, now)
                .returning()
                .fetchSingle();
        return style(value, List.of(), List.of());
    }

    @Override
    public String reserveReference(String userId, String styleId) {
        requireOwnedStyle(database.dsl(), userId, styleId, false);
        return ids.next();
    }

    @Override
    public StyleReferenceSnapshot createReference(
            String userId, String styleId, String referenceId, StoredStyleFile file) {
        return database.dsl().transactionResult(configuration -> {
            DSLContext transaction = DSL.using(configuration);
            requireOwnedStyle(transaction, userId, styleId, true);
            StylereferenceRecord value = transaction.insertInto(STYLEREFERENCE)
                    .set(STYLEREFERENCE.ID, referenceId)
                    .set(STYLEREFERENCE.STYLEID, styleId)
                    .set(STYLEREFERENCE.FILENAME, file.filename())
                    .set(STYLEREFERENCE.FILEPATH, file.databasePath())
                    .set(STYLEREFERENCE.CHARCOUNT, file.charCount())
                    .set(STYLEREFERENCE.STATUS, "ready")
                    .set(STYLEREFERENCE.ERRORMESSAGE, (String) null)
                    .set(STYLEREFERENCE.CREATEDAT, DatabaseTimestamp.now(clock))
                    .returning()
                    .fetchSingle();
            return reference(value);
        });
    }

    @Override
    public String deleteReference(String userId, String styleId, String referenceId) {
        return database.dsl().transactionResult(configuration -> {
            DSLContext transaction = DSL.using(configuration);
            requireOwnedStyle(transaction, userId, styleId, true);
            StylereferenceRecord value = transaction.selectFrom(STYLEREFERENCE)
                    .where(STYLEREFERENCE.ID.eq(referenceId)
                            .and(STYLEREFERENCE.STYLEID.eq(styleId)))
                    .forUpdate()
                    .fetchOne();
            if (value == null) {
                throw new ApiException(
                        404, "STYLE_REFERENCE_NOT_FOUND", "文风参考资料不存在");
            }
            transaction.deleteFrom(STYLEREFERENCE)
                    .where(STYLEREFERENCE.ID.eq(referenceId))
                    .execute();
            return value.getFilepath();
        });
    }

    @Override
    public List<String> deleteStyle(String userId, String styleId) {
        return database.dsl().transactionResult(configuration -> {
            DSLContext transaction = DSL.using(configuration);
            requireOwnedStyle(transaction, userId, styleId, true);
            List<String> paths = transaction.select(STYLEREFERENCE.FILEPATH)
                    .from(STYLEREFERENCE)
                    .where(STYLEREFERENCE.STYLEID.eq(styleId))
                    .orderBy(STYLEREFERENCE.ID.asc())
                    .fetch(STYLEREFERENCE.FILEPATH);
            transaction.deleteFrom(WRITINGSTYLE)
                    .where(WRITINGSTYLE.ID.eq(styleId))
                    .execute();
            return List.copyOf(paths);
        });
    }

    @Override
    public PortraitTaskSnapshot createPortraitTask(
            String userId, String styleId, PortraitSection section) {
        return database.dsl().transactionResult(configuration -> {
            DSLContext transaction = DSL.using(configuration);
            WritingstyleRecord style = requireOwnedStyle(transaction, userId, styleId, true);
            String ready = transaction.select(STYLEREFERENCE.ID)
                    .from(STYLEREFERENCE)
                    .where(STYLEREFERENCE.STYLEID.eq(styleId)
                            .and(STYLEREFERENCE.STATUS.eq("ready")))
                    .limit(1)
                    .fetchOne(STYLEREFERENCE.ID);
            if (ready == null) {
                throw new ApiException(
                        409, "STYLE_REFERENCE_REQUIRED", "请先上传可用的文风参考资料");
            }
            String active = transaction.select(STYLEPORTRAITTASK.ID)
                    .from(STYLEPORTRAITTASK)
                    .where(STYLEPORTRAITTASK.STYLEID.eq(styleId)
                            .and(STYLEPORTRAITTASK.STATUS.in("pending", "processing")))
                    .limit(1)
                    .fetchOne(STYLEPORTRAITTASK.ID);
            // 单活动任务保证多个分节回调不会同时覆盖同一组画像字段。
            if (active != null) {
                throw new ApiException(
                        409, "PORTRAIT_TASK_ACTIVE", "该文风已有画像任务正在执行");
            }
            if (style.getErrormessage() != null) {
                style.setErrormessage(null);
                style.setUpdatedat(DatabaseTimestamp.next(clock, style.getUpdatedat()));
                style.store();
            }
            LocalDateTime now = DatabaseTimestamp.now(clock);
            StyleportraittaskRecord created = transaction.insertInto(STYLEPORTRAITTASK)
                    .set(STYLEPORTRAITTASK.ID, ids.next())
                    .set(STYLEPORTRAITTASK.STYLEID, styleId)
                    .set(STYLEPORTRAITTASK.SECTION, section == null ? null : section.value())
                    .set(STYLEPORTRAITTASK.STATUS, "pending")
                    .set(STYLEPORTRAITTASK.ERRORMESSAGE, (String) null)
                    .set(STYLEPORTRAITTASK.CREATEDAT, now)
                    .set(STYLEPORTRAITTASK.UPDATEDAT, now)
                    .returning()
                    .fetchSingle();
            return task(created);
        });
    }

    @Override
    public List<PortraitSource> portraitSources(String styleId, String taskId) {
        DSLContext context = database.dsl();
        String boundStyle = context.select(STYLEPORTRAITTASK.STYLEID)
                .from(STYLEPORTRAITTASK)
                .where(STYLEPORTRAITTASK.ID.eq(taskId)
                        .and(STYLEPORTRAITTASK.STYLEID.eq(styleId)))
                .fetchOne(STYLEPORTRAITTASK.STYLEID);
        if (boundStyle == null) throw taskNotFound();
        return context.select(
                        STYLEREFERENCE.FILEPATH,
                        STYLEREFERENCE.FILENAME,
                        STYLEREFERENCE.CHARCOUNT)
                .from(STYLEREFERENCE)
                .where(STYLEREFERENCE.STYLEID.eq(styleId)
                        .and(STYLEREFERENCE.STATUS.eq("ready")))
                .orderBy(STYLEREFERENCE.CREATEDAT.asc(), STYLEREFERENCE.ID.asc())
                .fetch(value -> new PortraitSource(
                        value.get(STYLEREFERENCE.FILEPATH),
                        value.get(STYLEREFERENCE.FILENAME),
                        value.get(STYLEREFERENCE.CHARCOUNT)));
    }

    @Override
    public PortraitTaskSnapshot getPortraitTask(String userId, String taskId) {
        StyleportraittaskRecord value = database.dsl().select(STYLEPORTRAITTASK.fields())
                .from(STYLEPORTRAITTASK)
                .join(WRITINGSTYLE)
                .on(WRITINGSTYLE.ID.eq(STYLEPORTRAITTASK.STYLEID))
                .where(STYLEPORTRAITTASK.ID.eq(taskId)
                        .and(WRITINGSTYLE.USERID.eq(userId)))
                .fetchOneInto(STYLEPORTRAITTASK);
        if (value == null) throw taskNotFound();
        return task(value);
    }

    @Override
    public PortraitTaskSnapshot transitionPortraitTask(
            String styleId,
            String taskId,
            String target,
            PortraitSuccessData data,
            PortraitSection expectedSection,
            boolean validateSection) {
        return database.dsl().transactionResult(configuration -> {
            DSLContext transaction = DSL.using(configuration);
            StyleportraittaskRecord task = transaction.selectFrom(STYLEPORTRAITTASK)
                    .where(STYLEPORTRAITTASK.ID.eq(taskId))
                    .forUpdate()
                    .fetchOne();
            if (task == null) throw taskNotFound();
            if (!task.getStyleid().equals(styleId)) {
                throw new ApiException(
                        409, "PORTRAIT_TASK_MISMATCH", "画像任务与文风不匹配");
            }
            PortraitSection currentSection = task.getSection() == null
                    ? null
                    : PortraitSection.from(task.getSection());
            if (validateSection && currentSection != expectedSection) {
                throw new ApiException(
                        409,
                        "PORTRAIT_TASK_SECTION_MISMATCH",
                        "画像任务分节与完成结果不匹配");
            }
            WritingstyleRecord style = requireStyle(transaction, styleId, true);
            // 完全相同的目标状态是回调重放；其他跃迁严格限制为 pending → processing → 终态。
            if (task.getStatus().equals(target)
                    && List.of("processing", "success", "error").contains(target)) {
                return task(task);
            }
            boolean allowed = (task.getStatus().equals("pending") && target.equals("processing"))
                    || (task.getStatus().equals("processing")
                            && (target.equals("success") || target.equals("error")));
            if (!allowed) {
                throw new ApiException(
                        409, "PORTRAIT_TASK_STATE_CONFLICT", "画像任务状态冲突");
            }
            task.setStatus(target);
            task.setUpdatedat(DatabaseTimestamp.next(clock, task.getUpdatedat()));
            if (target.equals("success")) {
                applySuccess(style, data == null ? Map.of() : data.fields());
                if (expectedSection != null) {
                    style.setPortraitmarkdown(StyleService.buildPortraitMarkdown(sections(style)));
                }
                task.setErrormessage(null);
                style.setErrormessage(null);
                style.setUpdatedat(DatabaseTimestamp.next(clock, style.getUpdatedat()));
                style.store();
            } else if (target.equals("error")) {
                task.setErrormessage("画像生成失败");
                style.setErrormessage("画像生成失败");
                style.setUpdatedat(DatabaseTimestamp.next(clock, style.getUpdatedat()));
                style.store();
            }
            task.store();
            return task(task);
        });
    }

    @Override
    public StyleSnapshot updateSection(
            String userId, String styleId, PortraitSection section, String content) {
        return database.dsl().transactionResult(configuration -> {
            DSLContext transaction = DSL.using(configuration);
            WritingstyleRecord style = requireOwnedStyle(transaction, userId, styleId, true);
            setSection(style, section, content);
            style.setPortraitmarkdown(StyleService.buildPortraitMarkdown(sections(style)));
            style.setUpdatedat(DatabaseTimestamp.next(clock, style.getUpdatedat()));
            style.store();
            return aggregate(transaction, style);
        });
    }

    @Override
    public ApplyStyleResult applyStyle(
            String novelId, String userId, String styleId, String expectedStyleId) {
        return database.dsl().transactionResult(configuration -> {
            DSLContext transaction = DSL.using(configuration);
            NovelRecord novel = transaction.selectFrom(NOVEL)
                    .where(NOVEL.ID.eq(novelId).and(NOVEL.USERID.eq(userId)))
                    .forUpdate()
                    .fetchOne();
            if (novel == null) {
                throw new ApiException(404, "NOVEL_NOT_FOUND", "小说不存在");
            }
            String current = novel.getAppliedstyleid();
            // expectedStyleId 可以为 null；它是显式 CAS 基线，不允许最后写入者静默覆盖作者选择。
            if (!Objects.equals(current, expectedStyleId)) {
                throw new ApiException(
                        409,
                        "APPLIED_STYLE_VERSION_CONFLICT",
                        "小说当前应用文风已发生变化",
                        java.util.Collections.singletonMap("currentStyleId", current));
            }
            if (Objects.equals(current, styleId)) return new ApplyStyleResult(current, false);
            if (styleId != null) {
                WritingstyleRecord style = requireOwnedStyle(
                        transaction, userId, styleId, true);
                if (style.getPortraitmarkdown() == null || style.getPortraitmarkdown().isEmpty()) {
                    throw new ApiException(
                            409, "STYLE_PORTRAIT_INCOMPLETE", "文风画像尚未完整生成");
                }
            }
            novel.setAppliedstyleid(styleId);
            novel.setUpdatedat(DatabaseTimestamp.next(clock, novel.getUpdatedat()));
            novel.store();
            return new ApplyStyleResult(styleId, true);
        });
    }

    @Override
    public List<PortraitDispatchRecord> listReconcilable(
            int limit, OffsetDateTime staleBefore) {
        if (limit < 1) throw new IllegalArgumentException("领取数量必须大于零");
        LocalDateTime stale = DatabaseTimestamp.database(staleBefore);
        return database.dsl().select(
                        STYLEPORTRAITTASK.ID,
                        STYLEPORTRAITTASK.STYLEID,
                        WRITINGSTYLE.USERID,
                        STYLEPORTRAITTASK.SECTION,
                        STYLEPORTRAITTASK.STATUS,
                        STYLEPORTRAITTASK.UPDATEDAT)
                .from(STYLEPORTRAITTASK)
                .join(WRITINGSTYLE)
                .on(WRITINGSTYLE.ID.eq(STYLEPORTRAITTASK.STYLEID))
                .where(STYLEPORTRAITTASK.STATUS.eq("pending")
                        .or(STYLEPORTRAITTASK.STATUS.eq("processing")
                                .and(STYLEPORTRAITTASK.UPDATEDAT.le(stale))))
                .orderBy(STYLEPORTRAITTASK.UPDATEDAT.asc(), STYLEPORTRAITTASK.ID.asc())
                .limit(limit)
                .fetch(value -> new PortraitDispatchRecord(
                        value.get(STYLEPORTRAITTASK.ID),
                        value.get(STYLEPORTRAITTASK.STYLEID),
                        value.get(WRITINGSTYLE.USERID),
                        value.get(STYLEPORTRAITTASK.SECTION) == null
                                ? null
                                : PortraitSection.from(value.get(STYLEPORTRAITTASK.SECTION)),
                        value.get(STYLEPORTRAITTASK.STATUS),
                        DatabaseTimestamp.api(value.get(STYLEPORTRAITTASK.UPDATEDAT))));
    }

    @Override
    public void markDispatchTerminal(
            String styleId, String taskId, PortraitDispatchStatus status) {
        if (status == PortraitDispatchStatus.QUEUED
                || status == PortraitDispatchStatus.RUNNING) return;
        database.dsl().transaction(configuration -> {
            DSLContext transaction = DSL.using(configuration);
            StyleportraittaskRecord task = transaction.selectFrom(STYLEPORTRAITTASK)
                    .where(STYLEPORTRAITTASK.ID.eq(taskId))
                    .forUpdate()
                    .fetchOne();
            if (task == null
                    || !task.getStyleid().equals(styleId)
                    || !List.of("pending", "processing").contains(task.getStatus())) return;
            WritingstyleRecord style = requireStyle(transaction, styleId, true);
            String message = "智能体画像任务已终止："
                    + status.name().toLowerCase(java.util.Locale.ROOT);
            task.setStatus("error");
            task.setErrormessage(message);
            task.setUpdatedat(DatabaseTimestamp.next(clock, task.getUpdatedat()));
            style.setErrormessage(message);
            style.setUpdatedat(DatabaseTimestamp.next(clock, style.getUpdatedat()));
            task.store();
            style.store();
        });
    }

    private static StyleSnapshot aggregate(DSLContext context, WritingstyleRecord style) {
        List<StyleReferenceSnapshot> references = context.selectFrom(STYLEREFERENCE)
                .where(STYLEREFERENCE.STYLEID.eq(style.getId()))
                .orderBy(STYLEREFERENCE.CREATEDAT.asc(), STYLEREFERENCE.ID.asc())
                .fetch(JooqStyleRepository::reference);
        List<PortraitTaskSnapshot> tasks = context.selectFrom(STYLEPORTRAITTASK)
                .where(STYLEPORTRAITTASK.STYLEID.eq(style.getId()))
                .orderBy(STYLEPORTRAITTASK.CREATEDAT.asc(), STYLEPORTRAITTASK.ID.asc())
                .fetch(JooqStyleRepository::task);
        return style(style, references, tasks);
    }

    private static WritingstyleRecord requireOwnedStyle(
            DSLContext context, String userId, String styleId, boolean lock) {
        var query = context.selectFrom(WRITINGSTYLE)
                .where(WRITINGSTYLE.ID.eq(styleId).and(WRITINGSTYLE.USERID.eq(userId)));
        WritingstyleRecord value = lock ? query.forUpdate().fetchOne() : query.fetchOne();
        if (value == null) throw styleNotFound();
        return value;
    }

    private static WritingstyleRecord requireStyle(
            DSLContext context, String styleId, boolean lock) {
        var query = context.selectFrom(WRITINGSTYLE).where(WRITINGSTYLE.ID.eq(styleId));
        WritingstyleRecord value = lock ? query.forUpdate().fetchOne() : query.fetchOne();
        if (value == null) throw styleNotFound();
        return value;
    }

    private static void applySuccess(WritingstyleRecord style, Map<String, Object> fields) {
        for (Map.Entry<String, Object> field : fields.entrySet()) {
            switch (field.getKey()) {
                case "creativeMethodology" -> style.setCreativemethodology((String) field.getValue());
                case "uniqueMarkers" -> style.setUniquemarkers((String) field.getValue());
                case "generationStyle" -> style.setGenerationstyle((String) field.getValue());
                case "expressionFeatures" -> style.setExpressionfeatures((String) field.getValue());
                case "styleTraits" -> style.setStyletraits((String) field.getValue());
                case "portraitMarkdown" -> style.setPortraitmarkdown((String) field.getValue());
                case "originalCharCount" -> style.setOriginalcharcount((Integer) field.getValue());
                case "usedCharCount" -> style.setUsedcharcount((Integer) field.getValue());
                case "truncated" -> style.setTruncated((Boolean) field.getValue());
                case "errorMessage" -> style.setErrormessage((String) field.getValue());
                default -> throw new IllegalArgumentException(
                        "画像成功结果包含未知字段：" + field.getKey());
            }
        }
    }

    private static Map<String, String> sections(WritingstyleRecord style) {
        LinkedHashMap<String, String> values = new LinkedHashMap<>();
        values.put("creativeMethodology", style.getCreativemethodology());
        values.put("uniqueMarkers", style.getUniquemarkers());
        values.put("generationStyle", style.getGenerationstyle());
        values.put("expressionFeatures", style.getExpressionfeatures());
        values.put("styleTraits", style.getStyletraits());
        return values;
    }

    private static void setSection(
            WritingstyleRecord style, PortraitSection section, String content) {
        switch (section) {
            case CREATIVE_METHODOLOGY -> style.setCreativemethodology(content);
            case UNIQUE_MARKERS -> style.setUniquemarkers(content);
            case GENERATION_STYLE -> style.setGenerationstyle(content);
            case EXPRESSION_FEATURES -> style.setExpressionfeatures(content);
            case STYLE_TRAITS -> style.setStyletraits(content);
        }
    }

    private static StyleSnapshot style(
            WritingstyleRecord value,
            List<StyleReferenceSnapshot> references,
            List<PortraitTaskSnapshot> tasks) {
        return new StyleSnapshot(
                value.getId(),
                value.getName(),
                value.getSourcetype().getLiteral(),
                value.getCreativemethodology(),
                value.getUniquemarkers(),
                value.getGenerationstyle(),
                value.getExpressionfeatures(),
                value.getStyletraits(),
                value.getPortraitmarkdown(),
                value.getOriginalcharcount(),
                value.getUsedcharcount(),
                value.getTruncated(),
                value.getErrormessage(),
                DatabaseTimestamp.api(value.getCreatedat()),
                DatabaseTimestamp.api(value.getUpdatedat()),
                references,
                tasks);
    }

    private static StyleReferenceSnapshot reference(StylereferenceRecord value) {
        return new StyleReferenceSnapshot(
                value.getId(),
                value.getStyleid(),
                value.getFilename(),
                value.getFilepath(),
                value.getCharcount(),
                value.getStatus(),
                value.getErrormessage(),
                DatabaseTimestamp.api(value.getCreatedat()));
    }

    private static PortraitTaskSnapshot task(StyleportraittaskRecord value) {
        return new PortraitTaskSnapshot(
                value.getId(),
                value.getStyleid(),
                value.getSection() == null ? null : PortraitSection.from(value.getSection()),
                value.getStatus(),
                value.getErrormessage(),
                DatabaseTimestamp.api(value.getCreatedat()),
                DatabaseTimestamp.api(value.getUpdatedat()));
    }

    private static ApiException styleNotFound() {
        return new ApiException(404, "STYLE_NOT_FOUND", "文风不存在");
    }

    private static ApiException taskNotFound() {
        return new ApiException(404, "PORTRAIT_TASK_NOT_FOUND", "画像任务不存在");
    }
}
