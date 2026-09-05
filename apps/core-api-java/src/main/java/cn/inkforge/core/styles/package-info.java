/** 私有文风、受控参考文件和画像任务。 */
@org.springframework.modulith.ApplicationModule(displayName = "文风画像", allowedDependencies = {
        "db", "generated", "platform", "identity::authentication",
        "workflows::catalog", "workflows::execution", "workflows::protocol"
})
package cn.inkforge.core.styles;
