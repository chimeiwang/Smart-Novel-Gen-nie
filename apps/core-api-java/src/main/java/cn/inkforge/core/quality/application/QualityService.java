package cn.inkforge.core.quality.application;

import cn.inkforge.contracts.api.QualityCheckDto;
import cn.inkforge.contracts.api.QualityRunContextRequest;
import cn.inkforge.contracts.api.QualityRunContextResponse;
import cn.inkforge.contracts.api.QualityRunFailureRequest;
import cn.inkforge.contracts.api.QualityRunSuccessRequest;
import cn.inkforge.contracts.api.RunQualityCheckRequest;
import cn.inkforge.contracts.api.RunQualityCheckResponse;
import cn.inkforge.contracts.api.UpdateQualityCheckRequest;
import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.quality.domain.QualityRunCreation;
import java.util.Objects;
import org.openapitools.jackson.nullable.JsonNullable;

/** 质量检查用例入口；运行先耐久化，即时投递失败仍由后台补偿。 */
public final class QualityService {

    private final QualityRepository repository;
    private final QualityRunDispatcher dispatcher;

    public QualityService(QualityRepository repository, QualityRunDispatcher dispatcher) {
        this.repository = Objects.requireNonNull(repository);
        this.dispatcher = dispatcher;
    }

    public QualityCheckDto get(String userId, String checkId) {
        return repository.get(userId, checkId);
    }

    public QualityCheckDto update(
            String userId, String checkId, UpdateQualityCheckRequest request) {
        return repository.updateStatus(userId, checkId, request);
    }

    public RunQualityCheckResponse run(
            String userId, String checkId, RunQualityCheckRequest request) {
        if (dispatcher == null) {
            throw new ApiException(
                    503,
                    "QUALITY_RUN_UNAVAILABLE",
                    "质量检查运行服务暂时不可用");
        }
        QualityRunCreation creation = repository.createRun(userId, checkId, request);
        if (creation.created()) dispatcher.dispatch(creation.record());
        return new RunQualityCheckResponse(true, checkId, creation.record().runId());
    }

    public QualityRunContextResponse context(
            String checkId, QualityRunContextRequest request) {
        QualityRunContextResponse context = repository.context(
                request.getUserId(),
                checkId,
                request.getRunId(),
                nullable(request.getSourceTaskId()),
                nullable(request.getMessage()));
        if (!request.getNovelId().equals(context.getNovelId())) {
            throw new ApiException(
                    403,
                    "QUALITY_RESOURCE_MISMATCH",
                    "质量检查资源绑定不匹配");
        }
        return context;
    }

    public void complete(String checkId, QualityRunSuccessRequest request) {
        repository.completeRun(
                request.getUserId(),
                checkId,
                request.getRunId(),
                request.getNovelId(),
                request);
    }

    public void fail(String checkId, QualityRunFailureRequest request) {
        repository.failRun(
                request.getUserId(),
                checkId,
                request.getRunId(),
                request.getNovelId());
    }

    private static <T> T nullable(JsonNullable<T> value) {
        return value == null || value.isUndefined() ? null : value.orElse(null);
    }
}
