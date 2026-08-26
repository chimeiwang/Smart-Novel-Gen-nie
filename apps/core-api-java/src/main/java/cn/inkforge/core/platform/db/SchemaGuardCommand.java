package cn.inkforge.core.platform.db;

import java.io.PrintStream;
import java.sql.DriverManager;
import java.util.Map;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.node.ObjectNode;

/** 镜像内只读结构守卫入口；成功输出单行实时指纹，任何失败均不打印连接凭据。 */
public final class SchemaGuardCommand {

    private SchemaGuardCommand() {}

    public static void main(String[] arguments) {
        int status = run(arguments, System.getenv(), System.out, System.err);
        if (status != 0) {
            System.exit(status);
        }
    }

    static int run(Map<String, String> environment, PrintStream stdout, PrintStream stderr) {
        return run(new String[0], environment, stdout, stderr);
    }

    static int run(
            String[] arguments,
            Map<String, String> environment,
            PrintStream stdout,
            PrintStream stderr) {
        try {
            boolean compatibilityFingerprint = compatibilityFingerprintRequested(arguments);
            PostgresConnectionSettings settings =
                    PostgresConnectionSettings.parse(environment.get("DATABASE_URL"));
            SchemaProfile profile = videoPreviewEnabled(environment.get("VIDEO_PREVIEW_ENABLED"))
                    ? SchemaProfile.FULL
                    : SchemaProfile.WITHOUT_VIDEO_PREVIEW;
            try (var connection = DriverManager.getConnection(
                    settings.jdbcUrl(), settings.username(), settings.password())) {
                SchemaVerificationResult result =
                        new SchemaVerifier(SchemaContracts.loadBundled(), profile)
                                .verify(connection, "public");
                if (result.ready()) {
                    if (compatibilityFingerprint) {
                        SchemaContract actual = SchemaContractProjector.project(
                                new PostgresSchemaInspector().inspect(connection, "public"), profile);
                        stdout.println(compatibilityFingerprintV1(actual));
                    } else {
                        stdout.println(result.fingerprint());
                    }
                    return 0;
                }
                stderr.println("数据库结构与冻结契约不一致");
                result.diffs().forEach(diff -> stderr.println(diff.message()));
                return 1;
            }
        } catch (Exception exception) {
            stderr.println("数据库结构检查无法完成（"
                    + exception.getClass().getSimpleName()
                    + "）");
            return 2;
        }
    }

    static String compatibilityFingerprintV1(SchemaContract contract) {
        ObjectNode document = contract.document().asObject();
        document.put("contractVersion", 1);
        for (JsonNode table : document.path("tables")) {
            if (table.isObject()) {
                table.asObject().remove("checkConstraints");
            }
        }
        return SchemaContract.canonicalFingerprint(document);
    }

    private static boolean compatibilityFingerprintRequested(String[] arguments) {
        if (arguments.length == 0) {
            return false;
        }
        if (arguments.length == 1
                && arguments[0].equals("--compatibility-fingerprint-v1")) {
            return true;
        }
        throw new IllegalArgumentException("结构守卫参数无效");
    }

    private static boolean videoPreviewEnabled(String value) {
        if (value == null || value.isBlank()) {
            return false;
        }
        return switch (value.strip().toLowerCase()) {
            case "true", "1" -> true;
            case "false", "0" -> false;
            default -> throw new IllegalArgumentException("VIDEO_PREVIEW_ENABLED 必须是布尔值");
        };
    }
}
