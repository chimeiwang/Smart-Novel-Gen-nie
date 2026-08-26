package cn.inkforge.core.styles.infrastructure;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import cn.inkforge.core.styles.application.PortraitRunSubmitter;
import cn.inkforge.core.styles.application.PortraitSubmissionException;
import cn.inkforge.core.styles.application.PortraitTaskDispatcher;
import cn.inkforge.core.styles.domain.PortraitDispatchStatus;
import java.lang.reflect.Method;
import java.util.Arrays;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.boot.autoconfigure.condition.ConditionalOnBean;

class StyleConfigurationTest {

    @Test
    void 画像调度器不得依赖Agent投递Bean的配置扫描顺序() {
        Method factory = Arrays.stream(StyleConfiguration.class.getDeclaredMethods())
                .filter(method -> method.getReturnType().equals(PortraitTaskDispatcher.class))
                .findFirst()
                .orElseThrow();

        assertThat(factory.isAnnotationPresent(ConditionalOnBean.class)).isFalse();
        assertThat(factory.getParameterTypes()).contains(ObjectProvider.class);
    }

    @Test
    void 延迟端口必须允许Agent投递器在应用装配后出现() {
        @SuppressWarnings("unchecked")
        ObjectProvider<PortraitRunSubmitter> providers = mock(ObjectProvider.class);
        PortraitRunSubmitter delegate = mock(PortraitRunSubmitter.class);
        when(providers.getIfAvailable()).thenReturn(null, delegate);
        when(delegate.submit("user-1", "style-1", "task-1", "task-1", null))
                .thenReturn(PortraitDispatchStatus.QUEUED);
        ProviderPortraitRunSubmitter submitter = new ProviderPortraitRunSubmitter(providers);

        assertThatThrownBy(() -> submitter.submit(
                        "user-1", "style-1", "task-1", "task-1", null))
                .isInstanceOfSatisfying(PortraitSubmissionException.class, error ->
                        assertThat(error.code()).isEqualTo("AGENT_SERVICE_UNAVAILABLE"));
        assertThat(submitter.submit("user-1", "style-1", "task-1", "task-1", null))
                .isEqualTo(PortraitDispatchStatus.QUEUED);
    }
}
