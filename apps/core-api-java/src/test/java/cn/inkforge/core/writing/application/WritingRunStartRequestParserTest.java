package cn.inkforge.core.writing.application;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import cn.inkforge.contracts.api.StartWritingRunRequest;
import cn.inkforge.core.platform.http.ApiException;
import cn.inkforge.core.generated.model.WritingRunStartBody;
import jakarta.validation.Validation;
import org.openapitools.jackson.nullable.JsonNullableJackson3Module;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import tools.jackson.databind.ObjectMapper;
import tools.jackson.databind.json.JsonMapper;

class WritingRunStartRequestParserTest {

    private ObjectMapper json;
    private WritingRunStartRequestParser parser;

    @BeforeEach
    void setUp() {
        json = JsonMapper.builder()
                .addModule(new JsonNullableJackson3Module())
                .build();
        parser = new WritingRunStartRequestParser(
                json, Validation.buildDefaultValidatorFactory().getValidator());
    }

    @Test
    void 解析旧长篇请求并补齐冻结默认值() throws Exception {
        ParsedWritingRunStartRequest parsed = parse("""
                {
                  "clientRequestId": "request-00000001",
                  "novelId": "novel-1",
                  "chapterId": "chapter-1",
                  "userMessage": "开始写作"
                }
                """);

        assertThat(parsed).isInstanceOf(ParsedWritingRunStartRequest.Legacy.class);
        StartWritingRunRequest request =
                ((ParsedWritingRunStartRequest.Legacy) parsed).request();
        assertThat(request.getTargetWordCount()).isEqualTo(4000);
        assertThat(request.getSelectedAgents())
                .extracting(StartWritingRunRequest.SelectedAgentsEnum::getValue)
                .containsExactly("设定", "剧情", "写作", "校验", "编辑");
    }

    @Test
    void 旧长篇请求拒绝其他分支字段和类型强制转换() {
        assertValidation("""
                {
                  "clientRequestId": "request-00000001",
                  "novelId": "novel-1",
                  "chapterId": "chapter-1",
                  "userMessage": "开始写作",
                  "operation": "write_chapter"
                }
                """);
        assertValidation("""
                {
                  "clientRequestId": 1234567890123456,
                  "novelId": "novel-1",
                  "chapterId": "chapter-1",
                  "userMessage": "开始写作"
                }
                """);
    }

    @Test
    void 解析中短篇请求并保留分支身份() throws Exception {
        ParsedWritingRunStartRequest parsed = parse("""
                {
                  "clientRequestId": "request-00000001",
                  "workflow": "short_medium",
                  "novelId": "novel-1",
                  "operation": "generate_manuscript",
                  "documentType": "manuscript",
                  "chapterId": "chapter-1",
                  "sourceOutlineVersionId": "outline-version-1",
                  "userInstruction": "生成完整正文"
                }
                """);

        assertThat(parsed).isInstanceOf(ParsedWritingRunStartRequest.ShortMedium.class);
        var request = ((ParsedWritingRunStartRequest.ShortMedium) parsed).request();
        assertThat(request.getWorkflow()).isEqualTo("short_medium");
        assertThat(request.getSourceOutlineVersionId().get()).isEqualTo("outline-version-1");
    }

    @Test
    void 中短篇请求执行与文档身份必须匹配() {
        assertValidation("""
                {
                  "clientRequestId": "request-00000001",
                  "workflow": "short_medium",
                  "novelId": "novel-1",
                  "operation": "generate_outline",
                  "documentType": "manuscript",
                  "chapterId": "chapter-1"
                }
                """);
        assertValidation("""
                {
                  "clientRequestId": "request-00000001",
                  "workflow": "short_medium",
                  "novelId": "novel-1",
                  "operation": "replace_selection",
                  "documentType": "manuscript",
                  "chapterId": "chapter-1",
                  "baseVersionId": "version-1",
                  "userInstruction": "改写",
                  "selectionStart": 4,
                  "selectionEnd": 4,
                  "selectedTextHash": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
                }
                """);
    }

