package cn.inkforge.core.reviews.application;

import cn.inkforge.core.platform.id.CommandResourceId;
import cn.inkforge.core.workflows.protocol.ExecutionCanonicalJson;
import java.util.Map;
import java.util.Set;

/** Core 为同一候选原始位置派生创建身份；模型和过滤后的新下标不能参与分配。 */
public final class AgentUpdatesIdentity {
    private static final Map<String, String> NAMESPACES = Map.of(
            "characters", "characters", "locations", "locations", "items", "items", "factions", "factions",
            "glossaries", "glossary", "characterExperiences", "experiences", "outlineAdjustments", "outline_nodes",
            "foreshadowing", "foreshadowing", "references", "reference");

    private AgentUpdatesIdentity() {}

    public static Set<String> createSections() { return NAMESPACES.keySet(); }

    public static String requestKey(String artifactId, int revision, String section, int index) {
        if (artifactId == null || artifactId.isEmpty() || revision < 1 || index < 0 || !NAMESPACES.containsKey(section)) {
            throw new IllegalArgumentException("结构化候选创建身份无效");
        }
        return "agent-updates-" + ExecutionCanonicalJson.sha256(Map.of("artifactId", artifactId, "revision", revision,
                "section", section, "index", index));
    }

    public static String resourceId(String userId, String novelId, String artifactId, int revision, String section, int index) {
        return resourceId(userId, novelId, section, requestKey(artifactId, revision, section, index));
    }

    public static String resourceId(String userId, String novelId, String section, String requestKey) {
        if (!NAMESPACES.containsKey(section)) throw new IllegalArgumentException("结构化候选创建分区无效");
        return CommandResourceId.derive(NAMESPACES.get(section), userId, novelId, requestKey);
    }
}
