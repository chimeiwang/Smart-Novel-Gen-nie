package cn.inkforge.core.writing.application;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

import cn.inkforge.contracts.api.CancelWritingRunRequest;
import cn.inkforge.contracts.api.CancelWritingRunResponse;
import cn.inkforge.contracts.api.ResumeWritingRunRequest;
import cn.inkforge.contracts.api.ResumeWritingRunResponse;
import cn.inkforge.contracts.api.WritingRunV2Response;
import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.workflows.application.WorkflowRunCancellationService;
import org.junit.jupiter.api.Test;

class WritingRunServiceV2CancellationTest {

    @Test
    void 畸形但可恢复的V1任务直接透传resume且不构造公共Snapshot() {
        Dependencies dependencies = dependencies();
        ResumeWritingRunRequest request = new ResumeWritingRunRequest("resume-request-0001");
        ResumeWritingRunResponse expected = mock(ResumeWritingRunResponse.class);
        when(dependencies.engines().probe("user-1", "legacy-task"))
                .thenReturn(EngineIdentityProbe.EngineIdentity.V1_OR_MISSING);
        when(dependencies.queries().getPublic("user-1", "legacy-task"))
                .thenThrow(new IllegalStateException("损坏的历史公开投影不应被读取"));
        when(dependencies.commands().resume("user-1", "legacy-task", request))
                .thenReturn(expected);

        var result = dependencies.service().resume("user-1", "legacy-task", request);

        assertThat(result).isSameAs(expected);
        verify(dependencies.commands()).resume("user-1", "legacy-task", request);
        verify(dependencies.dispatcher()).runOnce();
        verifyNoInteractions(dependencies.queries(), dependencies.cancellations());
    }

    @Test
    void V1取消直接透传并完整保留原命令结果() {
        Dependencies dependencies = dependencies();
        CancelWritingRunRequest request = new CancelWritingRunRequest("cancel-request-0001");
        CancelWritingRunResponse expected = mock(CancelWritingRunResponse.class);
        when(expected.getCommandStatus())
                .thenReturn(CancelWritingRunResponse.CommandStatusEnum.SUCCEEDED);
        when(dependencies.engines().probe("user-1", "legacy-task"))
                .thenReturn(EngineIdentityProbe.EngineIdentity.V1_OR_MISSING);
        when(dependencies.commands().cancel("user-1", "legacy-task", request))
                .thenReturn(expected);

        var result = dependencies.service().cancel("user-1", "legacy-task", request);

        assertThat(result).isSameAs(expected);
        verify(dependencies.commands()).cancel("user-1", "legacy-task", request);
        verifyNoInteractions(
                dependencies.queries(),
                dependencies.cancellations(),
                dependencies.dispatcher());
    }

    @Test
    void V2未命中后的V1缺失与越权异常保持原样() {
        Dependencies dependencies = dependencies();
        ResumeWritingRunRequest resume = new ResumeWritingRunRequest("resume-request-0002");
        CancelWritingRunRequest cancel = new CancelWritingRunRequest("cancel-request-0002");
        ApiException missing = new ApiException(404, "WRITING_TASK_NOT_FOUND", "写作任务不存在");
        ApiException forbidden = new ApiException(403, "WRITING_TASK_FORBIDDEN", "无权访问该写作任务");
        when(dependencies.engines().probe("user-1", "missing-task"))
                .thenReturn(EngineIdentityProbe.EngineIdentity.V1_OR_MISSING);
        when(dependencies.engines().probe("user-1", "foreign-task"))
                .thenReturn(EngineIdentityProbe.EngineIdentity.V1_OR_MISSING);
        when(dependencies.commands().resume("user-1", "missing-task", resume))
                .thenThrow(missing);
        when(dependencies.commands().cancel("user-1", "foreign-task", cancel))
                .thenThrow(forbidden);

        assertThatThrownBy(() -> dependencies.service().resume("user-1", "missing-task", resume))
                .isSameAs(missing);
        assertThatThrownBy(() -> dependencies.service().cancel("user-1", "foreign-task", cancel))
                .isSameAs(forbidden);
        verifyNoInteractions(
                dependencies.queries(),
                dependencies.cancellations(),
                dependencies.dispatcher());
    }

