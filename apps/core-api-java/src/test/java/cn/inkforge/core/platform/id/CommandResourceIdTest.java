package cn.inkforge.core.platform.id;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;

class CommandResourceIdTest {

    @Test
    void 必须与Python按命名空间稳定隔离() {
        String value = CommandResourceId.derive("lore", "用户", "novel-1", "request-1");

        assertThat(value).isEqualTo(
                "ifc_da38c21cf2ef35831f611cc2e0ec7e98718e66b76dafa7a7b77b0f7740abd7c3");
        assertThat(CommandResourceId.derive("outline", "用户", "novel-1", "request-1"))
                .isNotEqualTo(value);
    }
}
