package cn.inkforge.cli.registry;

import static org.assertj.core.api.Assertions.assertThat;

import java.io.InputStream;
import java.util.Set;
import org.junit.jupiter.api.Test;
import tools.jackson.databind.json.JsonMapper;

class CommandCatalogTest {

    @Test
    void Java命令目录必须包含全部152项并与处理器注册双向一致() throws Exception {
        try (InputStream source = getClass()
                .getResourceAsStream("/cli-contracts/command-registry.json")) {
            assertThat(source).isNotNull();
            CommandCatalog catalog = CommandCatalog.load(
                    source, JsonMapper.builder().build());

            assertThat(catalog.specs()).hasSize(152);
            assertThat(catalog.specs().keySet()).hasSize(152);
            assertThat(catalog.require("long.session.create").inputMode())
                    .isEqualTo(CommandSpec.InputMode.JSON);
            assertThat(catalog.require("long.session.create").outputMode())
                    .isEqualTo(CommandSpec.OutputMode.JSON);
            assertThat(catalog.require("long.session.create").mutation()).isTrue();
            assertThat(catalog.require("long.session.create").requiresIdentity()).isTrue();
            assertThat(catalog.require("long.session.create").requiresClientRequestId()).isFalse();
            assertThat(catalog.require("auth.login").inputMode())
                    .isEqualTo(CommandSpec.InputMode.ARGV_TTY);
            assertThat(catalog.require("long.task.watch").outputMode())
                    .isEqualTo(CommandSpec.OutputMode.JSONL);
            assertThat(catalog.require("long.chapter.get").fileOutput().kind())
                    .isEqualTo(CommandSpec.FileOutputKind.PRIMARY_TEXT);
            assertThat(catalog.require("long.video.episode.delivery.download").requiresIdentity())
                    .isTrue();
            assertThat(catalog.specs().values())
                    .filteredOn(CommandSpec::requiresClientRequestId)
                    .allMatch(CommandSpec::mutation);
            assertThat(catalog.specs().keySet()).doesNotContainAnyElementsOf(Set.of(
                    "long.video.scene.create",
                    "long.video.adaptation.create",
                    "long.video.plan.start",
                    "long.video.prompt.start",
                    "long.foreshadowing.create",
                    "long.style.create"));
        }
    }
}
