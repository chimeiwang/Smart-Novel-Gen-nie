package cn.inkforge.core.identity.application;

/** 浏览器业务接口的统一会话入口；缺失、伪造或已失效会话统一返回 401。 */
@FunctionalInterface
public interface CurrentUserAccess {

    AuthenticatedUser require(String token);
}
