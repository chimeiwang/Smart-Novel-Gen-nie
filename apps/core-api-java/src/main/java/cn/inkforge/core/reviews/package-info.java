/** 待审核产物、正式应用决定和 Agent 复审入口。 */
@org.springframework.modulith.ApplicationModule(
        allowedDependencies = {
            "db",
            "generated",
            "identity::authentication",
            "lore::lore",
            "lore::lore-domain",
            "outlines::outlines",
            "outlines::outline-domain",
            "platform",
            "references::references",
            "references::reference-domain",
            "workflows::catalog",
            "workflows::protocol",
            "workflows::workflow-domain"
        })
package cn.inkforge.core.reviews;
