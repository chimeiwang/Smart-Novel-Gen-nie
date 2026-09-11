package cn.inkforge.core.video.infrastructure;

import cn.inkforge.core.platform.config.CoreSettings;
import cn.inkforge.core.platform.db.CoreDatabase;
import cn.inkforge.core.platform.id.CuidV1Generator;
import cn.inkforge.core.video.application.ProviderAssetTokenCodec;
import cn.inkforge.core.video.application.VideoAssetStore;
import cn.inkforge.core.video.application.VideoEpisodePostProductionReconciler;
import cn.inkforge.core.video.application.VideoEpisodePostProductionService;
import cn.inkforge.core.video.application.VideoIdGenerator;
import cn.inkforge.core.video.application.VideoMediaProbe;
import cn.inkforge.core.video.application.VideoProjectRepository;
import cn.inkforge.core.video.application.VideoProjectService;
import cn.inkforge.core.video.application.VideoPostProductionMediaProcessor;
import cn.inkforge.core.video.application.VideoRenderResultArchiver;
import cn.inkforge.core.video.application.VideoRenderSimulator;
import cn.inkforge.core.video.application.VideoVisualCanonRepository;
import cn.inkforge.core.video.application.VideoVisualCanonService;
import java.time.Clock;
import java.time.Duration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Conditional;
import org.springframework.context.annotation.Configuration;
import tools.jackson.databind.ObjectMapper;

/**
 * 视频域第一层装配。
 *
 * <p>整个配置只在存在 {@code DATABASE_URL} 时创建数据库协作者；供应商 dispatcher、Seedance reconciler
 * 和后期 worker 还各自受显式功能开关及依赖 Bean 门禁。这样最小健康上下文不会因为生产默认关闭视频或缺少
 * FFmpeg/供应商密钥而装配失败，也不会仅因代码存在就意外开始调度。
 */
@Configuration(proxyBeanMethods = false)
@ConditionalOnProperty(name = "DATABASE_URL")
class VideoConfiguration {

    @Bean
    JooqVideoEpisodeRepository videoEpisodeRepository(CoreDatabase database, CuidV1Generator ids,
            Clock coreClock, ObjectMapper json) {
        return new JooqVideoEpisodeRepository(database, ids, coreClock, json);
    }

    @Bean
    cn.inkforge.core.video.application.VideoEpisodeService videoEpisodeService(
            JooqVideoEpisodeRepository repository, CoreSettings settings) {
        return new cn.inkforge.core.video.application.VideoEpisodeService(repository, settings.videoPreviewEnabled());
    }

    @Bean
    JooqVideoEpisodeProductionRepository videoEpisodeProductionRepository(
            CoreDatabase database,
            CuidV1Generator ids,
            Clock coreClock,
            ObjectMapper json,
            CoreSettings settings) {
        return new JooqVideoEpisodeProductionRepository(
                database,
                ids,
                coreClock,
                json,
                settings.seedanceModel(),
                settings.seedanceExecutionMode(),
                settings.seedanceConfigured(),
                settings.seedanceEnabled(),
                settings.videoPreviewEnabled());
    }

    @Bean
    cn.inkforge.core.video.application.VideoEpisodeProductionService videoEpisodeProductionService(
            JooqVideoEpisodeProductionRepository repository, CoreSettings settings) {
        return new cn.inkforge.core.video.application.VideoEpisodeProductionService(
                repository, settings.videoPreviewEnabled());
    }

    @Bean
    VideoAssetStore videoAssetStore(CoreSettings settings) {
        return new VideoAssetStorage(settings.uploadsRoot());
    }

    @Bean
    VideoMediaProbe videoMediaProbe(ObjectMapper json) {
        return FfprobeVideoMediaProbe.discover(
                "ffprobe", System.getenv("PATH"), Duration.ofSeconds(30), json);
    }

    @Bean
    VideoIdGenerator videoIdGenerator(CuidV1Generator ids) {
        return ids::next;
    }

