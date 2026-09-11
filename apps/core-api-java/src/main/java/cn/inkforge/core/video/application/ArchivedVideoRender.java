package cn.inkforge.core.video.application;

/** 已从供应商临时地址完整流入受控存储的渲染结果。 */
public record ArchivedVideoRender(String assetId, StoredVideoAsset stored, int durationMs) {
    public ArchivedVideoRender {
        if (durationMs <= 0) throw new IllegalArgumentException("归档视频必须具有实测正时长");
    }
}
