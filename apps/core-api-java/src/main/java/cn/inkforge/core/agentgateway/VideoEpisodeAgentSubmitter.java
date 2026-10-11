package cn.inkforge.core.agentgateway;

import cn.inkforge.contracts.agent.AgentJobRequest;
import cn.inkforge.contracts.agent.AgentJobCancelRequest;
import cn.inkforge.core.video.application.VideoEpisodeTaskSubmitter;
import java.util.Map;
import org.springframework.boot.autoconfigure.condition.ConditionalOnBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

/** 把剧本与分镜任务投递到 V1 视频队列。 */
@Configuration(proxyBeanMethods = false)
class VideoEpisodeAgentSubmitter {
    @Bean
    @ConditionalOnBean(AgentServiceClient.class)
    VideoEpisodeTaskSubmitter videoEpisodeTaskSubmitter(AgentServiceClient client) {
        return new VideoEpisodeTaskSubmitter() {
            public void submit(String userId, String novelId, String taskId, Map<String, Object> payload) {
                client.submit(new AgentJobRequest("video-episode-" + taskId,
                        AgentJobRequest.KindEnum.VIDEO, novelId, payload, 20, "1.0", taskId, taskId, userId));
            }
            public void cancel(String userId, String novelId, String taskId) {
                client.cancel("video-episode-" + taskId, new AgentJobCancelRequest(novelId, "1.0", taskId, taskId));
            }
        };
    }
}
