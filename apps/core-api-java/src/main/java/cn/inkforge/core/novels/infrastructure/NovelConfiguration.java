package cn.inkforge.core.novels.infrastructure;

import cn.inkforge.core.novels.application.NovelRepository;
import cn.inkforge.core.novels.application.NovelService;
import cn.inkforge.contracts.api.StoryLengthProfile;
import cn.inkforge.core.platform.db.CoreDatabase;
import cn.inkforge.core.platform.id.CuidV1Generator;
import java.time.Clock;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.convert.converter.Converter;
import tools.jackson.databind.ObjectMapper;

@Configuration(proxyBeanMethods = false)
@ConditionalOnProperty(name = "DATABASE_URL")
class NovelConfiguration {

    @Bean
    NovelRepository novelRepository(
            CoreDatabase database,
            CuidV1Generator ids,
            Clock coreClock,
            ObjectMapper objectMapper) {
        return new JooqNovelRepository(database, ids, coreClock, objectMapper);
    }

    @Bean
    NovelService novelService(NovelRepository repository) {
        return new NovelService(repository);
    }

    @Bean
    Converter<String, StoryLengthProfile> storyLengthProfileConverter() {
        // Spring 的默认枚举转换只识别 LONG_SERIAL，公共契约使用 long_serial。
        return StoryLengthProfile::fromValue;
    }
}
