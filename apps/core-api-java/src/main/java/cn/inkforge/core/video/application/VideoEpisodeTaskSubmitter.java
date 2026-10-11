package cn.inkforge.core.video.application;

import java.util.Map;

/** 视频领域拥有普通队列端口；稳定任务身份用于未知网络结果重投。 */
public interface VideoEpisodeTaskSubmitter {
    void submit(String userId, String novelId, String taskId, Map<String, Object> payload);
    void cancel(String userId, String novelId, String taskId);
}
