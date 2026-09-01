package cn.inkforge.core.writing.application;

import cn.inkforge.contracts.api.CancelWritingRunRequest;
import cn.inkforge.contracts.api.CancelWritingRunPublicResponse;
import cn.inkforge.contracts.api.CancelWritingRunResponse;
import cn.inkforge.contracts.api.ResumeWritingRunRequest;
import cn.inkforge.contracts.api.ResumeWritingRunResponse;
import cn.inkforge.contracts.api.WritingRunListResponse;
import cn.inkforge.contracts.api.WritingRunStartResponse;
import cn.inkforge.contracts.api.WritingRunStatusPublicResponse;
import cn.inkforge.core.generated.model.WritingRunStartBody;
import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.workflows.application.WorkflowRunCancellationService;
import java.util.Objects;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/** 浏览器写作运行用例；数据库提交成功后只尽力即时投递，失败仍由后台补偿。 */
public final class WritingRunService {

    private static final Logger LOGGER = LoggerFactory.getLogger(WritingRunService.class);

    private final WritingRunStartRequestParser parser;
    private final WritingRunStarter starter;
    private final WritingCommandRepository commands;
    private final WritingRunQueryRepository queries;
    private final WritingRunCommandDispatcher dispatcher;
    private final EngineIdentityProbe engineIdentities;
    private final WorkflowRunCancellationService workflowCancellations;

    public WritingRunService(
            WritingRunStartRequestParser parser,
            WritingCommandRepository commands,
            WritingRunQueryRepository queries,
            WritingRunCommandDispatcher dispatcher) {
        this(
                parser,
                commands::start,
                commands,
                queries,
                dispatcher,
                EngineIdentityProbe.v1Only(),
                null);
    }

    public WritingRunService(
            WritingRunStartRequestParser parser,
            WritingRunStarter starter,
            WritingCommandRepository commands,
            WritingRunQueryRepository queries,
            WritingRunCommandDispatcher dispatcher) {
        this(
                parser,
                starter,
                commands,
                queries,
                dispatcher,
                EngineIdentityProbe.v1Only(),
                null);
    }

    public WritingRunService(
            WritingRunStartRequestParser parser,
            WritingRunStarter starter,
            WritingCommandRepository commands,
            WritingRunQueryRepository queries,
            WritingRunCommandDispatcher dispatcher,
            EngineIdentityProbe engineIdentities,
            WorkflowRunCancellationService workflowCancellations) {
        this.parser = Objects.requireNonNull(parser);
        this.starter = Objects.requireNonNull(starter);
        this.commands = Objects.requireNonNull(commands);
        this.queries = Objects.requireNonNull(queries);
        this.dispatcher = Objects.requireNonNull(dispatcher);
        this.engineIdentities = Objects.requireNonNull(engineIdentities);
        this.workflowCancellations = workflowCancellations;
    }

    public WritingRunStartResponse start(String userId, WritingRunStartBody body) {
        WritingRunStartResponse response = starter.start(userId, parser.parse(body));
        kick();
        return response;
    }

    public ResumeWritingRunResponse resume(
            String userId, String taskId, ResumeWritingRunRequest request) {
        if (engineIdentities.probe(userId, taskId)
                == EngineIdentityProbe.EngineIdentity.V2) {
            throw new ApiException(
                    409,
                    "WORKFLOW_RESUME_UNSUPPORTED",
                    "耐久 Workflow 不恢复旧 Run；请创建新的写作运行或提交当前待办决定");
        }
        ResumeWritingRunResponse response = commands.resume(userId, taskId, request);
        kick();
        return response;
    }

    public CancelWritingRunPublicResponse cancel(
            String userId, String taskId, CancelWritingRunRequest request) {
        if (engineIdentities.probe(userId, taskId)
                == EngineIdentityProbe.EngineIdentity.V2) {
            if (workflowCancellations == null) {
                throw new ApiException(
                        503,
                        "WORKFLOW_CANCELLATION_UNAVAILABLE",
                        "耐久 Workflow 取消暂时不可用");
            }
            workflowCancellations.cancel(userId, taskId, request.getClientRequestId());
            return (CancelWritingRunPublicResponse) queries.getPublic(userId, taskId);
        }
        CancelWritingRunResponse response = commands.cancel(userId, taskId, request);
        if (response.getCommandStatus() == CancelWritingRunResponse.CommandStatusEnum.PENDING) {
            kick();
        }
        return response;
    }

    public WritingRunStatusPublicResponse get(String userId, String taskId) {
        return queries.getPublic(userId, taskId);
    }

    public WritingRunListResponse list(
            String userId,
            String novelId,
            String chapterId,
            String writingSessionId,
            String operation,
            String outcome,
            String cursor,
            int limit) {
        return queries.list(
                userId,
                novelId,
                chapterId,
                writingSessionId,
                operation,
                outcome,
                cursor,
                limit);
    }

    private void kick() {
        try {
            dispatcher.runOnce();
        } catch (RuntimeException exception) {
            LOGGER.warn("写作命令即时投递失败，已交由后台重试");
        }
    }
}
