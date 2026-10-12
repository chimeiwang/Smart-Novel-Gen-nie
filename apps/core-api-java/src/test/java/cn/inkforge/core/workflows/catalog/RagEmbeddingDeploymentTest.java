package cn.inkforge.core.workflows.catalog;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import cn.inkforge.core.workflows.domain.WorkflowResolvedModel;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.HexFormat;
import org.junit.jupiter.api.Test;

class RagEmbeddingDeploymentTest {
    @Test
    void 仅RAG专用配置可授权且用户积分固定不收费() {
        var registry = ExecutionRegistryFixtures.ragOperationEnabled(ExecutionRegistry.Environment.TEST);
        var model = resolved("e2e-embedding-vector-v1", "http://e2e-control:8090", "embeddings_v1");
        var authorized = registry.requireAuthorizedDeployment(model);
        assertThat(authorized.billable()).isFalse();
        assertThat(authorized.pricingVersion()).isEqualTo("credit-pricing.v1");
        assertThat(authorized.provider()).isEqualTo("openai_embeddings");
        assertThatThrownBy(() -> registry.requireAuthorizedDeployment(resolved("another", "http://e2e-control:8090", "embeddings_v1")))
                .isInstanceOf(IllegalStateException.class);
        assertThatThrownBy(() -> registry.requireAuthorizedDeployment(resolved("e2e-embedding-vector-v1", "http://other:8090", "embeddings_v1")))
                .isInstanceOf(IllegalStateException.class);
        assertThatThrownBy(() -> registry.requireAuthorizedDeployment(resolved("e2e-embedding-vector-v1", "http://e2e-control:8090", "chat_json_output_v1")))
                .isInstanceOf(IllegalStateException.class);
        assertThatThrownBy(() -> registry.withRagEmbeddingConfig(null, null).requireAuthorizedDeployment(model))
                .isInstanceOf(IllegalStateException.class);
    }

    @Test
    void 保留原模型字符串且端点仅按显式配置规则产生指纹() throws Exception {
        String model = " 中文 自定义模型 " + "x".repeat(2100);
        String url = "https://Example.test:443/custom/v1///";
        var config = RagEmbeddingDeployment.fromConfiguration(model, url);
        String expected = HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256")
                .digest("https://Example.test:443/custom/v1/embeddings".getBytes(StandardCharsets.UTF_8)));
        assertThat(config.model()).isEqualTo(model);
        assertThat(config.endpointProfile()).isEqualTo("endpoint.rag-embedding." + expected + ".v1");
        var registry = ExecutionRegistryFixtures.ragOperationEnabled(ExecutionRegistry.Environment.PRODUCTION)
                .withRagEmbeddingConfig(model, url);
        assertThat(registry.requireAuthorizedDeployment(resolved(model, url, "embeddings_v1")).model()).isEqualTo(model);
        assertThat(RagEmbeddingDeployment.fromConfiguration("", url)).isNull();
        assertThat(RagEmbeddingDeployment.fromConfiguration(model, null)).isNull();
    }

    private static WorkflowResolvedModel resolved(String model, String base, String route) {
        String profile = RagEmbeddingDeployment.PROFILE;
        String endpoint = RagEmbeddingDeployment.fromConfiguration(model, base).endpointProfile();
        return new WorkflowResolvedModel(profile, WorkflowResolvedModel.fingerprint(profile,
                "openai_embeddings", model, "transport.openai-embeddings.v1", endpoint, route,
                "capability.openai-embeddings.batch.v1", "disabled", false), "openai_embeddings", model,
                "transport.openai-embeddings.v1", endpoint, route, "capability.openai-embeddings.batch.v1", "disabled", false);
    }
}
