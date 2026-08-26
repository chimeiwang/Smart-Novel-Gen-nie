package cn.inkforge.cli.transport;

import java.io.IOException;
import java.nio.file.Path;
import java.util.List;
import java.util.Map;
import tools.jackson.databind.JsonNode;

/** 命令层只依赖的公共 Core 传输端口。 */
public interface CoreApi {

    JsonNode request(String method, String path);

    JsonNode request(String method, String path, JsonNode body);

    default JsonNode request(
            String method,
            String path,
            Map<String, List<String>> query,
            JsonNode body) {
        if (query == null || query.isEmpty()) return request(method, path, body);
        throw new UnsupportedOperationException("当前 CoreApi 测试替身未实现查询参数");
    }

    LoginResult login(String username, String password);

    default SseStream openSse(String taskId, String lastEventId) {
        throw new UnsupportedOperationException("当前 CoreApi 测试替身未实现 SSE");
    }

    default JsonNode upload(
            String path,
            Path file,
            String mediaType,
            Map<String, String> fields)
            throws IOException {
        throw new UnsupportedOperationException("当前 CoreApi 测试替身未实现文件上传");
    }

    FileDescriptor download(String method, String path, Path target) throws IOException;
}
