package cn.inkforge.core.platform.http;

import cn.inkforge.serviceauth.ServiceScope;
import cn.inkforge.serviceauth.VerifiedServiceRequest;
import jakarta.servlet.http.HttpServletRequest;

/** 业务模块验证 Agent 内部请求时依赖的平台端口。 */
public interface InternalServiceAuthenticator {

    VerifiedServiceRequest authenticate(
            HttpServletRequest request,
            byte[] body,
            ServiceScope requiredScope,
            String taskId,
            String runId,
            String novelId,
            String unavailableCode,
            String unavailableMessage);
}
