package cn.inkforge.cli.transport;

import tools.jackson.databind.JsonNode;

/** Core 返回的公共错误；不保存请求头、Cookie 或原始异常文本。 */
public class CoreApiException extends RuntimeException {

    private final int statusCode;
    private final String code;
    private final String publicMessage;
    private final JsonNode details;
    private final String requestId;

    public CoreApiException(
            int statusCode,
            String code,
            String publicMessage,
            JsonNode details,
            String requestId) {
        super(publicMessage);
        this.statusCode = statusCode;
        this.code = code;
        this.publicMessage = publicMessage;
        this.details = details;
        this.requestId = requestId;
    }

    public int statusCode() {
        return statusCode;
    }

    public String code() {
        return code;
    }

    public String publicMessage() {
        return publicMessage;
    }

    public JsonNode details() {
        return details;
    }

    public String requestId() {
        return requestId;
    }
}
