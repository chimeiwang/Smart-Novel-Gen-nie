package cn.inkforge.core.identity.application;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import cn.inkforge.core.identity.domain.AuthUser;
import cn.inkforge.core.identity.domain.DuplicateUsernameException;
import cn.inkforge.core.identity.domain.InvalidSessionTokenException;
import cn.inkforge.core.identity.domain.PasswordCodec;
import cn.inkforge.core.identity.domain.SessionTokens;
import cn.inkforge.core.platform.http.ApiException;
import java.util.HashMap;
import java.util.Map;
import org.junit.jupiter.api.Test;

class AuthServiceTest {

    @Test
    void 注册必须先限流再规范用户名并保持UTF16密码长度() {
        FakeRepository repository = new FakeRepository();
        FakeRateLimiter limiter = new FakeRateLimiter();
        FakePasswords passwords = new FakePasswords();
        AuthService service = service(repository, limiter, passwords);

        AuthUser user = service.register(
                "  Alice_1  ", "😀😀😀", "😀😀😀", "198.51.100.10");

        assertThat(user.username()).isEqualTo("alice_1");
        assertThat(repository.byName).containsKey("alice_1");
        assertThat(passwords.hashed).isEqualTo("😀😀😀");
        assertThat(limiter.last)
                .isEqualTo(new RateLimitAttempt(AuthAction.REGISTER, "198.51.100.10", "alice_1"));

        assertThatThrownBy(() -> service.register(
                        "emoji_no", "😀😀a", "😀😀a", "198.51.100.10"))
                .isInstanceOfSatisfying(ApiException.class, error ->
                        assertThat(error.code()).isEqualTo("PASSWORD_TOO_SHORT"));
    }

    @Test
    void 注册规则确认密码与并发重名必须返回冻结错误() {
        FakeRepository repository = new FakeRepository();
        AuthService service = service(repository, new FakeRateLimiter(), new FakePasswords());

        assertCode(() -> service.register("a.b", "123456", "123456", "ip"), "INVALID_USERNAME");
        assertCode(() -> service.register("alice", "123456 ", "123456", "ip"), "PASSWORD_MISMATCH");
        repository.duplicate = true;
        assertCode(() -> service.register("alice", "123456", "123456", "ip"), "USERNAME_EXISTS");
    }

    @Test
    void 登录必须对缺失用户执行固定假哈希并统一凭据错误() {
        FakeRepository repository = new FakeRepository();
        FakePasswords passwords = new FakePasswords();
        passwords.matches = false;
        AuthService service = service(repository, new FakeRateLimiter(), passwords);

        assertCode(() -> service.login(" Missing ", "123456", "ip"), "INVALID_CREDENTIALS");
        assertThat(passwords.checkedHash).startsWith("$2b$12$");
        assertThat(repository.lastLookupName).isEqualTo("missing");
    }

    @Test
    void 当前用户必须验令牌后重新查库并拒绝已删除账号() {
        FakeRepository repository = new FakeRepository();
        AuthUser user = new AuthUser("user-1", "alice", "hash", 12);
        repository.byId.put(user.id(), user);
        AuthService service = service(repository, new FakeRateLimiter(), new FakePasswords());

        assertThat(service.currentUser("valid-token")).isEqualTo(user);
        assertThat(service.require("valid-token"))
                .isEqualTo(new AuthenticatedUser("user-1", "alice"));
        repository.byId.clear();
        assertCode(() -> service.currentUser("valid-token"), "UNAUTHENTICATED");
        assertCode(() -> service.currentUser(null), "UNAUTHENTICATED");
    }

    private AuthService service(
            FakeRepository repository, FakeRateLimiter limiter, FakePasswords passwords) {
        return new AuthService(
                repository,
                limiter,
                passwords,
                new SessionTokens() {
                    @Override
                    public String create(String userId) {
                        return "token-for-" + userId;
                    }

                    @Override
                    public String verify(String token) {
                        if (!"valid-token".equals(token)) {
                            throw new InvalidSessionTokenException();
                        }
                        return "user-1";
                    }
                },
                false);
    }

    private void assertCode(Runnable action, String code) {
        assertThatThrownBy(action::run)
                .isInstanceOfSatisfying(ApiException.class, error ->
                        assertThat(error.code()).isEqualTo(code));
    }

    private static final class FakeRepository implements AuthRepository {
        private final Map<String, AuthUser> byName = new HashMap<>();
        private final Map<String, AuthUser> byId = new HashMap<>();
        private boolean duplicate;
        private String lastLookupName;

        @Override
        public AuthUser findByUsername(String username) {
            lastLookupName = username;
            return byName.get(username);
        }

        @Override
        public AuthUser findById(String userId) {
            return byId.get(userId);
        }

        @Override
        public AuthUser register(String username, String passwordHash) {
            if (duplicate) {
                throw new DuplicateUsernameException();
            }
            AuthUser user = new AuthUser("user-new", username, passwordHash, 1_000_000_000L);
            byName.put(username, user);
            byId.put(user.id(), user);
            return user;
        }
    }

    private static final class FakeRateLimiter implements AuthRateLimiter {
        private RateLimitAttempt last;

        @Override
        public void check(AuthAction action, String clientIdentity, String username) {
            last = new RateLimitAttempt(action, clientIdentity, username);
        }
    }

    private static final class FakePasswords implements PasswordCodec {
        private String hashed;
        private String checkedHash;
        private boolean matches = true;

        @Override
        public String hash(String password) {
            hashed = password;
            return "hash:" + password;
        }

        @Override
        public boolean matches(String password, String passwordHash) {
            checkedHash = passwordHash;
            return matches;
        }
    }
}
