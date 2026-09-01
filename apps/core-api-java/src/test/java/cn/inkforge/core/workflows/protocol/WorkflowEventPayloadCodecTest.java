package cn.inkforge.core.workflows.protocol;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import cn.inkforge.contracts.api.ReviewStartedEventPayload;
import cn.inkforge.contracts.api.StepFinishedEventPayload;
import cn.inkforge.contracts.api.StepProgressEventPayload;
import jakarta.validation.Validation;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import tools.jackson.databind.json.JsonMapper;

class WorkflowEventPayloadCodecTest {

    private static final String MODEL_PROFILE = """
            {"profile":"writer.chapter_selection.v1","version":1,
             "reasoningMode":"bounded",
             "deploymentProfileKey":"deployment.writer.chapter_selection.v1",
             "promptProfile":{"name":"prompt.writer.chapter_selection.v1","version":1,
                              "sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}}
            """;
    private static final String RESOLVED_MODEL = """
            {"deploymentProfileKey":"deployment.writer.chapter_selection.v1",
             "deploymentFingerprint":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
             "provider":"openai_compatible","model":"deepseek-v4-flash",
             "transportProfile":"transport.deepseek-v4.v1",
             "endpointProfile":"endpoint.deepseek-official.v1",
             "structuredOutputRoute":"chat_json_output_v1",
             "capabilityVersion":"capability.deepseek-v4.chat-json.v1",
             "reasoningMode":"bounded","supportsRequestIdempotency":false}
            """;

    private static jakarta.validation.ValidatorFactory validatorFactory;
    private static WorkflowEventPayloadCodec codec;

    @BeforeAll
    static void createCodec() {
        validatorFactory = Validation.buildDefaultValidatorFactory();
        codec = new WorkflowEventPayloadCodec(
                JsonMapper.builder().build(), validatorFactory.getValidator());
    }

    @AfterAll
    static void closeValidator() {
        validatorFactory.close();
    }

    @Test
    void 按EventType返回生成Dto并保留精确字段() {
        Object parsed = codec.parse(
                "step_progress",
                """
                {"stepId":"step-1","fencingToken":2,"progressSequence":3,
                 "modelProfile":%s,"resolvedModel":%s,
                 "phase":"waiting_provider","elapsedSeconds":4,
                 "waitingOnProvider":true,"usageStatus":"partial"}
                """.formatted(MODEL_PROFILE, RESOLVED_MODEL));

        assertThat(parsed).isInstanceOfSatisfying(
                StepProgressEventPayload.class,
                value -> {
                    assertThat(value.getStepId()).isEqualTo("step-1");
                    assertThat(value.getProgressSequence()).isEqualTo(3);
                    assertThat(value.getModelProfile().getProfile())
                            .isEqualTo("writer.chapter_selection.v1");
                    assertThat(value.getResolvedModel().getModel())
                            .isEqualTo("deepseek-v4-flash");
                });

        Object finished = codec.parse(
                "step_finished",
                """
                {"stepId":"step-1","fencingToken":2,
                 "status":"failed","errorCode":"PROVIDER_REJECTED"}
                """);
        assertThat(finished).isInstanceOfSatisfying(
                StepFinishedEventPayload.class,
                value -> assertThat(value.getErrorCode()).isEqualTo("PROVIDER_REJECTED"));

        Object reviewStarted = codec.parse(
                "review_started",
                """
                {"artifactId":"artifact-1","artifactRevision":1,
                 "reviewerSteps":[
                   {"stepId":"review-1","ordinal":2,"purpose":"review",
                    "lane":"creative","modelProfile":%s,"status":"pending",
                    "attemptCount":0,"fencingToken":0},
                   {"stepId":"review-2","ordinal":3,"purpose":"review",
                    "lane":"creative","modelProfile":%s,"status":"pending",
                    "attemptCount":0,"fencingToken":0}]}
                """.formatted(MODEL_PROFILE, MODEL_PROFILE));
        assertThat(reviewStarted).isInstanceOfSatisfying(
                ReviewStartedEventPayload.class,
                value -> assertThat(value.getReviewerSteps()).hasSize(2));
    }

