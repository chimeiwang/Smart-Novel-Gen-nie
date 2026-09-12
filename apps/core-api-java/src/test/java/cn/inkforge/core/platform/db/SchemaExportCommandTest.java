package cn.inkforge.core.platform.db;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.io.ByteArrayOutputStream;
import java.io.PrintStream;
import java.nio.file.Files;
import java.nio.file.Path;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import tools.jackson.databind.ObjectMapper;

class SchemaExportCommandTest {
    @Test
    void 导出默认拒绝覆盖已有证据(@TempDir Path directory) throws Exception {
        Path output = directory.resolve("contract.json");
        Files.writeString(output, "原始证据");
        var document = new ObjectMapper().createObjectNode().put("fingerprint", "abc");
        assertThatThrownBy(() -> SchemaExportCommand.writeDocument(output, document, false))
                .isInstanceOf(java.nio.file.FileAlreadyExistsException.class);
        assertThat(Files.readString(output)).isEqualTo("原始证据");
        SchemaExportCommand.writeDocument(output, document, true);
        assertThat(new ObjectMapper().readTree(Files.readString(output)).path("fingerprint").asString())
                .isEqualTo("abc");
    }

    @Test
    void 帮助不连接数据库() {
        var output = new ByteArrayOutputStream();
        var errors = new ByteArrayOutputStream();
        assertThat(SchemaExportCommand.run(new String[]{"--help"}, new PrintStream(output), new PrintStream(errors))).isZero();
        assertThat(output.toString()).contains("--database-url-stdin");
        assertThat(errors.toString()).isEmpty();
    }
}