    @Test
    void 解析长篇新管线请求() throws Exception {
        ParsedWritingRunStartRequest parsed = parse("""
                {
                  "clientRequestId": "request-00000001",
                  "workflow": "long_serial",
                  "novelId": "novel-1",
                  "chapterId": "chapter-1",
                  "operation": "write_chapter",
                  "target": {"type": "chapter", "id": "chapter-1"},
                  "scope": {"kind": "chapter", "chapterId": "chapter-1"},
                  "userInstruction": "  写出不可逆的选择  "
                }
                """);

        assertThat(parsed).isInstanceOf(ParsedWritingRunStartRequest.LongSerial.class);
        var request = ((ParsedWritingRunStartRequest.LongSerial) parsed).request();
        assertThat(request.getWorkflow()).isEqualTo("long_serial");
        assertThat(request.getTargetWordCount()).isEqualTo(4000);
        assertThat(request.getUserInstruction()).isEqualTo("  写出不可逆的选择  ");
    }

    @Test
    void 长篇选区操作校验范围资源类型和嵌套多余字段() {
        assertValidation(longSelection("rewrite_chapter_selection", "outline_content", false));
        assertValidation(longSelection("rewrite_chapter_selection", "chapter_content", true));
        assertValidation("""
                {
                  "clientRequestId": "request-00000001",
                  "workflow": "long_serial",
                  "novelId": "novel-1",
                  "chapterId": "chapter-1",
                  "operation": "write_chapter",
                  "target": {"type": "chapter", "id": "chapter-1"},
                  "scope": {"kind": "chapter_range", "chapterStartOrder": 8, "chapterEndOrder": 2},
                  "userInstruction": "继续写作"
                }
                """);
    }

    @Test
    void 普通长篇操作拒绝选区且用户要求不能全是空白() {
        assertValidation(longSelection("write_chapter", "chapter_content", false));
        assertValidation("""
                {
                  "clientRequestId": "request-00000001",
                  "workflow": "long_serial",
                  "novelId": "novel-1",
                  "chapterId": "chapter-1",
                  "operation": "write_chapter",
                  "target": {"type": "chapter", "id": "chapter-1"},
                  "scope": {"kind": "chapter", "chapterId": "chapter-1"},
                  "userInstruction": "   "
                }
                """);
    }

    @Test
    void 请求必须命中且只命中一个冻结分支() {
        assertValidation("[]");
        assertValidation("""
                {
                  "clientRequestId": "request-00000001",
                  "workflow": "future_workflow",
                  "novelId": "novel-1"
                }
                """);
    }

    private ParsedWritingRunStartRequest parse(String value) throws Exception {
        return parser.parse(new WritingRunStartBody(json.readTree(value)));
    }

    private void assertValidation(String value) {
        assertThatThrownBy(() -> parse(value))
                .isInstanceOfSatisfying(ApiException.class, exception -> {
                    assertThat(exception.statusCode()).isEqualTo(422);
                    assertThat(exception.code()).isEqualTo("VALIDATION_ERROR");
                });
    }

    private static String longSelection(
            String operation, String resourceType, boolean nestedExtraField) {
        return """
                {
                  "clientRequestId": "request-00000001",
                  "workflow": "long_serial",
                  "novelId": "novel-1",
                  "chapterId": "chapter-1",
                  "operation": "%s",
                  "target": {"type": "chapter", "id": "chapter-1"},
                  "scope": {"kind": "chapter", "chapterId": "chapter-1"},
                  "selectionTarget": {
                    "resourceType": "%s",
                    "resourceId": "chapter-1",
                    "baseUpdatedAt": "2026-08-05T10:00:00Z",
                    "baseContentHash": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                    "selectionStart": 0,
                    "selectionEnd": 3,
                    "selectedTextHash": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"%s
                  },
                  "userInstruction": "改写选区"
                }
                """.formatted(
                operation,
                resourceType,
                nestedExtraField ? ",\n                    \"forgedContent\": \"不能信任\"" : "");
    }
}
