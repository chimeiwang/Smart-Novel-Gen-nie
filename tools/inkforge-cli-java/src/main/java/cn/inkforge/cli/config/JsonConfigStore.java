package cn.inkforge.cli.config;

import cn.inkforge.cli.runtime.StableJson;
import cn.inkforge.cli.transport.AtomicFiles;
import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;
import tools.jackson.databind.node.ObjectNode;

/** 只原子保存 origin 与用户名；会话由操作系统安全凭据后端独占。 */
public final class JsonConfigStore implements ConfigStore {

    private final Path path;
    private final ObjectMapper json;

    public JsonConfigStore(Path path, ObjectMapper json) {
        this.path = Objects.requireNonNull(path).toAbsolutePath().normalize();
        this.json = Objects.requireNonNull(json);
    }

    public static Path defaultPath(Map<String, String> environment, String userHome) {
        String localAppData = environment.get("LOCALAPPDATA");
        if (localAppData != null && !localAppData.isBlank()) {
            return Path.of(localAppData, "InkForge", "cli", "config.json");
        }
        return Path.of(userHome, ".config", "inkforge", "cli", "config.json");
    }

    @Override
    public Optional<ProfileConfig> get(String profile) {
        requireProfile(profile);
        JsonNode value = read().get("profiles").get(profile);
        if (value == null || !value.isObject()) return Optional.empty();
        JsonNode origin = value.get("origin");
        JsonNode username = value.get("username");
        if (origin == null
                || !origin.isTextual()
                || username == null
                || !username.isTextual()) {
            return Optional.empty();
        }
        try {
            return Optional.of(new ProfileConfig(origin.textValue(), username.textValue()));
        } catch (IllegalArgumentException exception) {
            return Optional.empty();
        }
    }

    @Override
    public void save(String profile, ProfileConfig config) {
        requireProfile(profile);
        ObjectNode root = read();
        ObjectNode profiles = object(root, "profiles");
        ObjectNode value = json.createObjectNode();
        value.put("origin", config.origin());
        value.put("username", config.username());
        profiles.set(profile, value);
        write(root);
    }

    @Override
    public void delete(String profile) {
        requireProfile(profile);
        ObjectNode root = read();
        ObjectNode profiles = object(root, "profiles");
        if (profiles.remove(profile) != null) write(root);
    }

    private ObjectNode read() {
        if (!Files.exists(path)) return empty();
        try {
            JsonNode parsed = json.readTree(Files.readAllBytes(path));
            if (parsed == null || !parsed.isObject()) return empty();
            ObjectNode root = (ObjectNode) parsed;
            if (!root.has("profiles") || !root.get("profiles").isObject()) {
                root.set("profiles", json.createObjectNode());
            }
            root.put("schemaVersion", 1);
            return root;
        } catch (IOException exception) {
            throw new IllegalStateException("CLI 配置读取失败", exception);
        }
    }

    private ObjectNode empty() {
        ObjectNode root = json.createObjectNode();
        root.put("schemaVersion", 1);
        root.set("profiles", json.createObjectNode());
        return root;
    }

    private ObjectNode object(ObjectNode root, String field) {
        JsonNode value = root.get(field);
        if (value instanceof ObjectNode object) return object;
        ObjectNode replacement = json.createObjectNode();
        root.set(field, replacement);
        return replacement;
    }

    private void write(ObjectNode root) {
        ObjectNode normalized = json.createObjectNode();
        normalized.put("schemaVersion", 1);
        normalized.set("profiles", object(root, "profiles"));
        byte[] payload = StableJson.pretty(json, normalized)
                .getBytes(java.nio.charset.StandardCharsets.UTF_8);
        try {
            AtomicFiles.write(
                    path,
                    new ByteArrayInputStream(payload),
                    "application/json; charset=utf-8");
        } catch (IOException exception) {
            throw new IllegalStateException("CLI 配置写入失败", exception);
        }
    }

    private static void requireProfile(String profile) {
        if (profile == null || profile.isEmpty()) {
            throw new IllegalArgumentException("profile 必须是非空字符串");
        }
    }
}
