package cn.inkforge.core.platform.db;

import static org.assertj.core.api.Assertions.assertThat;

import java.io.InputStream;
import java.sql.DriverManager;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
import tools.jackson.databind.ObjectMapper;

class DevSchemaReadOnlyAcceptanceTest {

    @Test
    @EnabledIfEnvironmentVariable(named = "INKFORGE_DEV_DATABASE_URL", matches = ".+")
    void Java结构守卫只读验收novelwriterdev() throws Exception {
        PostgresConnectionSettings settings =
                PostgresConnectionSettings.parse(System.getenv("INKFORGE_DEV_DATABASE_URL"));
        assertThat(settings.databaseName()).isEqualTo("novelwriterdev");

        try (InputStream input = getClass().getResourceAsStream("/db/schema-contract.json")) {
            if (input == null) {
                throw new IllegalStateException("缺少数据库结构契约");
            }
            SchemaContract expected = SchemaContract.load(new ObjectMapper().readTree(input));
            try (var connection = DriverManager.getConnection(
                    settings.jdbcUrl(), settings.username(), settings.password())) {
                SchemaVerificationResult result = new SchemaVerifier(expected).verify(connection, "public");

                assertThat(result.ready()).isTrue();
                assertThat(result.diffs()).isEmpty();
                assertThat(result.fingerprint()).isEqualTo(expected.fingerprint());
            }
        }
    }
}
