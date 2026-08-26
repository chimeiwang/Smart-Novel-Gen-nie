package cn.inkforge.core.quality.application;

import cn.inkforge.contracts.api.QualityCheckDto;
import cn.inkforge.contracts.api.QualityRunContextResponse;
import cn.inkforge.contracts.api.QualityRunSuccessRequest;
import cn.inkforge.contracts.api.RunQualityCheckRequest;
import cn.inkforge.contracts.api.UpdateQualityCheckRequest;
import cn.inkforge.core.quality.domain.QualityRunCreation;

/** 质量检查业务与 PostgreSQL 的权威边界。 */
public interface QualityRepository extends QualityDispatchRepository {

    QualityCheckDto get(String userId, String checkId);

    QualityCheckDto updateStatus(
            String userId, String checkId, UpdateQualityCheckRequest request);

    QualityRunCreation createRun(
            String userId, String checkId, RunQualityCheckRequest request);

    QualityRunContextResponse context(
            String userId,
            String checkId,
            String runId,
            String sourceTaskId,
            String message);

    void completeRun(
            String userId,
            String checkId,
            String runId,
            String novelId,
            QualityRunSuccessRequest result);
}
