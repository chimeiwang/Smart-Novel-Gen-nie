package cn.inkforge.core.styles.application;

import cn.inkforge.contracts.api.ApplyStyleRequest;
import cn.inkforge.contracts.api.ApplyStyleResponse;
import cn.inkforge.contracts.api.Body1;
import cn.inkforge.contracts.api.CreateStyleRequest;
import cn.inkforge.contracts.api.FullPortraitSuccessRequest;
import cn.inkforge.contracts.api.PortraitAcceptedResponse;
import cn.inkforge.contracts.api.PortraitContextResponse;
import cn.inkforge.contracts.api.PortraitFailureRequest;
import cn.inkforge.contracts.api.PortraitProcessingRequest;
import cn.inkforge.contracts.api.PortraitTaskResponse;
import cn.inkforge.contracts.api.SectionPortraitSuccessRequest;
import cn.inkforge.contracts.api.StyleReferenceResponse;
import cn.inkforge.contracts.api.StyleResponse;
import cn.inkforge.contracts.api.UpdatePortraitSectionRequest;
import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.platform.http.RequiredRequestField;
import cn.inkforge.core.styles.domain.ApplyStyleResult;
import cn.inkforge.core.styles.domain.PortraitSection;
import cn.inkforge.core.styles.domain.PortraitSource;
import cn.inkforge.core.styles.domain.PortraitSuccessData;
import cn.inkforge.core.styles.domain.PortraitTaskSnapshot;
import cn.inkforge.core.styles.domain.StyleReferenceSnapshot;
import cn.inkforge.core.styles.domain.StyleSnapshot;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.springframework.web.multipart.MultipartFile;

/** 私有文风、参考文件、画像状态机和小说应用 CAS 的应用服务。 */
public final class StyleService {

    private final StyleRepository repository;
    private final StyleFileStorage storage;
    private final PortraitRunSubmitter submitter;

    public StyleService(
            StyleRepository repository,
            StyleFileStorage storage,
            PortraitRunSubmitter submitter) {
        this.repository = java.util.Objects.requireNonNull(repository);
        this.storage = java.util.Objects.requireNonNull(storage);
        this.submitter = submitter;
    }

    public List<StyleResponse> list(String userId) {
        return repository.list(userId).stream().map(StyleService::style).toList();
    }

    public StyleResponse create(String userId, CreateStyleRequest request) {
        String name = request.getName().strip();
        if (name.isEmpty()) {
            throw new ApiException(422, "STYLE_NAME_REQUIRED", "文风名称不能为空");
        }
        return style(repository.create(userId, name));
    }

    public StyleReferenceResponse uploadReference(
            String userId, String styleId, MultipartFile upload) {
        String referenceId = repository.reserveReference(userId, styleId);
        StoredStyleFile stored = storage.save(styleId, referenceId, upload);
        try {
            return reference(repository.createReference(
                    userId, styleId, referenceId, stored));
        } catch (RuntimeException exception) {
            storage.delete(stored.databasePath());
            throw exception;
        }
    }

    public void deleteReference(String userId, String styleId, String referenceId) {
        String path = repository.deleteReference(userId, styleId, referenceId);
        storage.delete(path);
    }

    public void deleteStyle(String userId, String styleId) {
        List<String> paths = repository.deleteStyle(userId, styleId);
        paths.forEach(storage::delete);
    }

    public PortraitAcceptedResponse createPortrait(
            String userId, String styleId, PortraitSection section) {
        if (submitter == null) {
            throw new ApiException(
                    503,
                    "PORTRAIT_SERVICE_UNAVAILABLE",
                    "画像生成服务暂时不可用");
        }
        PortraitTaskSnapshot task = repository.createPortraitTask(userId, styleId, section);
        try {
            submitter.submit(userId, styleId, task.id(), task.id(), section);
        } catch (RuntimeException ignored) {
            // pending 事实已提交，受监督后台对账会复用同一 taskId 继续投递。
        }
        return new PortraitAcceptedResponse("pending", task.id());
    }

    public PortraitContextResponse portraitContext(String styleId, String taskId) {
        List<PortraitSource> sources = repository.portraitSources(styleId, taskId);
        if (sources.isEmpty()) {
            throw new ApiException(
                    409, "STYLE_REFERENCE_REQUIRED", "没有可用的文风参考资料");
        }
        List<String> parts = new ArrayList<>();
        int originalCount = 0;
        for (PortraitSource source : sources) {
            if (source.filepath() == null || source.filename() == null || source.charCount() < 0) {
                throw new ApiException(
                        409, "STYLE_REFERENCE_INVALID", "文风参考资料元数据无效");
            }
            String content = storage.read(source.filepath());
            parts.add("参考资料：" + source.filename() + "\n\n" + content);
            originalCount = Math.addExact(originalCount, source.charCount());
        }
        return new PortraitContextResponse(originalCount, String.join("\n\n", parts));
    }

    public PortraitTaskResponse getPortraitTask(String userId, String taskId) {
        return task(repository.getPortraitTask(userId, taskId));
    }

    public PortraitTaskResponse markProcessing(
            String styleId, String taskId, PortraitProcessingRequest request) {
        requireRun(taskId, request.getRunId());
        return task(repository.transitionPortraitTask(
                styleId, taskId, "processing", null, null, false));
    }

