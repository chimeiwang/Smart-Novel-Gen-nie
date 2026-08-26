package cn.inkforge.core.identity.application;

import cn.inkforge.core.identity.domain.AuthUser;
import cn.inkforge.core.identity.domain.DuplicateUsernameException;
import cn.inkforge.core.identity.domain.InvalidSessionTokenException;
import cn.inkforge.core.identity.domain.PasswordCodec;
import cn.inkforge.core.identity.domain.SessionTokens;
import cn.inkforge.core.platform.http.ApiException;
import java.util.Locale;
import java.util.Objects;
import java.util.regex.Pattern;

/** 保持现有用户名、bcryptjs、会话与错误语义的认证用例层。 */
public final class AuthService implements CurrentUserAccess {

    private static final Pattern USERNAME = Pattern.compile("^[a-z0-9_-]{3,32}$");
    private static final String DUMMY_PASSWORD_HASH =
            "$2b$12$C6UzMDM.H6dfI/f/IKcEe.5mGuDVYXrHD1Lh5MJ5CnCGg9iMi2D0S";

    private final AuthRepository repository;
    private final AuthRateLimiter rateLimiter;
    private final PasswordCodec passwords;
    private final SessionTokens sessions;
    private final boolean cookieSecure;

    public AuthService(
            AuthRepository repository,
            AuthRateLimiter rateLimiter,
            PasswordCodec passwords,
            SessionTokens sessions,
            boolean cookieSecure) {
        this.repository = Objects.requireNonNull(repository);
        this.rateLimiter = Objects.requireNonNull(rateLimiter);
        this.passwords = Objects.requireNonNull(passwords);
        this.sessions = Objects.requireNonNull(sessions);
        this.cookieSecure = cookieSecure;
    }

    public AuthUser register(
            String username,
            String password,
            String confirmPassword,
            String clientIdentity) {
        String normalized = normalizeUsername(username);
        rateLimiter.check(AuthAction.REGISTER, clientIdentity, normalized);
        if (!USERNAME.matcher(normalized).matches()) {
            throw new ApiException(
                    400,
                    "INVALID_USERNAME",
                    "用户名只能包含 3-32 位小写字母、数字、下划线或短横线");
        }
        if (password.length() < 6) {
            throw new ApiException(400, "PASSWORD_TOO_SHORT", "密码至少 6 位");
        }
        if (!password.equals(confirmPassword)) {
            throw new ApiException(400, "PASSWORD_MISMATCH", "两次输入的密码不一致");
        }
        String passwordHash = passwords.hash(password);
        try {
            return repository.register(normalized, passwordHash);
        } catch (DuplicateUsernameException exception) {
            throw new ApiException(409, "USERNAME_EXISTS", "用户名已存在");
        }
    }

    public AuthUser login(String username, String password, String clientIdentity) {
        String normalized = normalizeUsername(username);
        rateLimiter.check(AuthAction.LOGIN, clientIdentity, normalized);
        AuthUser user = normalized.isEmpty() ? null : repository.findByUsername(normalized);
        String passwordHash = user == null ? DUMMY_PASSWORD_HASH : user.passwordHash();
        boolean valid = passwords.matches(password, passwordHash);
        if (user == null || password.isEmpty() || !valid) {
            throw new ApiException(401, "INVALID_CREDENTIALS", "用户名或密码错误");
        }
        return user;
    }

    public AuthUser currentUser(String token) {
        if (token == null) {
            throw unauthenticated();
        }
        final String userId;
        try {
            userId = sessions.verify(token);
        } catch (InvalidSessionTokenException exception) {
            throw unauthenticated();
        }
        AuthUser user = repository.findById(userId);
        if (user == null) {
            throw unauthenticated();
        }
        return user;
    }

    @Override
    public AuthenticatedUser require(String token) {
        AuthUser user = currentUser(token);
        return new AuthenticatedUser(user.id(), user.username());
    }

    public String createSessionToken(String userId) {
        return sessions.create(userId);
    }

    public boolean cookieSecure() {
        return cookieSecure;
    }

    static String normalizeUsername(String username) {
        return username.strip().toLowerCase(Locale.ROOT);
    }

    private static ApiException unauthenticated() {
        return new ApiException(401, "UNAUTHENTICATED", "请先登录");
    }
}
