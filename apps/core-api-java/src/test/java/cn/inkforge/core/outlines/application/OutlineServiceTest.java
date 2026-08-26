package cn.inkforge.core.outlines.application;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import cn.inkforge.contracts.api.CreateForeshadowingRequest;
import cn.inkforge.contracts.api.CreateOutlineNodeRequest;
import cn.inkforge.contracts.api.ForeshadowingResponse;
import cn.inkforge.contracts.api.OutlineNodeMutationResponse;
import cn.inkforge.contracts.api.PlotProgressRequest;
import cn.inkforge.contracts.api.UpdateForeshadowingRequest;
import cn.inkforge.contracts.api.UpdateOutlineNodeRequest;
import cn.inkforge.core.outlines.domain.ForeshadowingData;
import cn.inkforge.core.outlines.domain.ForeshadowingPatch;
import cn.inkforge.core.outlines.domain.OutlineNodeData;
import cn.inkforge.core.outlines.domain.OutlineNodePatch;
import cn.inkforge.core.outlines.domain.PlotProgressData;
import cn.inkforge.core.platform.http.ApiException;
import java.time.OffsetDateTime;
import org.junit.jupiter.api.Test;

class OutlineServiceTest {

    private static final OffsetDateTime VERSION =
            OffsetDateTime.parse("2026-08-25T00:00:00Z");

    @Test
    void 节点新建必须展开默认值并分离幂等请求标识() {
        RecordingRepository repository = new RecordingRepository();
        OutlineService service = new OutlineService(repository);
        CreateOutlineNodeRequest request = new CreateOutlineNodeRequest(
                "outline-node-create-0001",
                CreateOutlineNodeRequest.KindEnum.STAGE,
                "第一卷");

        service.createNode("user-1", "novel-1", request);

        assertThat(repository.clientRequestId).isEqualTo("outline-node-create-0001");
        assertThat(repository.nodeData).isEqualTo(new OutlineNodeData(
                "第一卷",
                null,
                "stage",
                "planned",
                0,
                null,
                null,
                null,
                null,
                null,
                null));
    }

    @Test
    void Patch必须区分省略与显式null并拒绝空更新() {
        RecordingRepository repository = new RecordingRepository();
        OutlineService service = new OutlineService(repository);

        service.updateNode(
                "user-1",
                "novel-1",
                "node-1",
                new UpdateOutlineNodeRequest(VERSION).content(null));
        assertThat(repository.nodePatch.content().present()).isTrue();
        assertThat(repository.nodePatch.content().value()).isNull();
        assertThat(repository.nodePatch.title().present()).isFalse();

        assertCode(
                () -> service.updateNode(
                        "user-1",
                        "novel-1",
                        "node-1",
                        new UpdateOutlineNodeRequest(VERSION)),
                "EMPTY_UPDATE");
        assertCode(
                () -> service.updateNode(
                        "user-1",
                        "novel-1",
                        "node-1",
                        new UpdateOutlineNodeRequest(VERSION).title(null)),
                "OUTLINE_FIELD_REQUIRED");
    }

    @Test
    void 剧情进度显式null和伏笔完整文本必须原样传递() {
        RecordingRepository repository = new RecordingRepository();
        OutlineService service = new OutlineService(repository);

        service.savePlot(
                "user-1",
                "novel-1",
                new PlotProgressRequest("第一幕", null));
        assertThat(repository.plotData)
                .isEqualTo(new PlotProgressData("第一幕", null, null, null));
        assertThat(repository.expectedVersion).isNull();

        service.createForeshadowing(
                "user-1",
                "novel-1",
                new CreateForeshadowingRequest("伏笔").plantedContent("  原文\r\n  "));
        assertThat(repository.foreshadowingData.plantedContent())
                .isEqualTo("  原文\r\n  ");
        assertCode(
                () -> service.updateForeshadowing(
                        "user-1",
                        "novel-1",
                        "f-1",
                        new UpdateForeshadowingRequest()),
                "EMPTY_UPDATE");
    }

    private static void assertCode(Runnable action, String code) {
        assertThatThrownBy(action::run)
                .isInstanceOfSatisfying(ApiException.class, error ->
                        assertThat(error.code()).isEqualTo(code));
    }

    private static final class RecordingRepository implements OutlineRepository {
        private String clientRequestId;
        private OutlineNodeData nodeData;
        private OutlineNodePatch nodePatch;
        private PlotProgressData plotData;
        private OffsetDateTime expectedVersion;
        private ForeshadowingData foreshadowingData;

        @Override
        public cn.inkforge.contracts.api.OutlineContentResponse saveOutline(
                String novelId,
                String userId,
                String content,
                OffsetDateTime expectedUpdatedAt) {
            throw new UnsupportedOperationException();
        }

        @Override
        public cn.inkforge.contracts.api.PlotProgressResponse savePlot(
                String novelId,
                String userId,
                PlotProgressData data,
                OffsetDateTime expectedUpdatedAt) {
            plotData = data;
            expectedVersion = expectedUpdatedAt;
            return new cn.inkforge.contracts.api.PlotProgressResponse(
                    data.currentStage(), "plot-1", VERSION);
        }

        @Override
        public java.util.List<cn.inkforge.contracts.api.OutlineNodeResponse> listNodes(
                String novelId, String userId) {
            return java.util.List.of();
        }

        @Override
        public OutlineNodeMutationResponse createNode(
                String novelId,
                String userId,
                String clientRequestId,
                OutlineNodeData data) {
            this.clientRequestId = clientRequestId;
            nodeData = data;
            return new OutlineNodeMutationResponse();
        }

        @Override
        public OutlineNodeMutationResponse updateNode(
                String novelId,
                String userId,
                String nodeId,
                OutlineNodePatch patch,
                OffsetDateTime expectedUpdatedAt) {
            nodePatch = patch;
            return new OutlineNodeMutationResponse();
        }

        @Override
        public cn.inkforge.contracts.api.DeleteOutlineNodeResponse deleteNode(
                String novelId,
                String userId,
                String nodeId,
                OffsetDateTime expectedUpdatedAt) {
            throw new UnsupportedOperationException();
        }

        @Override
        public java.util.List<ForeshadowingResponse> listForeshadowings(
                String novelId, String userId) {
            return java.util.List.of();
        }

        @Override
        public ForeshadowingResponse createForeshadowing(
                String novelId, String userId, ForeshadowingData data) {
            foreshadowingData = data;
            return new ForeshadowingResponse(VERSION, "f-1", data.name(), VERSION);
        }

        @Override
        public ForeshadowingResponse updateForeshadowing(
                String novelId,
                String userId,
                String foreshadowingId,
                ForeshadowingPatch patch) {
            throw new UnsupportedOperationException();
        }

        @Override
        public void deleteForeshadowing(
                String novelId, String userId, String foreshadowingId) {
            throw new UnsupportedOperationException();
        }
    }
}
