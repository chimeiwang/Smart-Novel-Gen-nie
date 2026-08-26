package cn.inkforge.core.agentgateway;

/** Agent 明确在送达供应商前拒绝 Seedance 创建，可由上层按业务规则处理。 */
public final class SeedanceGatewayRejectedException extends RuntimeException {

    private final int statusCode;

    public SeedanceGatewayRejectedException(int statusCode, String detail) {
        super(detail);
        this.statusCode = statusCode;
    }

    public int statusCode() {
        return statusCode;
    }
}
