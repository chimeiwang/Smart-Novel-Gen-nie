package cn.inkforge.cli.transport;

/** Core 成功响应不符合 JSON 契约。 */
public final class CoreResponseContractException extends CoreApiException {

    public CoreResponseContractException(String message) {
        super(502, "CORE_RESPONSE_CONTRACT_ERROR", message, null, null);
    }
}
