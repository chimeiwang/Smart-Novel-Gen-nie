package cn.inkforge.core.writing.infrastructure;

import cn.inkforge.core.writing.application.WritingCommandSubmitter;
import cn.inkforge.core.writing.application.WritingSubmissionException;
import cn.inkforge.core.writing.domain.WritingAgentJobStatus;
import cn.inkforge.core.writing.domain.WritingDispatchRecord;
import java.util.Objects;
import org.springframework.beans.factory.ObjectProvider;

/**
 * 延迟解析实际 Agent 投递器，避免 Spring 配置扫描顺序决定写作调度器是否存在。
 *
 * <p>未配置 Agent 时仍保留耐久命令和后台补投能力；每次投递以稳定的暂时失败码退避，不制造空 Bean，
 * 也不让未知异常击穿后台监督器。
 */
final class ProviderWritingCommandSubmitter implements WritingCommandSubmitter {

    private final ObjectProvider<WritingCommandSubmitter> providers;

    ProviderWritingCommandSubmitter(ObjectProvider<WritingCommandSubmitter> providers) {
        this.providers = Objects.requireNonNull(providers);
    }

    @Override
    public WritingAgentJobStatus submit(WritingDispatchRecord command) {
        return delegate().submit(command);
    }

    @Override
    public void cancel(WritingDispatchRecord command) {
        delegate().cancel(command);
    }

    private WritingCommandSubmitter delegate() {
        WritingCommandSubmitter value = providers.getIfAvailable();
        if (value == null) {
            throw new WritingSubmissionException("AGENT_SERVICE_UNAVAILABLE");
        }
        return value;
    }
}
