package cn.inkforge.core.platform.http;

import jakarta.servlet.http.HttpServletRequest;
import org.springframework.web.context.request.RequestContextHolder;
import org.springframework.web.context.request.ServletRequestAttributes;

/** 获取过滤器在 JSON 反序列化前保存的原始请求字节，供服务签名验证使用。 */
public final class RawRequestBody {

    static final String ATTRIBUTE = RawRequestBody.class.getName() + ".bytes";

    private RawRequestBody() {}

    public static byte[] current() {
        if (!(RequestContextHolder.getRequestAttributes()
                instanceof ServletRequestAttributes attributes)) {
            throw unavailable();
        }
        HttpServletRequest request = attributes.getRequest();
        Object value = request.getAttribute(ATTRIBUTE);
        if (!(value instanceof byte[] bytes)) throw unavailable();
        return bytes.clone();
    }

    private static ApiException unavailable() {
        return new ApiException(
                500,
                "RAW_REQUEST_BODY_UNAVAILABLE",
                "内部请求原始正文不可用");
    }
}
