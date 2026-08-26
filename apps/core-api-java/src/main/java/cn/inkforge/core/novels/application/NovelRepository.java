package cn.inkforge.core.novels.application;

import cn.inkforge.contracts.api.CreateNovelResponse;
import cn.inkforge.contracts.api.DashboardResponse;
import cn.inkforge.contracts.api.NovelResponse;
import cn.inkforge.contracts.api.StoryLengthProfile;
import cn.inkforge.contracts.api.WorkspaceBootstrapResponse;
import cn.inkforge.contracts.api.WorkspaceLoreResponse;
import cn.inkforge.contracts.api.WorkspacePlanningResponse;
import cn.inkforge.contracts.api.WorkspaceResourcesResponse;
import cn.inkforge.contracts.api.WorkspaceResponse;
import cn.inkforge.core.novels.domain.NovelCreation;
import java.time.OffsetDateTime;
import java.util.List;

/** 小说和工作区聚合的持久化端口。 */
public interface NovelRepository {

    CreateNovelResponse create(NovelCreation creation);

    DashboardResponse dashboard(String userId);

    List<NovelResponse> list(String userId, StoryLengthProfile profile);

    NovelResponse get(String novelId, String userId);

    NovelResponse updateSummary(
            String novelId,
            String userId,
            String summary,
            OffsetDateTime expectedUpdatedAt);

    WorkspaceResponse workspace(
            String novelId, String userId, String chapterId);

    WorkspaceBootstrapResponse workspaceBootstrap(
            String novelId, String userId, String chapterId);

    WorkspaceLoreResponse workspaceLore(String novelId, String userId);

    WorkspacePlanningResponse workspacePlanning(String novelId, String userId);

    WorkspaceResourcesResponse workspaceResources(String novelId, String userId);
}
