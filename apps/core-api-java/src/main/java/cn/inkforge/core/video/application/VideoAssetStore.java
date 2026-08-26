package cn.inkforge.core.video.application;

import java.io.InputStream;
import java.nio.file.Path;
import org.springframework.web.multipart.MultipartFile;

/** 视频媒体的受控文件边界；数据库只保存这里返回的不可伪造文件事实。 */
public interface VideoAssetStore {

    StoredVideoAsset save(
            String projectId, String assetId, String modality, MultipartFile upload);

    StoredVideoAsset saveStream(
            String projectId,
            String assetId,
            String modality,
            InputStream input,
            long maximumBytes);

    Path resolve(String storageKey);

    boolean delete(String storageKey);
}
