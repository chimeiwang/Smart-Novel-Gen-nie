package cn.inkforge.core.platform.db;

import static org.assertj.core.api.Assertions.assertThat;

import java.sql.DriverManager;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;

class DevSchemaReadOnlyAcceptanceTest {

    @Test
    @EnabledIfEnvironmentVariable(named = "INKFORGE_DEV_DATABASE_URL", matches = ".+")
    void Java结构守卫只读验收novelwriterdev() throws Exception {
        PostgresConnectionSettings settings =
                PostgresConnectionSettings.parse(System.getenv("INKFORGE_DEV_DATABASE_URL"));
        assertThat(settings.databaseName()).isEqualTo("novelwriterdev");

        var expected = SchemaContracts.loadBundled();
        try (var connection = DriverManager.getConnection(
                settings.jdbcUrl(), settings.username(), settings.password())) {
            SchemaVerificationResult result =
                    new SchemaVerifier(expected, SchemaProfile.FULL).verify(connection, "public");

            assertThat(result.ready()).isTrue();
            assertThat(result.diffs()).isEmpty();
            assertThat(expected)
                    .extracting(SchemaContract::fingerprint)
                    .contains(result.fingerprint());
        }
    }
}
