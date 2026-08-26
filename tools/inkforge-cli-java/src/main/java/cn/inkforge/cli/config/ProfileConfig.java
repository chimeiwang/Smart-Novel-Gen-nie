package cn.inkforge.cli.config;

import cn.inkforge.cli.transport.CoreOrigin;

/** 普通配置只包含非敏感身份提示，不包含会话。 */
public record ProfileConfig(String origin, String username) {

    public ProfileConfig {
        origin = CoreOrigin.validate(origin);
        if (username == null || username.isBlank()) {
            throw new IllegalArgumentException("用户名不能为空");
        }
    }
}
