package cn.inkforge.cli.transport;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.file.Path;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Locale;
import java.util.NoSuchElementException;
import java.util.Set;
import java.util.UUID;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;
import tools.jackson.databind.node.ObjectNode;

/**
 * 保留原始 JSON 树和二进制流的公共 Core 客户端。
 *
 * <p>路径和 DTO 的完整性由同一 OpenAPI 生成客户端在编译期校验；这里避免 DTO 重序列化丢失显式 null。</p>
 */
public final class CoreApiClient implements CoreApi {

    private static final Set<String> METHODS = Set.of("GET", "POST", "PUT", "PATCH", "DELETE");
    private static final String COOKIE = "inkforge-token";

    private final String origin;
    private final String token;
    private final ObjectMapper json;
    private final HttpClient http;

    public CoreApiClient(String origin, String token, ObjectMapper json) {
        this.origin = CoreOrigin.validate(origin);
        this.token = token;
        this.json = json;
        this.http = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(30))
                .followRedirects(HttpClient.Redirect.NEVER)
                .build();
    }

    public JsonNode request(String method, String path) {
        return request(method, path, null);
    }

    public JsonNode request(String method, String path, JsonNode body) {
        return request(method, path, Map.of(), body);
    }

    @Override
    public JsonNode request(
            String method,
            String path,
            Map<String, List<String>> query,
            JsonNode body) {
        HttpRequest request = requestBuilder(method, path, query, body).build();
        HttpResponse<byte[]> response;
        try {
            response = http.send(request, HttpResponse.BodyHandlers.ofByteArray());
        } catch (InterruptedException exception) {
            Thread.currentThread().interrupt();
            throw new CoreTransportException();
        } catch (IOException exception) {
            throw new CoreTransportException();
        }
        ensureSuccess(response.statusCode(), response.body());
        if (response.statusCode() == 204 || response.body().length == 0) {
            return json.createObjectNode();
        }
        try {
            JsonNode result = json.readTree(response.body());
            if (result == null) {
                throw new CoreResponseContractException("Core API 成功响应不是有效 JSON");
            }
            return result;
        } catch (RuntimeException exception) {
            if (exception instanceof CoreResponseContractException contract) throw contract;
            throw new CoreResponseContractException("Core API 成功响应不是有效 JSON");
        }
    }

    public LoginResult login(String username, String password) {
        ObjectNode body = json.createObjectNode();
        body.put("username", username);
        body.put("password", password);
        HttpResponse<byte[]> response;
        try {
            response = http.send(
                    requestBuilder("POST", "/api/v1/auth/login", Map.of(), body).build(),
                    HttpResponse.BodyHandlers.ofByteArray());
        } catch (InterruptedException exception) {
            Thread.currentThread().interrupt();
            throw new CoreTransportException();
        } catch (IOException exception) {
            throw new CoreTransportException();
        }
        ensureSuccess(response.statusCode(), response.body());
        String session = sessionCookie(response.headers().allValues("set-cookie"));
        if (session == null) {
            throw new CoreApiException(
                    500,
                    "LOGIN_COOKIE_MISSING",
                    "登录成功响应缺少 inkforge-token Cookie",
                    null,
                    null);
        }
        JsonNode user;
        try {
            user = json.readTree(response.body());
        } catch (RuntimeException exception) {
            throw new CoreResponseContractException("登录响应格式无效");
        }
        if (user == null || !user.isObject()) {
            throw new CoreResponseContractException("登录响应格式无效");
        }
        return new LoginResult(user, session);
    }

    public FileDescriptor download(String method, String path, Path target) throws IOException {
        HttpResponse<InputStream> response;
        try {
            response = http.send(
                    requestBuilder(method, path, Map.of(), null).build(),
                    HttpResponse.BodyHandlers.ofInputStream());
        } catch (InterruptedException exception) {
            Thread.currentThread().interrupt();
            throw new CoreTransportException();
        } catch (IOException exception) {
            throw new CoreTransportException();
        }
        if (response.statusCode() < 200 || response.statusCode() >= 300) {
            try (InputStream body = response.body()) {
                ensureSuccess(response.statusCode(), body.readAllBytes());
            }
        }
        String mediaType = response.headers()
                .firstValue("content-type")
                .orElse("application/octet-stream");
        return AtomicFiles.write(target, response.body(), mediaType);
    }

    @Override
    public SseStream openSse(String taskId, String lastEventId) {
        String path = "/api/v1/writing/runs/" + encode(taskId) + "/events";
        validatePath(path);
        HttpRequest.Builder builder = HttpRequest.newBuilder(URI.create(origin + path))
                .timeout(Duration.ofSeconds(300))
                .header("Accept", "text/event-stream")
                .GET();
        if (lastEventId != null && !lastEventId.isEmpty()) {
            if (lastEventId.indexOf('\r') >= 0 || lastEventId.indexOf('\n') >= 0) {
                throw new IllegalArgumentException("Last-Event-ID 包含非法字符");
            }
            builder.header("Last-Event-ID", lastEventId);
        }
        if (token != null) builder.header("Cookie", COOKIE + "=" + token);
        HttpResponse<InputStream> response;
        try {
            response = http.send(builder.build(), HttpResponse.BodyHandlers.ofInputStream());
        } catch (InterruptedException exception) {
            Thread.currentThread().interrupt();
            throw new CoreSseConnectionException();
        } catch (IOException exception) {
            throw new CoreSseConnectionException();
        }
        if (response.statusCode() < 200 || response.statusCode() >= 300) {
            try (InputStream body = response.body()) {
                ensureSuccess(response.statusCode(), body.readAllBytes());
            } catch (IOException exception) {
                throw new CoreSseConnectionException();
            }
        }
        return new HttpSseStream(response.body());
    }

    @Override
    public JsonNode upload(
            String path,
            Path file,
            String mediaType,
            Map<String, String> fields)
            throws IOException {
        validatePath(path);
        String boundary = "inkforge-" + UUID.randomUUID();
        List<HttpRequest.BodyPublisher> parts = new ArrayList<>();
        for (Map.Entry<String, String> entry : fields.entrySet()) {
            requireMultipartToken(entry.getKey(), "表单字段名");
            requireMultipartValue(entry.getValue(), "表单字段值");
            parts.add(bytes(
                    "--" + boundary + "\r\n"
                            + "Content-Disposition: form-data; name=\""
                            + entry.getKey()
                            + "\"\r\n\r\n"
                            + entry.getValue()
                            + "\r\n"));
        }
        String filename = file.getFileName().toString();
        requireMultipartToken(filename, "文件名");
        requireMultipartToken(mediaType, "媒体类型");
        parts.add(bytes(
                "--" + boundary + "\r\n"
                        + "Content-Disposition: form-data; name=\"file\"; filename=\""
                        + filename
                        + "\"\r\n"
                        + "Content-Type: "
                        + mediaType
                        + "\r\n\r\n"));
        parts.add(HttpRequest.BodyPublishers.ofFile(file));
        parts.add(bytes("\r\n--" + boundary + "--\r\n"));
        HttpRequest.Builder builder = HttpRequest.newBuilder(URI.create(origin + path))
                .timeout(Duration.ofSeconds(300))
                .header("Accept", "application/json")
                .header("Content-Type", "multipart/form-data; boundary=" + boundary)
                .POST(HttpRequest.BodyPublishers.concat(
                        parts.toArray(HttpRequest.BodyPublisher[]::new)));
        if (token != null) builder.header("Cookie", COOKIE + "=" + token);
        HttpResponse<byte[]> response;
        try {
            response = http.send(builder.build(), HttpResponse.BodyHandlers.ofByteArray());
        } catch (InterruptedException exception) {
            Thread.currentThread().interrupt();
            throw new CoreTransportException();
        } catch (IOException exception) {
            throw new CoreTransportException();
        }
        ensureSuccess(response.statusCode(), response.body());
        if (response.statusCode() == 204 || response.body().length == 0) {
            return json.createObjectNode();
        }
        try {
            JsonNode result = json.readTree(response.body());
            if (result == null) {
                throw new CoreResponseContractException("Core API 上传响应不是有效 JSON");
            }
            return result;
        } catch (RuntimeException exception) {
            if (exception instanceof CoreResponseContractException contract) throw contract;
            throw new CoreResponseContractException("Core API 上传响应不是有效 JSON");
        }
    }

    private HttpRequest.Builder requestBuilder(
            String method,
            String path,
            Map<String, List<String>> query,
            JsonNode body) {
        String normalizedMethod = method == null ? "" : method.toUpperCase(Locale.ROOT);
        if (!METHODS.contains(normalizedMethod)) {
            throw new IllegalArgumentException("CLI HTTP 方法无效");
        }
        validatePath(path);
        HttpRequest.BodyPublisher publisher;
        if (body == null) {
            publisher = HttpRequest.BodyPublishers.noBody();
        } else {
            try {
                publisher = HttpRequest.BodyPublishers.ofByteArray(json.writeValueAsBytes(body));
            } catch (RuntimeException exception) {
                throw new IllegalArgumentException("CLI 请求 JSON 无法序列化", exception);
            }
        }
        HttpRequest.Builder builder = HttpRequest.newBuilder(
                        URI.create(origin + path + queryString(query)))
                .timeout(Duration.ofSeconds(300))
                .header("Accept", "application/json")
                .method(normalizedMethod, publisher);
        if (body != null) builder.header("Content-Type", "application/json");
        if (token != null) builder.header("Cookie", COOKIE + "=" + token);
        return builder;
    }

    private static void validatePath(String path) {
        if (path == null
                || !path.startsWith("/api/v1/")
                || path.contains("/internal/")
                || path.contains("?")
                || path.contains("#")) {
            throw new IllegalArgumentException("CLI 只能调用 /api/v1/** 公共接口");
        }
    }

    private static String queryString(Map<String, List<String>> query) {
        if (query == null || query.isEmpty()) return "";
        StringBuilder result = new StringBuilder("?");
        boolean first = true;
        for (Map.Entry<String, List<String>> entry : query.entrySet()) {
            if (entry.getKey() == null || entry.getKey().isEmpty()) {
                throw new IllegalArgumentException("CLI 查询参数名无效");
            }
            List<String> values = entry.getValue();
            if (values == null || values.isEmpty()) continue;
            for (String value : values) {
                if (!first) result.append('&');
                first = false;
                result.append(encode(entry.getKey())).append('=').append(encode(value));
            }
        }
        return first ? "" : result.toString();
    }

    private static String encode(String value) {
        if (value == null) return "";
        byte[] bytes = value.getBytes(StandardCharsets.UTF_8);
        StringBuilder encoded = new StringBuilder(bytes.length);
        for (byte raw : bytes) {
            int item = raw & 0xff;
            if (item >= 'A' && item <= 'Z'
                    || item >= 'a' && item <= 'z'
                    || item >= '0' && item <= '9'
                    || item == '-'
                    || item == '.'
                    || item == '_'
                    || item == '~') {
                encoded.append((char) item);
            } else {
                encoded.append('%');
                encoded.append(Character.toUpperCase(Character.forDigit(item >>> 4, 16)));
                encoded.append(Character.toUpperCase(Character.forDigit(item & 0x0f, 16)));
            }
        }
        return encoded.toString();
    }

    private static HttpRequest.BodyPublisher bytes(String value) {
        return HttpRequest.BodyPublishers.ofByteArray(value.getBytes(StandardCharsets.UTF_8));
    }

    private static void requireMultipartToken(String value, String label) {
        if (value == null
                || value.isEmpty()
                || value.indexOf('\r') >= 0
                || value.indexOf('\n') >= 0
                || value.indexOf('"') >= 0) {
            throw new IllegalArgumentException(label + "包含非法字符");
        }
    }

    private static void requireMultipartValue(String value, String label) {
        if (value == null || value.indexOf('\r') >= 0 || value.indexOf('\n') >= 0) {
            throw new IllegalArgumentException(label + "包含非法字符");
        }
    }

    private void ensureSuccess(int statusCode, byte[] body) {
        if (statusCode >= 200 && statusCode < 300) return;
        String code = "HTTP_" + statusCode;
        String message = "Core API 请求失败";
        JsonNode details = null;
        String requestId = null;
        try {
            JsonNode root = json.readTree(body);
            if (root != null && root.isObject()) {
                requestId = optionalText(root.get("requestId"));
                JsonNode detail = root.get("detail");
                JsonNode payload = detail != null && detail.isObject() ? detail : root;
                String parsedCode = optionalText(payload.get("code"));
                String parsedMessage = optionalText(payload.get("message"));
                if (parsedCode != null) code = parsedCode;
                if (parsedMessage != null) {
                    message = parsedMessage;
                } else if (detail != null && detail.isTextual()) {
                    message = detail.textValue();
                }
                details = payload.get("details");
                String nestedRequestId = optionalText(payload.get("requestId"));
                if (nestedRequestId != null) requestId = nestedRequestId;
            }
        } catch (RuntimeException ignored) {
            // 非 JSON 错误正文不进入 CLI 输出，避免泄漏代理或上游内部文本。
        }
        throw new CoreApiException(statusCode, code, message, details, requestId);
    }

    private static String optionalText(JsonNode value) {
        return value != null && value.isTextual() ? value.textValue() : null;
    }

    private static String sessionCookie(List<String> values) {
        String prefix = COOKIE + "=";
        for (String value : values) {
            String first = value.split(";", 2)[0].trim();
            if (first.startsWith(prefix) && first.length() > prefix.length()) {
                return first.substring(prefix.length());
            }
        }
        return null;
    }

    private final class HttpSseStream implements SseStream {

        private final BufferedReader input;
        private JsonNode next;
        private boolean exhausted;

        private HttpSseStream(InputStream source) {
            this.input = new BufferedReader(new InputStreamReader(source, StandardCharsets.UTF_8));
        }

        @Override
        public boolean hasNext() {
            if (next != null) return true;
            if (exhausted) return false;
            next = readFrame();
            if (next == null) exhausted = true;
            return next != null;
        }

        @Override
        public JsonNode next() {
            if (!hasNext()) throw new NoSuchElementException();
            JsonNode result = next;
            next = null;
            return result;
        }

        @Override
        public void close() {
            try {
                input.close();
            } catch (IOException ignored) {
                // 关闭失败不改变已确定的观察结果。
            }
        }

        private JsonNode readFrame() {
            String id = null;
            String event = null;
            List<String> data = new ArrayList<>();
            boolean populated = false;
            try {
                String line;
                while ((line = input.readLine()) != null) {
                    if (line.isEmpty()) {
                        if (populated) return event(id, event, data);
                        continue;
                    }
                    if (line.startsWith(":")) continue;
                    int separator = line.indexOf(':');
                    String field = separator < 0 ? line : line.substring(0, separator);
                    String value = separator < 0 ? "" : line.substring(separator + 1);
                    if (value.startsWith(" ")) value = value.substring(1);
                    switch (field) {
                        case "id" -> {
                            id = value;
                            populated = true;
                        }
                        case "event" -> {
                            event = value;
                            populated = true;
                        }
                        case "data" -> {
                            data.add(value);
                            populated = true;
                        }
                        default -> {
                            // 忽略 SSE 扩展字段。
                        }
                    }
                }
                return populated ? event(id, event, data) : null;
            } catch (IOException exception) {
                throw new CoreSseConnectionException();
            }
        }

        private JsonNode event(String id, String event, List<String> dataLines) {
            ObjectNode result = json.createObjectNode();
            if (id == null) result.putNull("id");
            else result.put("id", id);
            result.put("event", event == null ? "message" : event);
            String raw = String.join("\n", dataLines);
            JsonNode data;
            try {
                data = json.readTree(raw);
                if (data == null) data = json.getNodeFactory().textNode(raw);
            } catch (RuntimeException exception) {
                data = json.getNodeFactory().textNode(raw);
            }
            result.set("data", data);
            return result;
        }
    }
}
