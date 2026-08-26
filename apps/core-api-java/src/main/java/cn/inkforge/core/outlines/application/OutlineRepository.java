package cn.inkforge.core.outlines.application;

import cn.inkforge.contracts.api.DeleteOutlineNodeResponse;
import cn.inkforge.contracts.api.ForeshadowingResponse;
import cn.inkforge.contracts.api.OutlineContentResponse;
import cn.inkforge.contracts.api.OutlineNodeMutationResponse;
import cn.inkforge.contracts.api.OutlineNodeResponse;
import cn.inkforge.contracts.api.PlotProgressResponse;
import cn.inkforge.core.outlines.domain.ForeshadowingData;
import cn.inkforge.core.outlines.domain.ForeshadowingPatch;
import cn.inkforge.core.outlines.domain.OutlineNodeData;
import cn.inkforge.core.outlines.domain.OutlineNodePatch;
import cn.inkforge.core.outlines.domain.PlotProgressData;
import java.time.OffsetDateTime;
import java.util.List;

/** 大纲用例的 PostgreSQL 端口。 */
public interface OutlineRepository {

    OutlineContentResponse saveOutline(
            String novelId,
            String userId,
            String content,
            OffsetDateTime expectedUpdatedAt);

    PlotProgressResponse savePlot(
            String novelId,
            String userId,
            PlotProgressData data,
            OffsetDateTime expectedUpdatedAt);

    List<OutlineNodeResponse> listNodes(String novelId, String userId);

    OutlineNodeMutationResponse createNode(
            String novelId,
            String userId,
            String clientRequestId,
            OutlineNodeData data);

    OutlineNodeMutationResponse updateNode(
            String novelId,
            String userId,
            String nodeId,
            OutlineNodePatch patch,
            OffsetDateTime expectedUpdatedAt);

    DeleteOutlineNodeResponse deleteNode(
            String novelId,
            String userId,
            String nodeId,
            OffsetDateTime expectedUpdatedAt);

    List<ForeshadowingResponse> listForeshadowings(String novelId, String userId);

    ForeshadowingResponse createForeshadowing(
            String novelId, String userId, ForeshadowingData data);

    ForeshadowingResponse updateForeshadowing(
            String novelId,
            String userId,
            String foreshadowingId,
            ForeshadowingPatch patch);

    void deleteForeshadowing(String novelId, String userId, String foreshadowingId);
}
