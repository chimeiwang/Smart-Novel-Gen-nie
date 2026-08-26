package cn.inkforge.core.platform.db;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import org.junit.jupiter.api.Test;

class PostgresConnectionSettingsTest {

    @Test
    void SQLAlchemy地址必须安全转换为JDBC参数() {
        PostgresConnectionSettings settings = PostgresConnectionSettings.parse(
                "postgresql+asyncpg://ink%20forge:p%40ss@db.example:5433/novelwriterdev?sslmode=require");

        assertThat(settings.jdbcUrl())
                .isEqualTo("jdbc:postgresql://db.example:5433/novelwriterdev?sslmode=require");
        assertThat(settings.username()).isEqualTo("ink forge");
        assertThat(settings.password()).isEqualTo("p@ss");
        assertThat(settings.databaseName()).isEqualTo("novelwriterdev");
    }

    @Test
    void 缺少数据库名或凭据必须拒绝() {
        assertThatThrownBy(() -> PostgresConnectionSettings.parse("postgresql://localhost/"))
                .isInstanceOf(IllegalArgumentException.class);
    }
}
