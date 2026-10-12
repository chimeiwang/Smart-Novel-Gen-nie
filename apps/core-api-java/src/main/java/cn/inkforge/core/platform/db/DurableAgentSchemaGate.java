package cn.inkforge.core.platform.db;

import java.sql.Connection;

/**
 * V2 数据库能力的装配闸门。
 *
 * <p>兼容镜像的普通 readiness 同时接受迁移前、迁移后两份完整契约，保证在线迁移期间旧实例不掉线；但
 * {@code DURABLE_AGENT_EXECUTION_SCHEMA_READY=true} 只能装配在精确迁移后结构上。这里在任何 V2
 * repository/worker 创建前做只读校验，避免错误配置把缺列异常推迟到首个请求或后台循环。
 */
public final class DurableAgentSchemaGate {

    private final String fingerprint;

    DurableAgentSchemaGate(CoreDatabase database, SchemaProfile profile) {
        try (Connection connection = database.connection()) {
            SchemaVerificationResult result = new SchemaVerifier(
                            SchemaContracts.loadPostDurableAgentV2(), profile)
                    .verify(connection, "public");
            if (!result.ready()) {
                throw new IllegalStateException("耐久 Agent V2 数据库结构未精确命中迁移后契约");
            }
            this.fingerprint = result.fingerprint();
        } catch (IllegalStateException exception) {
            throw exception;
        } catch (Exception exception) {
            throw new IllegalStateException(
                    "耐久 Agent V2 数据库结构闸门无法完成只读校验（"
                            + exception.getClass().getSimpleName()
                            + "）",
                    exception);
        }
    }

    public String fingerprint() {
        return fingerprint;
    }
}