    public PortraitTaskResponse completePortrait(
            String styleId, String taskId, Body1 request) {
        if (request instanceof FullPortraitSuccessRequest full) {
            requireRun(taskId, full.getRunId());
            requireUntruncated("full", full.getMode(), full.getTruncated());
            LinkedHashMap<String, String> sections = new LinkedHashMap<>();
            sections.put("creativeMethodology", full.getCreativeMethodology());
            sections.put("uniqueMarkers", full.getUniqueMarkers());
            sections.put("generationStyle", full.getGenerationStyle());
            sections.put("expressionFeatures", full.getExpressionFeatures());
            sections.put("styleTraits", full.getStyleTraits());
            Map<String, Object> fields = new LinkedHashMap<>(sections);
            fields.put("portraitMarkdown", buildPortraitMarkdown(sections));
            fields.put("originalCharCount", full.getOriginalCharCount());
            fields.put("usedCharCount", full.getUsedCharCount());
            fields.put("truncated", false);
            fields.put("errorMessage", null);
            return task(repository.transitionPortraitTask(
                    styleId,
                    taskId,
                    "success",
                    new PortraitSuccessData(fields),
                    null,
                    true));
        }
        if (request instanceof SectionPortraitSuccessRequest sectionRequest) {
            requireRun(taskId, sectionRequest.getRunId());
            requireUntruncated("section", sectionRequest.getMode(), sectionRequest.getTruncated());
            PortraitSection section = PortraitSection.from(
                    sectionRequest.getSection().getValue());
            Map<String, Object> fields = new LinkedHashMap<>();
            fields.put(section.value(), sectionRequest.getContent());
            fields.put("originalCharCount", sectionRequest.getOriginalCharCount());
            fields.put("usedCharCount", sectionRequest.getUsedCharCount());
            fields.put("truncated", false);
            fields.put("errorMessage", null);
            return task(repository.transitionPortraitTask(
                    styleId,
                    taskId,
                    "success",
                    new PortraitSuccessData(fields),
                    section,
                    true));
        }
        throw new ApiException(422, "VALIDATION_ERROR", "画像成功结果类型无效");
    }

    public PortraitTaskResponse failPortrait(
            String styleId, String taskId, PortraitFailureRequest request) {
        requireRun(taskId, request.getRunId());
        return task(repository.transitionPortraitTask(
                styleId, taskId, "error", null, null, false));
    }

    public StyleResponse updateSection(
            String userId,
            String styleId,
            PortraitSection section,
            UpdatePortraitSectionRequest request) {
        String content = request.getContent().strip();
        if (content.isEmpty()) {
            throw new ApiException(
                    422, "PORTRAIT_SECTION_REQUIRED", "画像分节内容不能为空");
        }
        return style(repository.updateSection(userId, styleId, section, content));
    }

    public ApplyStyleResponse applyStyle(
            String userId, String novelId, ApplyStyleRequest request) {
        String styleId = RequiredRequestField.nullable(request.getStyleId(), "styleId");
        String expected = RequiredRequestField.nullable(
                request.getExpectedStyleId(), "expectedStyleId");
        ApplyStyleResult value = repository.applyStyle(novelId, userId, styleId, expected);
        return new ApplyStyleResponse(value.effective(), value.styleId());
    }

    public static String buildPortraitMarkdown(Map<String, String> sections) {
        LinkedHashMap<String, String> ordered = new LinkedHashMap<>();
        ordered.put("创作方法论", sections.get("creativeMethodology"));
        ordered.put("独特标记", sections.get("uniqueMarkers"));
        ordered.put("生成风格", sections.get("generationStyle"));
        ordered.put("表达特征", sections.get("expressionFeatures"));
        ordered.put("风格特质", sections.get("styleTraits"));
        if (ordered.values().stream().anyMatch(value -> value == null || value.isEmpty())) {
            return null;
        }
        return ordered.entrySet().stream()
                .map(value -> value.getKey() + "\n" + value.getValue())
                .collect(java.util.stream.Collectors.joining("\n\n"));
    }

    private static void requireRun(String taskId, String runId) {
        if (!taskId.equals(runId)) {
            throw new ApiException(
                    409, "PORTRAIT_RUN_MISMATCH", "画像运行与任务不匹配");
        }
    }

    private static void requireUntruncated(String expectedMode, String mode, Boolean truncated) {
        if (!expectedMode.equals(mode) || !Boolean.FALSE.equals(truncated)) {
            throw new ApiException(422, "VALIDATION_ERROR", "画像成功结果必须完整且模式匹配");
        }
    }

    private static StyleResponse style(StyleSnapshot value) {
        return new StyleResponse(
                value.createdAt(),
                value.creativeMethodology(),
                value.errorMessage(),
                value.expressionFeatures(),
                value.generationStyle(),
                value.id(),
                value.name(),
                value.originalCharCount(),
                value.portraitMarkdown(),
                value.references().stream().map(StyleService::reference).toList(),
                StyleResponse.SourceTypeEnum.fromValue(value.sourceType()),
                value.styleTraits(),
                value.tasks().stream().map(StyleService::task).toList(),
                value.truncated(),
                value.uniqueMarkers(),
                value.updatedAt(),
                value.usedCharCount());
    }

    private static StyleReferenceResponse reference(StyleReferenceSnapshot value) {
        return new StyleReferenceResponse(
                value.charCount(),
                value.createdAt(),
                value.errorMessage(),
                value.filename(),
                value.id(),
                StyleReferenceResponse.StatusEnum.fromValue(value.status()),
                value.styleId());
    }

    private static PortraitTaskResponse task(PortraitTaskSnapshot value) {
        PortraitTaskResponse.SectionEnum section = value.section() == null
                ? null
                : PortraitTaskResponse.SectionEnum.fromValue(value.section().value());
        return new PortraitTaskResponse(
                value.createdAt(),
                value.errorMessage(),
                value.id(),
                section,
                PortraitTaskResponse.StatusEnum.fromValue(value.status()),
                value.styleId(),
                value.updatedAt());
    }
}
