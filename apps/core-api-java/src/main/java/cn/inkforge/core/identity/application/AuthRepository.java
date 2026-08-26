package cn.inkforge.core.identity.application;

import cn.inkforge.core.identity.domain.AuthUser;

public interface AuthRepository {

    AuthUser findByUsername(String username);

    AuthUser findById(String userId);

    AuthUser register(String username, String passwordHash);
}
