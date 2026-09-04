package cn.inkforge.cli.operator;

import cn.inkforge.cli.runtime.CliInputException;
import java.io.IOException;
import java.nio.channels.FileChannel;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.nio.file.StandardOpenOption;
import java.nio.file.attribute.PosixFilePermissions;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.TimeUnit;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;
import tools.jackson.databind.node.ObjectNode;

/** 只安装本机运行包和非秘密配置；从不访问或迁移会话凭据。 */
final class OperatorInstallation {
    private static final Set<String> FIELDS = Set.of(
            "schemaVersion", "repositoryRoot", "repositoryRevision", "repositoryDirty",
            "jarSha256", "javaPath", "origin", "profile", "expectedUsername");
    private final Path stateRoot;
    private final ObjectMapper json;

    OperatorInstallation(Path stateRoot, ObjectMapper json) {
        this.stateRoot = stateRoot.toAbsolutePath().normalize();
        this.json = json;
    }

    static Path defaultState(String mode, String userHome) {
        return Path.of(userHome, "Library", "Application Support", "InkForge",
                mode.equals("local") ? "codex-operator" : "production-codex-operator");
    }

    static String origin(String mode) {
        if (mode.equals("local")) return "http://127.0.0.1:8000";
        if (mode.equals("production")) return "https://inkforge.cn";
        throw failure("OPERATOR_MODE_INVALID", "操作员模式只能为 local 或 production");
    }

    static String profile(String mode) {
        origin(mode);
        return mode.equals("local") ? "default" : "production";
    }

    Config install(String mode, Path repository, Path sourceJar, Path javaExecutable,
            String expectedUsername) throws IOException {
        String origin = origin(mode);
        String profile = profile(mode);
        rejectLinks(stateRoot);
        Path configPath = stateRoot.resolve("config.json");
        rejectLinks(configPath);
        String previousUsername = null;
        if (Files.exists(configPath)) {
            JsonNode previous = json.readTree(Files.readAllBytes(configPath));
            if (previous == null || !previous.isObject()
                    || !previous.path("schemaVersion").isIntegralNumber()
                    || !Set.of(4, 5).contains(previous.path("schemaVersion").intValue())
                    || !origin.equals(previous.path("origin").asText())
                    || !profile.equals(previous.path("profile").asText())) {
                throw failure("OPERATOR_CONFIG_INVALID", "现有操作员配置与当前环境不匹配");
            }
            previousUsername = username(previous.get("expectedUsername"));
        }
        if (expectedUsername != null && expectedUsername.isBlank()) {
            throw failure("OPERATOR_CONFIG_INVALID", "expectedUsername 不能为空白");
        }
        String requested = expectedUsername == null ? previousUsername : expectedUsername.strip();
        // 日常命令不能换账号；显式重新 configure 仍保留旧入口的账号切换能力。
        Path root = repository.toRealPath();
        if (!Files.isRegularFile(root.resolve("tools/inkforge-cli-java/pom.xml"))) {
            throw failure("OPERATOR_REPOSITORY_INVALID", "来源仓库缺少 Java CLI 模块");
        }
        String revision = git(root, "rev-parse", "HEAD").strip();
        if (!revision.matches("[0-9a-f]{40}")) {
            throw failure("OPERATOR_REPOSITORY_INVALID", "来源仓库 revision 无效");
        }
        boolean dirty = !git(root, "status", "--porcelain").isBlank();
        Path java = javaExecutable.toRealPath();
        if (!Files.isRegularFile(java) || !Files.isExecutable(java)) {
            throw failure("OPERATOR_JAVA_INVALID", "Java 运行路径不可执行");
        }
        if (!Files.isRegularFile(sourceJar)) {
            throw failure("OPERATOR_JAR_INVALID", "配置必须从已构建的 Java CLI JAR 运行");
        }
        privateDirectory(stateRoot);
        Path runtime = stateRoot.resolve("runtime");
        privateDirectory(runtime);
        Path installedJar = runtime.resolve("inkforge-cli.jar");
        rejectLinks(installedJar);
        Path temporaryJar = Files.createTempFile(runtime, ".install-", ".jar");
        Path temporaryJava = runtime.resolve(".java-" + UUID.randomUUID());
        try {
            Files.copy(sourceJar, temporaryJar, StandardCopyOption.REPLACE_EXISTING);
            privateFile(temporaryJar);
            try (FileChannel channel = FileChannel.open(temporaryJar, StandardOpenOption.WRITE)) {
                channel.force(true);
            }
            String hash = sha256(temporaryJar);
            Files.createSymbolicLink(temporaryJava, java);
            Path javaLink = runtime.resolve("java");
            if (Files.exists(javaLink, LinkOption.NOFOLLOW_LINKS) && !Files.isSymbolicLink(javaLink)) {
                throw failure("OPERATOR_RUNTIME_INVALID", "运行目录 java 必须是受控符号链接");
            }
            // 配置最后提交；中途故障会因哈希不符而关闭，绝不执行来源不明的包。
            replace(temporaryJar, installedJar);
            replace(temporaryJava, javaLink);
            Config config = new Config(stateRoot, root, revision, dirty, hash, java,
                    origin, profile, requested);
            write(config);
            return config;
        } finally {
            Files.deleteIfExists(temporaryJar);
            Files.deleteIfExists(temporaryJava);
        }
    }

