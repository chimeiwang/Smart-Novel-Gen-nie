package cn.inkforge.contracts.api;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import tools.jackson.databind.ObjectMapper;

class GeneratedContractCoverageTest {

    @Test
    void 关键公共与内部契约必须来自冻结OpenAPI() {
        assertThat(RegisterRequest.class).isNotNull();
        assertThat(NovelResponse.class).isNotNull();
        assertThat(RunCompletionCallback.class).isNotNull();
        assertThat(VideoAdaptationPlanCompletionCallback.class).isNotNull();
        assertThat(RunSnapshot.class).isNotNull();
        assertThat(WorkflowEventEnvelope.class).isNotNull();
        assertThat(StepProgressEventPayload.class).isNotNull();
        assertThat(ErrorResponse.class).isNotNull();
        assertThat(cn.inkforge.contracts.agent.AgentJobRequest.class).isNotNull();
        assertThat(cn.inkforge.contracts.agent.SeedanceRenderQueryResponse.class).isNotNull();
    }

    @Test
    void 写作运行联合必须按数字引擎版本反序列化() throws Exception {
        var json = new ObjectMapper();
        var v1 = json.readValue(
                """
                {
                  "engineVersion": 1,
                  "runId": "task-1",
                  "taskId": "task-1",
                  "id": "task-1",
                  "novelId": "novel-1",
                  "chapterId": "chapter-1",
                  "writingSessionId": null,
                  "phase": "active",
                  "targetWordCount": 4000,
                  "selectedAgents": [],
                  "createdAt": "2026-09-01T00:00:00Z",
                  "updatedAt": "2026-09-01T00:00:00Z",
                  "commandId": "command-1",
                  "commandStatus": "pending"
                }
                """,
                WritingRunStartResponse.class);
        var v2 = json.readValue(
                """
                {
                  "workflow": "long_serial",
                  "operation": null,
                  "status": "running",
                  "currentStep": null,
                  "cancelRequestedAt": null,
                  "lastEventSequence": 1,
                  "revision": 1,
                  "artifact": null,
                  "error": null,
                  "engineVersion": 2,
                  "runId": "run-2",
                  "taskId": "run-2",
                  "chapterId": null,
                  "commandId": null,
                  "commandStatus": null
                }
                """,
                WritingRunStartResponse.class);

        assertThat(v1).isInstanceOf(WritingRunResponse.class);
        assertThat(v2).isInstanceOf(WritingRunV2Response.class);
        assertThat(json.valueToTree(v1).path("engineVersion").isIntegralNumber()).isTrue();
        assertThat(json.valueToTree(v1).path("engineVersion").intValue()).isEqualTo(1);
        assertThat(json.valueToTree(v2).path("engineVersion").isIntegralNumber()).isTrue();
        assertThat(json.valueToTree(v2).path("engineVersion").intValue()).isEqualTo(2);
    }
}
