package cn.inkforge.core.outlines.application;

import cn.inkforge.contracts.api.CreateForeshadowingRequest;
import cn.inkforge.contracts.api.CreateOutlineNodeRequest;
import cn.inkforge.contracts.api.DeleteOutlineNodeRequest;
import cn.inkforge.contracts.api.DeleteOutlineNodeResponse;
import cn.inkforge.contracts.api.ForeshadowingResponse;
import cn.inkforge.contracts.api.OutlineContentRequest;
import cn.inkforge.contracts.api.OutlineContentResponse;
import cn.inkforge.contracts.api.OutlineNodeMutationResponse;
import cn.inkforge.contracts.api.OutlineNodeResponse;
import cn.inkforge.contracts.api.PlotProgressRequest;
import cn.inkforge.contracts.api.PlotProgressResponse;
import cn.inkforge.contracts.api.UpdateForeshadowingRequest;
import cn.inkforge.contracts.api.UpdateOutlineNodeRequest;
import cn.inkforge.core.outlines.domain.ForeshadowingData;
import cn.inkforge.core.outlines.domain.ForeshadowingPatch;
import cn.inkforge.core.outlines.domain.OutlineNodeData;
import cn.inkforge.core.outlines.domain.OutlineNodePatch;
import cn.inkforge.core.outlines.domain.PlotProgressData;
import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.platform.http.RequiredRequestField;
import cn.inkforge.core.platform.patch.PatchField;
import java.util.List;
import java.util.Objects;

/** 大纲、剧情进度和伏笔的公共用例层。 */
public final class OutlineService {

    private final OutlineRepository repository;

    public OutlineService(OutlineRepository repository) {
        this.repository = Objects.requireNonNull(repository);
    }

    public OutlineContentResponse saveOutline(
            String userId, String novelId, OutlineContentRequest request) {
        return repository.saveOutline(
                novelId,
                userId,
                request.getContent(),
                request.getExpectedUpdatedAt());
    }

    public PlotProgressResponse savePlot(
            String userId, String novelId, PlotProgressRequest request) {
        return repository.savePlot(
                novelId,
                userId,
                new PlotProgressData(
                        request.getCurrentStage(),
                        request.getCurrentGoal().orElse(null),
                        request.getCurrentConflict().orElse(null),
                        request.getNextMilestone().orElse(null)),
                RequiredRequestField.nullable(
                        request.getExpectedUpdatedAt(), "expectedUpdatedAt"));
    }

    public List<OutlineNodeResponse> listNodes(String userId, String novelId) {
        return repository.listNodes(novelId, userId);
    }

    public OutlineNodeMutationResponse createNode(
            String userId, String novelId, CreateOutlineNodeRequest request) {
        OutlineNodeData data = new OutlineNodeData(
                request.getTitle(),
                request.getContent().orElse(null),
                request.getKind().getValue(),
                request.getStatus().getValue(),
                request.getOrder(),
                request.getParentId().orElse(null),
                request.getLinkedChapterId().orElse(null),
                request.getEstimatedWordCount().orElse(null),
                request.getActualWordCount().orElse(null),
                request.getChapterStartOrder().orElse(null),
                request.getChapterEndOrder().orElse(null));
        return repository.createNode(
                novelId, userId, request.getClientRequestId(), data);
    }

    public OutlineNodeMutationResponse updateNode(
            String userId,
            String novelId,
            String nodeId,
            UpdateOutlineNodeRequest request) {
        OutlineNodePatch patch = new OutlineNodePatch(
                PatchField.from(request.getTitle()),
                PatchField.from(request.getContent()),
                PatchField.from(request.getKind()).map(value -> value.getValue()),
                PatchField.from(request.getStatus()).map(value -> value.getValue()),
                PatchField.from(request.getOrder()),
                PatchField.from(request.getParentId()),
                PatchField.from(request.getLinkedChapterId()),
                PatchField.from(request.getEstimatedWordCount()),
                PatchField.from(request.getActualWordCount()),
                PatchField.from(request.getChapterStartOrder()),
                PatchField.from(request.getChapterEndOrder()));
        if (patch.empty()) {
            throw new ApiException(422, "EMPTY_UPDATE", "至少需要提供一个更新字段");
        }
        if ((patch.title().present() && patch.title().value() == null)
                || (patch.kind().present() && patch.kind().value() == null)
                || (patch.status().present() && patch.status().value() == null)
                || (patch.order().present() && patch.order().value() == null)) {
            throw new ApiException(
                    422,
                    "OUTLINE_FIELD_REQUIRED",
                    "标题、类型、状态和顺序不能为 null");
        }
        return repository.updateNode(
                novelId,
                userId,
                nodeId,
                patch,
                request.getExpectedUpdatedAt());
    }

    public DeleteOutlineNodeResponse deleteNode(
            String userId,
            String novelId,
            String nodeId,
            DeleteOutlineNodeRequest request) {
        return repository.deleteNode(
                novelId, userId, nodeId, request.getExpectedUpdatedAt());
    }

    public List<ForeshadowingResponse> listForeshadowings(
            String userId, String novelId) {
        return repository.listForeshadowings(novelId, userId);
    }

    public ForeshadowingResponse createForeshadowing(
            String userId,
            String novelId,
            CreateForeshadowingRequest request) {
        if (request.getName().strip().isEmpty()) {
            throw new ApiException(
                    422, "FORESHADOWING_NAME_REQUIRED", "伏笔名称不能为空");
        }
        return repository.createForeshadowing(
                novelId,
                userId,
                new ForeshadowingData(
                        request.getName(),
                        request.getPlantedAt().orElse(null),
                        request.getPlantedContent().orElse(null),
                        request.getExpectedPayoff().orElse(null),
                        request.getPayoffAt().orElse(null),
                        request.getStatus().getValue()));
    }

    public ForeshadowingResponse updateForeshadowing(
            String userId,
            String novelId,
            String foreshadowingId,
            UpdateForeshadowingRequest request) {
        ForeshadowingPatch patch = new ForeshadowingPatch(
                PatchField.from(request.getName()),
                PatchField.from(request.getPlantedAt()),
                PatchField.from(request.getPlantedContent()),
                PatchField.from(request.getExpectedPayoff()),
                PatchField.from(request.getPayoffAt()),
                PatchField.from(request.getStatus()).map(value -> value.getValue()));
        if (patch.empty()) {
            throw new ApiException(422, "EMPTY_UPDATE", "至少需要提供一个更新字段");
        }
        if ((patch.name().present() && patch.name().value() == null)
                || (patch.status().present() && patch.status().value() == null)) {
            throw new ApiException(
                    422,
                    "FORESHADOWING_FIELD_REQUIRED",
                    "伏笔名称和状态不能为 null");
        }
        if (patch.name().present() && patch.name().value().strip().isEmpty()) {
            throw new ApiException(
                    422, "FORESHADOWING_NAME_REQUIRED", "伏笔名称不能为空");
        }
        return repository.updateForeshadowing(
                novelId, userId, foreshadowingId, patch);
    }

    public void deleteForeshadowing(
            String userId, String novelId, String foreshadowingId) {
        repository.deleteForeshadowing(novelId, userId, foreshadowingId);
    }
}
