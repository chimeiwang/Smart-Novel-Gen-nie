package cn.inkforge.core.chapters.infrastructure;

import cn.inkforge.core.chapters.application.ChapterRepository;
import cn.inkforge.core.chapters.application.ChapterService;
import cn.inkforge.core.platform.db.CoreDatabase;
import cn.inkforge.core.platform.id.CuidV1Generator;
import java.time.Clock;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@ConditionalOnProperty(name = "DATABASE_URL")
class ChapterConfiguration {

    @Bean
    ChapterRepository chapterRepository(
            CoreDatabase database, CuidV1Generator ids, Clock coreClock) {
        return new JooqChapterRepository(database, ids, coreClock);
    }

    @Bean
    ChapterService chapterService(ChapterRepository repository) {
        return new ChapterService(repository);
    }
}