    Config load(String mode, Path runningJar, Path runningJava) throws IOException {
        rejectLinks(stateRoot.resolve("config.json"));
        checkPrivate(stateRoot, true);
        checkPrivate(stateRoot.resolve("runtime"), true);
        Path configPath = stateRoot.resolve("config.json");
        checkPrivate(configPath, false);
        JsonNode raw = json.readTree(Files.readAllBytes(configPath));
        if (raw == null || !raw.isObject() || !raw.propertyNames().equals(FIELDS)
                || !raw.path("schemaVersion").isIntegralNumber()
                || raw.path("schemaVersion").intValue() != 5
                || !raw.path("repositoryDirty").isBoolean()) {
            throw failure("OPERATOR_CONFIG_INVALID", "操作员配置需重新运行 configure");
        }
        String configuredOrigin = text(raw, "origin");
        String configuredProfile = text(raw, "profile");
        if (!origin(mode).equals(configuredOrigin) || !profile(mode).equals(configuredProfile)) {
            throw failure("ORIGIN_MISMATCH", "操作员配置的 origin/profile 与当前 Skill 不匹配");
        }
        String revision = text(raw, "repositoryRevision");
        String hash = text(raw, "jarSha256");
        Path repository = Path.of(text(raw, "repositoryRoot"));
        Path java = Path.of(text(raw, "javaPath"));
        if (!revision.matches("[0-9a-f]{40}") || !hash.matches("[0-9a-f]{64}")
                || !repository.isAbsolute() || !java.isAbsolute()) {
            throw failure("OPERATOR_CONFIG_INVALID", "操作员配置的来源或运行包身份无效");
        }
        Path installedJar = stateRoot.resolve("runtime/inkforge-cli.jar");
        rejectLinks(installedJar);
        checkPrivate(installedJar, false);
        Path link = stateRoot.resolve("runtime/java");
        if (!Files.isSymbolicLink(link) || !link.toRealPath().equals(java.toRealPath())
                || !runningJava.toRealPath().equals(java.toRealPath())
                || !installedJar.toRealPath().equals(runningJar.toRealPath())
                || !sha256(installedJar).equals(hash)) {
            throw failure("OPERATOR_RUNTIME_INVALID", "操作员运行包或 Java 路径发生变化，请重新配置");
        }
        return new Config(stateRoot, repository, revision, raw.path("repositoryDirty").booleanValue(),
                hash, java, configuredOrigin, configuredProfile, username(raw.get("expectedUsername")));
    }

    void bindUsername(Config config, String username) throws IOException {
        write(new Config(stateRoot, config.repositoryRoot(), config.repositoryRevision(),
                config.repositoryDirty(), config.jarSha256(), config.javaPath(),
                config.origin(), config.profile(), username));
    }

    private void write(Config config) throws IOException {
        ObjectNode raw = json.createObjectNode();
        raw.put("schemaVersion", 5);
        raw.put("repositoryRoot", config.repositoryRoot().toString());
        raw.put("repositoryRevision", config.repositoryRevision());
        raw.put("repositoryDirty", config.repositoryDirty());
        raw.put("jarSha256", config.jarSha256());
        raw.put("javaPath", config.javaPath().toString());
        raw.put("origin", config.origin());
        raw.put("profile", config.profile());
        if (config.expectedUsername() == null) raw.putNull("expectedUsername");
        else raw.put("expectedUsername", config.expectedUsername());
        Path target = stateRoot.resolve("config.json");
        rejectLinks(target);
        Path temporary = Files.createTempFile(stateRoot, ".config-", ".json");
        try {
            privateFile(temporary);
            Files.writeString(temporary, json.writerWithDefaultPrettyPrinter().writeValueAsString(raw) + "\n");
            try (FileChannel channel = FileChannel.open(temporary, StandardOpenOption.WRITE)) {
                channel.force(true);
            }
            replace(temporary, target);
        } finally {
            Files.deleteIfExists(temporary);
        }
    }

