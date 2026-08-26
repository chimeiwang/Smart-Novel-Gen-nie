package cn.inkforge.core.agentgateway;

/** Agent 请求失败的稳定平台错误，不携带远端正文或底层地址。 */
public final class AgentGatewayException extends RuntimeException {

    private final String code;

    AgentGatewayException(String code, String message) {
        super(message);
        this.code = code;
    }

    public String code() {
        return code;
    }
}
