package cn.inkforge.core.video.application;

import java.util.List;

/** 视频项目和真实素材的 PostgreSQL 事务边界。 */
public interface VideoProjectRepository {

    VideoProjectSnapshot createProject(
            String userId, String novelId, VideoProjectCreation creation);

    List<VideoProjectSnapshot> listProjects(String userId, String novelId);

    VideoProjectAggregate getProject(String userId, String projectId);

    void requireWritableProject(String userId, String projectId);

    VideoAssetSnapshot createAsset(
            String userId, String projectId, VideoAssetCreation creation);

    VideoAssetSnapshot confirmAsset(String userId, String assetId, String rightsStatus);

    VideoAssetFile getAssetFile(String userId, String assetId);
}
