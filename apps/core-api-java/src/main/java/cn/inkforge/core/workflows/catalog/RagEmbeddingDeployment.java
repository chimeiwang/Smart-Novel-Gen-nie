package cn.inkforge.core.workflows.catalog;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;
import java.util.List;

/** 只绑定 RAG 的非秘密请求配置；不把配置指纹冒充供应商实际费用或重定向目的地证明。 */
public record RagEmbeddingDeployment(String model, String endpointProfile) {
    public static final String PROFILE = "deployment.rag.embedding.v2";
    public static final String BINDING = "binding.rag-embedding-config.v1";

    public static RagEmbeddingDeployment fromConfiguration(String model, String baseUrl) {
        if (model == null || model.isBlank() || baseUrl == null || baseUrl.isBlank()) return null;
        int end = baseUrl.length();
        while (end > 0 && baseUrl.charAt(end - 1) == '/') end--;
        String base = baseUrl.substring(0, end);
        if (!base.endsWith("/v1")) base += "/v1";
        try {
            String digest = HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256")
                    .digest((base + "/embeddings").getBytes(StandardCharsets.UTF_8)));
            return new RagEmbeddingDeployment(model, "endpoint.rag-embedding." + digest + ".v1");
        } catch (NoSuchAlgorithmException exception) {
            throw new IllegalStateException("当前 JVM 不支持 SHA-256", exception);
        }
    }

    ExecutionRegistry.DeploymentModel authorized(ExecutionRegistry.ConfiguredDeploymentBinding binding) {
        return new ExecutionRegistry.DeploymentModel("openai_embeddings", model,
                "transport.openai-embeddings.v1", endpointProfile, "embeddings_v1",
                "capability.openai-embeddings.batch.v1", "disabled", false,
                List.copyOf(binding.allowedEnvironments()), binding.pricingVersion(), false);
    }
}
