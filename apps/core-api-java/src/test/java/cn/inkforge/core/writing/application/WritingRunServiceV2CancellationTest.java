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
        verifyNoInteractions(dependencies.queries());
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
                dependencies.dispatcher());
    }







    @Test
    void 历史取消明确拒绝且不调用旧引擎或写作命令() {
        var d = dependencies();
        when(d.engines().probe("user-1", "old-run")).thenReturn(EngineIdentityProbe.EngineIdentity.V2);
        assertThatThrownBy(() -> d.service().cancel("user-1", "old-run", new CancelWritingRunRequest("retired-cancel")))
                .isInstanceOfSatisfying(ApiException.class, e -> assertThat(e.code()).isEqualTo("EXECUTION_ENGINE_RETIRED"));
        verifyNoInteractions(d.commands(), d.queries(), d.dispatcher());
    }

    private static Dependencies dependencies() {
        var parser = mock(WritingRunStartRequestParser.class);
        WritingRunStarter starter = (u, r) -> { throw new AssertionError("本测试不创建任务"); };
        var commands = mock(WritingCommandRepository.class);
        var queries = mock(WritingRunQueryRepository.class);
        var dispatcher = mock(WritingRunCommandDispatcher.class);
        var engines = mock(EngineIdentityProbe.class);
        return new Dependencies(new WritingRunService(parser, starter, commands, queries, dispatcher, engines), commands, queries, dispatcher, engines);
    }
    private record Dependencies(WritingRunService service, WritingCommandRepository commands,
            WritingRunQueryRepository queries, WritingRunCommandDispatcher dispatcher, EngineIdentityProbe engines) {}
}
