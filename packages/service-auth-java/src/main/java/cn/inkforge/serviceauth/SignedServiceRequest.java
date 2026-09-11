package cn.inkforge.serviceauth;

import java.util.Map;

/** 签名后应原样附加到内部 HTTP 请求的令牌和绑定头。 */
public record SignedServiceRequest(String token, Map<String, String> headers) {

    public SignedServiceRequest {
        headers = Map.copyOf(headers);
    }
}
