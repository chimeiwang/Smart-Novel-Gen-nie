package cn.inkforge.serviceauth;

import java.util.Map;

public record SignedServiceRequest(String token, Map<String, String> headers) {

    public SignedServiceRequest {
        headers = Map.copyOf(headers);
    }
}
