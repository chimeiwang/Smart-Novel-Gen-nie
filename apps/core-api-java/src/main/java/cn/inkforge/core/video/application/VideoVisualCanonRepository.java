package cn.inkforge.core.video.application;

import cn.inkforge.contracts.api.VisualCanonLibraryResponse;
import cn.inkforge.contracts.api.VisualCanonResponse;

/** 项目视觉设定槽与不可变版本的 PostgreSQL 边界。 */
public interface VideoVisualCanonRepository {

    VisualCanonLibraryResponse list(String userId, String projectId);

    VisualCanonResponse setCandidate(
            String userId, String projectId, VisualCanonCandidateCommand command);

    VisualCanonResponse approve(
            String userId, String canonId, VisualCanonApproval approval);

}
