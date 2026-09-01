package cn.inkforge.core.platform.db;

import java.io.InputStream;
import java.util.List;
import tools.jackson.databind.ObjectMapper;

/** 只从应用内冻结资源加载数据库结构契约，运行时不接受外部路径替换。 */
final class SchemaContracts {

    private SchemaContracts() {}

    private static final String PRE_DURABLE_AGENT_V2 =
            "/db/pre-durable-agent-v2/schema-contract.json";
    private static final String POST_DURABLE_AGENT_V2 =
            "/db/post-durable-agent-v2/schema-contract.json";

    static List<SchemaContract> loadBundled() {
        return List.of(load(PRE_DURABLE_AGENT_V2), load(POST_DURABLE_AGENT_V2));
    }

    static SchemaContract loadPreDurableAgentV2() {
        return load(PRE_DURABLE_AGENT_V2);
    }

    static SchemaContract loadPostDurableAgentV2() {
        return load(POST_DURABLE_AGENT_V2);
    }

    private static SchemaContract load(String resource) {
        try (InputStream input = SchemaContracts.class.getResourceAsStream(resource)) {
            if (input == null) {
                throw new IllegalStateException("应用缺少数据库结构契约：" + resource);
            }
            return SchemaContract.load(new ObjectMapper().readTree(input));
        } catch (Exception exception) {
            throw new IllegalStateException("数据库结构契约无法加载：" + resource, exception);
        }
    }
}
