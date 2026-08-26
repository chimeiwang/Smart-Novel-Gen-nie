package cn.inkforge.core.writing.application;

import java.util.List;
import java.util.Map;

/** 读取工具访问 ReviewArtifact 的窄端口，避免把审核仓储能力整体暴露给工具层。 */
public interface WritingReviewArtifactReader {

    List<Map<String, Object>> listTaskArtifacts(
            String userId,
            String novelId,
            String taskId,
            String status,
            String kind);

    Map<String, Object> get(String userId, String artifactId);
}
