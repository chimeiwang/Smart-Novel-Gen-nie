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

    private static final String EXPECTED_FINGERPRINT =
            "4f8cbf58820c7e601026012249f1896e4f8ad0231cfa6b9bd2fdad1c83c3d195";

    private final ObjectMapper objectMapper = new ObjectMapper();

    @Test
    void 当前结构契约必须与Python指纹完全一致() throws IOException {
        JsonNode document = readContract();

        SchemaContract loaded = SchemaContract.load(document);

        assertThat(loaded.fingerprint()).isEqualTo(EXPECTED_FINGERPRINT);
        assertThat(document.path("tables").size()).isEqualTo(86);
        assertThat(document.path("enums").size()).isEqualTo(22);
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

    private JsonNode readContract() throws IOException {
        try (InputStream input = getClass().getResourceAsStream("/db/schema-contract.json")) {
            if (input == null) {
                throw new IOException("测试资源缺少 schema-contract.json");
            }
            return objectMapper.readTree(input);
        }
    }
}
