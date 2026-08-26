package cn.inkforge.core.platform.http;

import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;

import cn.inkforge.core.platform.config.CoreSettings;
import org.junit.jupiter.api.Test;
import org.springframework.web.servlet.config.annotation.AsyncSupportConfigurer;

class InternalHttpConfigurationTest {

    @Test
    void SSE与文件流不得继承Servlet默认总超时() {
        InternalHttpConfiguration configuration =
                new InternalHttpConfiguration(mock(CoreSettings.class));
        AsyncSupportConfigurer async = mock(AsyncSupportConfigurer.class);

        configuration.configureAsyncSupport(async);

        verify(async).setDefaultTimeout(0L);
    }
}
