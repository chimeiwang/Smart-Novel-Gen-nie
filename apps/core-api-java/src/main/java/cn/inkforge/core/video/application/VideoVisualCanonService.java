package cn.inkforge.core.video.application;

import cn.inkforge.contracts.api.ApproveVisualCanonRequest;
import cn.inkforge.contracts.api.CreateVisualCanonCandidateRequest;
import cn.inkforge.contracts.api.SaveShotVisualReferencesRequest;
import cn.inkforge.contracts.api.ShotVisualReferenceSelectionRequest;
import cn.inkforge.contracts.api.ShotVisualReferenceSetResponse;
import cn.inkforge.contracts.api.VisualCanonLibraryResponse;
import cn.inkforge.contracts.api.VisualCanonResponse;
import cn.inkforge.core.platform.http.ApiException;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

/** 角色、服装、场景和道具视觉稳定性的应用门禁。 */
public final class VideoVisualCanonService {

    private static final Map<String, String> SETTING_KIND_BY_DUTY = Map.of(
            "identity", "character",
            "costume", "character",
            "scene", "location",
            "prop", "item");

    private final VideoVisualCanonRepository repository;
    private final boolean previewEnabled;

    public VideoVisualCanonService(
            VideoVisualCanonRepository repository, boolean previewEnabled) {
        this.repository = Objects.requireNonNull(repository);
        this.previewEnabled = previewEnabled;
    }

    public VisualCanonLibraryResponse list(String userId, String projectId) {
        return repository.list(userId, projectId);
    }

    public VisualCanonResponse setCandidate(
            String userId,
            String projectId,
            CreateVisualCanonCandidateRequest request) {
        requireEnabled();
        String duty = request.getDuty().getValue();
        String settingKind = request.getSettingKind().getValue();
        if (!settingKind.equals(SETTING_KIND_BY_DUTY.get(duty))) {
            throw new ApiException(
                    422,
                    "VALIDATION_ERROR",
                    "视觉设定职责与文字设定类型不匹配");
        }
        List<String> include = normalizedFeatures(request.getIncludeFeatures(), "包含特征");
        List<String> exclude = normalizedFeatures(request.getExcludeFeatures(), "排除特征");
        String label = request.getLabel().strip();
        if (label.isEmpty()) {
            throw new ApiException(422, "VALIDATION_ERROR", "视觉设定标签不能为空");
        }
        return repository.setCandidate(
                userId,
                projectId,
                new VisualCanonCandidateCommand(
                        settingKind,
                        request.getSettingId(),
                        duty,
                        request.getVariantKey(),
                        label,
                        request.getCandidateAssetId(),
                        include,
                        exclude,
                        request.getDefaultStrength()));
    }

    public VisualCanonResponse approve(
            String userId, String canonId, ApproveVisualCanonRequest request) {
        requireEnabled();
        return repository.approve(
                userId,
                canonId,
                new VisualCanonApproval(
                        request.getExpectedRevision(), request.getCandidateAssetId()));
    }

    public ShotVisualReferenceSetResponse saveShotReferences(
            String userId,
            String adaptationId,
            String shotId,
            SaveShotVisualReferencesRequest request) {
        requireEnabled();
        List<ShotVisualReferenceSelectionRequest> values =
                request.getReferences() == null ? List.of() : request.getReferences();
        List<ShotVisualReferenceSelection> references = values.stream()
                .map(value -> new ShotVisualReferenceSelection(
                        value.getCanonVersionId(), value.getStrength()))
                .toList();
        Set<String> unique = references.stream()
                .map(ShotVisualReferenceSelection::canonVersionId)
                .collect(java.util.stream.Collectors.toSet());
        if (unique.size() != references.size()) {
            throw new ApiException(
                    422,
                    "VALIDATION_ERROR",
                    "同一镜头不能重复绑定同一视觉设定版本");
        }
        return repository.saveShotReferences(
                userId,
                adaptationId,
                shotId,
                new ShotVisualReferencesCommand(request.getExpectedRevision(), references));
    }

    private static List<String> normalizedFeatures(List<String> values, String label) {
        if (values == null) return List.of();
        List<String> normalized = new ArrayList<>(values.size());
        for (String value : values) {
            String text = value == null ? "" : value.strip();
            if (text.isEmpty()) {
                throw new ApiException(422, "VALIDATION_ERROR", label + "不能为空");
            }
            normalized.add(text);
        }
        if (new HashSet<>(normalized).size() != normalized.size()) {
            throw new ApiException(422, "VALIDATION_ERROR", label + "不能重复");
        }
        return List.copyOf(normalized);
    }

    private void requireEnabled() {
        if (!previewEnabled) {
            throw new ApiException(
                    503,
                    "VIDEO_PREVIEW_DISABLED",
                    "当前环境未开启视频开发预览写入");
        }
    }
}
