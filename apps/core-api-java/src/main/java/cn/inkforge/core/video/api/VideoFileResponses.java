package cn.inkforge.core.video.api;

import cn.inkforge.core.platform.http.ApiException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import org.springframework.http.ContentDisposition;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.servlet.mvc.method.annotation.StreamingResponseBody;

/** 统一五个视频文件入口的流式响应，禁止把媒体整体读入 JVM 堆。 */
final class VideoFileResponses {

    private VideoFileResponses() {}

    static ResponseEntity<StreamingResponseBody> attachment(
            Path path, String mimeType, String filename) {
        return response(path, mimeType, filename, "attachment");
    }

    static ResponseEntity<StreamingResponseBody> inline(
            Path path, String mimeType, String filename) {
        return response(path, mimeType, filename, "inline");
    }

    static ResponseEntity<StreamingResponseBody> bare(
            Path path, String mimeType) {
        return response(path, mimeType, null, null);
    }

    private static ResponseEntity<StreamingResponseBody> response(
            Path path,
            String mimeType,
            String filename,
            String dispositionType) {
        if (path == null || !Files.isRegularFile(path, LinkOption.NOFOLLOW_LINKS)) {
            throw new ApiException(404, "VIDEO_ASSET_FILE_NOT_FOUND", "视频素材文件不存在");
        }
        MediaType contentType;
        try {
            contentType = MediaType.parseMediaType(mimeType);
        } catch (RuntimeException exception) {
            throw new ApiException(
                    409,
                    "VIDEO_ASSET_MIME_INVALID",
                    "视频素材的媒体类型已损坏");
        }
        long length;
        try {
            length = Files.size(path);
        } catch (java.io.IOException exception) {
            throw new ApiException(404, "VIDEO_ASSET_FILE_NOT_FOUND", "视频素材文件不存在");
        }
        StreamingResponseBody body = output -> {
            try (var input = Files.newInputStream(path)) {
                input.transferTo(output);
            }
        };
        ResponseEntity.BodyBuilder builder = ResponseEntity.ok()
                .contentType(contentType)
                .contentLength(length);
        if (filename != null && dispositionType != null) {
            ContentDisposition disposition = ("attachment".equals(dispositionType)
                            ? ContentDisposition.attachment()
                            : ContentDisposition.inline())
                    .filename(filename, StandardCharsets.UTF_8)
                    .build();
            builder.header(HttpHeaders.CONTENT_DISPOSITION, disposition.toString());
        }
        return builder.body(body);
    }
}
