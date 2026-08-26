package cn.inkforge.core.video.application;

import cn.inkforge.contracts.api.VideoPlanCallReservationRequest;
import cn.inkforge.contracts.api.VideoPlanCallReservationResponse;
import cn.inkforge.contracts.api.VideoPlanCompletionCallback;
import cn.inkforge.contracts.api.VideoPlanFailureCallback;
import cn.inkforge.contracts.api.VideoPlanProgressQuery;
import cn.inkforge.contracts.api.VideoPlanProgressResponse;
import cn.inkforge.contracts.api.VideoStoryPlanCheckpointCallback;
import java.util.Objects;

/** 隔离已退役场景规划协议的应用服务；只允许历史任务完成收敛。 */
public final class LegacyVideoPlanService {

    private final LegacyVideoPlanStore store;

    public LegacyVideoPlanService(LegacyVideoPlanStore store) {
        this.store = Objects.requireNonNull(store);
    }

    public VideoPlanProgressResponse progress(VideoPlanProgressQuery query) {
        return store.getProgress(query);
    }

    public VideoPlanCallReservationResponse reserve(VideoPlanCallReservationRequest request) {
        return store.reserveCall(request);
    }

    public void saveCheckpoint(VideoStoryPlanCheckpointCallback callback) {
        store.saveCheckpoint(callback);
    }

    public void complete(VideoPlanCompletionCallback callback) {
        store.complete(callback);
    }

    public void fail(VideoPlanFailureCallback callback) {
        store.fail(callback);
    }
}
