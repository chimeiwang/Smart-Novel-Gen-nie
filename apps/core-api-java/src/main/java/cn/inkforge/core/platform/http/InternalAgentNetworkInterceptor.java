package cn.inkforge.core.platform.http;

import cn.inkforge.core.platform.config.CidrBlock;
import cn.inkforge.core.platform.config.CoreSettings;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.util.List;
import org.springframework.web.servlet.HandlerInterceptor;

/** 内部接口只信任 TCP 直接对端；绝不使用任何转发头决定 Agent 身份。 */
public final class InternalAgentNetworkInterceptor implements HandlerInterceptor {

    private final List<CidrBlock> trustedAgentCidrs;

    public InternalAgentNetworkInterceptor(CoreSettings settings) {
        this.trustedAgentCidrs = settings.trustedAgentCidrs();
    }

    @Override
    public boolean preHandle(
            HttpServletRequest request, HttpServletResponse response, Object handler) {
        if (trustedAgentCidrs.isEmpty()) {
            throw new ApiException(
                    503,
                    "AGENT_SERVICE_NETWORK_UNAVAILABLE",
                    "智能体服务可信网段未配置");
        }
        String directPeer = request.getRemoteAddr();
        if (directPeer == null
                || trustedAgentCidrs.stream().noneMatch(cidr -> cidr.contains(directPeer))) {
            throw new ApiException(
                    403,
                    "AGENT_SERVICE_NETWORK_FORBIDDEN",
                    "智能体服务直接对端不在可信网段内");
        }
        return true;
    }
}
