/** 模型调用授权、精确用量结算与浏览器账单查询。 */
@org.springframework.modulith.ApplicationModule(
        allowedDependencies = {
            "db",
            "generated",
            "identity::authentication",
            "platform"
        })
package cn.inkforge.core.billing;