    @Test
    void V2Owner任意状态都稳定拒绝旧resume且不触碰V1命令() {
        Dependencies dependencies = dependencies();
        when(dependencies.engines().probe("user-1", "run-2"))
                .thenReturn(EngineIdentityProbe.EngineIdentity.V2);

        assertThatThrownBy(() -> dependencies.service().resume(
                        "user-1",
                        "run-2",
                        new ResumeWritingRunRequest("resume-request-0003")))
                .isInstanceOfSatisfying(ApiException.class, error -> {
                    assertThat(error.statusCode()).isEqualTo(409);
                    assertThat(error.code()).isEqualTo("WORKFLOW_RESUME_UNSUPPORTED");
                });

        verifyNoInteractions(
                dependencies.commands(),
                dependencies.queries(),
                dependencies.dispatcher(),
                dependencies.cancellations());
    }

    @Test
    void 按轻量持久Engine身份将V2取消交给Workflow并在提交后回读Snapshot() {
        Dependencies dependencies = dependencies();
        WritingRunV2Response after = mock(WritingRunV2Response.class);
        when(dependencies.engines().probe("user-1", "run-2"))
                .thenReturn(EngineIdentityProbe.EngineIdentity.V2);
        when(dependencies.queries().getPublic("user-1", "run-2")).thenReturn(after);

        var result = dependencies.service().cancel(
                "user-1", "run-2", new CancelWritingRunRequest("cancel-request-0003"));

        assertThat(result).isSameAs(after);
        verify(dependencies.cancellations())
                .cancel("user-1", "run-2", "cancel-request-0003");
        verify(dependencies.queries()).getPublic("user-1", "run-2");
        verifyNoInteractions(dependencies.commands(), dependencies.dispatcher());
    }

    @Test
    void 越权V2身份禁止回退到同ID的V1命令() {
        Dependencies dependencies = dependencies();
        ApiException forbidden = new ApiException(
                403, "WRITING_TASK_FORBIDDEN", "无权访问该写作任务");
        when(dependencies.engines().probe("user-1", "identity-collision"))
                .thenThrow(forbidden);

        assertThatThrownBy(() -> dependencies.service().resume(
                        "user-1",
                        "identity-collision",
                        new ResumeWritingRunRequest("resume-request-0004")))
                .isSameAs(forbidden);
        assertThatThrownBy(() -> dependencies.service().cancel(
                        "user-1",
                        "identity-collision",
                        new CancelWritingRunRequest("cancel-request-0004")))
                .isSameAs(forbidden);

        verifyNoInteractions(
                dependencies.commands(),
                dependencies.queries(),
                dependencies.dispatcher(),
                dependencies.cancellations());
    }

    @Test
    void V2取消器未装配时返回稳定503且不回退V1() {
        Dependencies dependencies = dependencies(null);
        when(dependencies.engines().probe("user-1", "run-2"))
                .thenReturn(EngineIdentityProbe.EngineIdentity.V2);

        assertThatThrownBy(() -> dependencies.service().cancel(
                        "user-1",
                        "run-2",
                        new CancelWritingRunRequest("cancel-request-0005")))
                .isInstanceOfSatisfying(ApiException.class, error -> {
                    assertThat(error.statusCode()).isEqualTo(503);
                    assertThat(error.code()).isEqualTo("WORKFLOW_CANCELLATION_UNAVAILABLE");
                });

        verifyNoInteractions(
                dependencies.commands(), dependencies.queries(), dependencies.dispatcher());
    }

    private static Dependencies dependencies() {
        return dependencies(mock(WorkflowRunCancellationService.class));
    }

    private static Dependencies dependencies(WorkflowRunCancellationService cancellations) {
        WritingRunStartRequestParser parser = mock(WritingRunStartRequestParser.class);
        WritingRunStarter starter = (userId, request) -> {
            throw new AssertionError("本测试不应启动新的写作运行");
        };
        WritingCommandRepository commands = mock(WritingCommandRepository.class);
        WritingRunQueryRepository queries = mock(WritingRunQueryRepository.class);
        WritingRunCommandDispatcher dispatcher = mock(WritingRunCommandDispatcher.class);
        EngineIdentityProbe engines = mock(EngineIdentityProbe.class);
        WritingRunService service = new WritingRunService(
                parser,
                starter,
                commands,
                queries,
                dispatcher,
                engines,
                cancellations);
        return new Dependencies(
                service, commands, queries, dispatcher, engines, cancellations);
    }

    private record Dependencies(
            WritingRunService service,
            WritingCommandRepository commands,
            WritingRunQueryRepository queries,
            WritingRunCommandDispatcher dispatcher,
            EngineIdentityProbe engines,
            WorkflowRunCancellationService cancellations) {}
}
