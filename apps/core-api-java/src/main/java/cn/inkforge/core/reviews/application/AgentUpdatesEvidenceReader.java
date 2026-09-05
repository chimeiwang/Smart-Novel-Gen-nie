package cn.inkforge.core.reviews.application;

import cn.inkforge.core.workflows.application.WorkflowEvidenceItemPlan;
import java.util.List;
import java.util.Objects;
import org.jooq.DSLContext;

/** 按 Core 已解析的目标读取完整来源；调用方持有领域事务/既有锁，读取不等于全 bundle 采用门禁。 */
public interface AgentUpdatesEvidenceReader {

    List<WorkflowEvidenceItemPlan> capture(DSLContext transaction, String novelId, List<Source> sources);

    /** 仅整树替换需要：冻结全部删除目标与显式成员集，空树也必须留下来源事实。 */
    List<WorkflowEvidenceItemPlan> captureOutlineTree(DSLContext transaction, String novelId);

    enum ResourceKind {
        CHARACTER("character"), LOCATION("location"), ITEM("item"), FACTION("faction"),
        GLOSSARY("glossary"), CHARACTER_EXPERIENCE("character_experience"), OUTLINE_NODE("outline_node"),
        FORESHADOWING("foreshadowing"), REFERENCE("reference"), OUTLINE_CONTENT("outline_content"),
        WORLD_SETTING("world_setting"), STORY_BACKGROUND("story_background"), CHAPTER_REFERENCE("chapter_reference");

        private final String wireName;

        ResourceKind(String wireName) { this.wireName = wireName; }

        public String wireName() { return wireName; }
    }

    /** 单例全文使用 novelId 定位；删除影响仅由 Core 按候选动作显式请求。 */
    record Source(ResourceKind kind, String id, boolean includeDeleteImpact) {
        public Source {
            Objects.requireNonNull(kind);
            if (id == null || id.isEmpty()) throw new IllegalArgumentException("资料来源 ID 不能为空");
        }

        public Source(ResourceKind kind, String id) { this(kind, id, false); }
    }
}
