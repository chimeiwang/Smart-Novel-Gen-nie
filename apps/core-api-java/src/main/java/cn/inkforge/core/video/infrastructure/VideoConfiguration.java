package cn.inkforge.core.video.infrastructure;

import cn.inkforge.core.platform.config.CoreSettings;
import cn.inkforge.core.platform.db.CoreDatabase;
import cn.inkforge.core.platform.id.CuidV1Generator;
import cn.inkforge.core.video.application.ProviderAssetTokenCodec;
import cn.inkforge.core.video.application.LegacyVideoPlanDispatchStore;
import cn.inkforge.core.video.application.LegacyVideoPlanDispatcher;
import cn.inkforge.core.video.application.LegacyVideoPlanService;
import cn.inkforge.core.video.application.LegacyVideoPlanStore;
import cn.inkforge.core.video.application.VideoAssetStore;
import cn.inkforge.core.video.application.VideoAdaptationRepository;
import cn.inkforge.core.video.application.VideoAdaptationDecisionStore;
import cn.inkforge.core.video.application.VideoAdaptationService;
import cn.inkforge.core.video.application.VideoAdaptationTaskStore;
import cn.inkforge.core.video.application.VideoAdaptationTaskDispatcher;
import cn.inkforge.core.video.application.VideoAdaptationTaskSubmitter;
import cn.inkforge.core.video.application.VideoIdGenerator;
import cn.inkforge.core.video.application.VideoMediaProbe;
import cn.inkforge.core.video.application.VideoProjectRepository;
import cn.inkforge.core.video.application.VideoProjectService;
import cn.inkforge.core.video.application.VideoPostProductionMediaProcessor;
import cn.inkforge.core.video.application.VideoPostProductionReconciler;
import cn.inkforge.core.video.application.VideoPostProductionRepository;
import cn.inkforge.core.video.application.VideoPostProductionService;
import cn.inkforge.core.video.application.VideoRenderGateway;
import cn.inkforge.core.video.application.VideoRenderReconciler;
import cn.inkforge.core.video.application.VideoRenderRepository;
import cn.inkforge.core.video.application.VideoRenderResultArchiver;
import cn.inkforge.core.video.application.VideoRenderService;
import cn.inkforge.core.video.application.VideoVisualCanonRepository;
import cn.inkforge.core.video.application.VideoVisualCanonService;
import java.time.Clock;
import java.time.Duration;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.boot.autoconfigure.condition.ConditionalOnBean;
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
    VideoAdaptationRepository videoAdaptationRepository(
            CoreDatabase database,
            CuidV1Generator ids,
            Clock coreClock,
            ObjectMapper json,
            JooqVideoVisualCanonRepository visualCanons) {
        return new JooqVideoAdaptationRepository(database, ids, coreClock, json, visualCanons);
    }

    @Bean
    VideoAdaptationService videoAdaptationService(
            VideoAdaptationRepository repository,
            VideoAdaptationDecisionStore decisions,
            VideoAdaptationTaskStore tasks,
            CoreSettings settings) {
        return new VideoAdaptationService(
                repository, decisions, tasks, settings.videoPreviewEnabled());
    }

    @Bean
    VideoAdaptationDecisionStore videoAdaptationDecisionStore(
            CoreDatabase database,
            CuidV1Generator ids,
            Clock coreClock,
            ObjectMapper json,
            JooqVideoVisualCanonRepository visualCanons) {
        return new JooqVideoAdaptationDecisionStore(
                database, ids, coreClock, json, visualCanons);
    }

    @Bean
    VideoAdaptationTaskStore videoAdaptationTaskStore(
            CoreDatabase database,
            CuidV1Generator ids,
            Clock coreClock,
            ObjectMapper json,
            JooqVideoVisualCanonRepository visualCanons,
            CoreSettings settings) {
        return new JooqVideoAdaptationTaskStore(
                database,
                ids,
                coreClock,
                json,
                visualCanons,
                settings.videoDispatchNamespace());
    }

    @Bean
    @ConditionalOnProperty(name = "VIDEO_DISPATCH_ENABLED", havingValue = "true")
    VideoAdaptationTaskDispatcher videoAdaptationTaskDispatcher(
            VideoAdaptationTaskStore tasks,
            ObjectProvider<VideoAdaptationTaskSubmitter> submitters) {
        // 每轮最多领取 20 条、失败后 5 秒退避；持久化租约和重试计数仍由 TaskStore 掌权。
        return new VideoAdaptationTaskDispatcher(
                tasks,
                new ProviderVideoAdaptationTaskSubmitter(submitters),
                20,
                Duration.ofSeconds(5));
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
    LegacyVideoPlanStore legacyVideoPlanStore(
            CoreDatabase database,
            CuidV1Generator ids,
            Clock coreClock,
            ObjectMapper json,
            CoreSettings settings) {
        return new JooqLegacyVideoPlanStore(
                database,
                ids,
                coreClock,
                json);
    }

    @Bean
    LegacyVideoPlanDispatchStore legacyVideoPlanDispatchStore(
            CoreDatabase database,
            Clock coreClock,
            ObjectMapper json,
            CoreSettings settings) {
        return new JooqLegacyVideoPlanDispatchStore(
                database,
                coreClock,
                json,
                settings.videoDispatchNamespace());
    }

    @Bean
    LegacyVideoPlanService legacyVideoPlanService(LegacyVideoPlanStore store) {
        return new LegacyVideoPlanService(store);
    }

    @Bean
    @ConditionalOnProperty(name = "VIDEO_DISPATCH_ENABLED", havingValue = "true")
    LegacyVideoPlanDispatcher legacyVideoPlanDispatcher(
            LegacyVideoPlanDispatchStore store,
            ObjectProvider<VideoAdaptationTaskSubmitter> submitters) {
        return new LegacyVideoPlanDispatcher(
                store,
                new ProviderVideoAdaptationTaskSubmitter(submitters),
                20,
                Duration.ofSeconds(5));
    }

    @Bean
    VideoRenderRepository videoRenderRepository(
            CoreDatabase database, CuidV1Generator ids, Clock coreClock, ObjectMapper json) {
        return new JooqVideoRenderRepository(database, ids, coreClock, json);
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
    VideoRenderService videoRenderService(
            VideoRenderRepository repository,
            VideoAssetStore storage,
            CoreSettings settings,
            ObjectProvider<ProviderAssetTokenCodec> tokens) {
        return new VideoRenderService(
                repository,
                storage,
                settings.seedanceConfigured(),
                settings.seedanceEnabled(),
                settings.seedanceModel(),
                settings.videoProviderMediaBaseUrl(),
                tokens.getIfAvailable());
    }

    @Bean
    @ConditionalOnProperty(name = "SEEDANCE_ENABLED", havingValue = "true")
    VideoRenderResultArchiver videoRenderResultArchiver(
            VideoAssetStore storage, CoreSettings settings) {
        return new SeedanceResultArchiver(
                storage, settings.seedanceResultAllowedHostSuffixes());
    }

    @Bean
    @ConditionalOnBean({VideoRenderGateway.class, VideoRenderResultArchiver.class})
    @ConditionalOnProperty(name = "SEEDANCE_ENABLED", havingValue = "true")
    VideoRenderReconciler videoRenderReconciler(
            VideoRenderRepository repository,
            VideoRenderGateway gateway,
            VideoRenderResultArchiver archiver,
            VideoAssetStore storage,
            CoreSettings settings,
            ObjectProvider<ProviderAssetTokenCodec> tokens) {
        // 只有网关与受控归档器同时存在才轮询；并发 3、3 秒循环是单机资源上限，不是业务状态来源。
        return new VideoRenderReconciler(
                repository,
                gateway,
                archiver,
                storage,
                settings.videoProviderMediaBaseUrl(),
                tokens.getIfAvailable(),
                3,
                Duration.ofSeconds(3));
    }

    @Bean
    VideoPostProductionRepository videoPostProductionRepository(
            CoreDatabase database, CuidV1Generator ids, Clock coreClock, ObjectMapper json) {
        return new JooqVideoPostProductionRepository(database, ids, coreClock, json);
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
    VideoPostProductionService videoPostProductionService(
            VideoPostProductionRepository repository,
            VideoAssetStore storage,
            VideoPostProductionMediaProcessor media) {
        return new VideoPostProductionService(repository, storage, media);
    }

    @Bean
    @ConditionalOnProperty(name = "VIDEO_PREVIEW_ENABLED", havingValue = "true")
    VideoPostProductionReconciler videoPostProductionReconciler(
            VideoPostProductionRepository repository,
            VideoPostProductionMediaProcessor media,
            VideoAssetStore storage) {
        // 生产默认关闭预览；单并发避免 2 核 2 GB 部署上多个 FFmpeg 同时挤占内存。
        return new VideoPostProductionReconciler(
                repository, media, storage, 1, Duration.ofSeconds(3));
    }
}
