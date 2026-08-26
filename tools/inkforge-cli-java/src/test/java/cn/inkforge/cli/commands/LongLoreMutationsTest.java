package cn.inkforge.cli.commands;

import static org.assertj.core.api.Assertions.assertThat;

import cn.inkforge.cli.config.MemoryConfigStore;
import cn.inkforge.cli.config.MemoryCredentialStore;
import cn.inkforge.cli.config.ProfileConfig;
import cn.inkforge.cli.runtime.CliApplication;
import cn.inkforge.cli.runtime.CliDependencies;
import cn.inkforge.cli.transport.CoreApi;
import cn.inkforge.cli.transport.FileDescriptor;
import cn.inkforge.cli.transport.LoginResult;
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.json.JsonMapper;

class LongLoreMutationsTest {

    private final JsonMapper json = JsonMapper.builder().build();

    @Test
    void 五类设定实体的十五个命令共享确定性创建与CAS协议() {
        RecordingApi api = new RecordingApi(json);
        CliApplication application = application(api);
        Map<String, Entity> entities = new LinkedHashMap<>();
        entities.put("character", new Entity("characters", "characterId", "{\"name\":\"沈砚\",\"currentStatus\":\"active\"}", "{\"appearance\":null}"));
        entities.put("location", new Entity("locations", "locationId", "{\"name\":\"旧城\"}", "{\"description\":null}"));
        entities.put("faction", new Entity("factions", "factionId", "{\"name\":\"巡夜司\"}", "{\"type\":\"官署\"}"));
        entities.put("item", new Entity("items", "itemId", "{\"name\":\"铜铃\"}", "{\"ownerId\":null}"));
        entities.put("glossary", new Entity("glossary", "glossaryId", "{\"term\":\"夜巡\",\"definition\":\"制度\"}", "{\"category\":null}"));

        for (Map.Entry<String, Entity> entry : entities.entrySet()) {
            String name = entry.getKey();
            Entity entity = entry.getValue();
            assertRequest(
                    application,
                    api,
                    "long.lore." + name + ".create",
                    "{\"novelId\":\"n1\",\"clientRequestId\":\"entity-create-0001\",\"data\":" + entity.createData() + "}",
                    "POST",
                    "/api/v1/novels/n1/" + entity.segment(),
                    append(entity.createData(), "clientRequestId", "entity-create-0001"));
            assertRequest(
                    application,
                    api,
                    "long.lore." + name + ".update",
                    "{\"novelId\":\"n1\",\"" + entity.idField() + "\":\"id/1\",\"expectedUpdatedAt\":\"v1\",\"data\":" + entity.updateData() + "}",
                    "PATCH",
                    "/api/v1/novels/n1/" + entity.segment() + "/id%2F1",
                    append(entity.updateData(), "expectedUpdatedAt", "v1"));
            assertRequest(
                    application,
                    api,
                    "long.lore." + name + ".delete",
                    "{\"novelId\":\"n1\",\"" + entity.idField() + "\":\"id/1\",\"expectedUpdatedAt\":\"v2\"}",
                    "DELETE",
                    "/api/v1/novels/n1/" + entity.segment() + "/id%2F1",
                    "{\"expectedUpdatedAt\":\"v2\"}");
        }
    }

    @Test
    void 关系与经历六个命令保持类型范围和资源路径() {
        RecordingApi api = new RecordingApi(json);
        CliApplication application = application(api);
        assertRequest(application, api, "long.lore.relation.create",
                "{\"novelId\":\"n1\",\"clientRequestId\":\"relation-create-0001\",\"data\":{\"characterId\":\"c1\",\"targetId\":\"c2\",\"relationType\":\"friend\",\"intimacy\":80,\"description\":null}}",
                "POST", "/api/v1/novels/n1/relations",
                "{\"characterId\":\"c1\",\"targetId\":\"c2\",\"relationType\":\"friend\",\"intimacy\":80,\"description\":null,\"clientRequestId\":\"relation-create-0001\"}");
        assertRequest(application, api, "long.lore.relation.update",
                "{\"novelId\":\"n1\",\"relationId\":\"r1\",\"expectedUpdatedAt\":\"v1\",\"data\":{\"intimacy\":60}}",
                "PATCH", "/api/v1/novels/n1/relations/r1",
                "{\"intimacy\":60,\"expectedUpdatedAt\":\"v1\"}");
        assertRequest(application, api, "long.lore.relation.delete",
                "{\"novelId\":\"n1\",\"relationId\":\"r1\",\"expectedUpdatedAt\":\"v2\"}",
                "DELETE", "/api/v1/novels/n1/relations/r1",
                "{\"expectedUpdatedAt\":\"v2\"}");
        assertRequest(application, api, "long.lore.experience.create",
                "{\"novelId\":\"n1\",\"characterId\":\"c/1\",\"clientRequestId\":\"experience-create-01\",\"data\":{\"chapterId\":null,\"content\":\"\",\"order\":1}}",
                "POST", "/api/v1/novels/n1/characters/c%2F1/experiences",
                "{\"chapterId\":null,\"content\":\"\",\"order\":1,\"clientRequestId\":\"experience-create-01\"}");
        assertRequest(application, api, "long.lore.experience.update",
                "{\"novelId\":\"n1\",\"experienceId\":\"e1\",\"expectedUpdatedAt\":\"v1\",\"data\":{\"chapterId\":null}}",
                "PATCH", "/api/v1/novels/n1/experiences/e1",
                "{\"chapterId\":null,\"expectedUpdatedAt\":\"v1\"}");
        assertRequest(application, api, "long.lore.experience.delete",
                "{\"novelId\":\"n1\",\"experienceId\":\"e1\",\"expectedUpdatedAt\":\"v2\"}",
                "DELETE", "/api/v1/novels/n1/experiences/e1",
                "{\"expectedUpdatedAt\":\"v2\"}");
    }

