package cn.inkforge.core.video.application;

/** 视频业务拥有后台生命周期端口；Operations 只负责启动和停止，不依赖基础设施实现。 */
public interface VideoEpisodeTaskLifecycle {
    void run() throws InterruptedException;
    void requestStop();
}
