package cn.inkforge.cli.transport;

import tools.jackson.databind.JsonNode;

/** 登录公共响应和只进入安全凭据后端的会话值。 */
public record LoginResult(JsonNode user, String token) {}
