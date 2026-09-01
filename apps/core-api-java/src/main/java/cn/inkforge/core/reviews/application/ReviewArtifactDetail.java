package cn.inkforge.core.reviews.application;

import cn.inkforge.contracts.api.ReviewArtifactResponse;
import java.util.Objects;

/** 精确 Artifact revision 的条件读取结果；304 时 response 为空。 */
public record ReviewArtifactDetail(String etag, ReviewArtifactResponse response) {

    public ReviewArtifactDetail {
        Objects.requireNonNull(etag);
    }

    public boolean notModified() {
        return response == null;
    }
}
