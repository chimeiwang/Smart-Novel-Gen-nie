package cn.inkforge.core.video.infrastructure;

import cn.inkforge.core.platform.config.CoreSettings;
import cn.inkforge.core.platform.db.CoreDatabase;
import cn.inkforge.core.platform.id.CuidV1Generator;
import cn.inkforge.core.video.application.ProviderAssetTokenCodec;
import cn.inkforge.core.video.application.VideoAssetStore;
import cn.inkforge.core.video.application.VideoEpisodeRenderReconciler;
import cn.inkforge.core.video.application.VideoEpisodeRenderRepository;
import cn.inkforge.core.video.application.VideoEpisodeRenderService;
import cn.inkforge.core.video.application.VideoRenderGateway;
import cn.inkforge.core.video.application.VideoRenderResultArchiver;
import cn.inkforge.core.video.application.VideoRenderSimulator;
import java.time.Clock;
import java.time.Duration;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import tools.jackson.databind.ObjectMapper;

/** 独立剧集逐镜生成装配；生产默认关闭的视频门禁不会因 Bean 存在而扩大开放范围。 */
@Configuration(proxyBeanMethods = false)
@ConditionalOnProperty(name = "DATABASE_URL")
class VideoEpisodeRenderConfiguration {

    @Bean
    VideoEpisodeRenderRepository videoEpisodeRenderRepository(
            CoreDatabase database,
            CuidV1Generator ids,
            Clock coreClock,
            ObjectMapper json) {
        return new JooqVideoEpisodeRenderRepository(database, ids, coreClock, json);
    }

    @Bean
    VideoEpisodeRenderService videoEpisodeRenderService(
            VideoEpisodeRenderRepository repository,
            VideoAssetStore storage,
            CoreSettings settings,
            ObjectProvider<ProviderAssetTokenCodec> tokens,
            VideoRenderSimulator simulator,
            ObjectProvider<VideoRenderGateway> gateways) {
        return new VideoEpisodeRenderService(
                repository,
                storage,
                settings.videoPreviewEnabled(),
                settings.seedanceConfigured(),
                settings.seedanceEnabled(),
                settings.videoProviderMediaBaseUrl(),
                tokens.getIfAvailable(),
                settings.seedanceExecutionMode(),
                simulator.available(),
                () -> gateways.getIfAvailable() != null);
    }

    @Bean
    @ConditionalOnProperty(name = "VIDEO_PREVIEW_ENABLED", havingValue = "true")
    VideoEpisodeRenderReconciler videoEpisodeRenderReconciler(
            VideoEpisodeRenderRepository repository,
            ObjectProvider<VideoRenderGateway> gateways,
            VideoRenderResultArchiver archiver,
            VideoRenderSimulator simulator,
            VideoAssetStore storage,
            CoreSettings settings,
            ObjectProvider<ProviderAssetTokenCodec> tokens) {
        return new VideoEpisodeRenderReconciler(
                repository,
                gateways::getIfAvailable,
                archiver,
                simulator,
                storage,
                settings.videoProviderMediaBaseUrl(),
                tokens.getIfAvailable(),
                3,
                Duration.ofSeconds(3));
    }
}
