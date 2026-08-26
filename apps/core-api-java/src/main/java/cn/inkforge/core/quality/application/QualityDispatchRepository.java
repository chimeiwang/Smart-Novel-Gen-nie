package cn.inkforge.core.quality.application;

import cn.inkforge.core.quality.domain.QualityDispatchRecord;
import java.util.List;

/** dispatcher 需要的窄持久化端口，避免后台执行器获得无关业务写能力。 */
public interface QualityDispatchRepository {

    List<QualityDispatchRecord> listDispatchable(int limit);

    void markRunning(String runId);

    void recordDispatchFailure(String runId, String errorCode);

    void failRun(String userId, String checkId, String runId, String novelId);
}
