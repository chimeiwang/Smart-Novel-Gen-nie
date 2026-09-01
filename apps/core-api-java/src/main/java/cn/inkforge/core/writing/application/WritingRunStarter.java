package cn.inkforge.core.writing.application;

import cn.inkforge.contracts.api.WritingRunStartResponse;

/** 公共写作启动在 V1/V2 之间做持久身份路由的端口。 */
public interface WritingRunStarter {

    WritingRunStartResponse start(String userId, ParsedWritingRunStartRequest request);
}
