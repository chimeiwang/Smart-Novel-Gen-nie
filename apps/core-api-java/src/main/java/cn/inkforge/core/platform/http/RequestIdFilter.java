package cn.inkforge.core.platform.http;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.util.UUID;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.slf4j.MDC;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

/** 接受合法调用方请求标识，否则生成 UUID；所有响应都返回同一标识。 */
@Component
@Order(Ordered.HIGHEST_PRECEDENCE)
public final class RequestIdFilter extends OncePerRequestFilter {

    public static final String HEADER = "X-Request-ID";
    private static final String ATTRIBUTE = RequestIdFilter.class.getName() + ".requestId";

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain filterChain)
            throws ServletException, IOException {
        String requestId = resolve(request.getHeader(HEADER));
        request.setAttribute(ATTRIBUTE, requestId);
        response.setHeader(HEADER, requestId);
        MDC.put("requestId", requestId);
        try {
            filterChain.doFilter(request, response);
            response.setHeader(HEADER, requestId);
        } finally {
            MDC.remove("requestId");
        }
    }

    static String requestId(HttpServletRequest request) {
        Object value = request.getAttribute(ATTRIBUTE);
        return value instanceof String requestId ? requestId : UUID.randomUUID().toString();
    }

    private static String resolve(String rawRequestId) {
        if (rawRequestId == null) {
            return UUID.randomUUID().toString();
        }
        String requestId = rawRequestId.strip();
        if (requestId.isEmpty() || requestId.length() > 128 || containsControlCharacter(requestId)) {
            return UUID.randomUUID().toString();
        }
        return requestId;
    }

    private static boolean containsControlCharacter(String value) {
        return value.chars().anyMatch(character -> character < 32 || character == 127);
    }
}
