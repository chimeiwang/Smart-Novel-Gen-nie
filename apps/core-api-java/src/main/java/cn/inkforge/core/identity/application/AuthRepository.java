package cn.inkforge.core.identity.application;

import cn.inkforge.core.identity.domain.AuthUser;

/** 用户名密码认证所需的用户查询和注册持久化端口。 */
public interface AuthRepository {

    AuthUser findByUsername(String username);

    AuthUser findById(String userId);

    AuthUser register(String username, String passwordHash);
}