    private static String username(JsonNode node) {
        if (node == null || node.isNull()) return null;
        if (!node.isTextual() || node.textValue().isBlank()) {
            throw failure("OPERATOR_CONFIG_INVALID", "操作员配置的预期用户名无效");
        }
        return node.textValue().strip();
    }

    private static String text(JsonNode node, String field) {
        JsonNode value = node.get(field);
        if (value == null || !value.isTextual() || value.textValue().isBlank()) {
            throw failure("OPERATOR_CONFIG_INVALID", "操作员配置缺少有效字段：" + field);
        }
        return value.textValue();
    }

    private static String git(Path root, String... arguments) throws IOException {
        java.util.List<String> command = new java.util.ArrayList<>(java.util.List.of("git", "-C", root.toString()));
        command.addAll(java.util.List.of(arguments));
        Process process = new ProcessBuilder(command).redirectError(ProcessBuilder.Redirect.DISCARD).start();
        process.getOutputStream().close();
        byte[] output = process.getInputStream().readAllBytes();
        try {
            if (!process.waitFor(30, TimeUnit.SECONDS) || process.exitValue() != 0) {
                process.destroyForcibly();
                throw failure("OPERATOR_REPOSITORY_INVALID", "无法读取来源仓库 revision 或工作区状态");
            }
        } catch (InterruptedException exception) {
            process.destroyForcibly();
            Thread.currentThread().interrupt();
            throw new IOException("读取来源仓库被中断", exception);
        }
        return new String(output, java.nio.charset.StandardCharsets.UTF_8);
    }

    static String sha256(Path path) throws IOException {
        try (var input = Files.newInputStream(path)) {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            byte[] buffer = new byte[65536];
            int count;
            while ((count = input.read(buffer)) != -1) digest.update(buffer, 0, count);
            return HexFormat.of().formatHex(digest.digest());
        } catch (NoSuchAlgorithmException exception) {
            throw new IllegalStateException(exception);
        }
    }

    private static void privateDirectory(Path path) throws IOException {
        rejectLinks(path);
        if (!Files.exists(path)) {
            Path parent = path.getParent();
            if (parent != null && !Files.exists(parent)) privateDirectory(parent);
            Files.createDirectory(path, PosixFilePermissions.asFileAttribute(PosixFilePermissions.fromString("rwx------")));
        }
        if (!Files.isDirectory(path)) throw failure("OPERATOR_RUNTIME_INVALID", "安装目录不是目录");
        Files.setPosixFilePermissions(path, PosixFilePermissions.fromString("rwx------"));
    }

    private static void privateFile(Path path) throws IOException {
        Files.setPosixFilePermissions(path, PosixFilePermissions.fromString("rw-------"));
    }

    private static void checkPrivate(Path path, boolean directory) throws IOException {
        rejectLinks(path);
        if (!(directory ? Files.isDirectory(path) : Files.isRegularFile(path))
                || !Files.getOwner(path).equals(Files.getOwner(Path.of(System.getProperty("user.home"))))
                || !Files.getPosixFilePermissions(path).equals(PosixFilePermissions.fromString(
                        directory ? "rwx------" : "rw-------"))) {
            throw failure("OPERATOR_RUNTIME_INVALID", "操作员运行包或配置权限不安全");
        }
    }

    private static void rejectLinks(Path path) throws IOException {
        Path current = path.toAbsolutePath().normalize();
        while (current != null) {
            if (Files.isSymbolicLink(current)) {
                throw failure("OPERATOR_RUNTIME_INVALID", "操作员状态路径不能包含符号链接");
            }
            current = current.getParent();
        }
    }

    private static void replace(Path from, Path to) throws IOException {
        Files.move(from, to, StandardCopyOption.ATOMIC_MOVE, StandardCopyOption.REPLACE_EXISTING);
    }

    private static CliInputException failure(String code, String message) {
        return new CliInputException(code, message, 3);
    }

    record Config(Path stateRoot, Path repositoryRoot, String repositoryRevision,
            boolean repositoryDirty, String jarSha256, Path javaPath, String origin,
            String profile, String expectedUsername) {}
}
