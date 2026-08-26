package cn.inkforge.core.video.application;

import java.util.List;

/** 视频制作台第一层读模型：项目及其全部真实素材。 */
public record VideoProjectAggregate(
        VideoProjectSnapshot project, List<VideoAssetSnapshot> assets) {

    public VideoProjectAggregate {
        assets = List.copyOf(assets);
    }
}
