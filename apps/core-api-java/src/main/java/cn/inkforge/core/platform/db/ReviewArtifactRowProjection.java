package cn.inkforge.core.platform.db;

import static cn.inkforge.core.db.generated.Tables.REVIEWARTIFACT;

import java.util.Arrays;
import org.jooq.Field;

/** 已上线写作与审核记录的稳定投影，避免生成模型中的未开放视频字段渗入普通查询。 */
public final class ReviewArtifactRowProjection {

    private static final Field<?>[] FIELDS = {
        REVIEWARTIFACT.ID,
        REVIEWARTIFACT.NOVELID,
        REVIEWARTIFACT.CHAPTERID,
        REVIEWARTIFACT.TASKID,
        REVIEWARTIFACT.WORKFLOWRUNID,
        REVIEWARTIFACT.ARTIFACTKEY,
        REVIEWARTIFACT.KIND,
        REVIEWARTIFACT.STATUS,
        REVIEWARTIFACT.TITLE,
        REVIEWARTIFACT.SUMMARY,
        REVIEWARTIFACT.PAYLOADJSON,
        REVIEWARTIFACT.DIFFJSON,
        REVIEWARTIFACT.CREATEDBYAGENT,
        REVIEWARTIFACT.UPDATEDBYAGENT,
        REVIEWARTIFACT.REVIEWERAGENT,
        REVIEWARTIFACT.REVISION,
        REVIEWARTIFACT.APPLIEDAT,
        REVIEWARTIFACT.CREATEDAT,
        REVIEWARTIFACT.UPDATEDAT
    };

    private ReviewArtifactRowProjection() {}

    /** 保留完整候选、差异和来源字段；普通写作不依赖视频扩展列，不能用摘要投影代替审核记录。 */
    public static Field<?>[] fields() {
        return Arrays.copyOf(FIELDS, FIELDS.length);
    }
}
