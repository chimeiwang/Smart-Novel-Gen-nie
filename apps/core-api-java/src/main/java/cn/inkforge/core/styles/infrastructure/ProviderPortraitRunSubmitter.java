package cn.inkforge.core.styles.infrastructure;

import cn.inkforge.core.styles.application.PortraitRunSubmitter;
import cn.inkforge.core.styles.application.PortraitSubmissionException;
import cn.inkforge.core.styles.domain.PortraitDispatchStatus;
import cn.inkforge.core.styles.domain.PortraitSection;
import java.util.Objects;
import org.springframework.beans.factory.ObjectProvider;

/** 延迟解析画像 Agent 端口，使耐久 dispatcher 不受 Spring 配置扫描顺序影响。 */
final class ProviderPortraitRunSubmitter implements PortraitRunSubmitter {

    private final ObjectProvider<PortraitRunSubmitter> providers;

    ProviderPortraitRunSubmitter(ObjectProvider<PortraitRunSubmitter> providers) {
        this.providers = Objects.requireNonNull(providers);
    }

    @Override
    public PortraitDispatchStatus submit(
            String userId,
            String styleId,
            String taskId,
            String runId,
            PortraitSection section) {
        PortraitRunSubmitter delegate = providers.getIfAvailable();
        if (delegate == null) {
            throw new PortraitSubmissionException("AGENT_SERVICE_UNAVAILABLE");
        }
        return delegate.submit(userId, styleId, taskId, runId, section);
    }
}
