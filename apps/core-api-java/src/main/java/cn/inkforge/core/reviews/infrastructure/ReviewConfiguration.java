package cn.inkforge.core.reviews.infrastructure;

import cn.inkforge.core.lore.application.LoreRepository;
import cn.inkforge.core.outlines.application.OutlineRepository;
import cn.inkforge.core.platform.config.CoreSettings;
import cn.inkforge.core.platform.db.CoreDatabase;
import cn.inkforge.core.platform.id.CuidV1Generator;
import cn.inkforge.core.references.application.ReferenceRepository;
import cn.inkforge.core.reviews.application.AgentUpdatesExecutor;
import cn.inkforge.core.reviews.application.FormalArtifactWriter;
import cn.inkforge.core.reviews.application.ReviewRepository;
import java.time.Clock;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import tools.jackson.databind.ObjectMapper;

@Configuration(proxyBeanMethods = false)
@ConditionalOnProperty(name = "DATABASE_URL")
class ReviewConfiguration {

    @Bean
    AgentUpdatesExecutor agentUpdatesExecutor(
            LoreRepository lore,
            OutlineRepository outlines,
            ReferenceRepository references,
            CuidV1Generator ids,
            CoreSettings settings) {
        return new AgentUpdatesExecutor(
                lore, outlines, references, ids, settings.ragIndexEnabled());
    }

    @Bean
    FormalArtifactWriter formalArtifactWriter(
            CoreDatabase database,
            CuidV1Generator ids,
            Clock coreClock,
            ObjectMapper objectMapper,
            AgentUpdatesExecutor updates) {
        return new JooqFormalArtifactWriter(
                database, ids, coreClock, objectMapper, updates);
    }

    @Bean
    ReviewRepository reviewRepository(
            CoreDatabase database,
            CuidV1Generator ids,
            Clock coreClock,
            ObjectMapper objectMapper,
            FormalArtifactWriter formalWriter) {
        return new JooqReviewRepository(
                database, ids, coreClock, objectMapper, formalWriter);
    }
}
