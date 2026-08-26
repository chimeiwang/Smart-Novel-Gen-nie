package cn.inkforge.core.platform.http;

import cn.inkforge.core.platform.config.CidrBlock;
import jakarta.servlet.http.HttpServletRequest;
import java.util.Collections;
import java.util.List;

/** 只接受可信直接对端转发的一份 X-Real-IP，不读取 X-Forwarded-For。 */
public final class ClientAddressResolver {

    private ClientAddressResolver() {}

    public static String resolve(HttpServletRequest request, List<CidrBlock> trustedProxies) {
        String peerText = request.getRemoteAddr();
        String peer;
        try {
            peer = CidrBlock.normalizeAddress(peerText);
        } catch (IllegalArgumentException exception) {
            return peerText == null ? "unknown" : peerText;
        }
        if (trustedProxies.stream().noneMatch(cidr -> cidr.contains(peer))) {
            return peer;
        }
        List<String> forwarded = Collections.list(request.getHeaders("X-Real-IP"));
        if (forwarded.size() != 1 || forwarded.getFirst().contains(",")) {
            return peer;
        }
        try {
            return CidrBlock.normalizeAddress(forwarded.getFirst().strip());
        } catch (IllegalArgumentException exception) {
            return peer;
        }
    }
}
