package cn.inkforge.core.video.infrastructure;

import cn.inkforge.core.db.generated.tables.records.VideochapteradaptationRecord;
import cn.inkforge.core.db.generated.tables.records.VideochapteradaptationheadRecord;
import cn.inkforge.core.db.generated.tables.records.VideoepisodeplanversionRecord;
import cn.inkforge.core.db.generated.tables.records.VideoprojectRecord;
import cn.inkforge.core.db.generated.tables.records.VideoshotRecord;
import java.util.List;

/** 同一正式镜头方案与分集方案下的后期制作数据库上下文。 */
record VideoPostProductionContext(
        VideochapteradaptationRecord adaptation,
        VideoprojectRecord project,
        VideochapteradaptationheadRecord head,
        VideoepisodeplanversionRecord episodePlan,
        List<VideoshotRecord> shots,
        List<List<VideoshotRecord>> episodes) {

    String planId() {
        return head.getCurrentshotplanversionid();
    }

    List<VideoshotRecord> requireEpisode(int episodeNo) {
        if (episodeNo < 1 || episodeNo > episodes.size()) {
            throw new cn.inkforge.core.platform.http.ApiException(
                    404, "VIDEO_EPISODE_NOT_FOUND", "正式分集不存在");
        }
        return episodes.get(episodeNo - 1);
    }
}
