package cn.inkforge.core.chapters.application;

import cn.inkforge.contracts.api.ChapterStatus;
import cn.inkforge.contracts.api.WorkspaceChapter;
import java.time.OffsetDateTime;
import java.util.List;

/** 章节用例所需的持久化端口；实现必须保持单事务锁顺序与 CAS 语义。 */
public interface ChapterRepository {

    WorkspaceChapter create(String novelId, String userId);

    List<WorkspaceChapter> list(String novelId, String userId);

    WorkspaceChapter get(String chapterId, String userId);

    OffsetDateTime updateDraft(
            String chapterId,
            String userId,
            String title,
            String content,
            OffsetDateTime expectedUpdatedAt);

    OffsetDateTime upsertProgress(
            String chapterId,
            String userId,
            String content,
            OffsetDateTime expectedUpdatedAt);

    ChapterRecord transitionStatus(
            String chapterId,
            String userId,
            ChapterStatus status,
            OffsetDateTime expectedUpdatedAt);
}
