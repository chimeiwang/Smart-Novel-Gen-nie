/** 历史 Run、候选来源、事件与账务的最小兼容读取；不提供执行调度。 */
@org.springframework.modulith.ApplicationModule(
        allowedDependencies = {
            "billing::domain", "billing::reconciliation", "db", "generated", "platform"
        })
package cn.inkforge.core.workflows;
