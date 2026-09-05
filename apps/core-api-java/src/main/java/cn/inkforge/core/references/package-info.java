/** 参考资料正式事实、RAG 派生索引与 Agent 回调。 */
@org.springframework.modulith.ApplicationModule(displayName = "参考资料索引", allowedDependencies = {
        "db", "generated", "platform", "identity::authentication",
        "workflows::catalog", "workflows::execution", "workflows::protocol"
})
package cn.inkforge.core.references;
