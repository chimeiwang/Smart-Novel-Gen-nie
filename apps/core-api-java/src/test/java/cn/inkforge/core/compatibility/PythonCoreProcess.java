package cn.inkforge.core.compatibility;

import java.io.IOException;
import java.net.ServerSocket;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.Comparator;
import java.util.Map;
import java.util.concurrent.TimeUnit;
import org.testcontainers.containers.GenericContainer;
import org.testcontainers.postgresql.PostgreSQLContainer;

/** 管理差分测试专用 Python Core 子进程及其受控临时目录。 */
final class PythonCoreProcess implements AutoCloseable {

    private final Process process;
    private final Path runtimeDirectory;
    private final Path log;
    private final int port;
    private final String testPassword;
    private final String jwtSecret;

    private PythonCoreProcess(
            Process process,
            Path runtimeDirectory,
            Path log,
            int port,
            String testPassword,
            String jwtSecret) {
        this.process = process;
        this.runtimeDirectory = runtimeDirectory;
        this.log = log;
        this.port = port;
        this.testPassword = testPassword;
        this.jwtSecret = jwtSecret;
    }

    static PythonCoreProcess start(
            PostgreSQLContainer database,
            GenericContainer<?> redis,
            String jwtSecret,
            String testPassword)
            throws Exception {
        Path root = repositoryRoot();
        Path python = root.resolve(".venv/bin/python");
        if (!Files.isExecutable(python)) {
            throw new IllegalStateException("业务差分测试缺少 .venv/bin/python");
        }
        Path runtimeDirectory = Files.createTempDirectory("inkforge-python-core-parity-")
                .toRealPath();
        int port = availablePort();
        Path log = runtimeDirectory.resolve("python-core.log");
        ProcessBuilder builder = new ProcessBuilder(
                        python.toString(),
                        "-m",
                        "uvicorn",
                        "inkforge_core.app:create_app",
                        "--factory",
                        "--host",
                        "127.0.0.1",
                        "--port",
                        Integer.toString(port),
                        "--log-level",
                        "warning")
                .directory(root.toFile())
                .redirectErrorStream(true)
                .redirectOutput(log.toFile());
        Map<String, String> environment = builder.environment();
        environment.put("ENVIRONMENT", "test");
        environment.put("DATABASE_URL", databaseUrl(database));
        environment.put("REDIS_URL", redisUrl(redis));
        environment.put("JWT_SECRET", jwtSecret);
        environment.put("UPLOADS_ROOT", runtimeDirectory.resolve("uploads").toString());
        environment.put("VIDEO_PREVIEW_ENABLED", "true");
        environment.put("VIDEO_DISPATCH_ENABLED", "false");
        environment.put("VIDEO_DISPATCH_NAMESPACE", "parity");
        environment.put("RAG_INDEX_ENABLED", "false");
        environment.put("PYTHONUNBUFFERED", "1");
        PythonCoreProcess runtime = new PythonCoreProcess(
                builder.start(), runtimeDirectory, log, port, testPassword, jwtSecret);
        try {
            runtime.waitUntilReady();
            return runtime;
        } catch (Exception exception) {
            runtime.close();
            throw exception;
        }
    }

    URI origin() {
        return URI.create("http://127.0.0.1:" + port);
    }

    private void waitUntilReady() throws Exception {
        HttpClient client = HttpClient.newBuilder()
                .connectTimeout(Duration.ofMillis(500))
                .version(HttpClient.Version.HTTP_1_1)
                .build();
        URI health = origin().resolve("/api/v1/health/live");
        long deadline = System.nanoTime() + Duration.ofSeconds(30).toNanos();
        while (System.nanoTime() < deadline) {
            if (!process.isAlive()) {
                throw new IllegalStateException("Python Core 提前退出：" + sanitizedLogTail());
            }
            try {
                HttpResponse<Void> response = client.send(
                        HttpRequest.newBuilder(health)
                                .timeout(Duration.ofSeconds(1))
                                .GET()
                                .build(),
                        HttpResponse.BodyHandlers.discarding());
                if (response.statusCode() == 200) return;
            } catch (IOException ignored) {
                // 进程仍在启动，继续短轮询。
            }
            Thread.sleep(100);
        }
        throw new IllegalStateException("Python Core 启动超时：" + sanitizedLogTail());
    }

    private String sanitizedLogTail() {
        try {
            String content = Files.readString(log)
                    .replace(testPassword, "<redacted>")
                    .replace(jwtSecret, "<redacted>");
            return content.substring(Math.max(0, content.length() - 4_000));
        } catch (IOException exception) {
            return "无法读取已脱敏日志";
        }
    }

    @Override
    public void close() throws Exception {
        if (process.isAlive()) {
            process.destroy();
            if (!process.waitFor(10, TimeUnit.SECONDS)) {
                process.destroyForcibly();
                process.waitFor(5, TimeUnit.SECONDS);
            }
        }
        if (Files.exists(runtimeDirectory)) {
            try (var paths = Files.walk(runtimeDirectory)) {
                paths.sorted(Comparator.reverseOrder()).forEach(path -> {
                    try {
                        Files.deleteIfExists(path);
                    } catch (IOException exception) {
                        throw new IllegalStateException("清理 Python 差分临时目录失败", exception);
                    }
                });
            }
        }
    }

    private static String databaseUrl(PostgreSQLContainer database) {
        return "postgresql://"
                + database.getUsername()
                + ":"
                + database.getPassword()
                + "@127.0.0.1:"
                + database.getMappedPort(5432)
                + "/"
                + database.getDatabaseName();
    }

    private static String redisUrl(GenericContainer<?> redis) {
        return "redis://127.0.0.1:" + redis.getMappedPort(6379) + "/0";
    }

    private static int availablePort() throws IOException {
        try (ServerSocket socket = new ServerSocket(0)) {
            return socket.getLocalPort();
        }
    }

    private static Path repositoryRoot() {
        Path current = Path.of(System.getProperty("user.dir")).toAbsolutePath().normalize();
        if (Files.isRegularFile(current.resolve("contracts/core/route-inventory.json"))) {
            return current;
        }
        Path root = current.resolve("../..").normalize();
        if (!Files.isRegularFile(root.resolve("contracts/core/route-inventory.json"))) {
            throw new IllegalStateException("无法定位仓库根目录");
        }
        return root;
    }
}
