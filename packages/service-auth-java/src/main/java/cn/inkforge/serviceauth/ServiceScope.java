package cn.inkforge.serviceauth;

import java.util.Arrays;
import com.fasterxml.jackson.annotation.JsonCreator;
import com.fasterxml.jackson.annotation.JsonValue;

/** Core 与 Agent 共享的服务权限；字符串值必须与 Python 契约一致。 */
public enum ServiceScope {
    AGENT_RUN("agent:run"),
    AGENT_CANCEL("agent:cancel"),
    AGENT_DEBUG_READ("agent:debug:read"),
    CALLBACK_EVENT("callback:event"),
    CALLBACK_CHECKPOINT("callback:checkpoint"),
    CALLBACK_COMPLETE("callback:complete"),
    CALLBACK_FAIL("callback:fail"),
    TOOL_READ("tool:read"),
    TOOL_WRITE("tool:write"),
    RAG_INDEX_WRITE("rag:index:write"),
    PORTRAIT_WRITE("portrait:write"),
    QUALITY_WRITE("quality:write"),
    VIDEO_WRITE("video:write"),
    VIDEO_RENDER("video:render"),
    BILLING_AUTHORIZE("billing:authorize"),
    BILLING_USAGE_WRITE("billing:usage:write");

    private final String value;

    ServiceScope(String value) {
        this.value = value;
    }

    @JsonValue
    public String value() {
        return value;
    }

    @JsonCreator
    public static ServiceScope fromValue(String value) {
        return Arrays.stream(values())
                .filter(scope -> scope.value.equals(value))
                .findFirst()
                .orElseThrow(() -> new IllegalArgumentException("未知服务权限：" + value));
    }
}
