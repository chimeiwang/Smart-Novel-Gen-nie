/** Core 权威的耐久 Run、Step、Evidence、Event 与执行调度。 */
@org.springframework.modulith.ApplicationModule(
        allowedDependencies = {
            "billing::domain", "billing::reconciliation", "db", "generated", "platform"
        })
package cn.inkforge.core.workflows;
