package cn.inkforge.core.shortmedium.domain;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatIllegalArgumentException;

import org.junit.jupiter.api.Test;

class ShortMediumVersionPayloadTest {

    @Test
    void 完整长正文逐字保存且正文版本必须冻结来源大纲() {
        String content = "正文".repeat(40_000) + "八万字尾部标记";
        ShortMediumVersionPayload payload = new ShortMediumVersionPayload(
                "chapter_draft",
                "manuscript",
                1,
                null,
                "request-12345678",
                "manual",
                content,
                ShortMediumText.sha256(content),
                null,
                null,
                "outline-version-1",
                null,
                null,
                null,
                null,
                false,
                null,
                null,
                null);

        assertThat(payload.content()).isEqualTo(content).endsWith("八万字尾部标记");
        assertThatIllegalArgumentException().isThrownBy(() -> new ShortMediumVersionPayload(
                "chapter_draft",
                "manuscript",
                1,
                null,
                "request-12345678",
                "manual",
                "正文",
                ShortMediumText.sha256("正文"),
                null,
                null,
                null,
                null,
                null,
                null,
                null,
                false,
                null,
                null,
                null));
    }

    @Test
    void 内容哈希与来源身份必须严格匹配() {
        assertThatIllegalArgumentException().isThrownBy(() -> new ShortMediumVersionPayload(
                "outline_draft",
                "outline",
                1,
                null,
                "request-12345678",
                "manual",
                "完整大纲",
                "0".repeat(64),
                null,
                null,
                null,
                null,
                null,
                null,
                null,
                false,
                null,
                null,
                null));
        assertThatIllegalArgumentException().isThrownBy(() -> new ShortMediumVersionPayload(
                "outline_draft",
                "outline",
                2,
                "version-1",
                "request-12345678",
                "restore",
                "完整大纲",
                ShortMediumText.sha256("完整大纲"),
                null,
                null,
                null,
                null,
                null,
                null,
                null,
                false,
                null,
                null,
                null));
    }

    @Test
    void 字数与请求标识长度必须沿用Python的Unicode语义() {
        assertThat(ShortMediumText.count("甲\u0085乙\u00a0丙\ufeff丁")).isEqualTo(4);
        String requestId = "😀".repeat(16);
        ShortMediumVersionPayload payload = new ShortMediumVersionPayload(
                "outline_draft",
                "outline",
                1,
                null,
                requestId,
                "manual",
                "大纲",
                ShortMediumText.sha256("大纲"),
                null,
                null,
                null,
                null,
                null,
                null,
                null,
                false,
                null,
                null,
                null);
        assertThat(payload.clientRequestId()).isEqualTo(requestId);
    }
}
