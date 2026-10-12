package cn.inkforge.core.references.infrastructure;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.mock;

import cn.inkforge.contracts.api.ReindexReferenceRequest;
import cn.inkforge.core.platform.config.CoreSettings;
import cn.inkforge.core.platform.db.CoreDatabase;
import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.platform.id.CuidV1Generator;
import cn.inkforge.core.references.application.RagIndexSubmitter;
import cn.inkforge.core.references.application.ReferenceService;
import cn.inkforge.core.references.application.RagIndexDispatcher;
import cn.inkforge.core.references.domain.RagDispatchStatus;
import cn.inkforge.core.workflows.catalog.ExecutionRegistry;
import java.time.Clock;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import tools.jackson.databind.ObjectMapper;

class ReferenceConfigurationTest {
    private final ApplicationContextRunner context = new ApplicationContextRunner()
            .withPropertyValues("DATABASE_URL=postgresql://isolated-unused", "RAG_INDEX_ENABLED=true")
            .withUserConfiguration(ReferenceConfiguration.class, Dependencies.class);

    @Test
    void 仅开RAG但未装配Agent客户端时保留未配置语义不创建路由器() {
        context.run(application -> {
            assertThat(application).hasNotFailed();
            assertThat(org.springframework.test.util.ReflectionTestUtils.getField(application.getBean(ReferenceService.class), "submitter")).isNull();
            assertThatThrownBy(() -> application.getBean(ReferenceService.class).reindex("user", "novel", "reference",
                    new ReindexReferenceRequest("0".repeat(64))))
                    .isInstanceOfSatisfying(ApiException.class, value -> assertThat(value.code()).isEqualTo("RAG_INDEX_UNAVAILABLE"));
        });
    }

    @Test
    void 原端口定义存在时统一注入双引擎路由器而非直连旧投递器() {
        context.withBean("ragAgentSubmitter", RagIndexSubmitter.class,
                () -> (user, novel, reference, hash, generation) -> RagDispatchStatus.QUEUED)
                .run(application -> {
                    assertThat(application).hasNotFailed();
                    assertThat(org.springframework.test.util.ReflectionTestUtils.getField(application.getBean(ReferenceService.class), "submitter"))
                            .isInstanceOf(RagIndexSubmissionRouter.class);
                    assertThat(org.springframework.test.util.ReflectionTestUtils.getField(application.getBean(RagIndexDispatcher.class), "submitter"))
                            .isInstanceOf(RagIndexSubmissionRouter.class);
                });
    }

    @Configuration(proxyBeanMethods = false)
    static class Dependencies {
        @Bean CoreDatabase database() { return mock(CoreDatabase.class); }
        @Bean CoreSettings settings() { return CoreSettings.from(Map.of("RAG_INDEX_ENABLED", "true")); }
        @Bean Clock coreClock() { return Clock.systemUTC(); }
        @Bean CuidV1Generator ids(Clock clock) { return new CuidV1Generator(clock); }
        @Bean ObjectMapper json() { return new ObjectMapper(); }
        @Bean ExecutionRegistry registry() { return mock(ExecutionRegistry.class); }
    }
}
