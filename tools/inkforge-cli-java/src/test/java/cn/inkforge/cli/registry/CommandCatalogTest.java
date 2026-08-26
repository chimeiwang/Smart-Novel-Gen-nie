package cn.inkforge.cli.registry;

import static org.assertj.core.api.Assertions.assertThat;

import java.io.InputStream;
import java.util.Set;
import org.junit.jupiter.api.Test;
import tools.jackson.databind.json.JsonMapper;

class CommandCatalogTest {

    @Test
    void Java命令目录必须逐项匹配冻结的125个Python命令() throws Exception {
        try (InputStream source = getClass()
                .getResourceAsStream("/cli-contracts/command-registry.json")) {
            assertThat(source).isNotNull();
            CommandCatalog catalog = CommandCatalog.load(
                    source, JsonMapper.builder().build());

            assertThat(catalog.specs()).hasSize(125);
            assertThat(catalog.specs().keySet()).hasSize(125);
            assertThat(catalog.require("auth.login").inputMode())
                    .isEqualTo(CommandSpec.InputMode.ARGV_TTY);
            assertThat(catalog.require("long.task.watch").outputMode())
                    .isEqualTo(CommandSpec.OutputMode.JSONL);
            assertThat(catalog.require("long.chapter.get").fileOutput().kind())
                    .isEqualTo(CommandSpec.FileOutputKind.PRIMARY_TEXT);
            assertThat(catalog.require("long.video.export.download").requiresIdentity())
                    .isTrue();
            assertThat(catalog.specs().values())
                    .filteredOn(CommandSpec::requiresClientRequestId)
                    .allMatch(CommandSpec::mutation);
            assertThat(catalog.specs().keySet()).doesNotContainAnyElementsOf(Set.of(
                    "long.video.scene.create",
                    "long.foreshadowing.create",
                    "long.style.create"));
        }
    }
}
