package cn.inkforge.core.outlines.api;

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
import cn.inkforge.core.generated.api.OutlinesApi;
import cn.inkforge.core.identity.application.AuthenticatedUser;
import cn.inkforge.core.identity.application.CurrentUserAccess;
import cn.inkforge.core.outlines.application.OutlineService;
import cn.inkforge.core.platform.http.ApiException;
import java.util.List;
import java.util.Optional;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.RestController;

/** 冻结的十个大纲、剧情进度与伏笔接口。 */
@RestController
public final class OutlineController implements OutlinesApi {

    private final Optional<OutlineService> configuredService;
    private final Optional<CurrentUserAccess> configuredUsers;

    public OutlineController(
            Optional<OutlineService> configuredService,
            Optional<CurrentUserAccess> configuredUsers) {
        this.configuredService = configuredService;
        this.configuredUsers = configuredUsers;
    }

    @Override
    public ResponseEntity<ForeshadowingResponse>
            createForeshadowingApiV1NovelsNovelIdForeshadowingsPost(
                    String novelId,
                    CreateForeshadowingRequest request,
                    String inkforgeToken) {
        return ResponseEntity.status(201)
                .body(service().createForeshadowing(
                        user(inkforgeToken).id(), novelId, request));
    }

    @Override
    public ResponseEntity<OutlineNodeMutationResponse>
            createNodeApiV1NovelsNovelIdOutlineNodesPost(
                    String novelId,
                    CreateOutlineNodeRequest request,
                    String inkforgeToken) {
        return ResponseEntity.status(201)
                .body(service().createNode(user(inkforgeToken).id(), novelId, request));
    }

    @Override
    public ResponseEntity<Void>
            deleteForeshadowingApiV1NovelsNovelIdForeshadowingsForeshadowingIdDelete(
                    String novelId,
                    String foreshadowingId,
                    String inkforgeToken) {
        service().deleteForeshadowing(
                user(inkforgeToken).id(), novelId, foreshadowingId);
        return ResponseEntity.noContent().build();
    }

    @Override
    public ResponseEntity<DeleteOutlineNodeResponse>
            deleteNodeApiV1NovelsNovelIdOutlineNodesNodeIdDelete(
                    String novelId,
                    String nodeId,
                    DeleteOutlineNodeRequest request,
                    String inkforgeToken) {
        return ResponseEntity.ok(service().deleteNode(
                user(inkforgeToken).id(), novelId, nodeId, request));
    }

    @Override
    public ResponseEntity<List<ForeshadowingResponse>>
            listForeshadowingsApiV1NovelsNovelIdForeshadowingsGet(
                    String novelId, String inkforgeToken) {
        return ResponseEntity.ok(service().listForeshadowings(
                user(inkforgeToken).id(), novelId));
    }

    @Override
    public ResponseEntity<List<OutlineNodeResponse>>
            listNodesApiV1NovelsNovelIdOutlineNodesGet(
                    String novelId, String inkforgeToken) {
        return ResponseEntity.ok(
                service().listNodes(user(inkforgeToken).id(), novelId));
    }

    @Override
    public ResponseEntity<OutlineContentResponse>
            saveOutlineApiV1NovelsNovelIdOutlinePut(
                    String novelId,
                    OutlineContentRequest request,
                    String inkforgeToken) {
        return ResponseEntity.ok(service().saveOutline(
                user(inkforgeToken).id(), novelId, request));
    }

    @Override
    public ResponseEntity<PlotProgressResponse>
            savePlotApiV1NovelsNovelIdPlotProgressPut(
                    String novelId,
                    PlotProgressRequest request,
                    String inkforgeToken) {
        return ResponseEntity.ok(
                service().savePlot(user(inkforgeToken).id(), novelId, request));
    }

    @Override
    public ResponseEntity<ForeshadowingResponse>
            updateForeshadowingApiV1NovelsNovelIdForeshadowingsForeshadowingIdPatch(
                    String novelId,
                    String foreshadowingId,
                    UpdateForeshadowingRequest request,
                    String inkforgeToken) {
        return ResponseEntity.ok(service().updateForeshadowing(
                user(inkforgeToken).id(), novelId, foreshadowingId, request));
    }

    @Override
    public ResponseEntity<OutlineNodeMutationResponse>
            updateNodeApiV1NovelsNovelIdOutlineNodesNodeIdPatch(
                    String novelId,
                    String nodeId,
                    UpdateOutlineNodeRequest request,
                    String inkforgeToken) {
        return ResponseEntity.ok(service().updateNode(
                user(inkforgeToken).id(), novelId, nodeId, request));
    }

    private OutlineService service() {
        return configuredService.orElseThrow(() -> new ApiException(
                503, "OUTLINE_SERVICE_UNAVAILABLE", "大纲服务暂时不可用"));
    }

    private AuthenticatedUser user(String token) {
        return configuredUsers.orElseThrow(() ->
                        new ApiException(503, "AUTH_UNAVAILABLE", "认证服务暂时不可用"))
                .require(token);
    }
}
