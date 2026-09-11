package cn.inkforge.core.video.infrastructure;

import cn.inkforge.core.platform.config.CoreSettings;
import cn.inkforge.core.platform.db.CoreDatabase;
import cn.inkforge.core.platform.id.CuidV1Generator;
import cn.inkforge.core.video.application.VideoEpisodeScriptRunService;
import cn.inkforge.core.video.application.VideoEpisodeScriptRunStore;
import cn.inkforge.core.video.application.VideoEpisodeStoryboardRunService;
import cn.inkforge.core.video.application.VideoEpisodeStoryboardRunStore;
import cn.inkforge.core.video.application.VideoEpisodeStoryboardCandidateService;
import cn.inkforge.core.workflows.application.DurableWorkflowService;
import cn.inkforge.core.workflows.catalog.ExecutionRegistry;
import java.time.Clock;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import tools.jackson.databind.ObjectMapper;

/** 独立剧集 V2 启动装配；没有数据库时不会影响最小健康上下文。 */
@Configuration(proxyBeanMethods = false)
@ConditionalOnProperty(name = "DATABASE_URL")
class VideoEpisodeWorkflowConfiguration {

    @Bean
    VideoEpisodeScriptRunStore videoEpisodeScriptRunStore(
            CoreDatabase database,
            CuidV1Generator ids,
            CoreSettings settings,
            ExecutionRegistry registry,
            ObjectProvider<DurableWorkflowService> workflows,
            ObjectMapper json) {
        return new JooqVideoEpisodeScriptRunStore(
                database, ids, settings, registry, workflows::getIfAvailable, json);
    }

    @Bean
    VideoEpisodeScriptRunService videoEpisodeScriptRunService(
            VideoEpisodeScriptRunStore runs) {
        return new VideoEpisodeScriptRunService(runs);
    }

    @Bean
    VideoEpisodeStoryboardRunStore videoEpisodeStoryboardRunStore(
            CoreDatabase database,
            CuidV1Generator ids,
            CoreSettings settings,
            ExecutionRegistry registry,
            ObjectProvider<DurableWorkflowService> workflows,
            ObjectMapper json) {
        return new JooqVideoEpisodeStoryboardRunStore(
                database, ids, settings, registry, workflows::getIfAvailable, json);
    }

    @Bean
    VideoEpisodeStoryboardRunService videoEpisodeStoryboardRunService(
            VideoEpisodeStoryboardRunStore runs) {
        return new VideoEpisodeStoryboardRunService(runs);
    }

    @Bean
    JooqVideoEpisodeStoryboardCandidateRepository videoEpisodeStoryboardCandidates(
            CoreDatabase database,
            CuidV1Generator ids,
            Clock coreClock,
            ObjectMapper json) {
        return new JooqVideoEpisodeStoryboardCandidateRepository(
                database, ids, coreClock, json);
    }

    @Bean
    VideoEpisodeStoryboardCandidateService videoEpisodeStoryboardCandidateService(
            JooqVideoEpisodeStoryboardCandidateRepository candidates,
            CoreSettings settings) {
        return new VideoEpisodeStoryboardCandidateService(
                candidates, settings.videoPreviewEnabled());
    }
}