    @Bean
    VideoProjectRepository videoProjectRepository(
            CoreDatabase database, CuidV1Generator ids, Clock coreClock) {
        return new JooqVideoProjectRepository(database, ids, coreClock);
    }

    @Bean
    JooqVideoVisualCanonRepository videoVisualCanonRepository(
            CoreDatabase database,
            CuidV1Generator ids,
            Clock coreClock,
            ObjectMapper json) {
        return new JooqVideoVisualCanonRepository(database, ids, coreClock, json);
    }

    @Bean
    VideoVisualCanonService videoVisualCanonService(
            VideoVisualCanonRepository repository, CoreSettings settings) {
        return new VideoVisualCanonService(repository, settings.videoPreviewEnabled());
    }

    @Bean
    VideoProjectService videoProjectService(
            VideoProjectRepository repository,
            VideoAssetStore storage,
            VideoMediaProbe probe,
            VideoIdGenerator ids,
            CoreSettings settings) {
        return new VideoProjectService(
                repository,
                storage,
                probe,
                ids,
                settings.videoPreviewEnabled(),
                settings.seedanceConfigured(),
                settings.seedanceEnabled());
    }

    @Bean
    @Conditional(ProviderAssetTokenConfiguredCondition.class)
    ProviderAssetTokenCodec providerAssetTokenCodec(
            CoreSettings settings, Clock coreClock, ObjectMapper json) {
        // 令牌只给供应商短时读取已冻结参考图，不能替代素材归属和 rightsStatus 校验。
        return new ProviderAssetTokenCodec(
                settings.videoProviderMediaTokenSecret().reveal(),
                Duration.ofMinutes(10),
                coreClock,
                json);
    }

    @Bean
    VideoRenderResultArchiver videoRenderResultArchiver(
            VideoAssetStore storage, CoreSettings settings, VideoMediaProbe mediaProbe) {
        return new SeedanceResultArchiver(
                storage, settings.seedanceResultAllowedHostSuffixes(), mediaProbe);
    }

    @Bean
    VideoRenderSimulator videoRenderSimulator(
            VideoAssetStore storage, CoreSettings settings, VideoMediaProbe mediaProbe) {
        return new FfmpegVideoRenderSimulator(
                FfprobeVideoMediaProbe.findExecutable("ffmpeg", System.getenv("PATH")),
                settings.uploadsRoot().resolve("video-simulation-work"),
                storage, mediaProbe, Duration.ofMinutes(2));
    }

    @Bean
    VideoPostProductionMediaProcessor videoPostProductionMediaProcessor(ObjectMapper json) {
        return FfmpegVideoPostProductionMediaProcessor.discover(
                "ffmpeg",
                "ffprobe",
                System.getenv("PATH"),
                Duration.ofMinutes(30),
                json);
    }

    @Bean
    JooqVideoEpisodePostProductionRepository videoEpisodePostProductionRepository(
            CoreDatabase database, CuidV1Generator ids, Clock coreClock, ObjectMapper json) {
        return new JooqVideoEpisodePostProductionRepository(database, ids, coreClock, json);
    }

    @Bean
    VideoEpisodePostProductionService videoEpisodePostProductionService(
            JooqVideoEpisodePostProductionRepository repository,
            VideoAssetStore storage,
            VideoPostProductionMediaProcessor media,
            CoreSettings settings) {
        return new VideoEpisodePostProductionService(
                repository, storage, media, settings.videoPreviewEnabled());
    }

    @Bean
    @ConditionalOnProperty(name = "VIDEO_PREVIEW_ENABLED", havingValue = "true")
    VideoEpisodePostProductionReconciler videoEpisodePostProductionReconciler(
            JooqVideoEpisodePostProductionRepository repository,
            VideoPostProductionMediaProcessor media,
            VideoAssetStore storage) {
        return new VideoEpisodePostProductionReconciler(
                repository, media, storage, 1, Duration.ofSeconds(3));
    }

}
