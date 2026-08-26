package cn.inkforge.core.video.application;

/** 让视频应用服务在写文件前取得稳定业务标识，同时保持单元测试可控。 */
@FunctionalInterface
public interface VideoIdGenerator {

    String next();
}
