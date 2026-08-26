package cn.inkforge.core.agentgateway;

/** Seedance 查询是可恢复短调用，失败后只能查询同一个 providerTaskId。 */
public final class SeedanceGatewayQueryException extends RuntimeException {

    public SeedanceGatewayQueryException() {
        super("Seedance 查询暂时失败");
    }
}
