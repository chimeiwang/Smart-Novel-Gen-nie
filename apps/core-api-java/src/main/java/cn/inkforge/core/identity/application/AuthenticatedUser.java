package cn.inkforge.core.identity.application;

/** 已完成会话校验的最小用户身份，避免向其他领域泄露密码哈希和认证内部模型。 */
public record AuthenticatedUser(String id, String username) {}
