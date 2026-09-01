/** 写作会话、耐久命令、Agent 回调、工具网关、Outbox 与 SSE。 */
@org.springframework.modulith.ApplicationModule(
        allowedDependencies = {
            "db",
            "generated",
            "identity::authentication",
            "novels::novels",
            "outlines::outlines",
            "platform",
            "references::reference-domain",
            "references::references",
            "reviews::application",
            "reviews::domain",
            "shortmedium::domain",
            "workflows::catalog",
            "workflows::execution",
            "workflows::workflow-domain"
        })
package cn.inkforge.core.writing;
