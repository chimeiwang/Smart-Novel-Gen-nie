package cn.inkforge.core.video.infrastructure;

import static cn.inkforge.core.db.generated.Tables.VIDEOEPISODEBOUNDARY;
import static cn.inkforge.core.db.generated.Tables.VIDEOEPISODEPLANVERSION;
import static cn.inkforge.core.db.generated.Tables.VIDEOSHOT;

import cn.inkforge.core.db.generated.tables.records.VideoepisodeplanversionRecord;
import cn.inkforge.core.db.generated.tables.records.VideoshotRecord;
import cn.inkforge.core.platform.http.ApiException;
import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;
import org.jooq.DSLContext;

/** 后期制作各写仓储和读模型共用的正式方案一致性入口。 */
final class VideoPostProductionDatabaseAccess {

    private VideoPostProductionDatabaseAccess() {}

    static VideoPostProductionContext context(
            DSLContext transaction, String userId, String adaptationId, boolean lock) {
        var base = VideoDatabaseAccess.ownedAdaptation(
                transaction, userId, adaptationId, lock);
        String planId = base.head().getCurrentshotplanversionid();
        if (planId == null) {
            throw error(
                    409,
                    "VIDEO_POST_PRODUCTION_FORMAL_PLAN_REQUIRED",
                    "请先确认正式镜头方案");
        }
        String episodePlanId = base.head().getCurrentepisodeplanversionid();
        if (episodePlanId == null) {
            throw error(
                    409,
                    "VIDEO_POST_PRODUCTION_EPISODE_PLAN_REQUIRED",
                    "请先保存正式分集方案");
        }
        VideoepisodeplanversionRecord episodePlan = transaction
                .selectFrom(VIDEOEPISODEPLANVERSION)
                .where(VIDEOEPISODEPLANVERSION.ID.eq(episodePlanId))
                .fetchOne();
        if (episodePlan == null
                || !episodePlan.getAdaptationid().equals(adaptationId)
                || !episodePlan.getShotplanversionid().equals(planId)) {
            throw error(
                    409,
                    "VIDEO_POST_PRODUCTION_PLAN_INVALID",
                    "当前正式镜头与分集版本指针不一致");
        }
        List<VideoshotRecord> shots = transaction.selectFrom(VIDEOSHOT)
                .where(VIDEOSHOT.PLANVERSIONID.eq(planId))
                .orderBy(VIDEOSHOT.ORDINAL)
                .fetch();
        if (shots.isEmpty()) {
            throw error(
                    409,
                    "VIDEO_POST_PRODUCTION_SHOTS_REQUIRED",
                    "当前正式方案没有可制作镜头");
        }
        Set<String> breaks = new LinkedHashSet<>(transaction
                .select(VIDEOEPISODEBOUNDARY.AFTERSHOTID)
                .from(VIDEOEPISODEBOUNDARY)
                .where(VIDEOEPISODEBOUNDARY.EPISODEPLANVERSIONID.eq(episodePlanId))
                .orderBy(VIDEOEPISODEBOUNDARY.ORDINAL)
                .fetch(VIDEOEPISODEBOUNDARY.AFTERSHOTID));
        Set<String> shotIds = shots.stream()
                .map(VideoshotRecord::getId)
                .collect(java.util.stream.Collectors.toSet());
        if (!shotIds.containsAll(breaks)) {
            throw error(
                    409,
                    "VIDEO_POST_PRODUCTION_EPISODE_PLAN_INVALID",
                    "当前分集版本引用了其他镜头方案");
        }
        List<List<VideoshotRecord>> episodes = new ArrayList<>();
        List<VideoshotRecord> current = new ArrayList<>();
        for (VideoshotRecord shot : shots) {
            current.add(shot);
            if (breaks.contains(shot.getId())) {
                episodes.add(List.copyOf(current));
                current.clear();
            }
        }
        if (!current.isEmpty()) episodes.add(List.copyOf(current));
        if (episodes.isEmpty()) {
            throw error(
                    409,
                    "VIDEO_POST_PRODUCTION_EPISODE_PLAN_INVALID",
                    "当前分集版本无法形成有效分集");
        }
        return new VideoPostProductionContext(
                base.adaptation(),
                base.project(),
                base.head(),
                episodePlan,
                List.copyOf(shots),
                List.copyOf(episodes));
    }

    private static ApiException error(int status, String code, String message) {
        return new ApiException(status, code, message);
    }
}
