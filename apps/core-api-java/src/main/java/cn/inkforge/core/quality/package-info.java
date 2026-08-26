@org.springframework.modulith.ApplicationModule(
        displayName = "质量检查",
        allowedDependencies = {
            "db",
            "generated",
            "identity::authentication",
            "platform"
        })
package cn.inkforge.core.quality;