    @Test
    void 参考资料四个命令保持完整文件与内容哈希门禁(@TempDir Path directory) throws Exception {
        RecordingApi api = new RecordingApi(json);
        CliApplication application = application(api);
        Path source = directory.resolve("资料.txt");
        Files.writeString(source, "正文\r\n尾部😀", StandardCharsets.UTF_8);
        assertRequest(application, api, "long.reference.create",
                "{\"novelId\":\"n1\",\"clientRequestId\":\"reference-create-01\",\"title\":\"资料\",\"type\":\"note\",\"contentFile\":" + json.writeValueAsString(source.toString()) + ",\"sourceUrl\":null}",
                "POST", "/api/v1/novels/n1/references",
                "{\"clientRequestId\":\"reference-create-01\",\"title\":\"资料\",\"type\":\"note\",\"content\":\"正文\\r\\n尾部😀\",\"sourceUrl\":null}");
        assertRequest(application, api, "long.reference.update",
                "{\"novelId\":\"n1\",\"referenceId\":\"ref/1\",\"expectedUpdatedAt\":\"v1\",\"title\":\"新标题\",\"sourceUrl\":null}",
                "PATCH", "/api/v1/novels/n1/references/ref%2F1",
                "{\"title\":\"新标题\",\"sourceUrl\":null,\"expectedUpdatedAt\":\"v1\"}");
        assertRequest(application, api, "long.reference.delete",
                "{\"novelId\":\"n1\",\"referenceId\":\"ref1\",\"expectedUpdatedAt\":\"v2\"}",
                "DELETE", "/api/v1/novels/n1/references/ref1",
                "{\"expectedUpdatedAt\":\"v2\"}");
        assertRequest(application, api, "long.reference.reindex",
                "{\"novelId\":\"n1\",\"referenceId\":\"ref1\",\"expectedContentHash\":\"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\"}",
                "POST", "/api/v1/novels/n1/references/ref1/reindex",
                "{\"expectedContentHash\":\"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\"}");
    }

    @Test
    void 设定关系与资料非法输入都在网络前拒绝() {
        RecordingApi api = new RecordingApi(json);
        CliApplication application = application(api);
        for (Case invalid : List.of(
                new Case("long.lore.character.create", "{\"novelId\":\"n1\",\"clientRequestId\":\"character-create-01\",\"data\":{\"name\":\"沈砚\",\"currentStatus\":\"gone\"}}"),
                new Case("long.lore.relation.create", "{\"novelId\":\"n1\",\"clientRequestId\":\"relation-create-0001\",\"data\":{\"characterId\":\"c1\",\"targetId\":\"c2\",\"relationType\":\"friend\",\"intimacy\":true}}"),
                new Case("long.reference.create", "{\"novelId\":\"n1\",\"clientRequestId\":\"reference-create-01\",\"title\":\"资料\",\"type\":\"note\"}"))) {
            int before = api.calls;
            assertThat(run(application, invalid.command(), invalid.payload()).exit()).isEqualTo(2);
            assertThat(api.calls).isEqualTo(before);
        }
    }

    private static String append(String object, String key, String value) {
        return object.substring(0, object.length() - 1)
                + ",\"" + key + "\":\"" + value + "\"}";
    }

    private void assertRequest(CliApplication app, RecordingApi api, String command, String input, String method, String path, String body) {
        Result result = run(app, command, input);
        assertThat(result.exit()).as(command + " " + result.stdout()).isZero();
        assertThat(api.method).isEqualTo(method);
        assertThat(api.path).isEqualTo(path);
        assertThat(api.body.toString()).isEqualTo(body);
    }

    private CliApplication application(RecordingApi api) {
        MemoryConfigStore configs = new MemoryConfigStore();
        MemoryCredentialStore credentials = new MemoryCredentialStore();
        configs.save("default", new ProfileConfig("http://127.0.0.1:8000", "nie"));
        credentials.set("default", "http://127.0.0.1:8000", "token");
        return CliApplication.createDefault(new CliDependencies(
                (origin, token) -> api, configs, credentials, prompt -> new char[0], () -> false, json));
    }

    private Result run(CliApplication app, String command, String input) {
        ByteArrayOutputStream out = new ByteArrayOutputStream();
        int exit = app.run(List.of(command), new ByteArrayInputStream(input.getBytes(StandardCharsets.UTF_8)), out, new ByteArrayOutputStream());
        return new Result(exit, out.toString(StandardCharsets.UTF_8));
    }

    private record Entity(String segment, String idField, String createData, String updateData) {}
    private record Case(String command, String payload) {}
    private record Result(int exit, String stdout) {}

    private static final class RecordingApi implements CoreApi {
        private final JsonMapper json;
        private String method;
        private String path;
        private JsonNode body;
        private int calls;
        private RecordingApi(JsonMapper json) { this.json = json; }
        @Override public JsonNode request(String method, String path) { return request(method, path, null); }
        @Override public JsonNode request(String method, String path, JsonNode body) {
            this.method = method; this.path = path; this.body = body; calls++;
            return json.createObjectNode().put("id", "ok");
        }
        @Override public LoginResult login(String username, String password) { throw new UnsupportedOperationException(); }
        @Override public FileDescriptor download(String method, String path, Path target) { throw new UnsupportedOperationException(); }
    }
}
