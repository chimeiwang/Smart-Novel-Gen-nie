package cn.inkforge.core.video.infrastructure;

import cn.inkforge.core.platform.config.CoreSettings;
import cn.inkforge.core.platform.db.CoreDatabase;
import cn.inkforge.core.platform.id.CuidV1Generator;
import cn.inkforge.core.video.application.VideoEpisodeImpactService;

import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import tools.jackson.databind.ObjectMapper;

import java.time.Clock;

/** 独立装配影响复核，避免供应商或媒体协作者缺失时阻断只读报告。 */
@Configuration(proxyBeanMethods = false)
@ConditionalOnProperty(name = "DATABASE_URL")
class VideoEpisodeImpactConfiguration {
    @Bean
    JooqVideoEpisodeImpactRepository videoEpisodeImpactRepository(
            CoreDatabase database,
            CuidV1Generator ids,
            Clock coreClock,
            ObjectMapper json) {
        return new JooqVideoEpisodeImpactRepository(database, ids, coreClock, json);
    }

    @Bean
    VideoEpisodeImpactService videoEpisodeImpactService(
            JooqVideoEpisodeImpactRepository repository, CoreSettings settings) {
        return new VideoEpisodeImpactService(repository, settings.videoPreviewEnabled());
    }
}
