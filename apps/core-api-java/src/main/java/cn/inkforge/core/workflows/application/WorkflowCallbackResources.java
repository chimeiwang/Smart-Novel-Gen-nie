package cn.inkforge.core.workflows.application;

/** V2 callback 验签前从 PostgreSQL 解析的权威资源归属。 */
public record WorkflowCallbackResources(String runId, String stepId, String novelId) {}
