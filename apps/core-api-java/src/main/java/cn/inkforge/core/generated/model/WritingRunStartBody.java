package cn.inkforge.core.generated.model;

import com.fasterxml.jackson.annotation.JsonCreator;
import com.fasterxml.jackson.annotation.JsonValue;
import java.util.Objects;
import tools.jackson.databind.JsonNode;

/**
 * 冻结 OpenAPI 中写作启动匿名 {@code anyOf} 的无损请求体。
 *
 * <p>OpenAPI Generator 无法正确生成该联合体，因此生成契约模块保留原始 JSON 树；writing
 * 模块随后严格判别旧长篇、中短篇和长篇新管线三个互斥分支。该类型属于 HTTP 契约边界，不能放入
 * writing 模块，否则生成接口会反向依赖业务实现模块。
 */
public final class WritingRunStartBody {

    private final JsonNode value;

    @JsonCreator(mode = JsonCreator.Mode.DELEGATING)
    public WritingRunStartBody(JsonNode value) {
        this.value = Objects.requireNonNull(value, "写作启动请求体不能为空");
    }

    @JsonValue
    public JsonNode value() {
        return value;
    }
}
