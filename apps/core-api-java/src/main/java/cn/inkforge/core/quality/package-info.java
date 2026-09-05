@org.springframework.modulith.ApplicationModule(
        displayName = "质量检查",
        allowedDependencies = {
            "db",
            "generated",
            "identity::authentication",
            "platform",
            "workflows::catalog",
            "workflows::execution",
            "workflows::protocol"
        })
package cn.inkforge.core.quality;
