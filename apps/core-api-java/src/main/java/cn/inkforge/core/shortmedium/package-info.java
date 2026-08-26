@org.springframework.modulith.ApplicationModule(
        allowedDependencies = {
            "db",
            "generated",
            "identity::authentication",
            "platform"
        })
package cn.inkforge.core.shortmedium;
