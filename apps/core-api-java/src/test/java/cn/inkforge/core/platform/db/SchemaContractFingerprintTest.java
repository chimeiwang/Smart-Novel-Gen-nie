package cn.inkforge.core.platform.db;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.io.IOException;
import java.io.InputStream;
import org.junit.jupiter.api.Test;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;
import tools.jackson.databind.node.ObjectNode;

class SchemaContractFingerprintTest {

    private static final String EXPECTED_PRE_MIGRATION_FINGERPRINT =
            "0b8da839b6a759aaa1063c0cb8395e98feff184a4b7e94ee0bf3aae4f252a7ce";
    private static final String EXPECTED_POST_MIGRATION_FINGERPRINT =
            "3a51237c2d642c3b08247adbb6468615ab9b7f651216c74b877d7ca38d8d5e32";

    private final ObjectMapper objectMapper = new ObjectMapper();

    @org.junit.jupiter.params.ParameterizedTest
    @org.junit.jupiter.params.provider.CsvSource({
        "FULL,3a51237c2d642c3b08247adbb6468615ab9b7f651216c74b877d7ca38d8d5e32,109",
        "WITHOUT_VIDEO_PREVIEW,ea1df9ad015cd8d811d6ab250a7098870aa2befcf0afa3273b845255a0ac11b2,50",
        "WITHOUT_PHONE_AUTH,fa70448d891837a1dffebb958771570bc4e889e6160a7b7a411c5b83f452fee7,108",
        "WITHOUT_VIDEO_PREVIEW_AND_PHONE_AUTH,e2bcc725ed42c7128274bbc19ba1e288ff0edc70f90124225e3214ecd03baa46,49"
    })
    void 迁移后四种投影与运维证据使用同一组冻结指纹(
            SchemaProfile profile, String fingerprint, int tableCount) {
        SchemaContract projected = SchemaContractProjector.project(
                SchemaContracts.loadPostDurableAgentV2(), profile);
        assertThat(projected.fingerprint()).isEqualTo(fingerprint);
        assertThat(projected.document().path("tables")).hasSize(tableCount);
    }

    @Test
    void 迁移前冻结契约必须与Python指纹完全一致() throws IOException {
        JsonNode document = readContract();

        SchemaContract loaded = SchemaContract.load(document);

        assertThat(loaded.fingerprint()).isEqualTo(EXPECTED_PRE_MIGRATION_FINGERPRINT);
        assertThat(document.path("tables").size()).isEqualTo(104);
        assertThat(document.path("enums").size()).isEqualTo(22);
        assertThat(document.path("tables").toString())
                .contains(
                        "VideoEpisode",
                        "VideoEpisodeSourceSetVersion",
                        "VideoEpisodeScriptDraft",
                        "VideoEpisodeScriptVersion",
                        "VideoEpisodeCommand",
                        "VideoStoryboardVersion",
                        "VideoProductionBaseline",
                        "VideoTakeAdoption");
    }

    @Test
    void 契约内容被修改后必须拒绝启动() throws IOException {
        JsonNode document = readContract();
        ObjectNode firstColumn = (ObjectNode) document.path("tables").get(0).path("columns").get(0);
        firstColumn.put("nullable", !firstColumn.path("nullable").asBoolean());

        assertThatThrownBy(() -> SchemaContract.load(document))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessage("数据库结构契约指纹不自洽");
    }

    @Test
    void 迁移后冻结契约必须来自PostgreSQL14且与迁移前契约明确分离() {
        SchemaContract pre = SchemaContracts.loadPreDurableAgentV2();
        SchemaContract post = SchemaContracts.loadPostDurableAgentV2();

        assertThat(pre.fingerprint()).isEqualTo(EXPECTED_PRE_MIGRATION_FINGERPRINT);
        assertThat(post.fingerprint()).isEqualTo(EXPECTED_POST_MIGRATION_FINGERPRINT);
        assertThat(post.fingerprint()).isNotEqualTo(pre.fingerprint());
        assertThat(post.document().path("source").path("serverVersionNum").asInt())
                .isBetween(140000, 149999);
        assertThat(post.document().path("tables")).hasSize(109);
        assertThat(post.document().path("enums")).hasSize(22);
        assertThat(post.document().path("tables").toString())
                .contains(
                        "WorkflowEvidenceBundle",
                        "WorkflowEvidenceItem",
                        "WorkflowEvent",
                        "WorkflowEvaluation",
                        "WorkflowBillingReservation");
        assertThat(pre.document().path("tables").toString())
                .doesNotContain(
                        "WorkflowEvidenceBundle",
                        "WorkflowEvidenceItem",
                        "WorkflowEvent",
                        "WorkflowEvaluation",
                        "WorkflowBillingReservation");
    }

    @Test
    void 生产投影必须与Python指纹完全一致() throws IOException {
        SchemaContract projected = SchemaContractProjector.project(
                SchemaContract.load(readContract()), SchemaProfile.WITHOUT_VIDEO_PREVIEW);

        assertThat(projected.fingerprint())
                .isEqualTo("b5d2c319303f1ca52d411b8f986aa98a5d48168338c75c65d675d23968c22c78");
        assertThat(projected.document().path("tables")).hasSize(45);
        assertThat(projected.document().path("tables").toString())
                .doesNotContain("VideoShotRenderTask", "videoAdaptationTaskId");
        assertThat(projected.document().path("tables").toString())
                .contains("UserPhoneIdentity");
    }

    @Test
    void 关闭手机号与视频能力的生产投影保持原结构() throws IOException {
        SchemaContract projected = SchemaContractProjector.project(
                SchemaContract.load(readContract()),
                SchemaProfile.WITHOUT_VIDEO_PREVIEW_AND_PHONE_AUTH);

        assertThat(projected.fingerprint())
                .isEqualTo("ecd541a96eba65d43fba66f59834f53987818b03ea10298f981a3ab965002fbe");
        assertThat(projected.document().path("tables")).hasSize(44);
        assertThat(projected.document().path("tables").toString())
                .doesNotContain("VideoShotRenderTask", "UserPhoneIdentity");
    }

    @Test
    void 耐久迁移后的生产投影不因新增剧集开发表漂移() {
        SchemaContract projected = SchemaContractProjector.project(
                SchemaContracts.loadPostDurableAgentV2(),
                SchemaProfile.WITHOUT_VIDEO_PREVIEW);

        assertThat(projected.fingerprint())
                .isEqualTo("ea1df9ad015cd8d811d6ab250a7098870aa2befcf0afa3273b845255a0ac11b2");
        assertThat(projected.document().path("tables")).hasSize(50);
        assertThat(projected.document().path("tables").toString())
                .contains("WorkflowEvidenceBundle", "UserPhoneIdentity")
                .doesNotContain("VideoEpisode", "videoEpisodeId");
        assertThat(projected.document().path("enums").toString())
                .doesNotContain("video_episode_script");
    }

    private JsonNode readContract() throws IOException {
        try (InputStream input = getClass().getResourceAsStream(
                "/db/pre-durable-agent-v2/schema-contract.json")) {
            if (input == null) {
                throw new IOException("测试资源缺少 schema-contract.json");
            }
            return objectMapper.readTree(input);
        }
    }
}
