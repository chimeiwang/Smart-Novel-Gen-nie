package cn.inkforge.core.writing.infrastructure;

import cn.inkforge.core.platform.http.ApiException;

/** V1 fresh start 的具名运维门禁；既有幂等请求必须在调用本门禁前完成解析。 */
final class V1FreshAgentStartGate {

    static final String ENVIRONMENT_VARIABLE = "V1_FRESH_AGENT_STARTS_ENABLED";

    private V1FreshAgentStartGate() {}

    static ApiException draining() {
        return new ApiException(
                503,
                "AGENT_FRESH_STARTS_DRAINING",
                "Agent 新建入口正在受控 drain，请稍后重试");
    }
}
