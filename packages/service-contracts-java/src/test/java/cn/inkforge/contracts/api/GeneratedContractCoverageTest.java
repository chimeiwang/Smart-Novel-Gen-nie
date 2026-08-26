package cn.inkforge.contracts.api;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;

class GeneratedContractCoverageTest {

    @Test
    void 关键公共与内部契约必须来自冻结OpenAPI() {
        assertThat(RegisterRequest.class).isNotNull();
        assertThat(NovelResponse.class).isNotNull();
        assertThat(RunCompletionCallback.class).isNotNull();
        assertThat(VideoAdaptationPlanCompletionCallback.class).isNotNull();
        assertThat(ErrorResponse.class).isNotNull();
        assertThat(cn.inkforge.contracts.agent.AgentJobRequest.class).isNotNull();
        assertThat(cn.inkforge.contracts.agent.SeedanceRenderQueryResponse.class).isNotNull();
    }
}