    @Test
    void 拒绝未知字段标量强制转换和跨字段矛盾() {
        assertInvalid(
                "step_progress",
                """
                {"stepId":"step-1","fencingToken":2,"progressSequence":3,
                 "modelProfile":%s,"resolvedModel":%s,
                 "phase":"waiting_provider","elapsedSeconds":4,
                 "waitingOnProvider":true,"usageStatus":"partial","reasoning":"秘密"}
                """.formatted(MODEL_PROFILE, RESOLVED_MODEL));
        assertInvalid(
                "step_progress",
                """
                {"stepId":1,"fencingToken":2,"progressSequence":3,
                 "modelProfile":%s,"resolvedModel":%s,
                 "phase":"waiting_provider","elapsedSeconds":4,
                 "waitingOnProvider":true,"usageStatus":"partial"}
                """.formatted(MODEL_PROFILE, RESOLVED_MODEL));
        assertInvalid(
                "step_progress",
                """
                {"stepId":"step-1","fencingToken":2,"progressSequence":3,
                 "modelProfile":%s,"resolvedModel":%s,
                 "phase":"waiting_provider","elapsedSeconds":4,
                 "waitingOnProvider":false,"usageStatus":"partial"}
                """.formatted(MODEL_PROFILE, RESOLVED_MODEL));
    }

    @Test
    void 拒绝非正序号重复列表和不成对Artifact引用() {
        assertInvalid(
                "step_queued",
                """
                {"stepId":"step-1","ordinal":1,"purpose":"generation","lane":"creative",
                 "modelProfile":%s,
                 "attemptCount":0,"fencingToken":1,"reason":"initial"}
                """.formatted(MODEL_PROFILE));
        assertInvalid(
                "review_started",
                """
                {"artifactId":"artifact-1","artifactRevision":1,
                 "reviewerSteps":[
                   {"stepId":"step-1","ordinal":2,"purpose":"review",
                    "lane":"creative","modelProfile":%s,"status":"pending",
                    "attemptCount":0,"fencingToken":0},
                   {"stepId":"step-1","ordinal":3,"purpose":"review",
                    "lane":"creative","modelProfile":%s,"status":"pending",
                    "attemptCount":0,"fencingToken":0}]}
                """.formatted(MODEL_PROFILE, MODEL_PROFILE));
        assertInvalid(
                "step_finished",
                """
                {"stepId":"step-1","fencingToken":2,"status":"failed"}
                """);
        assertInvalid(
                "step_finished",
                """
                {"stepId":"step-1","fencingToken":2,
                 "status":"completed","errorCode":"UNEXPECTED"}
                """);
        assertInvalid(
                "completed",
                """
                {"outcomeType":"discarded","artifactId":"artifact-1"}
                """);
    }

    @Test
    void 三类模型Step事件都拒绝缺失必需模型身份() {
        assertInvalid(
                "step_queued",
                """
                {"stepId":"step-1","ordinal":1,"purpose":"generation","lane":"creative",
                 "attemptCount":1,"fencingToken":1,"reason":"initial"}
                """);
        assertInvalid(
                "step_started",
                """
                {"stepId":"step-1","ordinal":1,"purpose":"generation",
                 "attemptCount":1,"fencingToken":1}
                """);
        assertInvalid(
                "step_progress",
                """
                {"stepId":"step-1","fencingToken":2,"progressSequence":3,
                 "phase":"waiting_provider","elapsedSeconds":4,
                 "waitingOnProvider":true,"usageStatus":"partial"}
                """);
    }

    private static void assertInvalid(String eventType, String payload) {
        assertThatThrownBy(() -> codec.parse(eventType, payload))
                .isInstanceOf(IllegalStateException.class)
                .hasMessage("持久 WorkflowEvent payload 不符合共享契约");
    }
}
