package cn.inkforge.core.platform.db;

import java.io.PrintStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.security.MessageDigest;
import java.sql.DriverManager;
import java.util.HexFormat;
import tools.jackson.databind.ObjectMapper;
import tools.jackson.databind.node.ObjectNode;

/** 运维只读导出入口；复用 Java 结构检查器，凭据只从环境或标准输入读取。 */
public final class SchemaExportCommand {
    private SchemaExportCommand() {}

    public static void main(String[] arguments) {
        int status = run(arguments, System.out, System.err);
        if (status != 0) System.exit(status);
    }

    static int run(String[] arguments, PrintStream stdout, PrintStream stderr) {
        try {
            if (arguments.length == 1 && "--help".equals(arguments[0])) {
                stdout.println("用法：inkforge-schema-export [--database-url-stdin] --output <文件> [--overwrite]");
                return 0;
            }
            Path output = null;
            boolean fromStdin = false;
            boolean overwrite = false;
            for (int i = 0; i < arguments.length; i++) {
                switch (arguments[i]) {
                    case "--database-url-stdin" -> fromStdin = true;
                    case "--overwrite" -> overwrite = true;
                    case "--output" -> output = Path.of(arguments[++i]);
                    default -> throw new IllegalArgumentException("结构导出参数无效");
                }
            }
            if (output == null) throw new IllegalArgumentException("缺少输出文件");
            if (!overwrite && Files.exists(output)) throw new java.nio.file.FileAlreadyExistsException(output.toString());
            String databaseUrl = fromStdin
                    ? new String(System.in.readAllBytes(), StandardCharsets.UTF_8).strip()
                    : System.getenv("DATABASE_URL");
            PostgresConnectionSettings settings = PostgresConnectionSettings.parse(databaseUrl);
            try (var connection = DriverManager.getConnection(settings.jdbcUrl(), settings.username(), settings.password())) {
                SchemaContract contract = new PostgresSchemaInspector().inspect(connection, "public");
                ObjectNode document = contract.document().asObject();
                ObjectNode source = document.putObject("source");
                source.put("product", "PostgreSQL");
                source.put("serverVersion", connection.getMetaData().getDatabaseProductVersion());
                source.put("sourceId", HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256")
                        .digest(settings.jdbcUrl().getBytes(StandardCharsets.UTF_8))));
                writeDocument(output, document, overwrite);
                stdout.println("schema-contract:" + contract.fingerprint());
                return 0;
            }
        } catch (Exception exception) {
            // JDBC 错误可能携带地址或认证信息；仅输出安全错误类型。
            stderr.println("结构契约导出失败（" + exception.getClass().getSimpleName() + "）");
            return 1;
        }
    }

    static void writeDocument(Path output, ObjectNode document, boolean overwrite) throws java.io.IOException {
        String content = new ObjectMapper().writerWithDefaultPrettyPrinter().writeValueAsString(document)
                .replace("\r\n", "\n") + "\n";
        Files.writeString(output, content, StandardCharsets.UTF_8,
                StandardOpenOption.WRITE,
                overwrite ? StandardOpenOption.CREATE : StandardOpenOption.CREATE_NEW,
                StandardOpenOption.TRUNCATE_EXISTING);
    }
}
