package cn.inkforge.core.writing.application;

import cn.inkforge.contracts.api.CancelWritingRunRequest;
import cn.inkforge.contracts.api.CancelWritingRunResponse;
import cn.inkforge.contracts.api.ResumeWritingRunRequest;
import cn.inkforge.contracts.api.ResumeWritingRunResponse;
import cn.inkforge.contracts.api.WritingRunListResponse;
import cn.inkforge.contracts.api.WritingRunResponse;
import cn.inkforge.contracts.api.WritingRunStatusResponse;
import cn.inkforge.core.generated.model.WritingRunStartBody;
import java.util.Objects;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

/** 浏览器写作运行用例；数据库提交成功后只尽力即时投递，失败仍由后台补偿。 */
public final class WritingRunService {

    private static final Logger LOGGER = LoggerFactory.getLogger(WritingRunService.class);

    private final WritingRunStartRequestParser parser;
    private final WritingCommandRepository commands;
    private final WritingRunQueryRepository queries;
    private final WritingRunCommandDispatcher dispatcher;

    public WritingRunService(
            WritingRunStartRequestParser parser,
            WritingCommandRepository commands,
            WritingRunQueryRepository queries,
            WritingRunCommandDispatcher dispatcher) {
        this.parser = Objects.requireNonNull(parser);
        this.commands = Objects.requireNonNull(commands);
        this.queries = Objects.requireNonNull(queries);
        this.dispatcher = Objects.requireNonNull(dispatcher);
    }

    public WritingRunResponse start(String userId, WritingRunStartBody body) {
        WritingRunResponse response = commands.start(userId, parser.parse(body));
        kick();
        return response;
    }

    public ResumeWritingRunResponse resume(
            String userId, String taskId, ResumeWritingRunRequest request) {
        ResumeWritingRunResponse response = commands.resume(userId, taskId, request);
        kick();
        return response;
    }

    public CancelWritingRunResponse cancel(
            String userId, String taskId, CancelWritingRunRequest request) {
        CancelWritingRunResponse response = commands.cancel(userId, taskId, request);
        if (response.getCommandStatus() == CancelWritingRunResponse.CommandStatusEnum.PENDING) {
            kick();
        }
        return response;
    }

    public WritingRunStatusResponse get(String userId, String taskId) {
        return queries.get(userId, taskId);
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
