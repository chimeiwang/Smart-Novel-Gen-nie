package cn.inkforge.core.compatibility;

import static org.assertj.core.api.Assertions.assertThat;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.ResultSet;
import java.sql.ResultSetMetaData;
import java.sql.Statement;
import java.time.Duration;
import java.util.HexFormat;
import java.util.LinkedHashMap;
import java.util.Locale;
import java.util.Map;
import java.util.TreeMap;
import org.testcontainers.postgresql.PostgreSQLContainer;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;
import tools.jackson.databind.node.ArrayNode;
import tools.jackson.databind.node.ObjectNode;

/** 执行语言中立业务 fixture，只归一化其中明确声明的动态值。 */
final class CoreBehaviorScenarioRunner {

    private final ObjectMapper json;
    private final HttpClient http = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(3))
            .version(HttpClient.Version.HTTP_1_1)
            .build();

    CoreBehaviorScenarioRunner(ObjectMapper json) {
        this.json = json;
    }

    ObjectNode run(
            String implementation,
            URI origin,
            PostgreSQLContainer database,
            ObjectNode fixture)
            throws Exception {
        Map<String, String> variables = new LinkedHashMap<>();
        String cookie = null;
        ArrayNode responses = json.createArrayNode();
        for (JsonNode value : fixture.withArray("steps")) {
            ObjectNode step = (ObjectNode) value;
            String name = step.path("name").textValue();
            String method = step.path("method").textValue();
            String path = substitute(step.path("path").textValue(), variables);
            JsonNode body = step.has("body")
                    ? substitute(step.get("body"), variables)
                    : null;
            HttpResponse<String> response = send(origin.resolve(path), method, body, cookie);
            assertThat(response.statusCode())
                    .as(implementation + " / " + name + " / " + response.body())
                    .isEqualTo(step.path("expectedStatus").intValue());

            String issuedCookie = response.headers()
                    .firstValue("set-cookie")
                    .map(header -> header.split(";", 2)[0])
                    .orElse(null);
            if (issuedCookie != null) cookie = issuedCookie;
            if (step.path("expectCookie").asBoolean(false)) {
                assertThat(issuedCookie).as(implementation + " / " + name).isNotBlank();
            }

            JsonNode responseBody = response.body().isBlank()
                    ? json.nullNode()
                    : json.readTree(response.body());
            capture(step.path("capture"), responseBody, variables, implementation, name);
            JsonNode normalized = normalize(
                    responseBody,
                    variables,
                    step.path("capture"),
                    step.path("normalizePointers"),
                    step.path("derivedNormalizations"));
            ObjectNode recorded = responses.addObject();
            recorded.put("name", name);
            recorded.put("status", response.statusCode());
            recorded.set("body", normalized);
            recorded.put("cookieIssued", issuedCookie != null);
        }

        ObjectNode result = json.createObjectNode();
        result.set("responses", responses);
        result.set("snapshots", snapshots(database, fixture.withArray("snapshotQueries")));
        return result;
    }

    private HttpResponse<String> send(
            URI uri, String method, JsonNode body, String cookie) throws Exception {
        HttpRequest.Builder request = HttpRequest.newBuilder(uri)
                .timeout(Duration.ofSeconds(15));
        if (cookie != null) request.header("Cookie", cookie);
        if (body == null) {
            request.method(method, HttpRequest.BodyPublishers.noBody());
        } else {
            request.header("Content-Type", "application/json")
                    .method(
                            method,
                            HttpRequest.BodyPublishers.ofString(
                                    json.writeValueAsString(body),
                                    StandardCharsets.UTF_8));
        }
        return http.send(request.build(), HttpResponse.BodyHandlers.ofString());
    }

    private void capture(
            JsonNode definitions,
            JsonNode response,
            Map<String, String> variables,
            String implementation,
            String stepName) {
        if (!definitions.isObject()) return;
        definitions.properties().forEach(entry -> {
            JsonNode value = response.at(entry.getValue().textValue());
            assertThat(value.isMissingNode() || value.isNull())
                    .as(implementation + " / " + stepName + " / capture " + entry.getKey())
                    .isFalse();
            assertThat(value.isValueNode())
                    .as(implementation + " / " + stepName + " / capture " + entry.getKey())
                    .isTrue();
            variables.put(
                    entry.getKey(),
                    value.isTextual() ? value.textValue() : value.toString());
        });
    }

    private JsonNode normalize(
            JsonNode source,
            Map<String, String> variables,
            JsonNode capturePointers,
            JsonNode normalizePointers,
            JsonNode derivedNormalizations) {
        JsonNode validated = source.deepCopy();
        normalizeDerivedValues(validated, variables, derivedNormalizations);
        JsonNode result = replaceCapturedValues(validated, variables);
        if (capturePointers.isObject()) {
            capturePointers.properties().forEach(entry -> replacePointer(
                    result,
                    entry.getValue().textValue(),
                    json.getNodeFactory().textNode("${" + entry.getKey() + "}")));
        }
        if (normalizePointers.isArray()) {
            normalizePointers.forEach(pointer -> {
                JsonNode current = result.at(pointer.textValue());
                assertThat(current.isTextual())
                        .as("归一化时间字段不是字符串：" + pointer.textValue())
                        .isTrue();
                replacePointer(
                        result,
                        pointer.textValue(),
                        json.getNodeFactory().textNode("<volatile>"));
            });
        }
        return result;
    }

    private void normalizeDerivedValues(
            JsonNode root,
            Map<String, String> variables,
            JsonNode definitions) {
        if (!definitions.isArray()) return;
        for (JsonNode definition : definitions) {
            String algorithm = definition.path("algorithm").textValue();
            assertThat(algorithm).isEqualTo("shortMediumConfirmationHash");
            validateShortMediumConfirmationHash(root, variables, definition);
        }
    }

    private void validateShortMediumConfirmationHash(
            JsonNode root,
            Map<String, String> variables,
            JsonNode definition) {
        String pointer = definition.path("pointer").textValue();
        JsonNode actual = requireDerivedValue(root, pointer);
        assertThat(actual.isTextual()).as("派生确认哈希不是字符串：" + pointer).isTrue();
        assertThat(actual.textValue()).matches("[0-9a-f]{64}");

        JsonNode diffSource = requireDerivedValue(
                root, definition.path("diffPointer").textValue());
        assertThat(diffSource.isObject()).as("派生确认哈希的 Diff 不是对象").isTrue();
        ObjectNode diff = ((ObjectNode) diffSource).deepCopy();
        assertThat(diff.remove("confirmationHash"))
                .as("派生确认哈希的 Diff 缺少 confirmationHash")
                .isNotNull();

        ObjectNode canonical = json.createObjectNode();
        canonical.set("documentType", requireDerivedValue(
                root, definition.path("documentTypePointer").textValue()).deepCopy());
        canonical.set("chapterId", requireDerivedValue(
                root, definition.path("chapterIdPointer").textValue()).deepCopy());
        canonical.set("baseVersionId", requireDerivedValue(
                root, definition.path("baseVersionIdPointer").textValue()).deepCopy());
        canonical.put(
                "currentDraftHash",
                substitute(definition.path("currentDraftHash").textValue(), variables));
        canonical.set("targetVersionId", requireDerivedValue(
                root, definition.path("targetVersionIdPointer").textValue()).deepCopy());
        canonical.set("diff", diff);

        String expected = sha256(json.writeValueAsString(canonicalize(canonical)));
        assertThat(actual.textValue())
                .as("中短篇 confirmationHash 没有绑定完整动态上下文")
                .isEqualTo(expected);
        replacePointer(
                root,
                pointer,
                json.getNodeFactory().textNode("<derived:shortMediumConfirmationHash>"));
    }

    private JsonNode requireDerivedValue(JsonNode root, String pointer) {
        JsonNode value = root.at(pointer);
        assertThat(value.isMissingNode()).as("派生值路径不存在：" + pointer).isFalse();
        return value;
    }

    private JsonNode canonicalize(JsonNode source) {
        if (source.isArray()) {
            ArrayNode result = json.createArrayNode();
            source.forEach(value -> result.add(canonicalize(value)));
            return result;
        }
        if (source.isObject()) {
            ObjectNode result = json.createObjectNode();
            TreeMap<String, JsonNode> sorted = new TreeMap<>();
            source.properties().forEach(entry -> sorted.put(entry.getKey(), entry.getValue()));
            sorted.forEach((name, value) -> result.set(name, canonicalize(value)));
            return result;
        }
        return source.deepCopy();
    }

    private static String sha256(String value) {
        try {
            byte[] digest = MessageDigest.getInstance("SHA-256")
                    .digest(value.getBytes(StandardCharsets.UTF_8));
            return HexFormat.of().formatHex(digest);
        } catch (NoSuchAlgorithmException exception) {
            throw new IllegalStateException("当前 JRE 缺少 SHA-256", exception);
        }
    }

    private JsonNode replaceCapturedValues(
            JsonNode source, Map<String, String> variables) {
        if (source.isTextual()) {
            String normalized = source.textValue();
            for (Map.Entry<String, String> variable : variables.entrySet()) {
                normalized = normalized.replace(
                        variable.getValue(), "${" + variable.getKey() + "}");
            }
            return json.getNodeFactory().textNode(normalized);
        }
        if (source.isArray()) {
            ArrayNode result = json.createArrayNode();
            source.forEach(value -> result.add(replaceCapturedValues(value, variables)));
            return result;
        }
        if (source.isObject()) {
            ObjectNode result = json.createObjectNode();
            source.properties().forEach(entry -> result.set(
                    entry.getKey(), replaceCapturedValues(entry.getValue(), variables)));
            return result;
        }
        return source.deepCopy();
    }

    private void replacePointer(JsonNode root, String pointer, JsonNode replacement) {
        int separator = pointer.lastIndexOf('/');
        if (separator < 0) throw new IllegalArgumentException("JSON Pointer 格式无效：" + pointer);
        String parentPointer = separator == 0 ? "" : pointer.substring(0, separator);
        String field = pointer.substring(separator + 1)
                .replace("~1", "/")
                .replace("~0", "~");
        JsonNode parent = root.at(parentPointer);
        assertThat(parent.isObject()).as("归一化路径不存在：" + pointer).isTrue();
        assertThat(parent.has(field)).as("归一化字段不存在：" + pointer).isTrue();
        ((ObjectNode) parent).set(field, replacement.deepCopy());
    }

    private JsonNode substitute(JsonNode source, Map<String, String> variables) {
        if (source.isTextual()) {
            return json.getNodeFactory().textNode(substitute(source.textValue(), variables));
        }
        if (source.isArray()) {
            ArrayNode result = json.createArrayNode();
            source.forEach(value -> result.add(substitute(value, variables)));
            return result;
        }
        if (source.isObject()) {
            ObjectNode result = json.createObjectNode();
            source.properties().forEach(entry ->
                    result.set(entry.getKey(), substitute(entry.getValue(), variables)));
            return result;
        }
        return source.deepCopy();
    }

    private String substitute(String source, Map<String, String> variables) {
        String result = source;
        for (Map.Entry<String, String> variable : variables.entrySet()) {
            result = result.replace("${" + variable.getKey() + "}", variable.getValue());
        }
        assertThat(result).as("fixture 存在未解析变量").doesNotContain("${");
        return result;
    }

    private ArrayNode snapshots(PostgreSQLContainer database, ArrayNode definitions)
            throws Exception {
        ArrayNode snapshots = json.createArrayNode();
        try (Connection connection = DriverManager.getConnection(
                database.getJdbcUrl(), database.getUsername(), database.getPassword())) {
            for (JsonNode definition : definitions) {
                String name = definition.path("name").textValue();
                String sql = definition.path("sql").textValue().stripLeading();
                assertThat(sql.toUpperCase(Locale.ROOT)).startsWith("SELECT ");
                ArrayNode rows = snapshots.addObject().put("name", name).putArray("rows");
                try (Statement statement = connection.createStatement();
                        ResultSet result = statement.executeQuery(sql)) {
                    ResultSetMetaData metadata = result.getMetaData();
                    while (result.next()) {
                        ObjectNode row = rows.addObject();
                        for (int column = 1; column <= metadata.getColumnCount(); column++) {
                            putDatabaseValue(
                                    row,
                                    metadata.getColumnLabel(column),
                                    result.getObject(column));
                        }
                    }
                }
                assertThat(rows.size())
                        .as(name)
                        .isEqualTo(definition.path("expectedRows").intValue());
            }
        }
        return snapshots;
    }

    private void putDatabaseValue(ObjectNode row, String name, Object value) {
        if (value == null) row.putNull(name);
        else if (value instanceof Integer item) row.put(name, item);
        else if (value instanceof Long item) row.put(name, item);
        else if (value instanceof Boolean item) row.put(name, item);
        else row.put(name, value.toString());
    }
}
