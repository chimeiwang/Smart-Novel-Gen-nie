package cn.inkforge.core.styles.application;

import cn.inkforge.core.styles.domain.ApplyStyleResult;
import cn.inkforge.core.styles.domain.PortraitDispatchRecord;
import cn.inkforge.core.styles.domain.PortraitDispatchStatus;
import cn.inkforge.core.styles.domain.PortraitSection;
import cn.inkforge.core.styles.domain.PortraitSource;
import cn.inkforge.core.styles.domain.PortraitSuccessData;
import cn.inkforge.core.styles.domain.PortraitTaskSnapshot;
import cn.inkforge.core.styles.domain.StyleReferenceSnapshot;
import cn.inkforge.core.styles.domain.StyleSnapshot;
import java.time.OffsetDateTime;
import java.util.List;

/** 文风、参考文件元数据、画像任务与应用关系的持久化端口。 */
public interface StyleRepository {

    List<StyleSnapshot> list(String userId);

    StyleSnapshot create(String userId, String name);

    String reserveReference(String userId, String styleId);

    StyleReferenceSnapshot createReference(
            String userId, String styleId, String referenceId, StoredStyleFile file);

    String deleteReference(String userId, String styleId, String referenceId);

    List<String> deleteStyle(String userId, String styleId);

    PortraitTaskSnapshot createPortraitTask(
            String userId, String styleId, PortraitSection section);

    List<PortraitSource> portraitSources(String styleId, String taskId);

    PortraitTaskSnapshot getPortraitTask(String userId, String taskId);

    PortraitTaskSnapshot transitionPortraitTask(
            String styleId,
            String taskId,
            String target,
            PortraitSuccessData data,
            PortraitSection expectedSection,
            boolean validateSection);

    StyleSnapshot updateSection(
            String userId, String styleId, PortraitSection section, String content);

    ApplyStyleResult applyStyle(
            String novelId, String userId, String styleId, String expectedStyleId);

    List<PortraitDispatchRecord> listReconcilable(
            int limit, OffsetDateTime staleBefore);

    void markDispatchTerminal(
            String styleId, String taskId, PortraitDispatchStatus status);
}
