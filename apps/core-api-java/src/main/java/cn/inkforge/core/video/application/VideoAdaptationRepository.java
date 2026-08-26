package cn.inkforge.core.video.application;

import cn.inkforge.contracts.api.CreateChapterAdaptationRequest;
import cn.inkforge.contracts.api.ChapterAdaptationListResponse;
import cn.inkforge.contracts.api.ChapterAdaptationResponse;
import java.util.List;

/** 章节改编根、正式版本链和耐久任务的 PostgreSQL 边界。 */
public interface VideoAdaptationRepository {

    VideoAdaptationSnapshot create(
            String userId, String projectId, CreateChapterAdaptationRequest request);

    VideoAdaptationSnapshot get(String userId, String adaptationId);

    List<VideoAdaptationSnapshot> list(String userId, String projectId);

    ChapterAdaptationResponse getDetail(String userId, String adaptationId);

    ChapterAdaptationListResponse listDetails(String userId, String projectId);
}
